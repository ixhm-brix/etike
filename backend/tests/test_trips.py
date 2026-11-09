from datetime import timedelta

from conftest import auth_header, register

from app.extensions import db
from app.models import Driver, User
from app.validation import local_now


def test_search_trips_by_route_and_date(client, make_trip):
    trip_id = make_trip(origin="Kigali", destination="Huye", hours_ahead=30)
    make_trip(origin="Kigali", destination="Musanze", hours_ahead=30)
    day = (local_now() + timedelta(hours=30)).date().isoformat()

    response = client.get(f"/api/trips?origin=Kigali&destination=Huye&date={day}")

    assert response.status_code == 200
    trips = response.get_json()["trips"]
    assert [t["trip_id"] for t in trips] == [trip_id]
    assert trips[0]["price_rwf"] == 5000
    assert trips[0]["company"]["name"]


def test_search_accepts_old_town_names(client, make_trip):
    trip_id = make_trip(origin="Kigali", destination="Huye")

    response = client.get("/api/trips?origin=nyabugogo&destination=Butare")

    assert [t["trip_id"] for t in response.get_json()["trips"]] == [trip_id]


def test_search_hides_full_and_past_trips(client, make_trip, passenger):
    full = make_trip(seats=1)
    client.post("/api/bookings", json={"trip_id": full}, headers=passenger)
    make_trip(hours_ahead=-2)

    response = client.get("/api/trips?origin=Kigali&destination=Huye")

    assert response.get_json()["trips"] == []


def test_search_other_date_is_empty(client, make_trip):
    make_trip(hours_ahead=24)
    far = (local_now() + timedelta(days=10)).date().isoformat()

    response = client.get(f"/api/trips?origin=Kigali&destination=Huye&date={far}")

    assert response.status_code == 200
    assert response.get_json()["trips"] == []


def test_search_validation(client):
    missing = client.get("/api/trips?origin=Kigali")
    unknown = client.get("/api/trips?origin=Kigali&destination=Atlantis")
    same = client.get("/api/trips?origin=Huye&destination=Huye")
    bad_date = client.get("/api/trips?origin=Kigali&destination=Huye&date=24/12/2026")

    for response in (missing, unknown, same, bad_date):
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "invalid_input"


def test_search_rides_by_type(client, make_offer):
    shared = make_offer(ride_type="shared")
    private = make_offer(ride_type="private")

    everything = client.get("/api/rides?origin=Kigali&destination=Musanze")
    only_private = client.get("/api/rides?origin=Kigali&destination=Musanze&type=private")
    bad_type = client.get("/api/rides?origin=Kigali&destination=Musanze&type=rental")

    assert {r["offer_id"] for r in everything.get_json()["rides"]} == {shared, private}
    assert [r["offer_id"] for r in only_private.get_json()["rides"]] == [private]
    assert bad_type.status_code == 400


def test_search_rides_hides_unapproved_drivers(client, make_offer):
    make_offer(approved=False)

    response = client.get("/api/rides?origin=Kigali&destination=Musanze")

    assert response.get_json()["rides"] == []


def test_approved_driver_posts_ride_that_shows_in_search(app, client):
    response = register(client, role="driver")
    driver = auth_header(response)
    with app.app_context():
        user = db.session.get(User, response.get_json()["user"]["user_id"])
        db.session.query(Driver).filter_by(user_id=user.user_id).update({"is_approved": True})
        db.session.commit()
    vehicle = client.post(
        "/api/drivers/vehicles",
        json={"plate_number": "rab 123 a", "model": "Toyota Noah", "seats": 6},
        headers=driver,
    ).get_json()["vehicle"]
    departure = (local_now() + timedelta(days=2)).replace(microsecond=0).isoformat()

    posted = client.post(
        "/api/rides",
        json={
            "vehicle_id": vehicle["vehicle_id"],
            "origin": "Rusizi",
            "destination": "Rubavu",
            "ride_type": "shared",
            "departure_time": departure,
            "price": 9000,
            "seats_available": 4,
        },
        headers=driver,
    )
    found = client.get("/api/rides?origin=Rusizi&destination=Rubavu")
    routes = client.get("/api/routes").get_json()["routes"]

    assert vehicle["plate_number"] == "RAB123A"
    assert posted.status_code == 201
    assert [r["seats_available"] for r in found.get_json()["rides"]] == [4]
    assert {"origin": "Rusizi", "destination": "Rubavu"}.items() <= routes[0].items()


def test_ride_seats_cannot_exceed_vehicle(app, client):
    response = register(client, role="driver")
    driver = auth_header(response)
    with app.app_context():
        db.session.query(Driver).update({"is_approved": True})
        db.session.commit()
    vehicle = client.post(
        "/api/drivers/vehicles",
        json={"plate_number": "RAC 456 B", "model": "Car", "seats": 4},
        headers=driver,
    ).get_json()["vehicle"]

    response = client.post(
        "/api/rides",
        json={
            "vehicle_id": vehicle["vehicle_id"],
            "origin": "Kigali",
            "destination": "Huye",
            "ride_type": "shared",
            "departure_time": "2099-01-01T08:00",
            "price": 5000,
            "seats_available": 9,
        },
        headers=driver,
    )

    assert response.status_code == 400
    assert "seats_available" in response.get_json()["error"]["fields"]


def test_places_list_kigali_first(client):
    places = client.get("/api/places").get_json()["places"]

    assert places[0] == "Kigali"
    assert len(places) == 28
    assert "Nyarugenge" not in places
