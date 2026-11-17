"""Bus booking is a future phase: with FEATURE_BUS_BOOKING off (the default),
everything bus-specific is unavailable and only rides are offered. The bus
code itself is still tested elsewhere, with the `bus` fixture."""

from datetime import timedelta

from conftest import new_phone

from app.extensions import db
from app.models import BusCompany, BusTrip, Route
from app.validation import local_now


def hidden_bus_trip(app):
    """A bus trip in the database while bus booking is switched off."""
    with app.app_context():
        trip = BusTrip(
            company=BusCompany(name="Test Bus Co", registration_number=f"TEST-{new_phone()}",
                               is_verified=True),
            route=Route(origin="Kigali", destination="Huye"),
            departure_time=local_now() + timedelta(days=1),
            price_rwf=5000, total_seats=30, available_seats=30,
        )
        db.session.add(trip)
        db.session.commit()
        return trip.trip_id


def test_off_by_default(app):
    assert app.config["FEATURE_BUS_BOOKING"] is False


def test_config_tells_the_website(client, app):
    off = client.get("/api/config").get_json()
    app.config["FEATURE_BUS_BOOKING"] = True
    on = client.get("/api/config").get_json()

    assert off["features"]["bus_booking"] is False
    assert on["features"]["bus_booking"] is True


def test_bus_search_returns_404(app, client):
    trip_id = hidden_bus_trip(app)

    for path in ("/api/trips?origin=Kigali&destination=Huye", f"/api/trips/{trip_id}",
                 f"/api/trips/{trip_id}/seats"):
        response = client.get(path)
        assert response.status_code == 404, path
        assert response.get_json()["error"]["message"] == "Bus booking is not available yet."


def test_bus_booking_returns_400(app, client, passenger):
    trip_id = hidden_bus_trip(app)

    by_trip = client.post("/api/bookings", json={"trip_id": trip_id}, headers=passenger)
    by_type = client.post("/api/bookings", json={"booking_type": "bus"}, headers=passenger)

    for response in (by_trip, by_type):
        assert response.status_code == 400
        assert response.get_json()["error"]["message"] == "Bus booking is not available yet."
    with app.app_context():
        assert db.session.get(BusTrip, trip_id).available_seats == 30


def test_search_returns_only_rides(app, client, make_offer):
    hidden_bus_trip(app)
    offer_id = make_offer(origin="Kigali", destination="Huye")

    rides = client.get("/api/rides?origin=Kigali&destination=Huye").get_json()["rides"]
    trips = client.get("/api/trips?origin=Kigali&destination=Huye")

    assert [r["offer_id"] for r in rides] == [offer_id]
    assert trips.status_code == 404


def test_admin_company_tools_return_404(app, client, make_admin):
    admin = make_admin()

    assert client.get("/api/admin/companies", headers=admin).status_code == 404
    assert client.post("/api/admin/companies/1/verify", headers=admin).status_code == 404


def test_rides_still_work(client, make_offer, passenger):
    offer_id = make_offer()

    response = client.post("/api/bookings", json={"offer_id": offer_id, "seats": 2},
                           headers=passenger)

    assert response.status_code == 201
    assert response.get_json()["booking"]["status"] == "confirmed"
