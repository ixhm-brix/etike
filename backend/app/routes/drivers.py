"""Driver actions: register vehicles and post ride offers."""

import os
import secrets

from flask import Blueprint, current_app, jsonify, request, send_file
from sqlalchemy.exc import IntegrityError

from .. import driver_documents as docs
from .. import validation as v
from ..auth import current_user, role_required
from ..errors import ApiError, bad_request, conflict, not_found
from ..extensions import db
from ..models import Driver, DriverDocument, RideOffer, Route, Vehicle, VehiclePhoto
from ..models.user import utcnow
from ..services import ride_service

drivers_bp = Blueprint("drivers", __name__)

MAX_VEHICLE_SEATS = 30  # minibuses included; big buses belong to bus companies
OLDEST_YEAR = 1980
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
    vehicle = Vehicle(driver_id=current_user().driver.driver_id, plate_number=plate,
                      **_vehicle_details(data))
    db.session.add(vehicle)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise conflict(
            "A vehicle with this plate number is already registered.", "plate_taken"
        ) from None
    return jsonify({"vehicle": vehicle.to_dict()}), 201


@drivers_bp.put("/drivers/vehicles/<int:vehicle_id>")
@role_required("driver")
def update_vehicle(vehicle_id):
    """Correct a car's details (the plate stays: a new plate is a new car)."""
    vehicle = _own_vehicle(vehicle_id)
    for field, value in _vehicle_details(v.json_body()).items():
        setattr(vehicle, field, value)
    db.session.commit()
    return jsonify({"vehicle": vehicle.to_dict()})


def _vehicle_details(data):
    """What passengers see about a car, checked."""
    has_ac = data.get("has_ac")
    if not isinstance(has_ac, bool):
        raise bad_request("Say whether the car has air conditioning.",
                          {"has_ac": "Choose yes or no."})
    return {
        "model": v.text(data, "model", min_len=2, max_len=60),
        "seats": v.integer(data, "seats", minimum=1, maximum=MAX_VEHICLE_SEATS),
        "colour": v.text(data, "colour", min_len=3, max_len=30).capitalize(),
        "year": v.integer(data, "year", minimum=OLDEST_YEAR,
                          maximum=v.local_now().year + 1),
        "has_ac": has_ac,
        "luggage": v.choice(data.get("luggage"), "luggage", ("small", "medium", "large")),
    }


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


@drivers_bp.get("/drivers/documents")
@role_required("driver")
def my_documents():
    """The driver's checklist of legal documents and their approval state."""
    driver = current_user().driver
    return jsonify(documents_summary(driver))


@drivers_bp.put("/drivers/details")
@role_required("driver")
def update_details():
    """Fill in or correct official details (step one after signing up as a
    driver; the documents are step two). Locked once approved: an
    approved driver asks an admin, so checked details can't change silently."""
    driver = current_user().driver
    if driver.is_approved:
        raise ApiError(409, "already_approved",
                       "Your account is approved, so your details are locked. "
                       "Contact ETIKE to change them.")
    details = v.driver_details(v.json_body())
    others = db.session.query(Driver).filter(Driver.driver_id != driver.driver_id)
    if others.filter(Driver.national_id_number == details["national_id_number"]).first():
        raise conflict("A driver with this national ID number is already registered.",
                       "national_id_taken")
    if others.filter(Driver.license_number == details["license_number"]).first():
        raise conflict("A driver with this licence number is already registered.",
                       "license_taken")
    for field, value in details.items():
        setattr(driver, field, value)
    if driver.rejected_at is not None:
        # Corrected details go back to the admins, like a new document.
        driver.rejected_at = None
        driver.rejection_reason = None
    db.session.commit()
    return jsonify(documents_summary(driver))


@drivers_bp.post("/drivers/documents/<doc_type>")
@role_required("driver")
def upload_document(doc_type):
    """Upload (or replace) one legal document: a JPEG, PNG or PDF under 5 MB,
    with its expiry date for documents that expire."""
    if doc_type not in docs.TYPES:
        raise not_found("Unknown document type.")
    driver = current_user().driver
    expires_on = None
    if doc_type in docs.NEEDS_EXPIRY:
        if not request.form.get("expires_on"):
            raise bad_request("Enter the date this document expires.",
                              {"expires_on": "Enter the expiry date."})
        expires_on = v.iso_date(request.form["expires_on"], "expires_on")
        if expires_on < v.local_now().date():
            raise bad_request("This document has expired. Upload a valid one.",
                              {"expires_on": "The date has passed."})

    upload = request.files.get("document")
    if upload is None:
        raise bad_request("Choose a file to upload.", {"document": "Choose a file."})
    data = upload.read(docs.MAX_BYTES + 1)
    if len(data) > docs.MAX_BYTES:
        raise bad_request("The file is too big. Use one under 5 MB.",
                          {"document": "Must be under 5 MB."})
    kind = docs.file_kind(data[:16])
    if kind is None:
        raise bad_request("Upload a photo (JPEG or PNG) or a PDF of the document.",
                          {"document": "Must be a JPEG, PNG or PDF."})

    folder = current_app.config["DOCUMENT_DIR"]
    os.makedirs(folder, exist_ok=True)
    filename = f"{secrets.token_hex(16)}.{kind}"
    with open(os.path.join(folder, filename), "wb") as f:
        f.write(data)

    old = next((d for d in driver.documents if d.doc_type == doc_type), None)
    old_file = old.filename if old else None
    if old:
        old.filename, old.kind, old.expires_on = filename, kind, expires_on
        old.uploaded_at = utcnow()
    else:
        driver.documents.append(DriverDocument(doc_type=doc_type, filename=filename,
                                               kind=kind, expires_on=expires_on))
    if driver.rejected_at is not None:
        # A rejected driver who fixes a document goes back to the admins.
        driver.rejected_at = None
        driver.rejection_reason = None
    db.session.commit()
    if old_file:
        _remove_document_file(old_file)
    return jsonify(documents_summary(driver)), 201


@drivers_bp.get("/drivers/documents/<doc_type>/file")
@role_required("driver")
def my_document_file(doc_type):
    doc = next((d for d in current_user().driver.documents if d.doc_type == doc_type), None)
    if doc is None:
        raise not_found("You have not uploaded this document.")
    return send_document(doc)


def documents_summary(driver):
    return {
        "documents": docs.checklist(driver),
        "problems": docs.problems(driver),
        "complete": not docs.problems(driver),
        "driver": driver.to_dict(),
        "details": driver.details_dict(),
    }


def send_document(doc):
    """Send a document file. Only ever reached by the API (with a login
    token), never by a public link; browsers must not cache it."""
    path = os.path.join(current_app.config["DOCUMENT_DIR"], doc.filename)
    if not os.path.exists(path):
        raise not_found("The file is missing on the server. Ask the driver to upload it again.")
    response = send_file(path, mimetype=docs.MIMETYPES[doc.kind], as_attachment=True,
                         download_name=f"{doc.doc_type}.{doc.kind}", max_age=0)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _remove_document_file(filename):
    path = os.path.join(current_app.config["DOCUMENT_DIR"], filename)
    if os.path.exists(path):
        os.remove(path)


def _own_vehicle(vehicle_id):
    vehicle = db.session.get(Vehicle, vehicle_id)
    if vehicle is None or vehicle.driver_id != current_user().driver.driver_id:
        raise not_found("Vehicle not found in your account.")
    return vehicle


@drivers_bp.get("/drivers/rides")
@role_required("driver")
def my_rides():
    """The driver's rides with their passengers and payments."""
    return jsonify({"rides": ride_service.driver_rides(current_user().driver)})


@drivers_bp.post("/rides/<int:offer_id>/start")
@role_required("driver")
def start_ride(offer_id):
    # The body may carry where the phone is ({lat, lng, accuracy}); optional.
    location = ride_service.location_from(request.get_json(silent=True))
    offer = ride_service.start(current_user().driver, offer_id, location)
    return jsonify({"ride": ride_service.ride_dict(offer)})


@drivers_bp.post("/rides/<int:offer_id>/end")
@role_required("driver")
def end_ride(offer_id):
    """End the ride: its passengers can now pay with MoMo."""
    location = ride_service.location_from(request.get_json(silent=True))
    offer = ride_service.end(current_user().driver, offer_id, location)
    return jsonify({"ride": ride_service.ride_dict(offer)})


@drivers_bp.post("/rides/<int:offer_id>/locations")
@role_required("driver")
def ride_location(offer_id):
    """Where the car is now, sent by the driver's phone while the ride is on."""
    location = ride_service.location_from(v.json_body())
    if location is None:
        raise bad_request("Send lat and lng.", {"lat": "Required."})
    saved = ride_service.record(current_user().driver, offer_id, location)
    return jsonify({"saved": saved}), 201 if saved else 200


@drivers_bp.get("/rides/<int:offer_id>/track")
@role_required()
def ride_track(offer_id):
    """The trip record on a map: for the driver, the ride's passengers, admins."""
    return jsonify(ride_service.trip_record(current_user(), offer_id))


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
    if not vehicle.complete:
        # Passengers choose a car by its photos and details.
        raise conflict("Finish your car first: add its colour, year, air conditioning, "
                       "luggage space and at least one photo.", "vehicle_incomplete")

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
    # Where passengers meet the driver, so nobody is left wondering.
    pickup = v.text(data, "pickup_point", min_len=5, max_len=200)

    offer = RideOffer(
        driver_id=driver.driver_id,
        vehicle_id=vehicle.vehicle_id,
        route=_get_or_create_route(origin, destination),
        ride_type=ride_type,
        departure_time=departure,
        price=price,
        seats_available=seats,
        pickup_point=pickup,
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
