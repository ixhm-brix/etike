"""A ride from the driver's side, like a taxi app: the driver taps Start ride
when they set off and End ride when they arrive. Once a ride has ended,
its passengers pay with MTN MoMo (payment_service), and the driver sees
each payment come in.
"""

from datetime import timedelta

from ..errors import conflict, not_found
from ..extensions import db
from ..models import Booking, RideOffer
from ..models.user import utcnow
from ..validation import local_now
from . import sms_service

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
    passengers = [
        {
            "booking_id": b.booking_id,
            "name": b.user.full_name,
            "seats": b.seats_booked,
            "amount": b.total_price,
            "payment_status": b.payment.status if b.payment else None,
        }
        for b in _confirmed(offer)
    ]
    return {
        **offer.to_dict(),
        "started_at": offer.started_at.isoformat() if offer.started_at else None,
        "ended_at": offer.ended_at.isoformat() if offer.ended_at else None,
        "passengers": passengers,
        "paid": sum(p["amount"] for p in passengers if p["payment_status"] == "success"),
        "to_collect": sum(p["amount"] for p in passengers),
    }


def start(driver, offer_id):
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
    db.session.commit()
    return offer


def end(driver, offer_id):
    offer = _own(driver, offer_id)
    if not offer.started_at:
        raise conflict("Start the ride first.", "not_started")
    if offer.ended_at:
        raise conflict("This ride has already ended.", "already_ended")
    offer.ended_at = utcnow()
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
