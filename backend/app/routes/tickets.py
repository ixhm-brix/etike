"""Tickets with a QR code.

The QR code holds a link to /verify.html with a signed token. Anyone who
scans it (for example bus staff at boarding) sees whether the ticket is
valid right now. The token can't be forged or changed without SECRET_KEY,
and validity is always checked live, so a cancelled ticket stops working
even though its QR code looks the same.
"""

import io
from datetime import timedelta

import segno
from flask import Blueprint, Response, current_app, jsonify, request
from itsdangerous import BadSignature, URLSafeSerializer

from ..auth import current_user, role_required
from ..errors import ApiError, not_found
from ..extensions import db
from ..models import Booking
from ..validation import local_now

tickets_bp = Blueprint("tickets", __name__)

# How long after departure a ticket still shows as valid (late boarding).
VALID_AFTER_DEPARTURE = timedelta(hours=3)


def _serializer():
    return URLSafeSerializer(current_app.config["SECRET_KEY"], salt="etike-ticket")


def ticket_token(booking):
    return _serializer().dumps({"b": booking.booking_id})


@tickets_bp.get("/bookings/<int:booking_id>/ticket")
@role_required()
def get_ticket(booking_id):
    booking = _own_confirmed(booking_id)
    token = ticket_token(booking)
    return jsonify({
        "booking": booking.to_dict(),
        "passenger": booking.user.full_name,
        "verify_url": f"{request.host_url}verify.html?t={token}",
    })


@tickets_bp.get("/bookings/<int:booking_id>/ticket/qr")
@role_required()
def ticket_qr(booking_id):
    booking = _own_confirmed(booking_id)
    url = f"{request.host_url}verify.html?t={ticket_token(booking)}"
    out = io.BytesIO()
    segno.make(url, error="m").save(out, kind="svg", scale=6, border=2, xmldecl=False,
                                     svgns=True, title=f"ETIKE ticket {booking.booking_id}")
    return Response(out.getvalue(), mimetype="image/svg+xml",
                    headers={"Cache-Control": "no-store"})


@tickets_bp.get("/tickets/verify")
def verify_ticket():
    """Public: what a scanner sees. Shows only what's needed to check a
    ticket at boarding: no phone number, and only the passenger's first name
    and last initial."""
    try:
        data = _serializer().loads(request.args.get("t", ""))
        booking = db.session.get(Booking, int(data["b"]))
    except (BadSignature, KeyError, TypeError, ValueError):
        booking = None
    if booking is None:
        return jsonify({"valid": False, "reason": "This is not an ETIKE ticket."})

    target = booking.trip or booking.offer
    if booking.status != "confirmed":
        reason = "This ticket was cancelled." if booking.status == "cancelled" \
            else "This ticket has not been paid."
        valid = False
    elif target.departure_time + VALID_AFTER_DEPARTURE < local_now():
        reason, valid = "This trip has already left.", False
    else:
        reason, valid = "Valid ticket.", True

    parts = booking.user.full_name.split()
    name = parts[0] + (f" {parts[-1][0]}." if len(parts) > 1 else "")
    return jsonify({
        "valid": valid,
        "reason": reason,
        "ticket": {
            "booking_id": booking.booking_id,
            "passenger": name,
            "type": booking.booking_type,
            "operator": (booking.trip.company.name if booking.trip
                         else booking.offer.driver.user.full_name),
            "origin": target.route.origin,
            "destination": target.route.destination,
            "departure_time": target.departure_time.isoformat(timespec="minutes"),
            "seat_numbers": booking.to_dict()["seat_numbers"],
            "status": booking.status,
        },
    })


def _own_confirmed(booking_id):
    booking = db.session.get(Booking, booking_id)
    if booking is None or booking.user_id != current_user().user_id:
        raise not_found("Booking not found.")
    if booking.offer_id is not None:
        # Like a taxi app: a ride needs no ticket, the booking is the proof.
        raise ApiError(404, "no_ticket", "Rides have no ticket: the driver sees your booking.")
    if booking.status != "confirmed":
        raise ApiError(409, "no_ticket", "There is no ticket until the booking is confirmed.")
    return booking
