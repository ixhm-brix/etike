"""Driver actions: register vehicles and post ride offers."""

from flask import Blueprint, jsonify
from sqlalchemy.exc import IntegrityError

from .. import validation as v
from ..auth import current_user, role_required
from ..errors import ApiError, bad_request, conflict, not_found
from ..extensions import db
from ..models import RideOffer, Route, Vehicle

drivers_bp = Blueprint("drivers", __name__)

MAX_VEHICLE_SEATS = 30  # minibuses included; big buses belong to bus companies


@drivers_bp.post("/drivers/vehicles")
@role_required("driver")
def add_vehicle():
    data = v.json_body()
    plate = "".join(v.text(data, "plate_number", min_len=4, max_len=12).split()).upper()
    vehicle = Vehicle(
        driver_id=current_user().driver.driver_id,
        plate_number=plate,
        model=v.text(data, "model", min_len=2, max_len=60),
        seats=v.integer(data, "seats", minimum=1, maximum=MAX_VEHICLE_SEATS),
    )
    db.session.add(vehicle)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise conflict(
            "A vehicle with this plate number is already registered.", "plate_taken"
        ) from None
    return jsonify({"vehicle": vehicle.to_dict()}), 201


@drivers_bp.get("/drivers/vehicles")
@role_required("driver")
def my_vehicles():
    vehicles = current_user().driver.vehicles
    return jsonify({"vehicles": [x.to_dict() for x in vehicles]})


@drivers_bp.post("/rides")
@role_required("driver")
def post_ride():
    driver = current_user().driver
    if not driver.is_approved:
        raise ApiError(
            403, "driver_not_approved", "Your driver account is waiting for approval."
        )

    data = v.json_body()
    vehicle = db.session.get(Vehicle, v.integer(data, "vehicle_id", minimum=1))
    if vehicle is None or vehicle.driver_id != driver.driver_id:
        raise not_found("Vehicle not found in your account.")

    origin, destination = v.route_places(data.get("origin"), data.get("destination"))
    ride_type = v.choice(data.get("ride_type"), "ride_type", ("shared", "private"))
    departure = v.iso_datetime(data.get("departure_time"), "departure_time")
    if departure <= v.local_now():
        raise bad_request(
            "The departure time must be in the future.",
            {"departure_time": "Must be in the future."},
        )
    price = v.integer(data, "price", minimum=1)
    seats = v.integer(
        data, "seats_available", minimum=1, maximum=vehicle.seats, default=vehicle.seats
    )

    offer = RideOffer(
        driver_id=driver.driver_id,
        vehicle_id=vehicle.vehicle_id,
        route=_get_or_create_route(origin, destination),
        ride_type=ride_type,
        departure_time=departure,
        price=price,
        seats_available=seats,
        status="open",
    )
    db.session.add(offer)
    db.session.commit()
    return jsonify({"ride": offer.to_dict()}), 201


def _get_or_create_route(origin, destination):
    route = db.session.query(Route).filter_by(origin=origin, destination=destination).first()
    if route:
        return route
    # Both names are checked against the official list, so this only ever
    # adds a real pair of districts that a driver is actually travelling.
    route = Route(origin=origin, destination=destination)
    db.session.add(route)
    return route
