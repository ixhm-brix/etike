"""Chat between a passenger and the driver of their ride, one conversation
per booking ("I'm at the gate in a red jacket" / "Arriving in 5 minutes").

Only those two people can read it. New messages can be sent from booking
until a day after the ride (Booking.contact_open); the history stays
readable. Opening a conversation marks the other person's messages read.
"""

from sqlalchemy import func

from ..errors import conflict, not_found
from ..extensions import db
from ..models import Booking, Message, RideOffer
from ..models.user import utcnow
from ..validation import text

MAX_LENGTH = 1000


def _conversation(user, booking_id):
    """The booking, if this user is its passenger or its ride's driver."""
    booking = db.session.get(Booking, booking_id)
    if booking is None or booking.offer is None:
        raise not_found("Conversation not found.")
    is_driver = user.driver is not None and booking.offer.driver_id == user.driver.driver_id
    if booking.user_id != user.user_id and not is_driver:
        raise not_found("Conversation not found.")
    return booking


def read(user, booking_id):
    """The conversation, oldest first. Marks the other person's messages read."""
    booking = _conversation(user, booking_id)
    messages = (db.session.query(Message).filter_by(booking_id=booking.booking_id)
                .order_by(Message.created_at, Message.message_id).all())
    now = utcnow()
    for m in messages:
        if m.sender_id != user.user_id and m.read_at is None:
            m.read_at = now
    db.session.commit()
    is_passenger = booking.user_id == user.user_id
    other = booking.offer.driver.user if is_passenger else booking.user
    return {
        "booking": booking.to_dict(),
        "with": {
            "name": other.full_name,
            "role": "driver" if is_passenger else "passenger",
            "phone": other.phone if booking.contact_open else None,
        },
        "can_send": booking.contact_open,
        "messages": [m.to_dict(user) for m in messages],
    }


def send(user, booking_id, data):
    booking = _conversation(user, booking_id)
    if not booking.contact_open:
        raise conflict("This conversation is closed: it ends a day after the ride.",
                       "conversation_closed")
    body = text(data, "body", min_len=1, max_len=MAX_LENGTH)
    message = Message(booking_id=booking.booking_id, sender_id=user.user_id, body=body)
    db.session.add(message)
    db.session.commit()
    return message


def unread_counts(user):
    """{booking_id: unread} over all of this user's conversations, as a
    passenger and as a driver."""
    ids = [i for (i,) in db.session.query(Booking.booking_id)
           .filter(Booking.user_id == user.user_id)]
    if user.driver is not None:
        ids += [i for (i,) in db.session.query(Booking.booking_id).join(RideOffer)
                .filter(RideOffer.driver_id == user.driver.driver_id)]
    return _unread(ids, user)


def _unread(booking_ids, user):
    if not booking_ids:
        return {}
    rows = (db.session.query(Message.booking_id, func.count(Message.message_id))
            .filter(Message.booking_id.in_(booking_ids), Message.sender_id != user.user_id,
                    Message.read_at.is_(None))
            .group_by(Message.booking_id).all())
    return dict(rows)


def unread_for_driver(driver_user, bookings):
    """Unread messages from these bookings' passengers, for their driver."""
    return _unread([b.booking_id for b in bookings], driver_user)
