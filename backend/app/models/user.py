from datetime import datetime, timezone

from ..extensions import db

ROLES = ("passenger", "driver", "admin")


def utcnow():
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = "users"
    __table_args__ = (
        db.CheckConstraint(f"role IN {ROLES}", name="role"),
    )

    user_id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(16), nullable=False, unique=True)
    email = db.Column(db.String(255))
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(16), nullable=False, default="passenger")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    driver = db.relationship("Driver", back_populates="user", uselist=False)

    def to_dict(self):
        data = {
            "user_id": self.user_id,
            "full_name": self.full_name,
            "phone": self.phone,
            "email": self.email,
            "role": self.role,
            "created_at": self.created_at.isoformat(),
        }
        if self.driver:
            data["driver"] = self.driver.to_dict()
        return data


class Driver(db.Model):
    __tablename__ = "drivers"

    driver_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False, unique=True)
    license_number = db.Column(db.String(30), nullable=False, unique=True)
    # Admins approve drivers after checking their licence; until then they
    # cannot post rides.
    is_approved = db.Column(db.Boolean, nullable=False, default=False)
    avg_rating = db.Column(db.Numeric(2, 1))  # updated after each rating
    # Set when an admin rejects the driver. Pending = neither approved nor rejected.
    rejected_at = db.Column(db.DateTime(timezone=True))

    user = db.relationship("User", back_populates="driver")
    vehicles = db.relationship("Vehicle", back_populates="driver")

    def to_dict(self):
        return {
            "driver_id": self.driver_id,
            "license_number": self.license_number,
            "is_approved": self.is_approved,
            "status": self.status,
            "avg_rating": float(self.avg_rating) if self.avg_rating is not None else None,
        }

    @property
    def status(self):
        if self.is_approved:
            return "approved"
        return "rejected" if self.rejected_at else "pending"


class Vehicle(db.Model):
    __tablename__ = "vehicles"
    __table_args__ = (
        db.CheckConstraint("seats >= 1", name="seats_positive"),
    )

    vehicle_id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("drivers.driver_id"), nullable=False)
    plate_number = db.Column(db.String(12), nullable=False, unique=True)
    model = db.Column(db.String(60), nullable=False)
    seats = db.Column(db.Integer, nullable=False)  # passenger seats, driver not counted

    driver = db.relationship("Driver", back_populates="vehicles")

    def to_dict(self):
        return {
            "vehicle_id": self.vehicle_id,
            "plate_number": self.plate_number,
            "model": self.model,
            "seats": self.seats,
        }
