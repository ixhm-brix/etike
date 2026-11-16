import logging

from flask import Blueprint, current_app, jsonify, request

from .. import validation as v
from ..auth import current_user, role_required
from ..errors import not_found
from ..extensions import db
from ..models import Booking
from ..services import payment_service

log = logging.getLogger(__name__)

payments_bp = Blueprint("payments", __name__)


@payments_bp.post("/payments")
@role_required("passenger")
def start_payment():
    data = v.json_body()
    booking_id = v.integer(data, "booking_id", minimum=1)
    # Pay from any MTN MoMo number; defaults to the account's number.
    sandbox = current_app.config["MOMO_TARGET_ENVIRONMENT"] == "sandbox"
    phone = v.momo_phone(data.get("phone") or current_user().phone, sandbox=sandbox)
    payment = payment_service.start(current_user(), booking_id, phone)
    return jsonify({"payment": payment.to_dict(), "provider": payment_service.provider_info()}), 201


@payments_bp.get("/payments/<int:booking_id>/status")
@role_required()
def payment_status(booking_id):
    booking = db.session.get(Booking, booking_id)
    if booking is None or booking.user_id != current_user().user_id:
        raise not_found("Booking not found.")
    if booking.payment is not None:
        payment_service.check(booking.payment)
        db.session.refresh(booking)
    return jsonify({
        "booking": booking.to_dict(),
        "payment": booking.payment.to_dict() if booking.payment else None,
        "provider": payment_service.provider_info(),
    })


@payments_bp.route("/payments/callback", methods=["POST", "PUT"])
def momo_callback():
    """Called by MoMo when a request to pay finishes.

    Anyone can reach this address, so nothing in the request is trusted: we
    only use it to find which payment to look at, then ask MoMo for the real
    status. Receiving the same callback twice changes nothing.
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        body = {}
    payment = payment_service.find_for_callback(
        reference=request.headers.get("X-Reference-Id") or body.get("referenceId"),
        external_id=body.get("externalId"),
    )
    if payment is None:
        # Not ours. Answer 200 so MoMo doesn't keep retrying.
        log.info("MoMo callback for an unknown payment ignored.")
        return jsonify({"status": "ignored"})
    payment = payment_service.check(payment)
    return jsonify({"status": payment.status})
