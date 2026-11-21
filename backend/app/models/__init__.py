"""Database models. Importing this package registers every table with
SQLAlchemy, which Flask-Migrate needs to see them."""

from .booking import Booking, BookingSeat
from .login_code import LoginCode
from .message import Message
from .payment import Payment
from .rating import Rating
from .transport import BusCompany, BusTrip, RideLocation, RideOffer, Route
from .user import Driver, DriverDocument, User, Vehicle, VehiclePhoto

__all__ = [
    "Booking",
    "BookingSeat",
    "BusCompany",
    "BusTrip",
    "Driver",
    "DriverDocument",
    "LoginCode",
    "Message",
    "Payment",
    "Rating",
    "RideLocation",
    "RideOffer",
    "Route",
    "User",
    "Vehicle",
    "VehiclePhoto",
]
