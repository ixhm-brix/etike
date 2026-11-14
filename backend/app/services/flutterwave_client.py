"""A small client for Flutterwave's v3 API: Rwanda mobile money charges and
transaction verification.

Endpoints (checked against Flutterwave's official Node SDK, v1.3.1):
  POST /v3/charges?type=mobile_money_rwanda
       -> {"status": "success", "meta": {"authorization": {"mode": "redirect",
           "redirect": "<page where the customer approves>"}}}
  GET  /v3/transactions/verify_by_reference?tx_ref=<our tx_ref>
       -> {"status": "success", "data": {"tx_ref", "amount", "currency", "status", ...}}

In test mode the customer approves on the redirect page with OTP 123456.
Uses only the standard library. The payment service gets a client from
get_client(), which tests replace with a fake.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from flask import current_app

log = logging.getLogger(__name__)


class FlutterwaveError(Exception):
    """Flutterwave could not be reached or refused the request."""


class FlutterwaveClient:
    def __init__(self, base_url, secret_key, timeout=20):
        self.base_url = base_url.rstrip("/")
        self.secret_key = secret_key
        self.timeout = timeout

    def charge_rwanda_mobile_money(self, tx_ref, amount, phone, email, fullname,
                                   redirect_url=None):
        """Start a charge. Returns the URL where the customer approves it."""
        body = {
            "tx_ref": tx_ref,
            "amount": str(amount),
            "currency": "RWF",
            "email": email,
            "phone_number": phone,
            "fullname": fullname,
        }
        if redirect_url:
            body["redirect_url"] = redirect_url
        data = self._call("POST", "/v3/charges?type=mobile_money_rwanda", body)
        redirect = (data.get("meta") or {}).get("authorization", {}).get("redirect")
        if data.get("status") != "success" or not redirect:
            log.warning("Flutterwave charge not started: %s", data.get("message"))
            raise FlutterwaveError(data.get("message") or "Charge not started")
        return redirect

    def verify_by_reference(self, tx_ref):
        """Return the transaction's `data`, or None if Flutterwave has no
        transaction for this tx_ref yet (the customer has not finished)."""
        query = urllib.parse.urlencode({"tx_ref": tx_ref})
        try:
            data = self._call("GET", f"/v3/transactions/verify_by_reference?{query}")
        except FlutterwaveError as err:
            if getattr(err, "status", None) in (400, 404):
                return None
            raise
        return data.get("data")

    def _call(self, method, path, body=None):
        headers = {"Authorization": f"Bearer {self.secret_key}", "Accept": "application/json"}
        payload = None
        if body is not None:
            payload = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base_url + path, data=payload, headers=headers,
                                     method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                return json.loads(res.read() or b"{}")
        except urllib.error.HTTPError as err:
            # Log Flutterwave's reason, never the secret key.
            detail = err.read()[:300].decode(errors="replace")
            log.warning("Flutterwave %s %s failed: %s %s", method, path.split("?")[0],
                        err.code, detail)
            error = FlutterwaveError(f"Flutterwave answered {err.code}")
            error.status = err.code
            raise error from None
        except (urllib.error.URLError, TimeoutError) as err:
            log.warning("Flutterwave %s unreachable: %s", path.split("?")[0], err)
            raise FlutterwaveError("Flutterwave could not be reached") from None


def get_client():
    """A FlutterwaveClient from the app settings, or None if not set up."""
    cfg = current_app.config
    if not cfg.get("FLW_SECRET_KEY"):
        return None
    return FlutterwaveClient(cfg["FLW_BASE_URL"], cfg["FLW_SECRET_KEY"])
