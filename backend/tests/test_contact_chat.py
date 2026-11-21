"""Where to meet and how to reach each other: the ride's meeting point,
phone numbers between passenger and driver, and chat per booking."""

from datetime import timedelta

from conftest import auth_header, register
from test_ride_trip import book

from app.extensions import db
from app.models import RideOffer


def test_new_rides_need_a_meeting_point(client, ride, passenger):
    driver, offer_id = ride()
    ride_seen = client.get(f"/api/rides/{offer_id}").get_json()["ride"]
    vehicles = client.get("/api/drivers/vehicles", headers=driver).get_json()["vehicles"]
    vehicle_id = vehicles[0]["vehicle_id"]

    missing = client.post("/api/rides", headers=driver, json={
        "vehicle_id": vehicle_id, "origin": "Kigali", "destination": "Huye",
        "ride_type": "shared", "departure_time": "2099-01-01T08:00", "price": 4000})

    assert ride_seen["pickup_point"] == "Nyabugogo bus park, gate 2"
    assert missing.status_code == 400 and "pickup_point" in missing.get_json()["error"]["fields"]


def test_phones_only_between_the_two_people_on_the_ride(client, ride, passenger):
    driver, offer_id = ride()
    booking_id = book(client, passenger, offer_id)

    mine = client.get(f"/api/bookings/{booking_id}", headers=passenger).get_json()["booking"]
    rides = client.get("/api/drivers/rides", headers=driver).get_json()["rides"]
    public = client.get(f"/api/rides/{offer_id}").get_json()["ride"]

    assert mine["driver_phone"].startswith("+2507")
    assert mine["pickup_point"] == "Nyabugogo bus park, gate 2"
    assert rides[0]["passengers"][0]["phone"].startswith("+2507")
    # Search results and ride details never show phone numbers.
    assert "phone" not in str(public)


def test_contact_closes_a_day_after_the_ride(app, client, ride, passenger):
    driver, offer_id = ride()
    booking_id = book(client, passenger, offer_id)
    with app.app_context():
        offer = db.session.get(RideOffer, offer_id)
        offer.departure_time -= timedelta(days=2)
        db.session.commit()

    mine = client.get(f"/api/bookings/{booking_id}", headers=passenger).get_json()["booking"]
    late = client.post(f"/api/bookings/{booking_id}/messages", json={"body": "Hello?"},
                       headers=passenger)
    history = client.get(f"/api/bookings/{booking_id}/messages", headers=passenger)

    assert mine["driver_phone"] is None
    assert late.status_code == 409 and late.get_json()["error"]["code"] == "conversation_closed"
    assert history.status_code == 200 and history.get_json()["can_send"] is False


def test_chat_between_passenger_and_driver(client, ride, passenger):
    driver, offer_id = ride()
    booking_id = book(client, passenger, offer_id)
    url = f"/api/bookings/{booking_id}/messages"

    sent = client.post(url, json={"body": "I'm at the gate, red jacket."}, headers=passenger)
    badge = client.get("/api/messages/unread", headers=driver).get_json()
    in_list = client.get("/api/drivers/rides", headers=driver).get_json()["rides"][0]
    opened = client.get(url, headers=driver).get_json()
    after = client.get("/api/messages/unread", headers=driver).get_json()
    client.post(url, json={"body": "Arriving in 5 minutes."}, headers=driver)
    seen_by_passenger = client.get(url, headers=passenger).get_json()

    assert sent.status_code == 201
    assert badge["total"] == 1 and badge["by_booking"] == {str(booking_id): 1}
    assert in_list["passengers"][0]["unread"] == 1
    assert opened["with"]["role"] == "passenger" and opened["messages"][0]["mine"] is False
    assert after["total"] == 0
    assert [(m["body"], m["mine"]) for m in seen_by_passenger["messages"]] == [
        ("I'm at the gate, red jacket.", True), ("Arriving in 5 minutes.", False)]
    assert seen_by_passenger["with"]["role"] == "driver"


def test_only_the_two_people_can_read_the_chat(client, ride, passenger):
    driver, offer_id = ride()
    booking_id = book(client, passenger, offer_id)
    stranger = auth_header(register(client))
    other_driver, _ = ride()
    url = f"/api/bookings/{booking_id}/messages"

    assert client.get(url, headers=stranger).status_code == 404
    assert client.get(url, headers=other_driver).status_code == 404
    assert client.post(url, json={"body": "hi"}, headers=stranger).status_code == 404
    assert client.post(url, json={"body": "  "}, headers=passenger).status_code == 400
    assert client.post(url, json={"body": "x" * 1001}, headers=passenger).status_code == 400
