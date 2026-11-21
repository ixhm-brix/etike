from ..extensions import db
from .user import utcnow


class Message(db.Model):
    """A chat message between a passenger and the driver about one booking,
    e.g. "I'm at the gate, in a red jacket". Only those two can read it."""

    __tablename__ = "messages"
    __table_args__ = (
        db.Index("ix_messages_booking_created", "booking_id", "created_at"),
    )

    message_id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.booking_id"), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    body = db.Column(db.String(1000), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    # When the other person opened the chat after this message arrived.
    read_at = db.Column(db.DateTime(timezone=True))

    sender = db.relationship("User")

    def to_dict(self, me):
        return {
            "message_id": self.message_id,
            "body": self.body,
            "mine": self.sender_id == me.user_id,
            "sender": self.sender.full_name,
            "at": self.created_at.isoformat(),
            "read": self.read_at is not None,
        }
