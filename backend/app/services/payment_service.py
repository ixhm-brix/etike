"""Paying for a booking with MTN MoMo (Collections API, "request to pay").

Bus tickets are paid before travel (a pending booking). Rides are paid
after the driver ends the ride (a confirmed booking whose ride has ended);
a failed ride payment can be tried again.

1. start(): the passenger asks to pay their booking. We save a
   pending payment with a new UUID reference and send MoMo a request to
   pay. The amount always comes from the booking, never from the client.
2. MoMo asks the passenger to approve on their phone with their MoMo PIN.
3. check() asks MoMo how it went. It runs when the payment page polls, and
   when MoMo calls our callback. We never trust what a callback says: it
   only tells us which payment to check, and the answer comes from MoMo.
4. Before confirming we compare the amount, currency and booking ID
   (externalId) in MoMo's answer with ours.
5. settle() applies the answer once. Calling it again changes nothing, so
   a callback that arrives twice is harmless.
"""

import logging
import uuid

from flask import current_app
from sqlalchemy.exc import IntegrityError

from ..errors import ApiError, conflict, not_found
from ..extensions import db
from ..models import Booking, Payment
from . import booking_service, momo_client, sms_service

log = logging.getLogger(__name__)


def get_payment_client():
    """Separate function so tests can swap in a fake client."""
    return momo_client.get_client()


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


def provider_info():
    """What the payment page needs to know about the MoMo set-up."""
    cfg = current_app.config
    return {
        "currency": cfg["MOMO_CURRENCY"],
        "sandbox": cfg["MOMO_TARGET_ENVIRONMENT"] == "sandbox",
    }


def start(user, booking_id, phone):
    """Start paying for the user's pending booking. Returns the Payment."""
    client = _require_client()
    booking_service.release_expired()

    booking = db.session.get(Booking, booking_id)
    if booking is None or booking.user_id != user.user_id:
        raise not_found("Booking not found.")
    if booking.offer_id is not None:
        return _start_ride_payment(client, booking, phone)
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

    payment = Payment(
        booking_id=booking.booking_id,
        amount=booking.total_price,
        method="mtn_momo",
        status="pending",
        reference=str(uuid.uuid4()),  # a new one for every request to pay
    )
    db.session.add(payment)
    try:
        db.session.commit()
    except IntegrityError:
        # Two "Pay" clicks at once: the unique booking_id stops the second.
        db.session.rollback()
        raise conflict("A payment for this booking is already in progress.",
                       "payment_in_progress") from None

    try:
        client.request_to_pay(
            reference=payment.reference,
            amount=payment.amount,
            phone=phone,
            external_id=booking.booking_id,
            message=f"ETIKE booking {booking.booking_id}",
        )
    except momo_client.MomoError:
        # MoMo never accepted the request, so nothing was charged. Remove the
        # payment so the passenger can try again while the seats are held.
        db.session.delete(payment)
        db.session.commit()
        raise ApiError(502, "payment_provider_error",
                       "We could not reach MoMo. Please try again in a moment.") from None
    return payment


def _start_ride_payment(client, booking, phone):
    """Pay for a ride after it has ended."""
    if booking.status != "confirmed":
        raise conflict("This booking was cancelled.", "booking_closed")
    if booking.offer.ended_at is None:
        raise conflict("You pay once the driver ends the ride.", "ride_not_ended")
    payment = booking.payment
    if payment is not None and payment.status == "pending":
        raise conflict("A payment for this ride is already in progress.", "payment_in_progress")
    if payment is not None and payment.status == "success":
        raise conflict("This ride is already paid.", "already_paid")
    if payment is None:
        payment = Payment(booking_id=booking.booking_id, method="mtn_momo")
        db.session.add(payment)
    # A new attempt (or a retry after a failed one): fresh reference.
    payment.amount = booking.total_price
    payment.status = "pending"
    payment.failure_reason = None
    payment.reference = str(uuid.uuid4())
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise conflict("A payment for this ride is already in progress.",
                       "payment_in_progress") from None
    try:
        client.request_to_pay(
            reference=payment.reference,
            amount=payment.amount,
            phone=phone,
            external_id=booking.booking_id,
            message=f"ETIKE ride {booking.booking_id}",
        )
    except momo_client.MomoError:
        # Nothing was charged: mark it failed so the passenger can try again.
        payment.status = "failed"
        payment.failure_reason = "NOT_SENT"
        db.session.commit()
        raise ApiError(502, "payment_provider_error",
                       "We could not reach MoMo. Please try again in a moment.") from None
    return payment


def check(payment):
    """Ask MoMo about a pending payment and apply the answer."""
    if payment.status != "pending":
        return payment
    client = _require_client()
    try:
        answer = client.get_status(payment.reference)
    except momo_client.MomoError:
        return payment  # keep it pending; the next check tries again
    outcome, reason = _outcome(payment, answer, current_app.config["MOMO_CURRENCY"])
    return settle(payment.payment_id, outcome, reason)


def _outcome(payment, answer, currency):
    """Turn MoMo's answer into ("success" | "failed" | "pending", reason)."""
    status = str(answer.get("status", "")).upper()
    if status == "SUCCESSFUL":
        # Never give seats for a payment that doesn't match what we asked for.
        try:
            amount_ok = float(answer.get("amount", 0)) == payment.amount
        except (TypeError, ValueError):
            amount_ok = False
        if (amount_ok and answer.get("currency") == currency
                and str(answer.get("externalId")) == str(payment.booking_id)):
            return "success", None
        log.error("Payment %s: MoMo's details do not match ours (%s %s, externalId %s).",
                  payment.payment_id, answer.get("amount"), answer.get("currency"),
                  answer.get("externalId"))
        return "failed", "DETAILS_MISMATCH"
    if status in ("FAILED", "REJECTED", "EXPIRED", "TIMEOUT"):
        # The reason is a word like APPROVAL_REJECTED, or {"code": ..., "message": ...}.
        reason = answer.get("reason")
        if isinstance(reason, dict):
            reason = reason.get("code") or reason.get("message")
        if not reason and status != "FAILED":
            reason = status
        return "failed", str(reason or "FAILED")[:60]
    return "pending", None


def settle(payment_id, outcome, reason=None):
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
        ride_paid = False
        if booking.offer_id is not None:
            # A ride is already booked; the payment only settles the fare.
            # A failed payment can simply be tried again.
            ride_paid = outcome == "success"
            if not ride_paid:
                payment.failure_reason = reason
        elif outcome == "success":
            confirmed = booking_service.confirm(booking)
        else:
            payment.failure_reason = reason
            if booking.status == "pending":
                booking_service.release(booking)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    if ride_paid:
        # Tell the driver the money came in (and the passenger, a receipt).
        sms_service.ride_paid(booking)
    if confirmed:
        # After the commit, so an SMS problem can never undo the booking.
        sms_service.booking_confirmed(booking)
    return payment


def find_for_callback(reference=None, external_id=None):
    """Find the payment a MoMo callback is about: by our reference if it is
    given, otherwise by the booking ID we sent as externalId."""
    if reference:
        payment = db.session.query(Payment).filter_by(reference=str(reference)).first()
        if payment:
            return payment
    if external_id and str(external_id).isdigit():
        return db.session.query(Payment).filter_by(booking_id=int(external_id)).first()
    return None
