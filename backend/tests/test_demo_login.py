"""One-click login into TEST accounts, for demos. Only when DEMO_LOGIN is on."""

import pytest
from conftest import PASSWORD, new_phone
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import Driver, User


def add_user(app, name, role, approved=True):
    with app.app_context():
        user = User(full_name=name, phone=f"+250{new_phone()[1:]}", role=role,
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
    add_user(app, "TEST Passenger", "passenger")

    response = demo_login(client, "passenger")

    assert response.status_code == 404
    assert client.get("/api/config").get_json()["features"]["demo_login"] is False


def test_logs_in_to_test_accounts(app, client, demo):
    ids = {role: add_user(app, f"TEST {role.title()}", role)
           for role in ("passenger", "driver", "admin")}

    for role, user_id in ids.items():
        body = demo_login(client, role).get_json()
        assert body["user"]["user_id"] == user_id
        assert body["user"]["role"] == role
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
        assert me.status_code == 200
    assert client.get("/api/config").get_json()["features"]["demo_login"] is True


def test_never_logs_in_to_real_accounts(app, client, demo):
    add_user(app, "Aline Uwase", "passenger")
    add_user(app, "Real Admin", "admin")

    assert demo_login(client, "passenger").status_code == 404
    assert demo_login(client, "admin").status_code == 404


def test_test_driver_must_be_approved(app, client, demo):
    add_user(app, "TEST Waiting Driver", "driver", approved=False)
    approved = add_user(app, "TEST Driver", "driver")

    assert demo_login(client, "driver").get_json()["user"]["user_id"] == approved


def test_unknown_role(client, demo):
    assert demo_login(client, "superuser").status_code == 400
