"""Public search: routes, bus trips and ride offers. No login needed."""

from datetime import datetime, time, timedelta

from flask import Blueprint, jsonify, request

from .. import validation as v
from ..errors import not_found
from ..extensions import db
from ..models import BusCompany, BusTrip, Driver, RideOffer, Route
from ..places import PLACES
from ..services.booking_service import release_expired

search_bp = Blueprint("search", __name__)


@search_bp.get("/places")
def list_places():
    """The places people can travel between, for the search forms."""
    return jsonify({"places": ["Kigali", *sorted(p for p in PLACES if p != "Kigali")]})


@search_bp.get("/routes")
def list_routes():
    routes = db.session.query(Route).order_by(Route.origin, Route.destination).all()
    return jsonify({"routes": [r.to_dict() for r in routes]})


@search_bp.get("/trips")
def search_trips():
    origin, destination, start, end = _search_window()
    release_expired()  # so seats from unpaid bookings show as free again
    trips = (
        db.session.query(BusTrip)
        .join(Route)
        .join(BusCompany)
        .filter(
            BusCompany.is_verified.is_(True),
            Route.origin == origin,
            Route.destination == destination,
            BusTrip.departure_time >= start,
            BusTrip.departure_time < end,
            BusTrip.available_seats > 0,
        )
        .order_by(BusTrip.departure_time, BusTrip.price_rwf)
        .all()
    )
    return jsonify({"trips": [t.to_dict() for t in trips]})


@search_bp.get("/trips/<int:trip_id>")
def get_trip(trip_id):
    trip = db.session.get(BusTrip, trip_id)
    if trip is None or not trip.company.is_verified:
        raise not_found("Bus trip not found.")
    return jsonify({"trip": trip.to_dict()})


@search_bp.get("/rides")
def search_rides():
    origin, destination, start, end = _search_window()
    release_expired()
    query = (
        db.session.query(RideOffer)
        .join(Route)
        .join(Driver)
        .filter(
            Route.origin == origin,
            Route.destination == destination,
            RideOffer.departure_time >= start,
            RideOffer.departure_time < end,
            RideOffer.status == "open",
            RideOffer.seats_available > 0,
            Driver.is_approved.is_(True),
        )
    )
    ride_type = request.args.get("type")
    if ride_type:
        ride_type = v.choice(ride_type, "type", ("shared", "private"))
        query = query.filter(RideOffer.ride_type == ride_type)
    rides = query.order_by(RideOffer.departure_time, RideOffer.price).all()
    return jsonify({"rides": [r.to_dict() for r in rides]})


@search_bp.get("/rides/<int:offer_id>")
def get_ride(offer_id):
    offer = db.session.get(RideOffer, offer_id)
    if offer is None or not offer.driver.is_approved:
        raise not_found("Ride not found.")
    return jsonify({"ride": offer.to_dict()})


def _search_window():
    """Read origin, destination and optional date from the query string.

    Returns the departure-time range to search: the whole chosen day, or
    from now on when no date is given. Departures in the past never show.
    """
    args = request.args
    origin, destination = v.route_places(args.get("origin"), args.get("destination"))
    now = v.local_now()
    day = args.get("date")
    if day:
        start = datetime.combine(v.iso_date(day), time.min)
        end = start + timedelta(days=1)
        start = max(start, now)
    else:
        start, end = now, datetime.max
    return origin, destination, start, end
