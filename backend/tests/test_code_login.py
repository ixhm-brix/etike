"""Logging in with a one-time code sent by SMS, without creating a password."""

from datetime import timedelta

import pytest
from conftest import PASSWORD, new_phone, register

from app.extensions import db
from app.models import LoginCode, User
from app.models.user import utcnow


@pytest.fixture()
def show_codes(app):
    """Like a laptop in development: no SMS keys, the code comes back."""
    app.config["SHOW_LOGIN_CODES"] = True


def ask(client, phone):
    return client.post("/api/auth/code", json={"phone": phone})


def verify(client, phone, code, **extra):
    return client.post("/api/auth/verify", json={"phone": phone, "code": code, **extra})


def test_new_number_becomes_a_passenger(app, client, show_codes):
    phone = new_phone()
    code = ask(client, phone).get_json()["dev_code"]

    needs_name = verify(client, phone, code)
    done = verify(client, phone, code, full_name="Aline Uwase")

    assert needs_name.status_code == 400
    assert needs_name.get_json()["error"]["code"] == "name_required"
    assert done.status_code == 201
    body = done.get_json()
    assert body["new_user"] is True
    assert body["access_token"]
    assert body["user"]["role"] == "passenger"
    assert body["user"]["full_name"] == "Aline Uwase"
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200


def test_existing_account_logs_in_without_password(client, show_codes):
    phone = new_phone()
    register(client, role="driver", phone=phone, full_name="Eric Driver")
    code = ask(client, phone).get_json()["dev_code"]

    response = verify(client, phone, code)

    assert response.status_code == 200
    assert response.get_json()["new_user"] is False
    assert response.get_json()["user"]["role"] == "driver"


def test_code_works_once(client, show_codes):
    phone = new_phone()
    code = ask(client, phone).get_json()["dev_code"]
    verify(client, phone, code, full_name="Test Person")

    again = verify(client, phone, code)

    assert again.status_code == 400
    assert again.get_json()["error"]["code"] == "invalid_code"


def test_wrong_code_and_attempt_limit(client, show_codes):
    phone = new_phone()
    code = ask(client, phone).get_json()["dev_code"]
    wrong = "000000" if code != "000000" else "111111"

    for _ in range(5):
        assert verify(client, phone, wrong).status_code == 400
    # After 5 wrong tries even the right code no longer works.
    assert verify(client, phone, code, full_name="Test Person").status_code == 400


def test_expired_code(app, client, show_codes):
    phone = new_phone()
    code = ask(client, phone).get_json()["dev_code"]
    with app.app_context():
        db.session.query(LoginCode).update({"expires_at": utcnow() - timedelta(minutes=1)})
        db.session.commit()

    assert verify(client, phone, code, full_name="Test Person").status_code == 400


def test_code_is_for_one_number_only(client, show_codes):
    phone, other = new_phone(), new_phone()
    code = ask(client, phone).get_json()["dev_code"]

    assert verify(client, other, code, full_name="Test Person").status_code == 400


def test_must_wait_before_asking_again(app, client, show_codes):
    phone = new_phone()
    first = ask(client, phone).get_json()["dev_code"]

    too_soon = ask(client, phone)
    with app.app_context():
        db.session.query(LoginCode).update(
            {"created_at": utcnow() - timedelta(minutes=2)})
        db.session.commit()
    second = ask(client, phone).get_json()["dev_code"]

    assert too_soon.status_code == 429
    # Only the newest code works.
    if first != second:
        assert verify(client, phone, first, full_name="Test Person").status_code == 400
    assert verify(client, phone, second, full_name="Test Person").status_code == 201


def test_limit_per_hour(app, client, show_codes):
    phone = new_phone()
    for _ in range(5):
        ask(client, phone)
        with app.app_context():
            db.session.query(LoginCode).update(
                {"created_at": utcnow() - timedelta(minutes=2)})
            db.session.commit()

    assert ask(client, phone).status_code == 429


def test_unavailable_on_a_server_without_sms(client):
    response = ask(client, new_phone())

    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "code_login_unavailable"


def test_code_is_texted_not_shown_when_sms_is_set_up(app, client, monkeypatch):
    from app.services import sms_service

    app.config.update(AT_USERNAME="sandbox", AT_API_KEY="test-key", SHOW_LOGIN_CODES=True)
    sent = []
    monkeypatch.setattr(sms_service, "send", lambda phone, text: sent.append((phone, text)) or True)
    phone = new_phone()

    response = ask(client, phone)

    assert response.status_code == 200
    assert "dev_code" not in response.get_json()
    assert sent[0][0] == "+250" + phone[1:]
    code = sent[0][1].split("code is ")[1][:6]
    assert verify(client, phone, code, full_name="Test Person").status_code == 201


def test_failed_sms_is_reported(app, client, monkeypatch):
    from app.services import sms_service

    app.config.update(AT_USERNAME="sandbox", AT_API_KEY="test-key")
    monkeypatch.setattr(sms_service, "send", lambda phone, text: False)

    assert ask(client, new_phone()).status_code == 502


def test_code_only_account_cannot_use_password_login(client, show_codes):
    phone = new_phone()
    code = ask(client, phone).get_json()["dev_code"]
    verify(client, phone, code, full_name="Test Person")

    response = client.post("/api/auth/login", json={"phone": phone, "password": PASSWORD})

    assert response.status_code == 401


def test_codes_are_not_stored_in_plain_text(app, client, show_codes):
    phone = new_phone()
    code = ask(client, phone).get_json()["dev_code"]

    with app.app_context():
        stored = db.session.query(LoginCode).one()
        assert code not in stored.code_hash
        assert db.session.query(User).count() == 0
