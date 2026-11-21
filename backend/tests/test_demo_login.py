"""One-click login into the Demo Traveller and Demo Driver (found by their
reserved @etike.test emails). Only when DEMO_LOGIN is on."""

import pytest
from conftest import PASSWORD, new_phone
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import Driver, User


def add_user(app, name, role, approved=True, email=None):
    """A user. Demo accounts have the emails local_test_data.py gives them."""
    with app.app_context():
        email = email or f"{name.lower().replace(' ', '.')}@etike.test"
        user = User(full_name=name, phone=f"+250{new_phone()[1:]}", role=role, email=email,
                    password_hash=generate_password_hash(PASSWORD))
        if role == "driver":
            user.driver = Driver(license_number=f"LIC{new_phone()}", is_approved=approved)
        db.session.add(user)
        db.session.commit()
        return user.user_id


@pytest.fixture()
def demo(app):
    app.config["DEMO_LOGIN"] = True


def demo_login(client, role):
    return client.post("/api/auth/demo", json={"role": role})


def test_off_by_default(app, client):
    add_user(app, "Demo Traveller", "passenger", email="demo.passenger@etike.test")

    response = demo_login(client, "passenger")

    assert response.status_code == 404
    assert client.get("/api/config").get_json()["features"]["demo_login"] is False


def test_logs_in_to_the_two_demo_accounts(app, client, demo):
    # Other sample accounts are never picked, even with an earlier ID.
    add_user(app, "Divine Iradukunda", "passenger")
    add_user(app, "Aline Uwase", "driver")
    ids = {"passenger": add_user(app, "Demo Traveller", "passenger",
                                 email="demo.passenger@etike.test"),
           "driver": add_user(app, "Demo Driver", "driver", email="demo.driver@etike.test")}

    for role, user_id in ids.items():
        body = demo_login(client, role).get_json()
        assert body["user"]["user_id"] == user_id
        assert body["user"]["role"] == role
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
        assert me.status_code == 200
    assert client.get("/api/config").get_json()["features"]["demo_login"] is True


def test_never_logs_in_to_real_accounts(app, client, demo):
    # Only the demo emails count, whatever the name says.
    add_user(app, "Demo Traveller", "passenger", email="someone@example.com")
    add_user(app, "Real Admin", "admin", email="admin@example.com")

    assert demo_login(client, "passenger").status_code == 404
    # No one-click admin: admins always log in with a password.
    assert demo_login(client, "admin").status_code == 400


def test_test_driver_must_be_approved(app, client, demo):
    add_user(app, "Demo Driver", "driver", approved=False, email="demo.driver@etike.test")

    assert demo_login(client, "driver").status_code == 404


def test_unknown_role(client, demo):
    assert demo_login(client, "superuser").status_code == 400


def test_signup_cannot_use_the_test_domain(client):
    response = client.post("/api/auth/register", json={
        "full_name": "Someone", "phone": new_phone(), "password": PASSWORD,
        "email": "someone@ETIKE.test"})

    assert response.status_code == 400
    assert "email" in response.get_json()["error"]["fields"]
