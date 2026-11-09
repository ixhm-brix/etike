"""Booking and cancelling seats without ever selling the same seat twice.

Each booking runs in one database transaction. The bus trip or ride offer
row is locked with SELECT ... FOR UPDATE before its seats are checked, so
when two people book the last seat at the same moment, the second request
waits for the first to finish and then sees that no seats are left.

Prices are always calculated here from the database, never taken from the
client.
"""

from ..errors import ApiError, bad_request, conflict, not_found
from ..extensions import db
from ..models import Booking, BusTrip, RideOffer
from ..validation import local_now

MAX_SEATS_PER_BOOKING = 10


def _locked(model, pk):
    """Load one row and lock it until the transaction ends."""
    return db.session.get(model, pk, with_for_update=True, populate_existing=True)


def book(user, trip_id=None, offer_id=None, seats=1):
    """Book seats on a bus trip or a ride offer. Returns the confirmed Booking."""
    if (trip_id is None) == (offer_id is None):
        raise bad_request("Send either trip_id or offer_id.")

    try:
        if trip_id is not None:
            booking = _book_bus(user, trip_id, seats)
        else:
            booking = _book_ride(user, offer_id, seats)
        db.session.add(booking)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return booking


def _book_bus(user, trip_id, seats):
    _check_seat_count(seats)
    trip = _locked(BusTrip, trip_id)
    if trip is None:
        raise not_found("Bus trip not found.")
    if trip.departure_time <= local_now():
        raise conflict("This bus has already left.", "departed")
    if trip.available_seats < seats:
        raise _not_enough_seats(trip.available_seats)

    trip.available_seats -= seats
    return Booking(
        user_id=user.user_id,
        booking_type="bus",
        trip_id=trip.trip_id,
        seats_booked=seats,
        total_price=trip.price_rwf * seats,
        # Payments arrive in Sprint 3; until then a booking is confirmed at once.
        status="confirmed",
    )


def _book_ride(user, offer_id, seats):
    offer = _locked(RideOffer, offer_id)
    if offer is None:
        raise not_found("Ride not found.")
    if offer.departure_time <= local_now():
        raise conflict("This ride has already left.", "departed")
    if offer.status == "cancelled":
        raise conflict("The driver cancelled this ride.", "ride_cancelled")

    if offer.ride_type == "private":
        # A private ride is the whole car for one price, booked all at once.
        if offer.status != "open" or offer.seats_available == 0:
            raise conflict("Someone just booked this car.", "seats_taken")
        seats = offer.seats_available
        total = offer.price
    else:
        _check_seat_count(seats)
        if offer.status != "open" or offer.seats_available < seats:
            raise _not_enough_seats(offer.seats_available if offer.status == "open" else 0)
        total = offer.price * seats

    offer.seats_available -= seats
    if offer.seats_available == 0:
        offer.status = "full"
    return Booking(
        user_id=user.user_id,
        booking_type=offer.ride_type,
        offer_id=offer.offer_id,
        seats_booked=seats,
        total_price=total,
        status="confirmed",
    )


def cancel(user, booking_id):
    """Cancel the user's booking and give its seats back."""
    try:
        booking = _locked(Booking, booking_id)
        # Someone else's booking looks the same as a missing one.
        if booking is None or booking.user_id != user.user_id:
            raise not_found("Booking not found.")
        if booking.status == "cancelled":
            raise conflict("This booking is already cancelled.", "already_cancelled")

        if booking.trip_id is not None:
            target = _locked(BusTrip, booking.trip_id)
            if target.departure_time <= local_now():
                raise conflict("This bus has already left, so it can't be cancelled.", "departed")
            target.available_seats += booking.seats_booked
        else:
            target = _locked(RideOffer, booking.offer_id)
            if target.departure_time <= local_now():
                raise conflict("This ride has already left, so it can't be cancelled.", "departed")
            target.seats_available += booking.seats_booked
            if target.status == "full":
                target.status = "open"

        booking.status = "cancelled"
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return booking


def _check_seat_count(seats):
    if isinstance(seats, bool) or not isinstance(seats, int):
        raise bad_request("seats must be a whole number.", {"seats": "Must be a whole number."})
    if not 1 <= seats <= MAX_SEATS_PER_BOOKING:
        msg = f"Must be between 1 and {MAX_SEATS_PER_BOOKING}."
        raise bad_request(f"seats: {msg}", {"seats": msg})


def _not_enough_seats(left):
    if left == 0:
        return ApiError(409, "seats_taken", "Sorry, the last seat was just taken.")
    seat_word = "seat is" if left == 1 else "seats are"
    return ApiError(409, "not_enough_seats", f"Only {left} {seat_word} left.")
