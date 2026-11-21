"""Chat between a passenger and the driver of their ride (one conversation
per booking). See services/message_service.py for the rules."""

from flask import Blueprint, jsonify

from .. import validation as v
from ..auth import current_user, role_required
from ..services import message_service

messages_bp = Blueprint("messages", __name__)


@messages_bp.get("/bookings/<int:booking_id>/messages")
@role_required()
def conversation(booking_id):
    return jsonify(message_service.read(current_user(), booking_id))


@messages_bp.post("/bookings/<int:booking_id>/messages")
@role_required()
def send_message(booking_id):
    message = message_service.send(current_user(), booking_id, v.json_body())
    return jsonify({"message": message.to_dict(current_user())}), 201


@messages_bp.get("/messages/unread")
@role_required()
def unread():
    """New messages for the tab bar badge: {"total": 3, "by_booking": {...}}."""
    counts = message_service.unread_counts(current_user())
    return jsonify({"total": sum(counts.values()),
                    "by_booking": {str(k): n for k, n in counts.items()}})
