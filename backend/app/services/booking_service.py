"""Booking and cancelling seats without ever selling the same seat twice.

Each booking runs in one database transaction. The bus trip or ride offer
row is locked with SELECT ... FOR UPDATE before its seats are checked, so
when two people book the last seat at the same moment, the second request
waits for the first to finish and then sees that no seats are left.

A new booking is "pending": it holds its seats for BOOKING_HOLD_MINUTES
while the passenger pays. Payment confirms it; a failed payment or an
expired hold cancels it and gives the seats back.

Prices are always calculated here from the database, never taken from the
client.
"""

import logging
from datetime import timedelta

from flask import current_app

from ..errors import ApiError, bad_request, conflict, not_found
from ..extensions import db
from ..models import Booking, BusTrip, RideOffer
from ..models.user import utcnow
from ..validation import local_now

log = logging.getLogger(__name__)

MAX_SEATS_PER_BOOKING = 10


def _locked(model, pk):
    """Load one row and lock it until the transaction ends."""
    return db.session.get(model, pk, with_for_update=True, populate_existing=True)


def book(user, trip_id=None, offer_id=None, seats=1):
    """Hold seats on a bus trip or a ride offer. Returns the pending Booking."""
    if (trip_id is None) == (offer_id is None):
        raise bad_request("Send either trip_id or offer_id.")

    release_expired()
    try:
        if trip_id is not None:
            booking = _book_bus(user, trip_id, seats)
        else:
            booking = _book_ride(user, offer_id, seats)
        booking.status = "pending"
        booking.expires_at = utcnow() + timedelta(
            minutes=current_app.config["BOOKING_HOLD_MINUTES"]
        )
        db.session.add(booking)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return booking


def _book_bus(user, trip_id, seats):
    _check_seat_count(seats)
    trip = _locked(BusTrip, trip_id)
    # Trips from companies we have not verified are not for sale.
    if trip is None or not trip.company.is_verified:
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
    )


def _book_ride(user, offer_id, seats):
    offer = _locked(RideOffer, offer_id)
    # Nor are rides from drivers who are not (or no longer) approved.
    if offer is None or not offer.driver.is_approved:
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

    _take_ride_seats(offer, seats)
    return Booking(
        user_id=user.user_id,
        booking_type=offer.ride_type,
        offer_id=offer.offer_id,
        seats_booked=seats,
        total_price=total,
    )


def cancel(user, booking_id):
    """Cancel the user's own unpaid booking and give its seats back."""
    try:
        booking = _locked(Booking, booking_id)
        # Someone else's booking looks the same as a missing one.
        if booking is None or booking.user_id != user.user_id:
            raise not_found("Booking not found.")
        if booking.status == "cancelled":
            raise conflict("This booking is already cancelled.", "already_cancelled")
        if booking.status == "confirmed":
            # Refunds are not built yet, so a paid booking stays as it is.
            raise conflict(
                "Paid bookings can't be cancelled online yet.", "paid_booking"
            )
        if booking.payment and booking.payment.status == "pending":
            raise conflict(
                "A payment for this booking is in progress. Wait for it to finish.",
                "payment_in_progress",
            )
        release(booking)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return booking


def release(booking):
    """Cancel a booking and return its seats. The caller commits."""
    if booking.trip_id is not None:
        trip = _locked(BusTrip, booking.trip_id)
        trip.available_seats += booking.seats_booked
    else:
        offer = _locked(RideOffer, booking.offer_id)
        offer.seats_available += booking.seats_booked
        if offer.status == "full":
            offer.status = "open"
    booking.status = "cancelled"


def confirm(booking):
    """Mark a paid booking confirmed. The caller holds the booking lock and commits.

    Returns True if the booking is confirmed. A payment can arrive after the
    hold expired and the seats went back; then we take them again if they
    are still free. If not, the booking stays cancelled and is logged so the
    payment can be refunded by hand.
    """
    if booking.status == "confirmed":
        return True
    if booking.status == "pending":
        booking.status = "confirmed"
        return True

    target = (_locked(BusTrip, booking.trip_id) if booking.trip_id is not None
              else _locked(RideOffer, booking.offer_id))
    free = target.available_seats if booking.trip_id is not None else (
        target.seats_available if target.status != "cancelled" else 0)
    if free >= booking.seats_booked and target.departure_time > local_now():
        if booking.trip_id is not None:
            target.available_seats -= booking.seats_booked
        else:
            _take_ride_seats(target, booking.seats_booked)
        booking.status = "confirmed"
        return True

    log.error("Booking %s was paid after its seats were released; refund needed.",
              booking.booking_id)
    return False


def release_expired():
    """Cancel pending bookings whose hold ran out, and return their seats.

    Runs before searches and bookings, and from `flask expire-bookings`.
    Returns how many bookings were released.
    """
    now = utcnow()
    ids = [
        row[0]
        for row in db.session.query(Booking.booking_id)
        .filter(Booking.status == "pending", Booking.expires_at < now)
        .all()
    ]
    released = 0
    for booking_id in ids:
        try:
            booking = _locked(Booking, booking_id)
            # Another request may have settled it since the query above.
            if booking.status == "pending" and _as_utc(booking.expires_at) < now:
                release(booking)
                released += 1
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
    return released


def _take_ride_seats(offer, seats):
    offer.seats_available -= seats
    if offer.seats_available == 0:
        offer.status = "full"


def _as_utc(dt):
    # SQLite gives times back without a time zone; they are stored as UTC.
    return dt if dt.tzinfo else dt.replace(tzinfo=utcnow().tzinfo)


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
