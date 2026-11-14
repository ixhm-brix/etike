import threading
import time

import pytest
from conftest import auth_header, is_postgres, register

from app.extensions import db
from app.models import BusTrip, RideOffer
from app.services import booking_service


def book(client, headers, **body):
    return client.post("/api/bookings", json=body, headers=headers)


def seats_left(app, model, pk):
    with app.app_context():
        row = db.session.get(model, pk)
        return row.available_seats if model is BusTrip else row.seats_available


def test_booking_reduces_seats(app, client, make_trip, passenger):
    trip_id = make_trip(seats=5, price=3500)

    response = book(client, passenger, trip_id=trip_id, seats=2)

    assert response.status_code == 201
    booking = response.get_json()["booking"]
    # Seats are held while the passenger pays.
    assert booking["status"] == "pending"
    assert booking["expires_at"]
    assert booking["total_price"] == 7000
    assert seats_left(app, BusTrip, trip_id) == 3


def test_price_from_client_is_ignored(client, make_trip, passenger):
    trip_id = make_trip(price=3500)

    response = book(client, passenger, trip_id=trip_id, seats=1, total_price=1)

    assert response.get_json()["booking"]["total_price"] == 3500


def test_overbooking_returns_409(app, client, make_trip, passenger):
    trip_id = make_trip(seats=2)

    response = book(client, passenger, trip_id=trip_id, seats=3)

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "not_enough_seats"
    # Nothing changed: the transaction was rolled back.
    assert seats_left(app, BusTrip, trip_id) == 2


def test_booking_validation(client, make_trip, passenger):
    trip_id = make_trip()

    both = book(client, passenger, trip_id=trip_id, offer_id=1)
    neither = book(client, passenger)
    zero = book(client, passenger, trip_id=trip_id, seats=0)
    missing = book(client, passenger, trip_id=99999)
    no_login = client.post("/api/bookings", json={"trip_id": trip_id})

    assert both.status_code == 400
    assert neither.status_code == 400
    assert zero.status_code == 400
    assert missing.status_code == 404
    assert no_login.status_code == 401


def test_cannot_book_departed_trip(client, make_trip, passenger):
    trip_id = make_trip(hours_ahead=-1)

    response = book(client, passenger, trip_id=trip_id)

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "departed"


def test_cancel_returns_seats(app, client, make_trip, passenger):
    trip_id = make_trip(seats=4)
    booking = book(client, passenger, trip_id=trip_id, seats=3).get_json()["booking"]

    cancelled = client.post(f"/api/bookings/{booking['booking_id']}/cancel", headers=passenger)
    again = client.post(f"/api/bookings/{booking['booking_id']}/cancel", headers=passenger)

    assert cancelled.status_code == 200
    assert cancelled.get_json()["booking"]["status"] == "cancelled"
    assert seats_left(app, BusTrip, trip_id) == 4
    assert again.status_code == 409


def test_cannot_cancel_someone_elses_booking(client, make_trip, passenger):
    trip_id = make_trip()
    booking = book(client, passenger, trip_id=trip_id).get_json()["booking"]
    stranger = auth_header(register(client))

    response = client.post(f"/api/bookings/{booking['booking_id']}/cancel", headers=stranger)

    assert response.status_code == 404


def test_my_bookings(client, make_trip, passenger):
    trip_id = make_trip()
    book(client, passenger, trip_id=trip_id)
    other = auth_header(register(client))

    mine = client.get("/api/bookings/mine", headers=passenger).get_json()["bookings"]
    theirs = client.get("/api/bookings/mine", headers=other).get_json()["bookings"]

    assert [b["trip_id"] for b in mine] == [trip_id]
    assert mine[0]["origin"] == "Kigali"
    assert theirs == []


def test_shared_ride_charges_per_seat_and_fills_up(app, client, make_offer, passenger):
    offer_id = make_offer(ride_type="shared", seats=3, price=4000)

    first = book(client, passenger, offer_id=offer_id, seats=2)
    second = book(client, passenger, offer_id=offer_id, seats=1)
    third = book(client, passenger, offer_id=offer_id, seats=1)

    assert first.get_json()["booking"]["total_price"] == 8000
    assert second.status_code == 201
    assert third.status_code == 409
    with app.app_context():
        offer = db.session.get(RideOffer, offer_id)
        assert (offer.seats_available, offer.status) == (0, "full")


def test_private_ride_books_all_seats(app, client, make_offer, passenger):
    offer_id = make_offer(ride_type="private", seats=4, price=60000)

    # Asking for one seat still books the whole car, for the whole-car price.
    response = book(client, passenger, offer_id=offer_id, seats=1)
    second = book(client, passenger, offer_id=offer_id)

    booking = response.get_json()["booking"]
    assert booking["booking_type"] == "private"
    assert booking["seats_booked"] == 4
    assert booking["total_price"] == 60000
    assert second.status_code == 409
    with app.app_context():
        assert db.session.get(RideOffer, offer_id).status == "full"


def test_cancel_reopens_full_offer(app, client, make_offer, passenger):
    offer_id = make_offer(ride_type="private", seats=4)
    booking = book(client, passenger, offer_id=offer_id).get_json()["booking"]

    client.post(f"/api/bookings/{booking['booking_id']}/cancel", headers=passenger)

    with app.app_context():
        offer = db.session.get(RideOffer, offer_id)
        assert (offer.seats_available, offer.status) == (4, "open")


def test_two_people_booking_the_last_seat(app, make_trip, monkeypatch):
    """Two bookings for the last seat at the same moment: only one succeeds.

    Each booking holds its row lock a little longer than usual, so the two
    requests are sure to overlap. Without SELECT ... FOR UPDATE both would
    see one free seat and both would succeed.
    """
    if not is_postgres(app):
        pytest.skip("Row locks need PostgreSQL; SQLite has no SELECT ... FOR UPDATE.")

    trip_id = make_trip(seats=1)
    setup = app.test_client()
    tokens = [auth_header(register(setup)) for _ in range(2)]

    original = booking_service._locked

    def slow_locked(model, pk):
        row = original(model, pk)
        time.sleep(0.5)
        return row

    monkeypatch.setattr(booking_service, "_locked", slow_locked)

    start = threading.Barrier(2)
    statuses = []

    def attempt(headers):
        client = app.test_client()
        start.wait()
        response = book(client, headers, trip_id=trip_id)
        statuses.append(response.status_code)

    threads = [threading.Thread(target=attempt, args=(t,)) for t in tokens]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(statuses) == [201, 409]
    assert seats_left(app, BusTrip, trip_id) == 0
