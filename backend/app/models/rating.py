from ..extensions import db
from .user import utcnow


class Rating(db.Model):
    """A passenger's rating of the driver after a shared or private ride."""

    __tablename__ = "ratings"
    __table_args__ = (db.CheckConstraint("score BETWEEN 1 AND 5", name="score_range"),)

    rating_id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(
        db.Integer, db.ForeignKey("bookings.booking_id"), nullable=False, unique=True
    )
    score = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.String(500))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    booking = db.relationship("Booking", back_populates="rating")

    def to_dict(self):
        # No passenger name: comments are shown publicly on the driver.
        return {
            "score": self.score,
            "comment": self.comment,
            "created_at": self.created_at.isoformat(),
        }
