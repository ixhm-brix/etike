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
    # Empty for people who only ever log in with an SMS code.
    password_hash = db.Column(db.String(255))
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
    __table_args__ = (
        db.CheckConstraint("gender IN ('female', 'male')", name="gender_allowed"),
    )

    driver_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False, unique=True)
    # Filled in on the driver page after sign-up, with the details below.
    license_number = db.Column(db.String(30), unique=True)
    # Admins approve drivers after checking their licence; until then they
    # cannot post rides.
    is_approved = db.Column(db.Boolean, nullable=False, default=False)
    avg_rating = db.Column(db.Numeric(2, 1))  # updated after each rating
    # Set when an admin rejects the driver. Pending = neither approved nor rejected.
    rejected_at = db.Column(db.DateTime(timezone=True))
    # Shown to the driver, so they know what to fix.
    rejection_reason = db.Column(db.String(300))

    # Personal details as on the driver's national ID, filled in on the driver
    # page after sign-up and checked by an admin against the uploaded ID. Personal data: only the
    # driver (details_dict) and admins ever see them, never passengers.
    national_id_number = db.Column(db.String(16), unique=True)
    date_of_birth = db.Column(db.Date)
    gender = db.Column(db.String(6))
    home_district = db.Column(db.String(40))
    home_sector = db.Column(db.String(60))

    user = db.relationship("User", back_populates="driver")
    vehicles = db.relationship("Vehicle", back_populates="driver")
    documents = db.relationship("DriverDocument", back_populates="driver",
                                cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "driver_id": self.driver_id,
            "license_number": self.license_number,
            "is_approved": self.is_approved,
            "status": self.status,
            "rejection_reason": self.rejection_reason if self.rejected_at else None,
            "avg_rating": float(self.avg_rating) if self.avg_rating is not None else None,
        }

    DETAIL_FIELDS = ("national_id_number", "date_of_birth", "gender", "home_district",
                     "home_sector", "license_number")

    def details_dict(self):
        """Private: for the driver themselves and admins only. Kept out of
        to_dict, which is saved in the browser at login."""
        born = self.date_of_birth
        return {
            "national_id_number": self.national_id_number,
            "date_of_birth": born.isoformat() if born else None,
            "gender": self.gender,
            "home_district": self.home_district,
            "home_sector": self.home_sector,
            "license_number": self.license_number,
        }

    @property
    def has_details(self):
        return all(getattr(self, f) for f in self.DETAIL_FIELDS)

    @property
    def status(self):
        if self.is_approved:
            return "approved"
        return "rejected" if self.rejected_at else "pending"


class Vehicle(db.Model):
    __tablename__ = "vehicles"
    __table_args__ = (
        db.CheckConstraint("seats >= 1", name="seats_positive"),
        db.CheckConstraint("luggage IN ('small', 'medium', 'large')", name="luggage_allowed"),
    )

    vehicle_id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("drivers.driver_id"), nullable=False)
    plate_number = db.Column(db.String(12), nullable=False, unique=True)
    model = db.Column(db.String(60), nullable=False)
    seats = db.Column(db.Integer, nullable=False)  # passenger seats, driver not counted
    # What passengers want to know, and how they spot the car at the meeting
    # point. Required for new cars; older ones are completed on the driver page.
    colour = db.Column(db.String(30))
    year = db.Column(db.Integer)
    has_ac = db.Column(db.Boolean)  # air conditioning
    luggage = db.Column(db.String(6))  # small, medium or large boot

    driver = db.relationship("Driver", back_populates="vehicles")
    photos = db.relationship("VehiclePhoto", back_populates="vehicle",
                             order_by="VehiclePhoto.photo_id", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "vehicle_id": self.vehicle_id,
            "plate_number": self.plate_number,
            "model": self.model,
            "seats": self.seats,
            "colour": self.colour,
            "year": self.year,
            "has_ac": self.has_ac,
            "luggage": self.luggage,
            "photos": [p.to_dict() for p in self.photos],
            "complete": self.complete,
        }

    @property
    def complete(self):
        """Ready to carry passengers: every detail filled in and a photo."""
        return (all(x is not None for x in (self.colour, self.year, self.has_ac, self.luggage))
                and bool(self.photos))


class VehiclePhoto(db.Model):
    """A photo of a driver's car, shown to passengers. The file lives in
    UPLOAD_DIR under a random name; Nginx serves it at /uploads/<filename>."""

    __tablename__ = "vehicle_photos"

    photo_id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.vehicle_id"), nullable=False,
                           index=True)
    filename = db.Column(db.String(64), nullable=False, unique=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    vehicle = db.relationship("Vehicle", back_populates="photos")

    def to_dict(self):
        return {"photo_id": self.photo_id, "url": f"/uploads/{self.filename}"}


class DriverDocument(db.Model):
    """A legal document a driver uploaded for approval (see
    app/driver_documents.py). Personal data: the file lives in DOCUMENT_DIR,
    which Nginx never serves; only the driver and admins can download it
    through the API. One file per type; a new upload replaces the old one."""

    __tablename__ = "driver_documents"
    __table_args__ = (
        db.UniqueConstraint("driver_id", "doc_type", name="uq_driver_documents_one_per_type"),
    )

    document_id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("drivers.driver_id"), nullable=False,
                          index=True)
    doc_type = db.Column(db.String(30), nullable=False)
    filename = db.Column(db.String(64), nullable=False, unique=True)
    kind = db.Column(db.String(4), nullable=False)  # jpg, png or pdf
    expires_on = db.Column(db.Date)
    uploaded_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    driver = db.relationship("Driver", back_populates="documents")
