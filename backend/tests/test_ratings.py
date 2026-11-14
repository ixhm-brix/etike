from conftest import auth_header, register

from app.extensions import db
from app.models import Booking, Driver, RideOffer


def passenger_account(client):
    response = register(client)
    return response.get_json()["user"]["user_id"], auth_header(response)


def ride_booking(app, make_offer, user_id, status="confirmed", hours_ahead=-3, bus_trip=None):
    """A booking made directly in the database, for a ride that has already
    left (bookings can't be made through the API after departure)."""
    with app.app_context():
        if bus_trip:
            booking = Booking(user_id=user_id, booking_type="bus", trip_id=bus_trip,
                              seats_booked=1, total_price=5000, status=status)
        else:
            offer_id = make_offer(hours_ahead=hours_ahead)
            booking = Booking(user_id=user_id, booking_type="shared", offer_id=offer_id,
                              seats_booked=1, total_price=4000, status=status)
        db.session.add(booking)
        db.session.commit()
        return booking.booking_id


def rate(client, headers, booking_id, score=5, comment=None):
    body = {"booking_id": booking_id, "score": score}
    if comment:
        body["comment"] = comment
    return client.post("/api/ratings", json=body, headers=headers)


def test_rating_updates_driver_average(app, client, make_offer):
    user_id, headers = passenger_account(client)
    booking_id = ride_booking(app, make_offer, user_id)

    response = rate(client, headers, booking_id, score=4, comment="On time, careful driver.")

    assert response.status_code == 201
    assert response.get_json()["driver_avg_rating"] == 4.0
    with app.app_context():
        driver_id = db.session.get(Booking, booking_id).offer.driver_id
    public = client.get(f"/api/drivers/{driver_id}/ratings").get_json()
    assert public["count"] == 1
    assert public["recent"][0]["comment"] == "On time, careful driver."


def test_average_over_several_ratings(app, client, make_offer):
    user_id, headers = passenger_account(client)
    first = ride_booking(app, make_offer, user_id)
    with app.app_context():
        offer = db.session.get(Booking, first).offer
        # A second booking on another ride by the same driver.
        second_offer = RideOffer(driver_id=offer.driver_id, vehicle_id=offer.vehicle_id,
                                 route_id=offer.route_id, ride_type="shared",
                                 departure_time=offer.departure_time, price=4000,
                                 seats_available=1, status="open")
        db.session.add(second_offer)
        db.session.flush()
        second = Booking(user_id=user_id, booking_type="shared",
                         offer_id=second_offer.offer_id, seats_booked=1, total_price=4000,
                         status="confirmed")
        db.session.add(second)
        db.session.commit()
        second_id, driver_id = second.booking_id, offer.driver_id

    rate(client, headers, first, score=5)
    rate(client, headers, second_id, score=2)

    with app.app_context():
        assert float(db.session.get(Driver, driver_id).avg_rating) == 3.5


def test_one_rating_per_booking(app, client, make_offer):
    user_id, headers = passenger_account(client)
    booking_id = ride_booking(app, make_offer, user_id)

    rate(client, headers, booking_id)
    again = rate(client, headers, booking_id, score=1)

    assert again.status_code == 409
    assert again.get_json()["error"]["code"] == "already_rated"


def test_score_must_be_1_to_5(app, client, make_offer):
    user_id, headers = passenger_account(client)
    booking_id = ride_booking(app, make_offer, user_id)

    for score in (0, 6, "five"):
        response = rate(client, headers, booking_id, score=score)
        assert response.status_code == 400


def test_only_own_bookings(app, client, make_offer):
    user_id, _ = passenger_account(client)
    booking_id = ride_booking(app, make_offer, user_id)
    _, stranger = passenger_account(client)

    assert rate(client, stranger, booking_id).status_code == 404


def test_only_after_departure(app, client, make_offer):
    user_id, headers = passenger_account(client)
    booking_id = ride_booking(app, make_offer, user_id, hours_ahead=5)

    response = rate(client, headers, booking_id)

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "not_departed"


def test_only_confirmed_rides(app, client, make_offer):
    user_id, headers = passenger_account(client)
    booking_id = ride_booking(app, make_offer, user_id, status="cancelled")

    assert rate(client, headers, booking_id).status_code == 409


def test_bus_trips_cannot_be_rated(app, client, make_trip):
    user_id, headers = passenger_account(client)
    booking_id = ride_booking(app, None, user_id, bus_trip=make_trip(hours_ahead=-3))

    assert rate(client, headers, booking_id).status_code == 400
