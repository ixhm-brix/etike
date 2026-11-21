"""Booking and cancelling seats without ever selling the same seat twice.

Each booking runs in one database transaction. The bus trip or ride offer
row is locked with SELECT ... FOR UPDATE before its seats are checked, so
when two people book the last seat at the same moment, the second request
waits for the first to finish and then sees that no seats are left.

Bus tickets are paid before travel: a new bus booking is "pending" and
holds its seats for BOOKING_HOLD_MINUTES while the passenger pays. Payment
confirms it; a failed payment or an expired hold cancels it and gives the
seats back.

Shared and private rides are paid to the driver during or after the ride,
so a ride booking is "confirmed" straight away.

A confirmed booking can be cancelled until CANCEL_CUTOFF_HOURS before
departure. Cancelling a paid bus ticket marks its payment as a refund due.

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
from . import seat_service, sms_service

log = logging.getLogger(__name__)

MAX_SEATS_PER_BOOKING = 10


def _locked(model, pk):
    """Load one row and lock it until the transaction ends."""
    return db.session.get(model, pk, with_for_update=True, populate_existing=True)


def book(user, trip_id=None, offer_id=None, seats=1, seat_numbers=None):
    """Book seats on a bus trip (pending until paid) or a ride (confirmed).

    `seat_numbers` are the seats chosen on the seat map; without them the
    lowest free seats are given.
    """
    if (trip_id is None) == (offer_id is None):
        raise bad_request("Send either trip_id or offer_id.")
    if seat_numbers is not None:
        seat_numbers = _check_seat_numbers(seat_numbers)
        seats = len(seat_numbers)

    release_expired()
    try:
        if trip_id is not None:
            booking = _book_bus(user, trip_id, seats, seat_numbers)
            booking.status = "pending"
            booking.expires_at = utcnow() + timedelta(
                minutes=current_app.config["BOOKING_HOLD_MINUTES"]
            )
        else:
            booking = _book_ride(user, offer_id, seats, seat_numbers)
            # Paid to the driver, so there is nothing to wait for.
            booking.status = "confirmed"
        db.session.add(booking)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    if booking.status == "confirmed":
        # After the commit, so an SMS problem can never undo the booking.
        sms_service.booking_confirmed(booking)
    return booking


def _book_bus(user, trip_id, seats, wanted=None):
    _check_seat_count(seats)
    trip = _locked(BusTrip, trip_id)
    # Trips from companies we have not verified are not for sale.
    if trip is None or not trip.company.is_verified:
        raise not_found("Bus trip not found.")
    if trip.departure_time <= local_now():
        raise conflict("This bus has already left.", "departed")
    if trip.available_seats < seats:
        raise _not_enough_seats(trip.available_seats)
    numbers = seat_service.pick(trip.total_seats, seat_service.taken(trip_id=trip.trip_id),
                                seats, wanted)
    if numbers is None:
        raise _not_enough_seats(trip.available_seats)

    trip.available_seats -= seats
    booking = Booking(
        user_id=user.user_id,
        booking_type="bus",
        trip_id=trip.trip_id,
        seats_booked=seats,
        total_price=trip.price_rwf * seats,
    )
    seat_service.hold(booking, numbers, trip_id=trip.trip_id)
    return booking


def _book_ride(user, offer_id, seats, wanted=None):
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
        wanted = None  # the whole car: every seat on offer
    else:
        _check_seat_count(seats)
        if offer.status != "open" or offer.seats_available < seats:
            raise _not_enough_seats(offer.seats_available if offer.status == "open" else 0)
        total = offer.price * seats
    numbers = seat_service.pick(offer.vehicle.seats, _ride_held(offer), seats, wanted)
    if numbers is None:
        raise _not_enough_seats(offer.seats_available)

    _take_ride_seats(offer, seats)
    booking = Booking(
        user_id=user.user_id,
        booking_type=offer.ride_type,
        offer_id=offer.offer_id,
        seats_booked=seats,
        total_price=total,
    )
    seat_service.hold(booking, numbers, offer_id=offer.offer_id)
    return booking


def _ride_held(offer):
    """Seats a passenger can't have: booked ones, and any the driver did not
    offer (a driver can offer fewer seats than the car has; those are the
    highest numbers)."""
    held = set(seat_service.taken(offer_id=offer.offer_id))
    booked = len(held)
    not_offered = offer.vehicle.seats - (offer.seats_available + booked)
    held.update(range(offer.vehicle.seats - not_offered + 1, offer.vehicle.seats + 1))
    return sorted(held)


def cancel(user, booking_id):
    """Cancel the user's own booking and give its seats back.

    An unpaid booking can always be cancelled. A confirmed one can be
    cancelled until the cut-off before departure; if it was paid, its
    payment is marked as a refund due.
    """
    was_confirmed = False
    try:
        booking = _locked(Booking, booking_id)
        # Someone else's booking looks the same as a missing one.
        if booking is None or booking.user_id != user.user_id:
            raise not_found("Booking not found.")
        if booking.status == "cancelled":
            raise conflict("This booking is already cancelled.", "already_cancelled")
        if booking.offer is not None and booking.offer.started_at is not None:
            raise conflict("This ride has already started, so it can't be cancelled.",
                           "ride_started")
        if booking.payment and booking.payment.status == "pending":
            raise conflict(
                "A payment for this booking is in progress. Wait for it to finish.",
                "payment_in_progress",
            )
        if booking.status == "confirmed":
            was_confirmed = True
            if local_now() >= booking.cancel_until:
                hours = current_app.config["CANCEL_CUTOFF_HOURS"]
                raise conflict(
                    f"It's too late to cancel: bookings can be cancelled until {hours:g} "
                    "hours before departure.",
                    "too_late_to_cancel",
                )
            if booking.payment and booking.payment.status == "success":
                booking.payment.refund_status = "due"
        release(booking)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    if was_confirmed:
        sms_service.booking_cancelled(booking)
    return booking


def release(booking):
    """Cancel a booking and return its seats. The caller commits."""
    seat_service.free(booking)
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

    is_bus = booking.trip_id is not None
    target = _locked(BusTrip, booking.trip_id) if is_bus else _locked(RideOffer, booking.offer_id)
    free = target.available_seats if is_bus else (
        target.seats_available if target.status != "cancelled" else 0)
    if free >= booking.seats_booked and target.departure_time > local_now():
        total = target.total_seats if is_bus else target.vehicle.seats
        held = (seat_service.taken(trip_id=target.trip_id) if is_bus
                else _ride_held(target))
        # The same seats if they are still free, otherwise any free seats.
        old = [int(n) for n in (booking.seat_numbers or "").split(",") if n]
        numbers = old if old and not set(old) & set(held) else seat_service.pick(
            total, held, booking.seats_booked)
        if numbers:
            if is_bus:
                target.available_seats -= booking.seats_booked
                seat_service.hold(booking, numbers, trip_id=target.trip_id)
            else:
                _take_ride_seats(target, booking.seats_booked)
                seat_service.hold(booking, numbers, offer_id=target.offer_id)
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


def _check_seat_numbers(numbers):
    if (not isinstance(numbers, list) or not numbers
            or not all(isinstance(n, int) and not isinstance(n, bool) for n in numbers)):
        raise bad_request("Choose your seats on the seat map.",
                          {"seat_numbers": "Must be a list of seat numbers."})
    if len(set(numbers)) != len(numbers):
        raise bad_request("Each seat can only be chosen once.",
                          {"seat_numbers": "Seat numbers must be different."})
    _check_seat_count(len(numbers))
    return numbers


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
