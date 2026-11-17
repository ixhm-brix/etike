"""Seat numbers and seat maps.

Every bus trip and ride has seats numbered 1..N. A booking holds specific
seat numbers in booking_seats, whose unique constraints make it impossible
for two bookings to hold the same seat on the same trip or ride.

Seat maps are drawn from the number of seats only; we don't know each
vehicle's real layout, so the map is a close approximation:
  - bus (or any vehicle with more than 8 seats): driver at the front, then
    rows of 2 + aisle + 2, and a back row of up to 5
  - car: driver and one passenger in front, then rows of up to 3
"""

from ..errors import ApiError, bad_request
from ..extensions import db
from ..models import BookingSeat

DRIVER = "driver"
AISLE = None


def layout(total, kind):
    """Rows of cells for drawing: a seat number, "driver", or None (gap)."""
    numbers = list(range(1, total + 1))
    if kind == "bus" or total > 8:
        rows = [[DRIVER, AISLE, AISLE, AISLE, AISLE]]
        while numbers:
            if len(numbers) <= 5 and len(numbers) != 4:
                # Back row: one bench across the bus.
                rows.append(numbers + [AISLE] * (5 - len(numbers)))
                break
            left, right, numbers = numbers[:2], numbers[2:4], numbers[4:]
            rows.append(left + [AISLE] + right + [AISLE] * (2 - len(right)))
        return rows
    rows = [[DRIVER, numbers.pop(0)]] if numbers else [[DRIVER, AISLE]]
    while numbers:
        rows.append(numbers[:3])
        numbers = numbers[3:]
    return rows


def taken(trip_id=None, offer_id=None):
    """Seat numbers held by bookings on this trip or ride."""
    query = db.session.query(BookingSeat.seat_number)
    query = query.filter_by(trip_id=trip_id) if trip_id else query.filter_by(offer_id=offer_id)
    return sorted(row[0] for row in query)


def pick(total, held, count, wanted=None):
    """Choose seat numbers for a booking.

    `wanted` is the list the passenger chose on the map; without it the
    lowest free seats are used. Raises a 409 naming any seat already taken.
    """
    free = [n for n in range(1, total + 1) if n not in set(held)]
    if wanted is None:
        if len(free) < count:
            return None
        return free[:count]
    if any(n < 1 or n > total for n in wanted):
        raise bad_request(f"Seat numbers go from 1 to {total}.",
                          {"seat_numbers": f"Must be between 1 and {total}."})
    gone = [n for n in wanted if n in set(held)]
    if gone:
        word = "Seat" if len(gone) == 1 else "Seats"
        raise ApiError(409, "seats_taken",
                       f"{word} {', '.join(map(str, gone))} {'was' if len(gone) == 1 else 'were'} "
                       "just taken. Please choose another.")
    return sorted(wanted)


def hold(booking, numbers, trip_id=None, offer_id=None):
    """Record the booking's seats. The caller commits."""
    booking.seat_numbers = ",".join(map(str, numbers))
    for n in numbers:
        db.session.add(BookingSeat(booking=booking, trip_id=trip_id, offer_id=offer_id,
                                   seat_number=n))


def free(booking):
    """Give the booking's seats back (the record of which seats stays)."""
    db.session.query(BookingSeat).filter_by(booking_id=booking.booking_id).delete(
        synchronize_session=False)
