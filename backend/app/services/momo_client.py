"""A small client for the MTN MoMo Collections API ("request to pay").

Docs: https://momodeveloper.mtn.com
The flow is:
  1. POST /collection/token/             -> access token (Basic auth with the
                                            API user and API key)
  2. POST /collection/v1_0/requesttopay  -> 202; MoMo asks the payer to approve
                                            on their phone with their PIN
  3. GET  /collection/v1_0/requesttopay/<reference>
                                         -> status PENDING / SUCCESSFUL / FAILED,
                                            with a reason when it failed

Every call also sends the Collections subscription key. Uses only the
standard library. The payment service gets a client from get_client(), which
tests replace with a fake, so tests never call MoMo.
"""

import base64
import json
import logging
import threading
import time
import urllib.error
import urllib.request

from flask import current_app

log = logging.getLogger(__name__)


class MomoError(Exception):
    """MoMo could not be reached or refused the request."""


class MomoClient:
    def __init__(self, base_url, subscription_key, api_user, api_key, target_environment,
                 currency, callback_url=None, timeout=20):
        self.base_url = base_url.rstrip("/")
        self.subscription_key = subscription_key
        self.api_user = api_user
        self.api_key = api_key
        self.target_environment = target_environment
        self.currency = currency
        self.callback_url = callback_url
        self.timeout = timeout
        self._token = None
        self._token_expires = 0
        self._token_lock = threading.Lock()

    def request_to_pay(self, reference, amount, phone, external_id, message):
        """Ask the payer to approve a payment. `reference` is a new UUID we
        choose; MoMo knows the payment by it from then on."""
        headers = {
            "X-Reference-Id": reference,
            "X-Target-Environment": self.target_environment,
        }
        if self.callback_url:
            headers["X-Callback-Url"] = self.callback_url
        body = {
            "amount": str(amount),
            "currency": self.currency,
            "externalId": str(external_id),
            # MSISDN: the number with country code and no "+", e.g. 250781234567.
            "payer": {"partyIdType": "MSISDN", "partyId": phone.lstrip("+")},
            "payerMessage": message,
            "payeeNote": message,
        }
        self._call("POST", "/collection/v1_0/requesttopay", headers, body, auth=True)

    def get_status(self, reference):
        """Return MoMo's record of a request to pay: a dict with "status",
        "amount", "currency", "externalId" and, when it failed, "reason"."""
        return self._call(
            "GET",
            f"/collection/v1_0/requesttopay/{reference}",
            {"X-Target-Environment": self.target_environment},
            auth=True,
        ) or {}

    def _access_token(self):
        # Tokens last about an hour; reuse one until shortly before it expires.
        with self._token_lock:
            if self._token and time.time() < self._token_expires - 60:
                return self._token
            basic = base64.b64encode(f"{self.api_user}:{self.api_key}".encode()).decode()
            data = self._call("POST", "/collection/token/", {"Authorization": f"Basic {basic}"})
            self._token = data["access_token"]
            self._token_expires = time.time() + int(data.get("expires_in", 3600))
            return self._token

    def _call(self, method, path, headers, body=None, auth=False):
        headers = {"Ocp-Apim-Subscription-Key": self.subscription_key, **headers}
        if auth:
            headers["Authorization"] = f"Bearer {self._access_token()}"
        return http_json(self.base_url + path, method, headers, body, self.timeout)


def http_json(url, method, headers, body=None, timeout=20):
    """Send one request to MoMo and return the parsed JSON answer (or None)."""
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers = {**headers, "Content-Type": "application/json"}
    elif method == "POST":
        data = b""  # MoMo wants a Content-Length even on empty POSTs
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    path = url.split("//", 1)[-1].split("/", 1)[-1]
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read()
    except urllib.error.HTTPError as err:
        # Log MoMo's reason, but never the keys or tokens.
        log.warning("MoMo %s /%s failed: %s %s", method, path, err.code,
                    err.read()[:300].decode(errors="replace"))
        raise MomoError(f"MoMo answered {err.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        log.warning("MoMo %s /%s unreachable: %s", method, path, err)
        raise MomoError("MoMo could not be reached") from None
    return json.loads(raw) if raw else None


def create_sandbox_user(base_url, subscription_key, reference, callback_host):
    """Sandbox only: create an API user and its API key (the Sandbox User
    Provisioning API). In production these come from the MoMo partner portal."""
    headers = {"Ocp-Apim-Subscription-Key": subscription_key}
    base_url = base_url.rstrip("/")
    http_json(f"{base_url}/v1_0/apiuser", "POST", {**headers, "X-Reference-Id": reference},
              {"providerCallbackHost": callback_host})
    data = http_json(f"{base_url}/v1_0/apiuser/{reference}/apikey", "POST", headers)
    return data["apiKey"]


def get_client():
    """A MomoClient from the app settings, or None if MoMo is not set up."""
    cfg = current_app.config
    if not (cfg.get("MOMO_SUBSCRIPTION_KEY") and cfg.get("MOMO_API_USER")
            and cfg.get("MOMO_API_KEY")):
        return None
    # One client per app, so the access token is reused between requests.
    client = current_app.extensions.get("momo_client")
    if client is None:
        client = MomoClient(
            base_url=cfg["MOMO_BASE_URL"],
            subscription_key=cfg["MOMO_SUBSCRIPTION_KEY"],
            api_user=cfg["MOMO_API_USER"],
            api_key=cfg["MOMO_API_KEY"],
            target_environment=cfg["MOMO_TARGET_ENVIRONMENT"],
            currency=cfg["MOMO_CURRENCY"],
            callback_url=cfg.get("MOMO_CALLBACK_URL"),
        )
        current_app.extensions["momo_client"] = client
    return client
