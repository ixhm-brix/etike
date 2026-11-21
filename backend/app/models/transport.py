"""Bus companies, routes, bus trips and ride offers from drivers.

Departure times are stored as Rwanda local time (UTC+2 all year, no
daylight saving), which is how timetables are written.
"""

from ..extensions import db
from .user import utcnow

RIDE_TYPES = ("shared", "private")
OFFER_STATUSES = ("open", "full", "cancelled")


class BusCompany(db.Model):
    __tablename__ = "bus_companies"

    company_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    contact_phone = db.Column(db.String(16))
    registration_number = db.Column(db.String(40), nullable=False, unique=True)
    licence_number = db.Column(db.String(40), unique=True)
    is_verified = db.Column(db.Boolean, nullable=False, default=False)

    def to_dict(self):
        return {"company_id": self.company_id, "name": self.name}

    def admin_dict(self):
        return {
            "company_id": self.company_id,
            "name": self.name,
            "contact_phone": self.contact_phone,
            "registration_number": self.registration_number,
            "licence_number": self.licence_number,
            "is_verified": self.is_verified,
        }


class Route(db.Model):
    __tablename__ = "routes"
    __table_args__ = (
        db.UniqueConstraint("origin", "destination", name="uq_routes_origin_destination"),
        db.CheckConstraint("origin <> destination", name="different_places"),
    )

    route_id = db.Column(db.Integer, primary_key=True)
    origin = db.Column(db.String(40), nullable=False)
    destination = db.Column(db.String(40), nullable=False)

    def to_dict(self):
        return {"route_id": self.route_id, "origin": self.origin, "destination": self.destination}


class BusTrip(db.Model):
    __tablename__ = "bus_trips"
    __table_args__ = (
        db.CheckConstraint("price_rwf >= 0", name="price_not_negative"),
        db.CheckConstraint("total_seats >= 1", name="total_seats_positive"),
        db.CheckConstraint(
            "available_seats >= 0 AND available_seats <= total_seats", name="available_seats_range"
        ),
        db.Index("ix_bus_trips_route_departure", "route_id", "departure_time"),
    )

    trip_id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("bus_companies.company_id"), nullable=False)
    route_id = db.Column(db.Integer, db.ForeignKey("routes.route_id"), nullable=False)
    departure_time = db.Column(db.DateTime, nullable=False)
    price_rwf = db.Column(db.Integer, nullable=False)
    total_seats = db.Column(db.Integer, nullable=False)
    available_seats = db.Column(db.Integer, nullable=False)

    company = db.relationship("BusCompany")
    route = db.relationship("Route")

    def to_dict(self):
        return {
            "trip_id": self.trip_id,
            "company": self.company.to_dict(),
            "origin": self.route.origin,
            "destination": self.route.destination,
            "departure_time": self.departure_time.isoformat(timespec="minutes"),
            "price_rwf": self.price_rwf,
            "available_seats": self.available_seats,
        }


class RideOffer(db.Model):
    __tablename__ = "ride_offers"
    __table_args__ = (
        db.CheckConstraint(f"ride_type IN {RIDE_TYPES}", name="ride_type"),
        db.CheckConstraint(f"status IN {OFFER_STATUSES}", name="status"),
        db.CheckConstraint("price >= 0", name="price_not_negative"),
        db.CheckConstraint("seats_available >= 0", name="seats_not_negative"),
        db.Index("ix_ride_offers_route_departure", "route_id", "departure_time"),
    )

    offer_id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("drivers.driver_id"), nullable=False)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.vehicle_id"), nullable=False)
    route_id = db.Column(db.Integer, db.ForeignKey("routes.route_id"), nullable=False)
    ride_type = db.Column(db.String(10), nullable=False)
    departure_time = db.Column(db.DateTime, nullable=False)
    # Shared ride: price per seat. Private ride: price for the whole car.
    price = db.Column(db.Integer, nullable=False)
    seats_available = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(10), nullable=False, default="open")
    # Where the driver picks passengers up, in their words ("Nyabugogo bus
    # park, gate 2"). Required for new rides; older rides may have none.
    pickup_point = db.Column(db.String(200))
    # Set by the driver's Start ride and End ride buttons. Passengers pay
    # with MoMo once the ride has ended.
    started_at = db.Column(db.DateTime(timezone=True))
    ended_at = db.Column(db.DateTime(timezone=True))

    driver = db.relationship("Driver")
    vehicle = db.relationship("Vehicle")
    route = db.relationship("Route")

    @property
    def progress(self):
        """"scheduled", "in_progress" or "ended"."""
        if self.ended_at:
            return "ended"
        return "in_progress" if self.started_at else "scheduled"

    def to_dict(self):
        return {
            "offer_id": self.offer_id,
            "ride_type": self.ride_type,
            "origin": self.route.origin,
            "destination": self.route.destination,
            "departure_time": self.departure_time.isoformat(timespec="minutes"),
            "price": self.price,
            "seats_available": self.seats_available,
            "status": self.status,
            "progress": self.progress,
            "pickup_point": self.pickup_point,
            "driver_id": self.driver_id,
            "driver_name": self.driver.user.full_name,
            "driver_rating": float(self.driver.avg_rating) if self.driver.avg_rating else None,
            "vehicle": {
                "model": self.vehicle.model,
                "seats": self.vehicle.seats,
                "colour": self.vehicle.colour,
                "year": self.vehicle.year,
                "has_ac": self.vehicle.has_ac,
                "luggage": self.vehicle.luggage,
                "photos": [p.to_dict() for p in self.vehicle.photos],
            },
        }


class RideLocation(db.Model):
    """Where the driver's phone was during a ride: at Start ride ("start"),
    every half minute or so while it was on ("track"), and at End ride
    ("end"). Recorded only with the driver's permission, so a ride can have
    none. Personal data: only the driver, the ride's passengers and admins
    can see it."""

    __tablename__ = "ride_locations"
    __table_args__ = (
        db.CheckConstraint("kind IN ('start', 'track', 'end')", name="kind"),
    )

    location_id = db.Column(db.Integer, primary_key=True)
    offer_id = db.Column(db.Integer, db.ForeignKey("ride_offers.offer_id"), nullable=False,
                         index=True)
    kind = db.Column(db.String(5), nullable=False)
    lat = db.Column(db.Float, nullable=False)
    lng = db.Column(db.Float, nullable=False)
    accuracy_m = db.Column(db.Integer)  # how sure the phone was, in metres
    recorded_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    def to_dict(self):
        return {"kind": self.kind, "lat": self.lat, "lng": self.lng,
                "accuracy_m": self.accuracy_m, "at": self.recorded_at.isoformat()}
