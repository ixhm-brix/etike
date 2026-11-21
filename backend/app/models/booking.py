from datetime import timedelta

from flask import current_app

from ..extensions import db
from ..validation import local_now
from .user import utcnow

BOOKING_TYPES = ("bus", "shared", "private")
BOOKING_STATUSES = ("pending", "confirmed", "cancelled")


# How long after departure passenger and driver can still reach each other.
CONTACT_WINDOW = timedelta(days=1)


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
    # The seat numbers this booking has, e.g. "3,4". Kept after cancelling.
    seat_numbers = db.Column(db.String(80))
    # While a booking is pending, its seats are held until this time.
    expires_at = db.Column(db.DateTime(timezone=True))

    user = db.relationship("User")
    trip = db.relationship("BusTrip")
    offer = db.relationship("RideOffer")
    payment = db.relationship("Payment", back_populates="booking", uselist=False)
    rating = db.relationship("Rating", back_populates="booking", uselist=False)

    @property
    def cancel_until(self):
        """Last moment (Rwanda time) a confirmed booking can be cancelled."""
        target = self.trip or self.offer
        hours = current_app.config["CANCEL_CUTOFF_HOURS"]
        return target.departure_time - timedelta(hours=hours)

    @property
    def contact_open(self):
        """Passenger and driver of a ride booking can call and message each
        other from booking until a day after the ride."""
        if self.offer is None or self.status != "confirmed":
            return False
        return local_now() <= self.offer.departure_time + CONTACT_WINDOW

    @property
    def can_pay(self):
        """A ride is paid once it has ended, if not paid (or paying) yet."""
        if self.offer is None or self.status != "confirmed" or self.offer.ended_at is None:
            return False
        return self.payment is None or self.payment.status == "failed"

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
            "seat_numbers": [int(n) for n in self.seat_numbers.split(",")]
            if self.seat_numbers else [],
            "total_price": self.total_price,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "payment_status": self.payment.status if self.payment else None,
            "refund_status": self.payment.refund_status if self.payment else None,
            # Rides are paid with MoMo after the driver ends the ride.
            "pay_after_ride": self.offer_id is not None,
            "ride_progress": self.offer.progress if self.offer else None,
            "pickup_point": self.offer.pickup_point if self.offer else None,
            # Only between the two people on this ride, and only for a while.
            "driver_phone": self.offer.driver.user.phone if self.contact_open else None,
            # The plate helps the passenger find the right car; only once booked.
            "vehicle": {"model": self.offer.vehicle.model, "colour": self.offer.vehicle.colour,
                        "plate_number": self.offer.vehicle.plate_number}
            if self.offer and self.status == "confirmed" else None,
            "can_pay": self.can_pay,
            "cancel_until": self.cancel_until.isoformat(timespec="minutes"),
            "driver_id": self.offer.driver_id if self.offer else None,
            "rating": self.rating.to_dict() if self.rating else None,
        }


class BookingSeat(db.Model):
    """One seat held by a booking. The unique constraints stop two bookings
    from ever holding the same seat on the same trip or ride. Rows are
    deleted when the booking is cancelled, which frees the seat."""

    __tablename__ = "booking_seats"
    __table_args__ = (
        db.UniqueConstraint("trip_id", "seat_number", name="uq_booking_seats_trip_seat"),
        db.UniqueConstraint("offer_id", "seat_number", name="uq_booking_seats_offer_seat"),
        db.CheckConstraint("(trip_id IS NULL) <> (offer_id IS NULL)", name="one_target"),
        db.CheckConstraint("seat_number >= 1", name="seat_number_positive"),
    )

    seat_id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.booking_id"), nullable=False,
                           index=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("bus_trips.trip_id"))
    offer_id = db.Column(db.Integer, db.ForeignKey("ride_offers.offer_id"))
    seat_number = db.Column(db.Integer, nullable=False)

    booking = db.relationship("Booking")
