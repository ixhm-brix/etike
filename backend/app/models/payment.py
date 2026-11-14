from ..extensions import db
from .user import utcnow

PAYMENT_STATUSES = ("pending", "success", "failed")


class Payment(db.Model):
    """One mobile money payment (through Flutterwave) per booking. If it
    fails, the booking is cancelled and the passenger books again."""

    __tablename__ = "payments"
    __table_args__ = (
        db.CheckConstraint(f"status IN {PAYMENT_STATUSES}", name="status"),
        db.CheckConstraint("method = 'momo'", name="method"),
        db.CheckConstraint("amount >= 0", name="amount_not_negative"),
    )

    payment_id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(
        db.Integer, db.ForeignKey("bookings.booking_id"), nullable=False, unique=True
    )
    amount = db.Column(db.Integer, nullable=False)
    method = db.Column(db.String(10), nullable=False, default="momo")
    status = db.Column(db.String(10), nullable=False, default="pending")
    # Our tx_ref for Flutterwave, e.g. "etike-12-3f9a1c2b"; used to verify.
    reference = db.Column(db.String(64), nullable=False, unique=True)
    # Flutterwave page where the customer approves the payment.
    checkout_url = db.Column(db.String(500))
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
            "checkout_url": self.checkout_url if self.status == "pending" else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
