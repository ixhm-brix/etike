from conftest import PASSWORD, auth_header, new_phone, register


def test_register_passenger(client):
    response = register(client, phone="078 123 4567")

    assert response.status_code == 201
    body = response.get_json()
    assert body["access_token"]
    assert body["user"]["role"] == "passenger"
    # Phone numbers are stored in one format.
    assert body["user"]["phone"] == "+250781234567"
    assert "password_hash" not in body["user"]


def test_register_driver_needs_licence(client):
    response = client.post(
        "/api/auth/register",
        json={"full_name": "Driver", "phone": new_phone(), "password": PASSWORD, "role": "driver"},
    )

    assert response.status_code == 400
    assert "license_number" in response.get_json()["error"]["fields"]


def test_register_driver_starts_unapproved(client):
    response = register(client, role="driver")

    assert response.status_code == 201
    assert response.get_json()["user"]["driver"]["is_approved"] is False


def test_cannot_register_as_admin(client):
    response = register(client, role="admin")

    assert response.status_code == 400
    assert "role" in response.get_json()["error"]["fields"]


def test_register_rejects_bad_phone_and_short_password(client):
    bad_phone = register(client, phone="12345")
    short_password = register(client, password="short")

    assert bad_phone.status_code == 400
    assert "phone" in bad_phone.get_json()["error"]["fields"]
    assert short_password.status_code == 400
    assert "password" in short_password.get_json()["error"]["fields"]


def test_duplicate_phone(client):
    phone = new_phone()
    register(client, phone=phone)

    # Same number written differently is still the same number.
    response = register(client, phone="+250" + phone[1:])

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "phone_taken"


def test_login_and_me(client):
    phone = new_phone()
    register(client, phone=phone, full_name="Aline")

    login = client.post("/api/auth/login", json={"phone": phone, "password": PASSWORD})
    me = client.get("/api/auth/me", headers=auth_header(login))

    assert login.status_code == 200
    assert me.status_code == 200
    assert me.get_json()["user"]["full_name"] == "Aline"


def test_login_wrong_password(client):
    phone = new_phone()
    register(client, phone=phone)

    wrong = client.post("/api/auth/login", json={"phone": phone, "password": "wrong-password"})
    unknown = client.post("/api/auth/login", json={"phone": new_phone(), "password": PASSWORD})

    assert wrong.status_code == 401
    # Unknown phone gets the same answer, so accounts can't be discovered.
    assert unknown.status_code == 401
    assert wrong.get_json() == unknown.get_json()


def test_me_needs_token(client):
    missing = client.get("/api/auth/me")
    broken = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-token"})

    assert missing.status_code == 401
    assert broken.status_code == 401
    assert missing.get_json()["error"]["code"] == "unauthorized"


def test_role_restrictions(client, passenger):
    driver = auth_header(register(client, role="driver"))

    # Passengers cannot add vehicles; drivers cannot book.
    vehicle = client.post(
        "/api/drivers/vehicles",
        json={"plate_number": "RAB 123 A", "model": "Car", "seats": 4},
        headers=passenger,
    )
    booking = client.post("/api/bookings", json={"trip_id": 1}, headers=driver)

    assert vehicle.status_code == 403
    assert booking.status_code == 403


def test_unapproved_driver_cannot_post_ride(client):
    driver = auth_header(register(client, role="driver"))
    vehicle = client.post(
        "/api/drivers/vehicles",
        json={"plate_number": "RAB 123 A", "model": "Car", "seats": 4},
        headers=driver,
    )

    response = client.post(
        "/api/rides",
        json={
            "vehicle_id": vehicle.get_json()["vehicle"]["vehicle_id"],
            "origin": "Kigali",
            "destination": "Huye",
            "ride_type": "shared",
            "departure_time": "2099-01-01T08:00",
            "price": 5000,
        },
        headers=driver,
    )

    assert vehicle.status_code == 201
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "driver_not_approved"
