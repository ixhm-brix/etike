"""Rides are confirmed without paying first (they are paid after the ride,
see test_ride_trip.py); confirmed bookings can be cancelled until the
cut-off; cancelling a paid bus ticket creates a refund."""

from app.extensions import db
from app.models import BusTrip, Payment, RideOffer


def book(client, headers, **body):
    return client.post("/api/bookings", json=body, headers=headers)


def cancel(client, headers, booking_id):
    return client.post(f"/api/bookings/{booking_id}/cancel", headers=headers)


def paid_bus_booking(client, passenger, momo, trip_id, seats=1):
    booking = book(client, passenger, trip_id=trip_id, seats=seats).get_json()["booking"]
    client.post("/api/payments", json={"booking_id": booking["booking_id"]}, headers=passenger)
    momo.answers("SUCCESSFUL")
    client.get(f"/api/payments/{booking['booking_id']}/status", headers=passenger)
    return booking["booking_id"]


def test_ride_is_confirmed_without_paying(app, client, make_offer, passenger):
    offer_id = make_offer(ride_type="shared", seats=3, price=4000)

    booking = book(client, passenger, offer_id=offer_id, seats=2).get_json()["booking"]

    assert booking["status"] == "confirmed"
    assert booking["pay_after_ride"] is True
    assert booking["expires_at"] is None
    assert booking["total_price"] == 8000
    with app.app_context():
        assert db.session.get(RideOffer, offer_id).seats_available == 1


def test_bus_still_needs_payment(client, make_trip, passenger):
    booking = book(client, passenger, trip_id=make_trip()).get_json()["booking"]

    assert booking["status"] == "pending"
    assert booking["pay_after_ride"] is False


def test_ride_is_not_paid_before_it_ends(client, make_offer, passenger, momo):
    booking = book(client, passenger, offer_id=make_offer()).get_json()["booking"]

    response = client.post("/api/payments", json={"booking_id": booking["booking_id"],
                                                  "phone": "0781234567"}, headers=passenger)

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "ride_not_ended"
    assert booking["can_pay"] is False
    assert momo.requests == []


def test_cancel_paid_bus_ticket_creates_refund(app, client, make_trip, passenger, momo):
    trip_id = make_trip(seats=3, price=5000, hours_ahead=24)
    booking_id = paid_bus_booking(client, passenger, momo, trip_id, seats=2)

    response = cancel(client, passenger, booking_id)

    booking = response.get_json()["booking"]
    assert response.status_code == 200
    assert booking["status"] == "cancelled"
    assert booking["refund_status"] == "due"
    with app.app_context():
        assert db.session.get(BusTrip, trip_id).available_seats == 3
        payment = db.session.query(Payment).filter_by(booking_id=booking_id).one()
        # The payment itself stays a success: the money was received.
        assert (payment.status, payment.refund_status, payment.amount) == ("success", "due", 10000)


def test_too_late_to_cancel_paid_ticket(app, client, make_trip, passenger, momo):
    trip_id = make_trip(seats=3, hours_ahead=1)  # inside the 2-hour cut-off
    booking_id = paid_bus_booking(client, passenger, momo, trip_id)

    response = cancel(client, passenger, booking_id)

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "too_late_to_cancel"
    with app.app_context():
        assert db.session.get(BusTrip, trip_id).available_seats == 2
        assert db.session.query(Payment).one().refund_status is None


def test_unpaid_booking_can_be_cancelled_any_time(client, make_trip, passenger):
    booking = book(client, passenger, trip_id=make_trip(hours_ahead=1)).get_json()["booking"]

    response = cancel(client, passenger, booking["booking_id"])

    assert response.status_code == 200
    assert response.get_json()["booking"]["refund_status"] is None


def test_cancel_ride_returns_seats_and_needs_no_refund(app, client, make_offer, passenger):
    offer_id = make_offer(ride_type="private", seats=4, hours_ahead=24)
    booking = book(client, passenger, offer_id=offer_id).get_json()["booking"]

    response = cancel(client, passenger, booking["booking_id"])

    assert response.get_json()["booking"]["status"] == "cancelled"
    assert response.get_json()["booking"]["refund_status"] is None
    with app.app_context():
        offer = db.session.get(RideOffer, offer_id)
        assert (offer.seats_available, offer.status) == (4, "open")


def test_too_late_to_cancel_ride(client, make_offer, passenger):
    booking = book(client, passenger, offer_id=make_offer(hours_ahead=1)).get_json()["booking"]

    response = cancel(client, passenger, booking["booking_id"])

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "too_late_to_cancel"


def test_cutoff_hours_can_be_changed(app, client, make_offer, passenger):
    app.config["CANCEL_CUTOFF_HOURS"] = 0.5
    booking = book(client, passenger, offer_id=make_offer(hours_ahead=1)).get_json()["booking"]

    assert cancel(client, passenger, booking["booking_id"]).status_code == 200


def test_admin_lists_and_completes_refunds(client, make_trip, passenger, momo, make_admin):
    booking_id = paid_bus_booking(client, passenger, momo, make_trip(price=5000))
    cancel(client, passenger, booking_id)
    admin = make_admin()

    due = client.get("/api/admin/refunds", headers=admin).get_json()["refunds"]
    done = client.post(f"/api/admin/refunds/{due[0]['payment_id']}/done", headers=admin)
    again = client.post(f"/api/admin/refunds/{due[0]['payment_id']}/done", headers=admin)
    left = client.get("/api/admin/refunds", headers=admin).get_json()["refunds"]
    sent = client.get("/api/admin/refunds?status=refunded", headers=admin).get_json()["refunds"]
    mine = client.get("/api/bookings/mine", headers=passenger).get_json()["bookings"]

    assert [(r["booking_id"], r["amount"]) for r in due] == [(booking_id, 5000)]
    assert due[0]["passenger_phone"].startswith("+2507")
    assert done.get_json()["refund"]["refund_status"] == "refunded"
    assert again.status_code == 200  # marking twice changes nothing
    assert left == []
    assert len(sent) == 1
    assert mine[0]["refund_status"] == "refunded"


def test_only_admins_see_refunds(client, passenger, make_trip, momo):
    booking_id = paid_bus_booking(client, passenger, momo, make_trip())
    cancel(client, passenger, booking_id)

    assert client.get("/api/admin/refunds", headers=passenger).status_code == 403
    assert client.post("/api/admin/refunds/1/done", headers=passenger).status_code == 403
    assert client.get("/api/admin/refunds").status_code == 401


def test_no_refund_for_a_payment_that_was_not_cancelled(client, make_trip, passenger, momo,
                                                        make_admin):
    paid_bus_booking(client, passenger, momo, make_trip())

    response = client.post("/api/admin/refunds/1/done", headers=make_admin())

    assert response.status_code == 404
