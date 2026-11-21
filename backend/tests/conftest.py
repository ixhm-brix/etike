"""Shared test setup.

Tests run on in-memory SQLite by default, or on PostgreSQL when
TEST_DATABASE_URL is set (as in CI). On PostgreSQL the schema comes from the
real migrations, so the tests also prove the migrations match the models.

All test data is created here or inside the tests. It is never committed as
seed data, and it only ever lives in the test database.
"""

import io
from datetime import timedelta

import pytest
from flask_migrate import upgrade
from sqlalchemy import text
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import BusCompany, BusTrip, Driver, RideOffer, Route, User, Vehicle
from app.validation import local_now

PASSWORD = "correct-horse-battery"


def is_postgres(app):
    return app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql")


@pytest.fixture(scope="session")
def _migrated():
    """Bring a PostgreSQL test database up to date once per test run."""
    app = create_app("testing")
    if is_postgres(app):
        with app.app_context():
            upgrade()


@pytest.fixture()
def app(_migrated):
    app = create_app("testing")
    with app.app_context():
        if not is_postgres(app):
            db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        if is_postgres(app):
            tables = ", ".join(t.name for t in db.metadata.sorted_tables)
            db.session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
            db.session.commit()
        db.engine.dispose()


@pytest.fixture()
def client(app):
    return app.test_client()


# ---- Helpers that create test rows and return plain values ----

_phone_counter = iter(range(1000000, 9999999))


def new_phone():
    return f"078{next(_phone_counter)}"


# What a driver fills in on the driver page after signing up (besides a
# unique ID and licence number, which details_for() adds).
DRIVER_DETAILS = {"date_of_birth": "1990-05-14", "gender": "female",
                  "home_district": "Huye", "home_sector": "Ngoma"}


def details_for():
    """A full set of driver details with a unique ID and licence number."""
    return {**DRIVER_DETAILS, "national_id_number": new_national_id(),
            "license_number": f"TEST{new_phone()}"}


def new_national_id():
    """A different 16-digit number each time."""
    return f"119907{next(_phone_counter):010d}"


def register(client, role="passenger", **extra):
    body = {"full_name": "Test User", "phone": new_phone(), "password": PASSWORD, "role": role}
    body.update(extra)
    return client.post("/api/auth/register", json=body)


def auth_header(response):
    return {"Authorization": f"Bearer {response.get_json()['access_token']}"}


@pytest.fixture()
def passenger(client):
    return auth_header(register(client))


@pytest.fixture()
def bus(app):
    """Switch bus booking on (it is a future phase, off by default).

    Bus tests use this, so the bus code stays tested while it is hidden."""
    app.config["FEATURE_BUS_BOOKING"] = True


@pytest.fixture()
def make_trip(app, bus):
    """make_trip(seats=2, price=5000, hours_ahead=24, verified=True) -> trip_id

    Creating a bus trip makes a bus test, so this switches bus booking on."""

    def make(seats=2, price=5000, hours_ahead=24, origin="Kigali", destination="Huye",
             verified=True):
        with app.app_context():
            company = BusCompany(name="Test Bus Co", registration_number=f"TEST-{new_phone()}",
                                 is_verified=verified)
            trip = BusTrip(
                company=company,
                route=_route(origin, destination),
                departure_time=local_now() + timedelta(hours=hours_ahead),
                price_rwf=price,
                total_seats=seats,
                available_seats=seats,
            )
            db.session.add(trip)
            db.session.commit()
            return trip.trip_id

    return make


@pytest.fixture()
def make_offer(app):
    """make_offer(ride_type="shared", seats=3, price=4000, approved=True) -> offer_id"""

    def make(ride_type="shared", seats=3, price=4000, approved=True, hours_ahead=24,
             origin="Kigali", destination="Musanze"):
        with app.app_context():
            user = User(
                full_name="Test Driver",
                phone=f"+250{new_phone()[1:]}",
                password_hash="not-used",
                role="driver",
            )
            user.driver = Driver(license_number=f"TEST{new_phone()}", is_approved=approved)
            vehicle = Vehicle(driver=user.driver, plate_number=f"T{new_phone()[-6:]}",
                              model="Test car", seats=seats)
            offer = RideOffer(
                driver=user.driver,
                vehicle=vehicle,
                route=_route(origin, destination),
                ride_type=ride_type,
                departure_time=local_now() + timedelta(hours=hours_ahead),
                price=price,
                seats_available=seats,
            )
            db.session.add_all([user, offer])
            db.session.commit()
            return offer.offer_id

    return make


class FakeMomo:
    """Stands in for MTN MoMo in tests.

    After a request to pay, MoMo says PENDING until the test calls
    .answers("SUCCESSFUL") or .answers("FAILED", reason="APPROVAL_REJECTED").
    """

    def __init__(self):
        self.requests = []
        self.answer = {"status": "PENDING"}
        self.fail_requests = False
        self.status_checks = 0

    def request_to_pay(self, reference, amount, phone, external_id, message):
        from app.services.momo_client import MomoError

        if self.fail_requests:
            raise MomoError("MoMo could not be reached")
        self.requests.append({"reference": reference, "amount": amount, "phone": phone,
                              "external_id": external_id})

    def get_status(self, reference):
        self.status_checks += 1
        return self.answer

    def answers(self, status, **changes):
        """Make MoMo report this status for the last request to pay."""
        last = self.requests[-1]
        self.answer = {"status": status, "amount": str(last["amount"]), "currency": "EUR",
                       "externalId": str(last["external_id"]), **changes}


@pytest.fixture()
def momo(monkeypatch):
    from app.services import payment_service

    fake = FakeMomo()
    monkeypatch.setattr(payment_service, "get_payment_client", lambda: fake)
    return fake


@pytest.fixture()
def make_admin(app, client):
    """make_admin() -> auth headers for a new admin account."""

    def make():
        phone = new_phone()
        with app.app_context():
            db.session.add(User(full_name="Test Admin", phone=f"+250{phone[1:]}",
                                password_hash=generate_password_hash(PASSWORD), role="admin"))
            db.session.commit()
        login = client.post("/api/auth/login", json={"phone": phone, "password": PASSWORD})
        return auth_header(login)

    return make


def _route(origin, destination):
    route = db.session.query(Route).filter_by(origin=origin, destination=destination).first()
    return route or Route(origin=origin, destination=destination)


# The smallest file each check accepts: a PDF is recognised by "%PDF-".
PDF = b"%PDF-1.4\n%test document\n"


@pytest.fixture
def documents(app, client, tmp_path):
    """documents(headers, skip=()) does everything a driver needs for approval:
    fills in their details, then uploads every legal document (except the
    types in skip), each valid for a year."""
    app.config["DOCUMENT_DIR"] = str(tmp_path / "documents")
    from app import driver_documents

    expires = (local_now() + timedelta(days=365)).date().isoformat()

    def upload_all(headers, skip=()):
        filled = client.put("/api/drivers/details", json=details_for(), headers=headers)
        assert filled.status_code == 200, filled.get_json()
        for doc_type in driver_documents.TYPES:
            if doc_type in skip:
                continue
            response = client.post(
                f"/api/drivers/documents/{doc_type}",
                data={"document": (io.BytesIO(PDF), "doc.pdf"), "expires_on": expires},
                headers=headers, content_type="multipart/form-data",
            )
            assert response.status_code == 201, response.get_json()

    return upload_all


# What a driver fills in when registering a car (plate and seats vary).
CAR = {"model": "Toyota RAV4", "colour": "Blue", "year": 2019, "has_ac": True,
       "luggage": "medium"}
# The smallest file the photo check accepts as a JPEG.
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 32


@pytest.fixture()
def add_car(app, client, tmp_path):
    """add_car(headers, plate, seats=4, photo=True) -> the vehicle, registered
    with every detail and (by default) a photo, so its rides can be posted."""
    app.config["UPLOAD_DIR"] = str(tmp_path / "uploads")

    def add(headers, plate, seats=4, photo=True):
        response = client.post("/api/drivers/vehicles", headers=headers,
                               json={**CAR, "plate_number": plate, "seats": seats})
        assert response.status_code == 201, response.get_json()
        vehicle = response.get_json()["vehicle"]
        if photo:
            client.post(f"/api/drivers/vehicles/{vehicle['vehicle_id']}/photos", headers=headers,
                        data={"photo": (io.BytesIO(JPEG), "car.jpg")},
                        content_type="multipart/form-data")
        return vehicle

    return add


@pytest.fixture()
def ride(app, client, add_car):
    """ride(minutes_ahead=30, seats=3) -> (driver headers, offer_id), posted by an
    approved driver through the API."""

    def make(minutes_ahead=30, seats=3, price=4000):
        signup = register(client, role="driver")
        headers = auth_header(signup)
        with app.app_context():
            driver = db.session.get(Driver, signup.get_json()["user"]["driver"]["driver_id"])
            driver.is_approved = True
            db.session.commit()
        vehicle = add_car(headers, f"RA{signup.get_json()['user']['phone'][-5:]}", seats)
        departure = (local_now() + timedelta(minutes=minutes_ahead)).replace(microsecond=0)
        posted = client.post("/api/rides", headers=headers, json={
            "vehicle_id": vehicle["vehicle_id"], "origin": "Kigali", "destination": "Huye",
            "ride_type": "shared", "departure_time": departure.isoformat(), "price": price,
            "seats_available": seats, "pickup_point": "Nyabugogo bus park, gate 2"})
        assert posted.status_code == 201, posted.get_json()
        return headers, posted.get_json()["ride"]["offer_id"]

    return make
