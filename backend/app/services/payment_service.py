"""Paying for a booking with Rwanda mobile money through Flutterwave.

1. start(): the passenger asks to pay their pending booking. We save a
   pending payment with a unique tx_ref and ask Flutterwave to start a
   charge. The amount always comes from the booking, never from the client.
2. The passenger approves on the Flutterwave page we send them to.
3. check() asks Flutterwave how it went (verify by tx_ref). It runs when
   the payment page polls, and when Flutterwave's webhook arrives. We never
   trust a webhook's body: it only tells us which payment to check.
4. Before confirming we compare tx_ref, currency and amount with ours.
5. settle() applies the answer once. Calling it again changes nothing, so
   a webhook that arrives twice is harmless.
"""

import logging
import uuid

from flask import current_app
from sqlalchemy.exc import IntegrityError

from ..errors import ApiError, bad_request, conflict, not_found
from ..extensions import db
from ..models import Booking, Payment
from . import booking_service, flutterwave_client, sms_service

log = logging.getLogger(__name__)


def get_payment_client():
    """Separate function so tests can swap in a fake client."""
    return flutterwave_client.get_client()


def _require_client():
    client = get_payment_client()
    if client is None:
        raise ApiError(
            503,
            "payments_unavailable",
            "Mobile money payments are not available right now. Your seats stay "
            "held until the booking expires.",
        )
    return client


def start(user, booking_id, phone, email=None):
    """Start paying for the user's pending booking. Returns the Payment."""
    client = _require_client()
    booking_service.release_expired()

    booking = db.session.get(Booking, booking_id)
    if booking is None or booking.user_id != user.user_id:
        raise not_found("Booking not found.")
    if booking.payment is not None:
        if booking.payment.status == "pending":
            raise conflict("A payment for this booking is already in progress.",
                           "payment_in_progress")
        raise conflict("This booking already has a payment.", "already_paid")
    if booking.status == "cancelled":
        raise conflict("This booking has expired or was cancelled. Please book again.",
                       "booking_closed")
    if booking.status != "pending":
        raise conflict("This booking is already paid.", "already_paid")

    # Flutterwave requires an email address for every charge.
    email = email or user.email
    if not email:
        raise bad_request("Add an email address to pay with mobile money.",
                          {"email": "Flutterwave needs an email address for the receipt."})
    if not user.email:
        user.email = email

    payment = Payment(
        booking_id=booking.booking_id,
        amount=booking.total_price,
        method="momo",
        status="pending",
        # Unique, and shows which booking it belongs to.
        reference=f"etike-{booking.booking_id}-{uuid.uuid4().hex[:8]}",
    )
    db.session.add(payment)
    try:
        db.session.commit()
    except IntegrityError:
        # Two "Pay" clicks at once: the unique booking_id stops the second.
        db.session.rollback()
        raise conflict("A payment for this booking is already in progress.",
                       "payment_in_progress") from None

    redirect_url = current_app.config.get("FLW_REDIRECT_URL")
    try:
        payment.checkout_url = client.charge_rwanda_mobile_money(
            tx_ref=payment.reference,
            amount=payment.amount,
            phone=phone.lstrip("+"),
            email=email,
            fullname=user.full_name,
            redirect_url=f"{redirect_url}?booking={booking.booking_id}" if redirect_url else None,
        )
        db.session.commit()
    except flutterwave_client.FlutterwaveError:
        # The charge never started, so nothing was taken. Remove the payment
        # so the passenger can try again while the seats are held.
        db.session.delete(payment)
        db.session.commit()
        raise ApiError(502, "payment_provider_error",
                       "We could not start the payment. Please try again in a moment.") from None
    return payment


def check(payment):
    """Ask Flutterwave about a pending payment and apply the answer."""
    if payment.status != "pending":
        return payment
    client = _require_client()
    try:
        transaction = client.verify_by_reference(payment.reference)
    except flutterwave_client.FlutterwaveError:
        return payment  # keep it pending; the next check tries again
    return settle(payment.payment_id, _outcome(payment, transaction))


def _outcome(payment, transaction):
    """"success", "failed" or "pending", after checking the details match."""
    if not transaction:
        return "pending"
    status = str(transaction.get("status", "")).lower()
    if status == "successful":
        # Never give seats for a payment that doesn't match what we asked for.
        try:
            amount_ok = float(transaction.get("amount", 0)) >= payment.amount
        except (TypeError, ValueError):
            amount_ok = False
        if (transaction.get("tx_ref") == payment.reference
                and transaction.get("currency") == "RWF" and amount_ok):
            return "success"
        log.error("Payment %s: Flutterwave details do not match (tx_ref %s, %s %s).",
                  payment.payment_id, transaction.get("tx_ref"),
                  transaction.get("amount"), transaction.get("currency"))
        return "failed"
    if status == "failed":
        return "failed"
    return "pending"


def settle(payment_id, outcome):
    """Record the outcome of a payment, exactly once."""
    if outcome not in ("success", "failed"):
        return db.session.get(Payment, payment_id)

    confirmed = False
    try:
        payment = db.session.get(Payment, payment_id, with_for_update=True,
                                 populate_existing=True)
        if payment.status != "pending":
            db.session.commit()
            return payment  # already settled
        booking = db.session.get(Booking, payment.booking_id, with_for_update=True,
                                 populate_existing=True)
        payment.status = outcome
        if outcome == "success":
            confirmed = booking_service.confirm(booking)
        elif booking.status == "pending":
            booking_service.release(booking)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    if confirmed:
        # After the commit, so an SMS problem can never undo the booking.
        sms_service.booking_confirmed(booking)
    return payment


def find_by_reference(reference):
    if not reference:
        return None
    return db.session.query(Payment).filter_by(reference=str(reference)).first()
