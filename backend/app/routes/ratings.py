from flask import Blueprint, jsonify
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from .. import validation as v
from ..auth import current_user, role_required
from ..errors import bad_request, conflict, not_found
from ..extensions import db
from ..models import Booking, Driver, Rating, RideOffer

ratings_bp = Blueprint("ratings", __name__)


@ratings_bp.post("/ratings")
@role_required("passenger")
def rate_driver():
    data = v.json_body()
    booking = db.session.get(Booking, v.integer(data, "booking_id", minimum=1))
    if booking is None or booking.user_id != current_user().user_id:
        raise not_found("Booking not found.")
    if booking.offer_id is None:
        raise bad_request("Only shared and private rides can be rated, not bus trips.")
    if booking.status != "confirmed":
        raise conflict("Only paid, confirmed rides can be rated.", "not_confirmed")
    if booking.offer.departure_time > v.local_now():
        raise conflict("You can rate this ride after it has left.", "not_departed")
    if booking.rating is not None:
        raise conflict("You have already rated this ride.", "already_rated")

    rating = Rating(
        booking_id=booking.booking_id,
        score=v.integer(data, "score", minimum=1, maximum=5),
        comment=v.text(data, "comment", min_len=1, max_len=500, required=False),
    )
    db.session.add(rating)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        raise conflict("You have already rated this ride.", "already_rated") from None

    # Recalculate the driver's average from all their ratings.
    driver = booking.offer.driver
    average = (
        db.session.query(func.avg(Rating.score))
        .join(Booking, Rating.booking_id == Booking.booking_id)
        .join(RideOffer, Booking.offer_id == RideOffer.offer_id)
        .filter(RideOffer.driver_id == driver.driver_id)
        .scalar()
    )
    driver.avg_rating = round(float(average), 1)
    db.session.commit()
    return jsonify({"rating": rating.to_dict(), "driver_avg_rating": float(driver.avg_rating)}), 201


@ratings_bp.get("/drivers/<int:driver_id>/ratings")
def driver_ratings(driver_id):
    driver = db.session.get(Driver, driver_id)
    if driver is None or not driver.is_approved:
        raise not_found("Driver not found.")
    query = (
        db.session.query(Rating)
        .join(Booking, Rating.booking_id == Booking.booking_id)
        .join(RideOffer, Booking.offer_id == RideOffer.offer_id)
        .filter(RideOffer.driver_id == driver_id)
    )
    recent = query.order_by(Rating.created_at.desc()).limit(10).all()
    return jsonify({
        "driver_id": driver_id,
        "driver_name": driver.user.full_name,
        "avg_rating": float(driver.avg_rating) if driver.avg_rating is not None else None,
        "count": query.count(),
        "recent": [r.to_dict() for r in recent],
    })
