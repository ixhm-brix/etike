from datetime import timedelta

from conftest import auth_header, register

from app.extensions import db
from app.models import Booking, BusTrip
from app.models.user import utcnow


def book(client, headers, **body):
    return client.post("/api/bookings", json=body, headers=headers).get_json()["booking"]


def pay(client, headers, booking_id, **extra):
    return client.post("/api/payments", json={"booking_id": booking_id, **extra},
                       headers=headers)


def status(client, headers, booking_id):
    return client.get(f"/api/payments/{booking_id}/status", headers=headers).get_json()


def seats_left(app, trip_id):
    with app.app_context():
        return db.session.get(BusTrip, trip_id).available_seats


def test_payments_unavailable_without_momo_settings(client, make_trip, passenger):
    booking = book(client, passenger, trip_id=make_trip())

    response = pay(client, passenger, booking["booking_id"])

    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "payments_unavailable"


def test_start_uses_server_amount(client, make_trip, passenger, momo):
    booking = book(client, passenger, trip_id=make_trip(price=3500), seats=2)

    # A client trying to pay less is ignored.
    response = pay(client, passenger, booking["booking_id"], amount=1, phone="078 123 4567")

    assert response.status_code == 201
    payment = response.get_json()["payment"]
    assert payment["amount"] == 7000
    assert payment["status"] == "pending"
    assert payment["method"] == "mtn_momo"
    sent = momo.requests[0]
    assert sent["amount"] == 7000
    assert sent["phone"] == "250781234567"
    assert sent["external_id"] == booking["booking_id"]
    assert len(sent["reference"]) == 36  # a UUID


def test_only_mtn_numbers_can_pay(client, make_trip, passenger, momo):
    booking = book(client, passenger, trip_id=make_trip())

    airtel = pay(client, passenger, booking["booking_id"], phone="0731234567")

    assert airtel.status_code == 400
    assert "phone" in airtel.get_json()["error"]["fields"]
    assert momo.requests == []


def test_successful_payment_confirms_booking(app, client, make_trip, passenger, momo):
    trip_id = make_trip(seats=3)
    booking = book(client, passenger, trip_id=trip_id)
    pay(client, passenger, booking["booking_id"])

    # Pending first (the passenger hasn't entered their PIN yet), then success.
    still_waiting = status(client, passenger, booking["booking_id"])
    momo.answers("SUCCESSFUL")
    done = status(client, passenger, booking["booking_id"])

    assert still_waiting["booking"]["status"] == "pending"
    assert still_waiting["payment"]["status"] == "pending"
    assert done["payment"]["status"] == "success"
    assert done["booking"]["status"] == "confirmed"
    assert seats_left(app, trip_id) == 2


def test_created_status_keeps_waiting(client, make_trip, passenger, momo):
    """The sandbox answers CREATED before SUCCESSFUL; that is still waiting."""
    booking = book(client, passenger, trip_id=make_trip())
    pay(client, passenger, booking["booking_id"])

    momo.answers("CREATED")
    waiting = status(client, passenger, booking["booking_id"])
    momo.answers("SUCCESSFUL")
    done = status(client, passenger, booking["booking_id"])

    assert waiting["booking"]["status"] == "pending"
    assert done["booking"]["status"] == "confirmed"


def test_failed_payment_cancels_and_returns_seats(app, client, make_trip, passenger, momo):
    trip_id = make_trip(seats=3)
    booking = book(client, passenger, trip_id=trip_id, seats=2)
    pay(client, passenger, booking["booking_id"])

    momo.answers("FAILED", reason="INTERNAL_PROCESSING_ERROR")
    done = status(client, passenger, booking["booking_id"])

    assert done["payment"]["status"] == "failed"
    assert done["payment"]["failure_reason"] == "INTERNAL_PROCESSING_ERROR"
    assert done["booking"]["status"] == "cancelled"
    assert seats_left(app, trip_id) == 3


def test_rejected_payment_cancels_and_returns_seats(app, client, make_trip, passenger, momo):
    trip_id = make_trip(seats=3)
    booking = book(client, passenger, trip_id=trip_id)
    pay(client, passenger, booking["booking_id"])

    # The passenger said no on their phone.
    momo.answers("FAILED", reason="APPROVAL_REJECTED")
    done = status(client, passenger, booking["booking_id"])

    assert done["payment"]["failure_reason"] == "APPROVAL_REJECTED"
    assert done["booking"]["status"] == "cancelled"
    assert seats_left(app, trip_id) == 3


def test_reason_can_be_an_object(client, make_trip, passenger, momo):
    booking = book(client, passenger, trip_id=make_trip())
    pay(client, passenger, booking["booking_id"])

    momo.answers("FAILED", reason={"code": "PAYER_NOT_FOUND", "message": "Payer not found"})

    done = status(client, passenger, booking["booking_id"])
    assert done["payment"]["failure_reason"] == "PAYER_NOT_FOUND"


def test_wrong_amount_is_never_confirmed(app, client, make_trip, passenger, momo):
    trip_id = make_trip(seats=3, price=5000)
    booking = book(client, passenger, trip_id=trip_id)
    pay(client, passenger, booking["booking_id"])

    momo.answers("SUCCESSFUL", amount="100")
    done = status(client, passenger, booking["booking_id"])

    assert done["booking"]["status"] == "cancelled"
    assert done["payment"]["status"] == "failed"
    assert seats_left(app, trip_id) == 3


def test_wrong_currency_or_booking_is_never_confirmed(client, make_trip, passenger, momo):
    first = book(client, passenger, trip_id=make_trip())
    pay(client, passenger, first["booking_id"])
    momo.answers("SUCCESSFUL", currency="USD")
    second = book(client, passenger, trip_id=make_trip())

    assert status(client, passenger, first["booking_id"])["booking"]["status"] == "cancelled"

    pay(client, passenger, second["booking_id"])
    momo.answers("SUCCESSFUL", externalId="99999")
    assert status(client, passenger, second["booking_id"])["booking"]["status"] == "cancelled"


def test_cannot_pay_someone_elses_booking(client, make_trip, passenger, momo):
    booking = book(client, passenger, trip_id=make_trip())
    stranger = auth_header(register(client))

    response = pay(client, stranger, booking["booking_id"])

    assert response.status_code == 404


def test_paying_twice_is_refused(client, make_trip, passenger, momo):
    booking = book(client, passenger, trip_id=make_trip())
    pay(client, passenger, booking["booking_id"])

    again = pay(client, passenger, booking["booking_id"])

    assert again.status_code == 409
    assert len(momo.requests) == 1


def test_momo_error_lets_passenger_retry(client, make_trip, passenger, momo):
    booking = book(client, passenger, trip_id=make_trip())
    momo.fail_requests = True
    first = pay(client, passenger, booking["booking_id"])
    momo.fail_requests = False
    second = pay(client, passenger, booking["booking_id"])

    assert first.status_code == 502
    assert second.status_code == 201
    # Each request to pay gets its own reference.
    assert len(momo.requests) == 1


def test_callback_is_idempotent(app, client, make_trip, passenger, momo):
    trip_id = make_trip(seats=3)
    booking = book(client, passenger, trip_id=trip_id)
    pay(client, passenger, booking["booking_id"])
    momo.answers("SUCCESSFUL")
    body = {"externalId": str(booking["booking_id"]), "status": "SUCCESSFUL"}

    first = client.post("/api/payments/callback", json=body)
    second = client.put("/api/payments/callback", json=body)

    assert first.get_json()["status"] == "success"
    assert second.get_json()["status"] == "success"
    # Received twice, but the seat was only taken once.
    assert seats_left(app, trip_id) == 2
    assert status(client, passenger, booking["booking_id"])["booking"]["status"] == "confirmed"


def test_callback_alone_never_confirms(app, client, make_trip, passenger, momo):
    """A callback saying SUCCESSFUL changes nothing until MoMo itself agrees."""
    booking = book(client, passenger, trip_id=make_trip())
    pay(client, passenger, booking["booking_id"])

    forged = client.post(
        "/api/payments/callback",
        json={"externalId": str(booking["booking_id"]), "status": "SUCCESSFUL"},
    )
    unknown = client.post("/api/payments/callback", json={"externalId": "424242"})
    junk = client.post("/api/payments/callback", data="not json")

    assert forged.get_json()["status"] == "pending"
    assert unknown.get_json()["status"] == "ignored"
    assert junk.status_code == 200
    with app.app_context():
        assert db.session.get(Booking, booking["booking_id"]).status == "pending"


def test_status_tells_the_page_about_sandbox_currency(client, make_trip, passenger, momo):
    booking = book(client, passenger, trip_id=make_trip())

    provider = status(client, passenger, booking["booking_id"])["provider"]

    assert provider == {"currency": "EUR", "sandbox": True}


def expire(app, booking_id):
    with app.app_context():
        db.session.get(Booking, booking_id).expires_at = utcnow() - timedelta(minutes=1)
        db.session.commit()


def test_expired_booking_returns_seats(app, client, make_trip, passenger, momo):
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


def test_payment_after_expiry_still_gets_seats_if_free(app, client, make_trip, passenger, momo):
    trip_id = make_trip(seats=2)
    booking = book(client, passenger, trip_id=trip_id)
    pay(client, passenger, booking["booking_id"])
    expire(app, booking["booking_id"])
    client.get("/api/trips?origin=Kigali&destination=Huye")  # releases the hold

    momo.answers("SUCCESSFUL")
    done = status(client, passenger, booking["booking_id"])

    assert done["booking"]["status"] == "confirmed"
    assert seats_left(app, trip_id) == 1


def test_momo_create_user_needs_subscription_key(app):
    result = app.test_cli_runner().invoke(args=["momo-create-user"])

    assert result.exit_code != 0
    assert "MOMO_SUBSCRIPTION_KEY" in result.output
