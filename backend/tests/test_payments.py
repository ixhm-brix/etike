from datetime import timedelta

from conftest import auth_header, register

from app.extensions import db
from app.models import Booking, BusTrip
from app.models.user import utcnow

EMAIL = "passenger@example.test"


def book(client, headers, **body):
    return client.post("/api/bookings", json=body, headers=headers).get_json()["booking"]


def pay(client, headers, booking_id, **extra):
    body = {"booking_id": booking_id, "email": EMAIL, **extra}
    return client.post("/api/payments", json=body, headers=headers)


def status(client, headers, booking_id):
    return client.get(f"/api/payments/{booking_id}/status", headers=headers).get_json()


def seats_left(app, trip_id):
    with app.app_context():
        return db.session.get(BusTrip, trip_id).available_seats


def test_payments_unavailable_without_keys(client, make_trip, passenger):
    booking = book(client, passenger, trip_id=make_trip())

    response = pay(client, passenger, booking["booking_id"])

    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "payments_unavailable"


def test_start_uses_server_amount(client, make_trip, passenger, flutterwave):
    booking = book(client, passenger, trip_id=make_trip(price=3500), seats=2)

    # A client trying to pay less is ignored.
    response = pay(client, passenger, booking["booking_id"], amount=1)

    assert response.status_code == 201
    payment = response.get_json()["payment"]
    assert payment["amount"] == 7000
    assert payment["status"] == "pending"
    assert payment["checkout_url"].startswith("https://")
    assert flutterwave.charges[0]["amount"] == 7000
    assert flutterwave.charges[0]["tx_ref"].startswith(f"etike-{booking['booking_id']}-")


def test_email_is_required_for_flutterwave(client, make_trip, passenger, flutterwave):
    booking = book(client, passenger, trip_id=make_trip())

    response = client.post("/api/payments", json={"booking_id": booking["booking_id"]},
                           headers=passenger)

    assert response.status_code == 400
    assert "email" in response.get_json()["error"]["fields"]


def test_successful_payment_confirms_booking(app, client, make_trip, passenger, flutterwave):
    trip_id = make_trip(seats=3)
    booking = book(client, passenger, trip_id=trip_id)
    pay(client, passenger, booking["booking_id"])

    still_waiting = status(client, passenger, booking["booking_id"])
    flutterwave.pays("successful")
    done = status(client, passenger, booking["booking_id"])

    assert still_waiting["booking"]["status"] == "pending"
    assert done["payment"]["status"] == "success"
    assert done["booking"]["status"] == "confirmed"
    assert seats_left(app, trip_id) == 2


def test_failed_payment_cancels_and_returns_seats(app, client, make_trip, passenger,
                                                  flutterwave):
    trip_id = make_trip(seats=3)
    booking = book(client, passenger, trip_id=trip_id, seats=2)
    pay(client, passenger, booking["booking_id"])

    flutterwave.pays("failed")
    done = status(client, passenger, booking["booking_id"])

    assert done["payment"]["status"] == "failed"
    assert done["booking"]["status"] == "cancelled"
    assert seats_left(app, trip_id) == 3


def test_wrong_amount_is_never_confirmed(app, client, make_trip, passenger, flutterwave):
    trip_id = make_trip(seats=3, price=5000)
    booking = book(client, passenger, trip_id=trip_id)
    pay(client, passenger, booking["booking_id"])

    flutterwave.pays("successful", amount=100)
    done = status(client, passenger, booking["booking_id"])

    assert done["booking"]["status"] == "cancelled"
    assert done["payment"]["status"] == "failed"
    assert seats_left(app, trip_id) == 3


def test_wrong_currency_is_never_confirmed(client, make_trip, passenger, flutterwave):
    booking = book(client, passenger, trip_id=make_trip())
    pay(client, passenger, booking["booking_id"])

    flutterwave.pays("successful", currency="USD")

    assert status(client, passenger, booking["booking_id"])["booking"]["status"] == "cancelled"


def test_cannot_pay_someone_elses_booking(client, make_trip, passenger, flutterwave):
    booking = book(client, passenger, trip_id=make_trip())
    stranger = auth_header(register(client))

    response = pay(client, stranger, booking["booking_id"])

    assert response.status_code == 404


def test_paying_twice_is_refused(client, make_trip, passenger, flutterwave):
    booking = book(client, passenger, trip_id=make_trip())
    pay(client, passenger, booking["booking_id"])

    again = pay(client, passenger, booking["booking_id"])

    assert again.status_code == 409
    assert len(flutterwave.charges) == 1


def test_provider_error_lets_passenger_retry(client, make_trip, passenger, flutterwave):
    booking = book(client, passenger, trip_id=make_trip())
    flutterwave.fail_charges = True
    first = pay(client, passenger, booking["booking_id"])
    flutterwave.fail_charges = False
    second = pay(client, passenger, booking["booking_id"])

    assert first.status_code == 502
    assert second.status_code == 201


def test_webhook_checks_secret_hash_and_is_idempotent(app, client, make_trip, passenger,
                                                     flutterwave):
    app.config["FLW_SECRET_HASH"] = "test-secret-hash"
    trip_id = make_trip(seats=3)
    booking = book(client, passenger, trip_id=trip_id)
    pay(client, passenger, booking["booking_id"])
    tx_ref = flutterwave.charges[0]["tx_ref"]
    flutterwave.pays("successful")
    body = {"event": "charge.completed", "data": {"tx_ref": tx_ref, "status": "successful"}}

    forged = client.post("/api/payments/webhook", json=body, headers={"verif-hash": "nope"})
    first = client.post("/api/payments/webhook", json=body,
                        headers={"verif-hash": "test-secret-hash"})
    second = client.post("/api/payments/webhook", json=body,
                         headers={"verif-hash": "test-secret-hash"})

    assert forged.status_code == 401
    assert first.get_json()["status"] == "success"
    assert second.get_json()["status"] == "success"
    # Received twice, but the seat was only taken once.
    assert seats_left(app, trip_id) == 2


def test_webhook_body_alone_never_confirms(app, client, make_trip, passenger, flutterwave):
    """A webhook saying "successful" changes nothing until Flutterwave agrees."""
    app.config["FLW_SECRET_HASH"] = "test-secret-hash"
    booking = book(client, passenger, trip_id=make_trip())
    pay(client, passenger, booking["booking_id"])
    tx_ref = flutterwave.charges[0]["tx_ref"]

    client.post("/api/payments/webhook",
                json={"data": {"tx_ref": tx_ref, "status": "successful"}},
                headers={"verif-hash": "test-secret-hash"})

    with app.app_context():
        assert db.session.get(Booking, booking["booking_id"]).status == "pending"


def expire(app, booking_id):
    with app.app_context():
        db.session.get(Booking, booking_id).expires_at = utcnow() - timedelta(minutes=1)
        db.session.commit()


def test_expired_booking_returns_seats(app, client, make_trip, passenger, flutterwave):
    trip_id = make_trip(seats=2)
    booking = book(client, passenger, trip_id=trip_id, seats=2)
    expire(app, booking["booking_id"])

    # Any search releases expired holds first.
    found = client.get("/api/trips?origin=Kigali&destination=Huye").get_json()["trips"]
    late = pay(client, passenger, booking["booking_id"])

    assert [t["available_seats"] for t in found] == [2]
    assert late.status_code == 409
    with app.app_context():
        assert db.session.get(Booking, booking["booking_id"]).status == "cancelled"


def test_expire_bookings_command(app, client, make_trip, passenger):
    trip_id = make_trip(seats=2)
    booking = book(client, passenger, trip_id=trip_id)
    expire(app, booking["booking_id"])

    result = app.test_cli_runner().invoke(args=["expire-bookings"])

    assert "Released 1" in result.output
    assert seats_left(app, trip_id) == 2


def test_payment_after_expiry_still_gets_seats_if_free(app, client, make_trip, passenger,
                                                       flutterwave):
    trip_id = make_trip(seats=2)
    booking = book(client, passenger, trip_id=trip_id)
    pay(client, passenger, booking["booking_id"])
    expire(app, booking["booking_id"])
    client.get("/api/trips?origin=Kigali&destination=Huye")  # releases the hold

    flutterwave.pays("successful")
    done = status(client, passenger, booking["booking_id"])

    assert done["booking"]["status"] == "confirmed"
    assert seats_left(app, trip_id) == 1
