"""Shared test setup.

Tests run on in-memory SQLite by default, or on PostgreSQL when
TEST_DATABASE_URL is set (as in CI). On PostgreSQL the schema comes from the
real migrations, so the tests also prove the migrations match the models.

All test data is created here or inside the tests. It is never committed as
seed data, and it only ever lives in the test database.
"""

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


def register(client, role="passenger", **extra):
    body = {"full_name": "Test User", "phone": new_phone(), "password": PASSWORD, "role": role}
    if role == "driver":
        body["license_number"] = f"TEST{new_phone()}"
    body.update(extra)
    return client.post("/api/auth/register", json=body)


def auth_header(response):
    return {"Authorization": f"Bearer {response.get_json()['access_token']}"}


@pytest.fixture()
def passenger(client):
    return auth_header(register(client))


@pytest.fixture()
def make_trip(app):
    """make_trip(seats=2, price=5000, hours_ahead=24, verified=True) -> trip_id"""

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


class FakeFlutterwave:
    """Stands in for Flutterwave in tests.

    Set .transaction to what verify_by_reference should return: None while
    the customer hasn't paid, or a dict like Flutterwave's `data`.
    """

    def __init__(self):
        self.charges = []
        self.transaction = None
        self.fail_charges = False

    def charge_rwanda_mobile_money(self, tx_ref, amount, phone, email, fullname,
                                   redirect_url=None):
        from app.services.flutterwave_client import FlutterwaveError

        if self.fail_charges:
            raise FlutterwaveError("Flutterwave could not be reached")
        self.charges.append({"tx_ref": tx_ref, "amount": amount, "phone": phone,
                             "email": email})
        return f"https://checkout.example.test/{tx_ref}"

    def verify_by_reference(self, tx_ref):
        return self.transaction

    def pays(self, status="successful", **changes):
        """Make the last charge come back with this status."""
        charge = self.charges[-1]
        self.transaction = {"tx_ref": charge["tx_ref"], "amount": charge["amount"],
                            "currency": "RWF", "status": status, **changes}


@pytest.fixture()
def flutterwave(monkeypatch):
    from app.services import payment_service

    fake = FakeFlutterwave()
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
