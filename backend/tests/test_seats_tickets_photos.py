"""Choosing seats on a seat map, QR tickets, and car photos."""

import io
import threading
import time

import pytest
from conftest import CAR, auth_header, is_postgres, register

from app.extensions import db
from app.models import BookingSeat, BusTrip, Driver, RideOffer
from app.services import booking_service
from app.services.seat_service import layout

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def book(client, headers, **body):
    return client.post("/api/bookings", json=body, headers=headers)


# ---- Seats ----

def test_layouts():
    assert layout(4, "car") == [["driver", 1], [2, 3, 4]]
    assert layout(7, "car") == [["driver", 1], [2, 3, 4], [5, 6, 7]]
    bus = layout(30, "bus")
    assert bus[0][0] == "driver"
    assert sorted(n for row in bus for n in row if isinstance(n, int)) == list(range(1, 31))


def test_choose_seats_on_a_bus(app, client, make_trip, passenger):
    trip_id = make_trip(seats=10, price=3000)

    response = book(client, passenger, trip_id=trip_id, seat_numbers=[7, 3])
    seats = client.get(f"/api/trips/{trip_id}/seats").get_json()

    booking = response.get_json()["booking"]
    assert response.status_code == 201
    assert booking["seat_numbers"] == [3, 7]
    assert booking["seats_booked"] == 2
    assert booking["total_price"] == 6000
    assert seats["taken"] == [3, 7]
    assert seats["total"] == 10
    assert seats["rows"][0][0] == "driver"


def test_seat_already_taken(client, make_trip, passenger):
    trip_id = make_trip(seats=10)
    book(client, passenger, trip_id=trip_id, seat_numbers=[5])
    other = auth_header(register(client))

    response = book(client, other, trip_id=trip_id, seat_numbers=[4, 5])

    assert response.status_code == 409
    assert "Seat 5" in response.get_json()["error"]["message"]


def test_bad_seat_choices(client, make_trip, passenger):
    trip_id = make_trip(seats=10)

    assert book(client, passenger, trip_id=trip_id, seat_numbers=[11]).status_code == 400
    assert book(client, passenger, trip_id=trip_id, seat_numbers=[2, 2]).status_code == 400
    assert book(client, passenger, trip_id=trip_id, seat_numbers=[]).status_code == 400
    assert book(client, passenger, trip_id=trip_id, seat_numbers="1").status_code == 400


def test_without_a_choice_the_lowest_free_seats_are_given(client, make_trip, passenger):
    trip_id = make_trip(seats=10)
    book(client, passenger, trip_id=trip_id, seat_numbers=[1, 3])

    booking = book(client, passenger, trip_id=trip_id, seats=2).get_json()["booking"]

    assert booking["seat_numbers"] == [2, 4]


def test_cancelling_frees_the_seats(app, client, make_trip, passenger):
    trip_id = make_trip(seats=10)
    booking = book(client, passenger, trip_id=trip_id, seat_numbers=[4]).get_json()["booking"]

    client.post(f"/api/bookings/{booking['booking_id']}/cancel", headers=passenger)
    seats = client.get(f"/api/trips/{trip_id}/seats").get_json()
    again = book(client, passenger, trip_id=trip_id, seat_numbers=[4])

    assert seats["taken"] == []
    assert again.status_code == 201
    mine = client.get("/api/bookings/mine", headers=passenger).get_json()["bookings"]
    # The cancelled booking still remembers which seat it had.
    assert [b["seat_numbers"] for b in mine] == [[4], [4]]


def test_shared_ride_seats(client, make_offer, passenger):
    offer_id = make_offer(ride_type="shared", seats=4)

    booking = book(client, passenger, offer_id=offer_id, seat_numbers=[1, 4]).get_json()["booking"]
    seats = client.get(f"/api/rides/{offer_id}/seats").get_json()

    assert booking["seat_numbers"] == [1, 4]
    assert seats["taken"] == [1, 4]
    assert seats["rows"] == [["driver", 1], [2, 3, 4]]


def test_private_ride_takes_every_seat(client, make_offer, passenger):
    offer_id = make_offer(ride_type="private", seats=4)

    booking = book(client, passenger, offer_id=offer_id, seat_numbers=[2]).get_json()["booking"]

    assert booking["seat_numbers"] == [1, 2, 3, 4]


def test_seats_the_driver_did_not_offer_are_not_bookable(app, client, make_offer, passenger):
    offer_id = make_offer(ride_type="shared", seats=4)
    with app.app_context():
        db.session.get(RideOffer, offer_id).seats_available = 2  # offers 2 of 4
        db.session.commit()

    seats = client.get(f"/api/rides/{offer_id}/seats").get_json()
    response = book(client, passenger, offer_id=offer_id, seat_numbers=[4])

    assert seats["taken"] == [3, 4]
    assert response.status_code == 409


def test_two_people_choosing_the_same_seat(app, make_trip, monkeypatch):
    """Like the last-seat test, but both choose seat 7 of 10 at once."""
    if not is_postgres(app):
        pytest.skip("Row locks need PostgreSQL; SQLite has no SELECT ... FOR UPDATE.")
    trip_id = make_trip(seats=10)
    setup = app.test_client()
    tokens = [auth_header(register(setup)) for _ in range(2)]
    original = booking_service._locked

    def slow_locked(model, pk):
        row = original(model, pk)
        time.sleep(0.5)
        return row

    monkeypatch.setattr(booking_service, "_locked", slow_locked)
    start, statuses = threading.Barrier(2), []

    def attempt(headers):
        client = app.test_client()
        start.wait()
        statuses.append(book(client, headers, trip_id=trip_id, seat_numbers=[7]).status_code)

    threads = [threading.Thread(target=attempt, args=(t,)) for t in tokens]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(statuses) == [201, 409]
    with app.app_context():
        assert db.session.query(BookingSeat).filter_by(trip_id=trip_id).count() == 1
        assert db.session.get(BusTrip, trip_id).available_seats == 9


# ---- Tickets ----

def paid_ticket(client, passenger, momo, trip_id, seats=(2,)):
    response = book(client, passenger, trip_id=trip_id, seat_numbers=list(seats))
    booking = response.get_json()["booking"]
    client.post("/api/payments", json={"booking_id": booking["booking_id"]}, headers=passenger)
    momo.answers("SUCCESSFUL")
    client.get(f"/api/payments/{booking['booking_id']}/status", headers=passenger)
    return booking["booking_id"]


def verify_link(client, passenger, booking_id):
    ticket = client.get(f"/api/bookings/{booking_id}/ticket", headers=passenger).get_json()
    return ticket["verify_url"].split("t=")[1]


def test_ticket_and_qr_code(client, make_trip, passenger, momo):
    booking_id = paid_ticket(client, passenger, momo, make_trip(seats=10), seats=(2, 3))

    ticket = client.get(f"/api/bookings/{booking_id}/ticket", headers=passenger)
    qr = client.get(f"/api/bookings/{booking_id}/ticket/qr", headers=passenger)

    assert ticket.status_code == 200
    assert "/verify.html?t=" in ticket.get_json()["verify_url"]
    assert ticket.get_json()["booking"]["seat_numbers"] == [2, 3]
    assert qr.status_code == 200
    assert qr.mimetype == "image/svg+xml"
    assert b"<svg" in qr.data


def test_scanning_a_valid_ticket(client, make_trip, passenger, momo):
    booking_id = paid_ticket(client, passenger, momo, make_trip(seats=10))
    token = verify_link(client, passenger, booking_id)

    result = client.get(f"/api/tickets/verify?t={token}").get_json()

    assert result["valid"] is True
    assert result["ticket"]["booking_id"] == booking_id
    assert result["ticket"]["seat_numbers"] == [2]
    assert "phone" not in result["ticket"]


def test_cancelled_ticket_is_not_valid(client, make_trip, passenger, momo):
    booking_id = paid_ticket(client, passenger, momo, make_trip(seats=10, hours_ahead=24))
    token = verify_link(client, passenger, booking_id)

    client.post(f"/api/bookings/{booking_id}/cancel", headers=passenger)
    result = client.get(f"/api/tickets/verify?t={token}").get_json()

    assert result["valid"] is False
    assert "cancelled" in result["reason"]


def test_forged_ticket_is_not_valid(client):
    for token in ("", "abc", "eyJiIjoxfQ.forged-signature"):
        result = client.get(f"/api/tickets/verify?t={token}").get_json()
        assert result["valid"] is False


def test_no_ticket_before_payment_or_for_others(client, make_trip, passenger):
    booking = book(client, passenger, trip_id=make_trip()).get_json()["booking"]
    stranger = auth_header(register(client))

    unpaid = client.get(f"/api/bookings/{booking['booking_id']}/ticket", headers=passenger)
    other = client.get(f"/api/bookings/{booking['booking_id']}/ticket", headers=stranger)

    assert unpaid.status_code == 409
    assert other.status_code == 404


def test_rides_have_no_ticket(client, make_offer, passenger):
    # Like a taxi app: the booking is the proof, and the driver sees it.
    booking = book(client, passenger, offer_id=make_offer()).get_json()["booking"]

    assert client.get(f"/api/bookings/{booking['booking_id']}/ticket",
                      headers=passenger).status_code == 404


# ---- Car photos ----

@pytest.fixture()
def driver_with_car(app, client, tmp_path):
    app.config["UPLOAD_DIR"] = str(tmp_path)
    response = register(client, role="driver")
    headers = auth_header(response)
    vehicle = client.post("/api/drivers/vehicles", headers=headers,
                          json={**CAR, "plate_number": "RAB 123 A", "seats": 4})
    return headers, vehicle.get_json()["vehicle"]["vehicle_id"], tmp_path


def upload(client, headers, vehicle_id, data, name="car.jpg"):
    return client.post(f"/api/drivers/vehicles/{vehicle_id}/photos", headers=headers,
                       data={"photo": (io.BytesIO(data), name)},
                       content_type="multipart/form-data")


def test_upload_and_delete_photo(client, driver_with_car):
    headers, vehicle_id, folder = driver_with_car

    response = upload(client, headers, vehicle_id, JPEG)

    assert response.status_code == 201
    photo = response.get_json()["photo"]
    assert photo["url"].startswith("/uploads/") and photo["url"].endswith(".jpg")
    assert len(list(folder.iterdir())) == 1

    gone = client.delete(f"/api/drivers/vehicles/{vehicle_id}/photos/{photo['photo_id']}",
                         headers=headers)
    assert gone.get_json()["vehicle"]["photos"] == []
    assert list(folder.iterdir()) == []


def test_only_real_images_are_accepted(client, driver_with_car):
    headers, vehicle_id, folder = driver_with_car

    script = upload(client, headers, vehicle_id, b"<script>alert(1)</script>", "car.jpg")
    svg = upload(client, headers, vehicle_id, b"<svg xmlns='http://www.w3.org/2000/svg'/>",
                 "car.svg")
    png = upload(client, headers, vehicle_id, PNG, "anything.txt")

    assert script.status_code == 400
    assert svg.status_code == 400
    # Judged by content, not by name: this is a PNG.
    assert png.status_code == 201
    assert png.get_json()["photo"]["url"].endswith(".png")


def test_photo_limits(client, driver_with_car):
    headers, vehicle_id, _ = driver_with_car

    too_big = upload(client, headers, vehicle_id, JPEG + b"\x00" * (3 * 1024 * 1024))
    for _ in range(3):
        upload(client, headers, vehicle_id, JPEG)
    fourth = upload(client, headers, vehicle_id, JPEG)

    assert too_big.status_code == 400
    assert fourth.status_code == 409


def test_only_the_cars_driver_can_add_photos(client, driver_with_car, passenger):
    _, vehicle_id, _ = driver_with_car
    other_driver = auth_header(register(client, role="driver"))

    assert upload(client, other_driver, vehicle_id, JPEG).status_code == 404
    assert upload(client, passenger, vehicle_id, JPEG).status_code == 403


def test_photos_show_on_rides(app, client, driver_with_car):
    headers, vehicle_id, _ = driver_with_car
    upload(client, headers, vehicle_id, JPEG)
    with app.app_context():
        db.session.query(Driver).update({"is_approved": True})
        db.session.commit()
    client.post("/api/rides", headers=headers, json={
        "vehicle_id": vehicle_id, "origin": "Kigali", "destination": "Huye",
        "ride_type": "shared", "departure_time": "2099-01-01T08:00", "price": 5000,
        "pickup_point": "Nyabugogo bus park, gate 2"})

    ride = client.get("/api/rides?origin=Kigali&destination=Huye").get_json()["rides"][0]

    assert len(ride["vehicle"]["photos"]) == 1


def test_car_needs_details_and_a_photo_before_rides(app, client, add_car):
    from app.models import Driver

    signup = register(client, role="driver")
    headers = auth_header(signup)
    with app.app_context():
        driver_id = signup.get_json()["user"]["driver"]["driver_id"]
        db.session.get(Driver, driver_id).is_approved = True
        db.session.commit()
    missing = client.post("/api/drivers/vehicles", headers=headers,
                          json={"plate_number": "RAD 111 A", "model": "Toyota Vitz", "seats": 4})
    no_photo = add_car(headers, "RAD 222 B", photo=False)
    ride = {"origin": "Kigali", "destination": "Huye", "ride_type": "private",
            "departure_time": "2099-01-01T08:00", "price": 30000,
            "pickup_point": "Nyabugogo bus park, gate 2"}

    refused = client.post("/api/rides", headers=headers,
                          json={**ride, "vehicle_id": no_photo["vehicle_id"]})
    fixed = client.put(f"/api/drivers/vehicles/{no_photo['vehicle_id']}", headers=headers,
                       json={**CAR, "colour": "white", "seats": 4})
    car = add_car(headers, "RAD 333 C")
    posted = client.post("/api/rides", headers=headers,
                         json={**ride, "vehicle_id": car["vehicle_id"]})
    shown = client.get(f"/api/rides/{posted.get_json()['ride']['offer_id']}").get_json()["ride"]

    assert missing.status_code == 400 and "has_ac" in missing.get_json()["error"]["fields"]
    assert no_photo["complete"] is False
    assert refused.status_code == 409
    assert refused.get_json()["error"]["code"] == "vehicle_incomplete"
    assert fixed.get_json()["vehicle"]["colour"] == "White"
    assert posted.status_code == 201
    assert {k: shown["vehicle"][k] for k in ("colour", "year", "has_ac", "luggage", "seats")} == {
        "colour": "Blue", "year": 2019, "has_ac": True, "luggage": "medium", "seats": 4}
    assert "plate_number" not in shown["vehicle"]  # only booked passengers see the plate
