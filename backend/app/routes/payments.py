import hmac
import logging

from flask import Blueprint, current_app, jsonify, request

from .. import validation as v
from ..auth import current_user, role_required
from ..errors import ApiError, bad_request, not_found
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
    # Pay from any Rwandan mobile money number; defaults to the account's.
    phone = v.phone(data["phone"]) if data.get("phone") else current_user().phone
    email = v.text(data, "email", min_len=3, max_len=255, required=False)
    if email and "@" not in email:
        raise bad_request("Enter a valid email address.", {"email": "Not a valid email address."})
    payment = payment_service.start(current_user(), booking_id, phone, email)
    return jsonify({"payment": payment.to_dict()}), 201


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
    })


@payments_bp.post("/payments/webhook")
def flutterwave_webhook():
    """Called by Flutterwave when a charge finishes.

    Flutterwave sends the secret hash from our dashboard in the verif-hash
    header. Even when it matches, we don't trust the body: we only take the
    tx_ref from it and verify the transaction with Flutterwave's API.
    """
    secret_hash = current_app.config.get("FLW_SECRET_HASH")
    if not secret_hash:
        raise ApiError(503, "payments_unavailable", "Webhooks are not configured.")
    received = request.headers.get("verif-hash", "")
    if not hmac.compare_digest(received.encode(), secret_hash.encode()):
        raise ApiError(401, "unauthorized", "Invalid webhook signature.")

    body = request.get_json(silent=True) or {}
    data = body.get("data") or {}
    payment = payment_service.find_by_reference(data.get("tx_ref") or body.get("txRef"))
    if payment is None:
        # Not ours (or not a charge). Answer 200 so Flutterwave stops retrying.
        log.info("Webhook for an unknown tx_ref ignored.")
        return jsonify({"status": "ignored"})
    payment = payment_service.check(payment)
    return jsonify({"status": payment.status})
