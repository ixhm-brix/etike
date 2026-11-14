"""Database models. Importing this package registers every table with
SQLAlchemy, which Flask-Migrate needs to see them."""

from .booking import Booking
from .payment import Payment
from .rating import Rating
from .transport import BusCompany, BusTrip, RideOffer, Route
from .user import Driver, User, Vehicle

__all__ = [
    "Booking",
    "BusCompany",
    "BusTrip",
    "Driver",
    "Payment",
    "Rating",
    "RideOffer",
    "Route",
    "User",
    "Vehicle",
]
