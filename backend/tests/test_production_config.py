"""The API refuses to start in production when it is unsafe."""

import pytest

from app import check_production

GOOD = {
    "DATABASE_URL": "postgresql+psycopg://u:p@db/etike",
    "SECRET_KEY": "a" * 64,
    "JWT_SECRET_KEY": "b" * 64,
    "DEMO_LOGIN": False,
}


def test_good_settings_start():
    check_production(dict(GOOD))


@pytest.mark.parametrize("change, message", [
    ({"DEMO_LOGIN": True}, "DEMO_LOGIN must be off"),
    ({"SECRET_KEY": None}, "Missing environment variables: SECRET_KEY"),
    ({"JWT_SECRET_KEY": "change-me"}, "long random value for: JWT_SECRET_KEY"),
    ({"SECRET_KEY": "short"}, "long random value for: SECRET_KEY"),
    ({"JWT_SECRET_KEY": "a" * 64}, "must be different"),
])
def test_unsafe_settings_refuse_to_start(change, message):
    with pytest.raises(RuntimeError, match=message):
        check_production({**GOOD, **change})


def test_large_request_is_refused(client):
    response = client.post("/api/auth/login", data=b"x" * (7 * 1024 * 1024),
                           content_type="application/json")

    assert response.status_code == 413
