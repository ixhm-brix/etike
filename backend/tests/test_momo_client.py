"""The MoMo HTTP client, run against a tiny local server that answers like
the MoMo API. No request leaves the machine."""

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.services.momo_client import MomoClient, MomoError, create_sandbox_user

KEY = "test-subscription-key"


class ImitationMomo(BaseHTTPRequestHandler):
    def _reply(self, code, body=None):
        raw = json.dumps(body).encode() if body is not None else b""
        self.send_response(code)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _handle(self):
        seen = self.server.seen
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length)) if length else None
        seen.append((self.command, self.path, dict(self.headers), body))

        if self.headers.get("Ocp-Apim-Subscription-Key") != KEY:
            return self._reply(401, {"message": "invalid subscription key"})
        if self.path == "/v1_0/apiuser":
            return self._reply(201)
        if self.path.endswith("/apikey"):
            return self._reply(201, {"apiKey": "made-up-api-key"})
        if self.path == "/collection/token/":
            expected = "Basic " + base64.b64encode(b"user-1:key-1").decode()
            if self.headers.get("Authorization") != expected:
                return self._reply(401)
            return self._reply(200, {"access_token": "token-1", "expires_in": 3600})
        if self.headers.get("Authorization") != "Bearer token-1":
            return self._reply(401)
        if self.path == "/collection/v1_0/requesttopay":
            self.server.payments[self.headers["X-Reference-Id"]] = body
            return self._reply(202)
        reference = self.path.rsplit("/", 1)[-1]
        if reference in self.server.payments:
            return self._reply(200, {**self.server.payments[reference], "status": "SUCCESSFUL"})
        return self._reply(404, {"code": "RESOURCE_NOT_FOUND"})

    do_GET = do_POST = _handle

    def log_message(self, *args):
        pass


@pytest.fixture()
def server():
    httpd = HTTPServer(("127.0.0.1", 0), ImitationMomo)
    httpd.seen, httpd.payments = [], {}
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd
    httpd.shutdown()


def make_client(server, **changes):
    settings = {
        "base_url": f"http://127.0.0.1:{server.server_port}",
        "subscription_key": KEY,
        "api_user": "user-1",
        "api_key": "key-1",
        "target_environment": "sandbox",
        "currency": "EUR",
        **changes,
    }
    return MomoClient(**settings)


def test_request_to_pay_then_status(server):
    client = make_client(server)

    client.request_to_pay("ref-1", 7000, "250781234567", external_id=12, message="ETIKE booking 12")
    answer = client.get_status("ref-1")

    method, path, headers, body = server.seen[1]
    assert (method, path) == ("POST", "/collection/v1_0/requesttopay")
    assert headers["X-Reference-Id"] == "ref-1"
    assert headers["X-Target-Environment"] == "sandbox"
    assert "X-Callback-Url" not in headers
    assert body == {
        "amount": "7000",
        "currency": "EUR",
        "externalId": "12",
        "payer": {"partyIdType": "MSISDN", "partyId": "250781234567"},
        "payerMessage": "ETIKE booking 12",
        "payeeNote": "ETIKE booking 12",
    }
    assert answer["status"] == "SUCCESSFUL"
    assert answer["externalId"] == "12"


def test_token_is_fetched_once_and_reused(server):
    client = make_client(server)

    client.request_to_pay("ref-1", 100, "250781234567", 1, "x")
    client.get_status("ref-1")
    client.get_status("ref-1")

    token_calls = [s for s in server.seen if s[1] == "/collection/token/"]
    assert len(token_calls) == 1


def test_callback_url_is_sent_when_set(server):
    client = make_client(server, callback_url="https://etike.example/api/payments/callback")

    client.request_to_pay("ref-1", 100, "250781234567", 1, "x")

    assert server.seen[1][2]["X-Callback-Url"] == "https://etike.example/api/payments/callback"


def test_bad_keys_raise_momo_error(server):
    with pytest.raises(MomoError):
        make_client(server, subscription_key="wrong").get_status("ref-1")
    with pytest.raises(MomoError):
        make_client(server, api_key="wrong").get_status("ref-1")


def test_unreachable_momo_raises_momo_error():
    client = MomoClient("http://127.0.0.1:9", KEY, "user-1", "key-1", "sandbox", "EUR", timeout=2)

    with pytest.raises(MomoError):
        client.get_status("ref-1")


def test_create_sandbox_user(server):
    base = f"http://127.0.0.1:{server.server_port}"

    api_key = create_sandbox_user(base, KEY, "new-user-id", "localhost")

    assert api_key == "made-up-api-key"
    assert server.seen[0][2]["X-Reference-Id"] == "new-user-id"
    assert server.seen[0][3] == {"providerCallbackHost": "localhost"}
    assert server.seen[1][1] == "/v1_0/apiuser/new-user-id/apikey"
