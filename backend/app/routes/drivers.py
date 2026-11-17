"""Driver actions: register vehicles and post ride offers."""

import os
import secrets

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy.exc import IntegrityError

from .. import validation as v
from ..auth import current_user, role_required
from ..errors import ApiError, bad_request, conflict, not_found
from ..extensions import db
from ..models import RideOffer, Route, Vehicle, VehiclePhoto

drivers_bp = Blueprint("drivers", __name__)

MAX_VEHICLE_SEATS = 30  # minibuses included; big buses belong to bus companies
MAX_PHOTOS = 3
MAX_PHOTO_BYTES = 3 * 1024 * 1024

# Photos are recognised by their first bytes, never by the file name the
# browser sends, so a script renamed to .jpg is refused.
def _image_type(head):
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


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


@drivers_bp.post("/drivers/vehicles/<int:vehicle_id>/photos")
@role_required("driver")
def add_photo(vehicle_id):
    vehicle = _own_vehicle(vehicle_id)
    if len(vehicle.photos) >= MAX_PHOTOS:
        raise conflict(f"A car can have up to {MAX_PHOTOS} photos. Remove one first.",
                       "too_many_photos")
    upload = request.files.get("photo")
    if upload is None:
        raise bad_request("Choose a photo to upload.", {"photo": "Choose a photo."})
    data = upload.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        raise bad_request("The photo is too big. Use one under 3 MB.",
                          {"photo": "Must be under 3 MB."})
    kind = _image_type(data[:16])
    if kind is None:
        raise bad_request("Upload a JPEG, PNG or WebP photo.",
                          {"photo": "Must be a JPEG, PNG or WebP image."})

    folder = current_app.config["UPLOAD_DIR"]
    os.makedirs(folder, exist_ok=True)
    filename = f"{secrets.token_hex(16)}.{kind}"
    with open(os.path.join(folder, filename), "wb") as f:
        f.write(data)
    photo = VehiclePhoto(vehicle=vehicle, filename=filename)
    db.session.add(photo)
    db.session.commit()
    return jsonify({"photo": photo.to_dict(), "vehicle": vehicle.to_dict()}), 201


@drivers_bp.delete("/drivers/vehicles/<int:vehicle_id>/photos/<int:photo_id>")
@role_required("driver")
def delete_photo(vehicle_id, photo_id):
    vehicle = _own_vehicle(vehicle_id)
    photo = db.session.get(VehiclePhoto, photo_id)
    if photo is None or photo.vehicle_id != vehicle.vehicle_id:
        raise not_found("Photo not found.")
    path = os.path.join(current_app.config["UPLOAD_DIR"], photo.filename)
    db.session.delete(photo)
    db.session.commit()
    if os.path.exists(path):
        os.remove(path)
    return jsonify({"vehicle": vehicle.to_dict()})


def _own_vehicle(vehicle_id):
    vehicle = db.session.get(Vehicle, vehicle_id)
    if vehicle is None or vehicle.driver_id != current_user().driver.driver_id:
        raise not_found("Vehicle not found in your account.")
    return vehicle


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
