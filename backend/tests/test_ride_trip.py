"""A ride like a taxi app: the driver starts and ends it, then each
passenger pays with MoMo and the driver sees the payment come in."""

from datetime import timedelta

import pytest
from conftest import auth_header, register

from app.extensions import db
from app.models import Driver
from app.validation import local_now


@pytest.fixture()
def ride(app, client):
    """ride(minutes_ahead=30, seats=3) -> (driver headers, offer_id), posted by an
    approved driver through the API."""

    def make(minutes_ahead=30, seats=3, price=4000):
        signup = register(client, role="driver")
        headers = auth_header(signup)
        with app.app_context():
            driver = db.session.get(Driver, signup.get_json()["user"]["driver"]["driver_id"])
            driver.is_approved = True
            db.session.commit()
        vehicle = client.post("/api/drivers/vehicles", headers=headers, json={
            "plate_number": f"RA{signup.get_json()['user']['phone'][-5:]}", "model": "Toyota RAV4",
            "seats": seats}).get_json()["vehicle"]
        departure = (local_now() + timedelta(minutes=minutes_ahead)).replace(microsecond=0)
        posted = client.post("/api/rides", headers=headers, json={
            "vehicle_id": vehicle["vehicle_id"], "origin": "Kigali", "destination": "Huye",
            "ride_type": "shared", "departure_time": departure.isoformat(), "price": price,
            "seats_available": seats})
        assert posted.status_code == 201, posted.get_json()
        return headers, posted.get_json()["ride"]["offer_id"]

    return make


def book(client, passenger, offer_id, seats=1):
    response = client.post("/api/bookings", json={"offer_id": offer_id, "seats": seats},
                           headers=passenger)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["booking"]["booking_id"]


def start(client, driver, offer_id):
    return client.post(f"/api/rides/{offer_id}/start", headers=driver)


def end(client, driver, offer_id):
    return client.post(f"/api/rides/{offer_id}/end", headers=driver)


def pay(client, passenger, booking_id):
    return client.post("/api/payments", json={"booking_id": booking_id, "phone": "0781234567"},
                       headers=passenger)


def booking_of(client, passenger, booking_id):
    return client.get(f"/api/bookings/{booking_id}", headers=passenger).get_json()["booking"]


def test_full_trip_start_end_pay(client, ride, passenger, momo):
    driver, offer_id = ride(price=4000)
    booking_id = book(client, passenger, offer_id, seats=2)

    started = start(client, driver, offer_id)
    during = booking_of(client, passenger, booking_id)
    ended = end(client, driver, offer_id)
    after = booking_of(client, passenger, booking_id)
    paying = pay(client, passenger, booking_id)
    momo.answers("SUCCESSFUL")
    client.get(f"/api/payments/{booking_id}/status", headers=passenger)
    rides = client.get("/api/drivers/rides", headers=driver).get_json()["rides"]

    assert started.get_json()["ride"]["progress"] == "in_progress"
    assert during["ride_progress"] == "in_progress" and during["can_pay"] is False
    assert ended.get_json()["ride"]["progress"] == "ended"
    assert after["can_pay"] is True
    assert paying.status_code == 201
    assert momo.requests[-1]["amount"] == 8000  # the server's price, 2 seats
    mine = next(r for r in rides if r["offer_id"] == offer_id)
    assert mine["passengers"][0]["payment_status"] == "success"
    assert mine["paid"] == mine["to_collect"] == 8000
    assert booking_of(client, passenger, booking_id)["can_pay"] is False


def test_failed_ride_payment_can_be_tried_again(client, ride, passenger, momo):
    driver, offer_id = ride()
    booking_id = book(client, passenger, offer_id)
    start(client, driver, offer_id)
    end(client, driver, offer_id)

    pay(client, passenger, booking_id)
    momo.answers("FAILED", reason="APPROVAL_REJECTED")
    client.get(f"/api/payments/{booking_id}/status", headers=passenger)
    failed = booking_of(client, passenger, booking_id)
    again = pay(client, passenger, booking_id)

    # A failed payment never cancels a ride that already happened.
    assert failed["status"] == "confirmed" and failed["can_pay"] is True
    assert again.status_code == 201
    assert len(momo.requests) == 2


def test_ride_rules(client, ride, passenger):
    early_driver, early_offer = ride(minutes_ahead=180)
    driver, offer_id = ride()

    too_early = start(client, early_driver, early_offer)
    nobody = start(client, driver, offer_id)
    not_started = end(client, driver, offer_id)

    assert too_early.get_json()["error"]["code"] == "too_early"
    assert nobody.get_json()["error"]["code"] == "no_passengers"
    assert not_started.get_json()["error"]["code"] == "not_started"


def test_only_the_rides_own_driver_can_start_it(client, ride, passenger):
    driver, offer_id = ride()
    other_driver, _ = ride()
    book(client, passenger, offer_id)

    assert start(client, other_driver, offer_id).status_code == 404
    assert start(client, passenger, offer_id).status_code == 403
    assert start(client, driver, offer_id).status_code == 200
    assert start(client, driver, offer_id).get_json()["error"]["code"] == "already_started"


def test_started_ride_cannot_be_cancelled(app, client, ride, passenger):
    driver, offer_id = ride()
    booking_id = book(client, passenger, offer_id)
    start(client, driver, offer_id)

    response = client.post(f"/api/bookings/{booking_id}/cancel", headers=passenger)

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "ride_started"
