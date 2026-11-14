from ..extensions import db
from .user import utcnow

BOOKING_TYPES = ("bus", "shared", "private")
BOOKING_STATUSES = ("pending", "confirmed", "cancelled")


class Booking(db.Model):
    __tablename__ = "bookings"
    __table_args__ = (
        db.CheckConstraint(f"booking_type IN {BOOKING_TYPES}", name="booking_type"),
        db.CheckConstraint(f"status IN {BOOKING_STATUSES}", name="status"),
        # A booking is for a bus trip or a ride offer, never both or neither.
        db.CheckConstraint("(trip_id IS NULL) <> (offer_id IS NULL)", name="one_target"),
        db.CheckConstraint("seats_booked >= 1", name="seats_booked_positive"),
        db.CheckConstraint("total_price >= 0", name="total_price_not_negative"),
        # Finds unpaid bookings whose hold has run out.
        db.Index("ix_bookings_status_expires", "status", "expires_at"),
    )

    booking_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False, index=True)
    booking_type = db.Column(db.String(10), nullable=False)
    trip_id = db.Column(db.Integer, db.ForeignKey("bus_trips.trip_id"))
    offer_id = db.Column(db.Integer, db.ForeignKey("ride_offers.offer_id"))
    seats_booked = db.Column(db.Integer, nullable=False)
    total_price = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(10), nullable=False, default="pending")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    # While a booking is pending, its seats are held until this time.
    expires_at = db.Column(db.DateTime(timezone=True))

    user = db.relationship("User")
    trip = db.relationship("BusTrip")
    offer = db.relationship("RideOffer")
    payment = db.relationship("Payment", back_populates="booking", uselist=False)
    rating = db.relationship("Rating", back_populates="booking", uselist=False)

    def to_dict(self):
        target = self.trip or self.offer
        return {
            "booking_id": self.booking_id,
            "booking_type": self.booking_type,
            "trip_id": self.trip_id,
            "offer_id": self.offer_id,
            "origin": target.route.origin,
            "destination": target.route.destination,
            "departure_time": target.departure_time.isoformat(timespec="minutes"),
            "operator": self.trip.company.name if self.trip else self.offer.driver.user.full_name,
            "seats_booked": self.seats_booked,
            "total_price": self.total_price,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "payment_status": self.payment.status if self.payment else None,
            "driver_id": self.offer.driver_id if self.offer else None,
            "rating": self.rating.to_dict() if self.rating else None,
        }
