from ..extensions import db
from .user import utcnow

PAYMENT_STATUSES = ("pending", "success", "failed")
# Set when a paid booking is cancelled: the money is owed back ("due") until
# an admin has sent it ("refunded").
REFUND_STATUSES = ("due", "refunded")


class Payment(db.Model):
    """One MTN MoMo payment per booking. If it fails, the booking is
    cancelled and the passenger books again."""

    __tablename__ = "payments"
    __table_args__ = (
        db.CheckConstraint(f"status IN {PAYMENT_STATUSES}", name="status"),
        db.CheckConstraint("method = 'mtn_momo'", name="method"),
        db.CheckConstraint("amount >= 0", name="amount_not_negative"),
        db.CheckConstraint(
            f"refund_status IS NULL OR refund_status IN {REFUND_STATUSES}", name="refund_status"
        ),
    )

    payment_id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(
        db.Integer, db.ForeignKey("bookings.booking_id"), nullable=False, unique=True
    )
    amount = db.Column(db.Integer, nullable=False)
    method = db.Column(db.String(10), nullable=False, default="mtn_momo")
    status = db.Column(db.String(10), nullable=False, default="pending")
    # The X-Reference-Id (a UUID) we gave MoMo for this request to pay.
    reference = db.Column(db.String(64), nullable=False, unique=True)
    # Why it failed, in MoMo's words, e.g. APPROVAL_REJECTED or EXPIRED.
    failure_reason = db.Column(db.String(60))
    refund_status = db.Column(db.String(10))
    refunded_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    booking = db.relationship("Booking", back_populates="payment")

    def to_dict(self):
        return {
            "payment_id": self.payment_id,
            "booking_id": self.booking_id,
            "amount": self.amount,
            "method": self.method,
            "status": self.status,
            "failure_reason": self.failure_reason,
            "refund_status": self.refund_status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
