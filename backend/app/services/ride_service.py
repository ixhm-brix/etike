"""A ride from the driver's side, like a taxi app: the driver taps Start ride
when they set off and End ride when they arrive. Once a ride has ended,
its passengers pay with MTN MoMo (payment_service), and the driver sees
each payment come in.

With the driver's permission, their phone also records where the ride
started and ended and, while it is on, where the car is about every half
minute. The driver, the ride's passengers and admins can see that trip
record on a map.
"""

import math
from datetime import timedelta

from ..errors import bad_request, conflict, not_found
from ..extensions import db
from ..models import Booking, RideLocation, RideOffer
from ..models.user import utcnow
from ..validation import local_now
from . import message_service, sms_service

# Positions must be in or near Rwanda (a margin for GPS drift at borders).
LAT_RANGE = (-3.2, -0.7)
LNG_RANGE = (28.6, 31.2)
MAX_ACCURACY_M = 1000      # vaguer than this is no use on a map
MIN_GAP = timedelta(seconds=15)  # the phone sends about every 30 s; ignore floods
MAX_POINTS = 2000          # about 16 hours at one point every 30 s

# A driver can start a ride from this long before its departure time.
START_EARLY = timedelta(hours=1)
# The driver's list shows rides from this far back (to follow payments).
RECENT = timedelta(days=2)


def driver_rides(driver):
    """The driver's rides from the last two days onwards, soonest first,
    each with its passengers and what they have paid."""
    offers = (
        db.session.query(RideOffer)
        .filter(RideOffer.driver_id == driver.driver_id,
                RideOffer.departure_time >= local_now() - RECENT,
                RideOffer.status != "cancelled")
        .order_by(RideOffer.departure_time)
        .limit(40)
        .all()
    )
    return [ride_dict(o) for o in offers]


def ride_dict(offer):
    bookings = _confirmed(offer)
    unread = message_service.unread_for_driver(offer.driver.user, bookings)
    passengers = [
        {
            "booking_id": b.booking_id,
            "name": b.user.full_name,
            "seats": b.seats_booked,
            "amount": b.total_price,
            "payment_status": b.payment.status if b.payment else None,
            # Only between the two people on this ride, and only for a while.
            "phone": b.user.phone if b.contact_open else None,
            "unread": unread.get(b.booking_id, 0),
        }
        for b in bookings
    ]
    return {
        **offer.to_dict(),
        "started_at": offer.started_at.isoformat() if offer.started_at else None,
        "ended_at": offer.ended_at.isoformat() if offer.ended_at else None,
        "passengers": passengers,
        "paid": sum(p["amount"] for p in passengers if p["payment_status"] == "success"),
        "to_collect": sum(p["amount"] for p in passengers),
    }


def location_from(data):
    """A position sent by the driver's phone ({lat, lng, accuracy}), or None
    when the driver didn't share one (the ride works without)."""
    if not isinstance(data, dict) or data.get("lat") is None or data.get("lng") is None:
        return None
    try:
        lat, lng = float(data["lat"]), float(data["lng"])
        accuracy = data.get("accuracy")
        accuracy = None if accuracy is None else round(float(accuracy))
    except (TypeError, ValueError):
        raise bad_request("The location must be numbers.", {"lat": "Must be a number."}) from None
    if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LNG_RANGE[0] <= lng <= LNG_RANGE[1]):
        raise bad_request("This location is not in Rwanda.", {"lat": "Must be in Rwanda."})
    if accuracy is not None and not 0 <= accuracy <= MAX_ACCURACY_M:
        raise bad_request("This location is too vague to record.",
                          {"accuracy": f"Must be at most {MAX_ACCURACY_M} m."})
    return lat, lng, accuracy


def _save(offer, kind, location):
    lat, lng, accuracy = location
    db.session.add(RideLocation(offer_id=offer.offer_id, kind=kind, lat=lat, lng=lng,
                                accuracy_m=accuracy))


def record(driver, offer_id, location):
    """A position while the ride is on. Returns False when it was skipped
    (too soon after the last one, or the ride has enough points)."""
    offer = _own(driver, offer_id)
    if offer.progress != "in_progress":
        raise conflict("Positions are only recorded while the ride is on.", "ride_not_on")
    last = (db.session.query(RideLocation).filter_by(offer_id=offer.offer_id)
            .order_by(RideLocation.location_id.desc()).first())
    count = db.session.query(RideLocation).filter_by(offer_id=offer.offer_id).count()
    if (last and utcnow() - _as_utc(last.recorded_at) < MIN_GAP) or count >= MAX_POINTS:
        return False
    _save(offer, "track", location)
    db.session.commit()
    return True


def trip_record(user, offer_id):
    """The recorded trip: its points in order, when and where it started and
    ended, and the distance driven. For the ride's driver, its passengers
    and admins only."""
    offer = db.session.get(RideOffer, offer_id)
    allowed = offer is not None and (
        user.role == "admin"
        or (user.driver is not None and offer.driver_id == user.driver.driver_id)
        or db.session.query(Booking.booking_id).filter_by(
            offer_id=offer_id, user_id=user.user_id, status="confirmed").first()
    )
    if not allowed:
        raise not_found("Ride not found.")
    points = (db.session.query(RideLocation).filter_by(offer_id=offer_id)
              .order_by(RideLocation.recorded_at, RideLocation.location_id).all())
    usable = [p for p in points if p.accuracy_m is None or p.accuracy_m <= 150]
    km = sum(_km(a, b) for a, b in zip(usable, usable[1:], strict=False))  # pairs in a row
    return {
        "ride": offer.to_dict(),
        "started_at": offer.started_at.isoformat() if offer.started_at else None,
        "ended_at": offer.ended_at.isoformat() if offer.ended_at else None,
        "points": [p.to_dict() for p in points],
        "distance_km": round(km, 1),
    }


def _km(a, b):
    """Straight-line distance between two points (they are close together)."""
    la1, lo1, la2, lo2 = map(math.radians, (a.lat, a.lng, b.lat, b.lng))
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(h))


def _as_utc(dt):
    # SQLite gives times back without a time zone; they are stored as UTC.
    return dt if dt.tzinfo else dt.replace(tzinfo=utcnow().tzinfo)


def start(driver, offer_id, location=None):
    offer = _own(driver, offer_id)
    if offer.started_at:
        raise conflict("This ride has already started.", "already_started")
    if offer.status == "cancelled":
        raise conflict("This ride was cancelled.", "ride_cancelled")
    if local_now() < offer.departure_time - START_EARLY:
        raise conflict("You can start this ride from one hour before departure.",
                       "too_early")
    if not _confirmed(offer):
        raise conflict("Nobody has booked this ride, so there is no trip to start.",
                       "no_passengers")
    offer.started_at = utcnow()
    if location:
        _save(offer, "start", location)
    db.session.commit()
    return offer


def end(driver, offer_id, location=None):
    offer = _own(driver, offer_id)
    if not offer.started_at:
        raise conflict("Start the ride first.", "not_started")
    if offer.ended_at:
        raise conflict("This ride has already ended.", "already_ended")
    offer.ended_at = utcnow()
    if location:
        _save(offer, "end", location)
    db.session.commit()
    for booking in _confirmed(offer):
        sms_service.ride_ended(booking)
    return offer


def _own(driver, offer_id):
    offer = db.session.get(RideOffer, offer_id)
    # Another driver's ride looks the same as a missing one.
    if offer is None or offer.driver_id != driver.driver_id:
        raise not_found("Ride not found.")
    return offer


def _confirmed(offer):
    return (db.session.query(Booking)
            .filter_by(offer_id=offer.offer_id, status="confirmed")
            .order_by(Booking.booking_id).all())
