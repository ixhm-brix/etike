from flask import Blueprint, jsonify

from .. import validation as v
from ..auth import current_user, role_required
from ..extensions import db
from ..models import Booking
from ..services import booking_service

bookings_bp = Blueprint("bookings", __name__)


@bookings_bp.post("/bookings")
@role_required("passenger")
def create_booking():
    data = v.json_body()
    # Any price the client sends is ignored; the service works it out.
    trip_id = v.integer(data, "trip_id", minimum=1) if data.get("trip_id") is not None else None
    offer_id = v.integer(data, "offer_id", minimum=1) if data.get("offer_id") is not None else None
    booking = booking_service.book(
        current_user(), trip_id=trip_id, offer_id=offer_id, seats=data.get("seats", 1)
    )
    return jsonify({"booking": booking.to_dict()}), 201


@bookings_bp.get("/bookings/mine")
@role_required()
def my_bookings():
    bookings = (
        db.session.query(Booking)
        .filter_by(user_id=current_user().user_id)
        .order_by(Booking.created_at.desc())
        .all()
    )
    return jsonify({"bookings": [b.to_dict() for b in bookings]})


@bookings_bp.post("/bookings/<int:booking_id>/cancel")
@role_required()
def cancel_booking(booking_id):
    booking = booking_service.cancel(current_user(), booking_id)
    return jsonify({"booking": booking.to_dict()})
