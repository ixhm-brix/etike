"""A ride like a taxi app: the driver starts and ends it, then each
passenger pays with MoMo and the driver sees the payment come in."""

from datetime import timedelta

from conftest import auth_header, register


def book(client, passenger, offer_id, seats=1):
    response = client.post("/api/bookings", json={"offer_id": offer_id, "seats": seats},
                           headers=passenger)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["booking"]["booking_id"]


def start(client, driver, offer_id):
    return client.post(f"/api/rides/{offer_id}/start", headers=driver)


def end(client, driver, offer_id):
    return client.post(f"/api/rides/{offer_id}/end", headers=driver)


def pay(client, passenger, booking_id):
    return client.post("/api/payments", json={"booking_id": booking_id, "phone": "0781234567"},
                       headers=passenger)


def booking_of(client, passenger, booking_id):
    return client.get(f"/api/bookings/{booking_id}", headers=passenger).get_json()["booking"]


def test_full_trip_start_end_pay(client, ride, passenger, momo):
    driver, offer_id = ride(price=4000)
    booking_id = book(client, passenger, offer_id, seats=2)

    started = start(client, driver, offer_id)
    during = booking_of(client, passenger, booking_id)
    ended = end(client, driver, offer_id)
    after = booking_of(client, passenger, booking_id)
    paying = pay(client, passenger, booking_id)
    momo.answers("SUCCESSFUL")
    client.get(f"/api/payments/{booking_id}/status", headers=passenger)
    rides = client.get("/api/drivers/rides", headers=driver).get_json()["rides"]

    assert started.get_json()["ride"]["progress"] == "in_progress"
    assert during["ride_progress"] == "in_progress" and during["can_pay"] is False
    assert ended.get_json()["ride"]["progress"] == "ended"
    assert after["can_pay"] is True
    assert paying.status_code == 201
    assert momo.requests[-1]["amount"] == 8000  # the server's price, 2 seats
    mine = next(r for r in rides if r["offer_id"] == offer_id)
    assert mine["passengers"][0]["payment_status"] == "success"
    assert mine["paid"] == mine["to_collect"] == 8000
    assert booking_of(client, passenger, booking_id)["can_pay"] is False


def test_failed_ride_payment_can_be_tried_again(client, ride, passenger, momo):
    driver, offer_id = ride()
    booking_id = book(client, passenger, offer_id)
    start(client, driver, offer_id)
    end(client, driver, offer_id)

    pay(client, passenger, booking_id)
    momo.answers("FAILED", reason="APPROVAL_REJECTED")
    client.get(f"/api/payments/{booking_id}/status", headers=passenger)
    failed = booking_of(client, passenger, booking_id)
    again = pay(client, passenger, booking_id)

    # A failed payment never cancels a ride that already happened.
    assert failed["status"] == "confirmed" and failed["can_pay"] is True
    assert again.status_code == 201
    assert len(momo.requests) == 2


def test_ride_rules(client, ride, passenger):
    early_driver, early_offer = ride(minutes_ahead=180)
    driver, offer_id = ride()

    too_early = start(client, early_driver, early_offer)
    nobody = start(client, driver, offer_id)
    not_started = end(client, driver, offer_id)

    assert too_early.get_json()["error"]["code"] == "too_early"
    assert nobody.get_json()["error"]["code"] == "no_passengers"
    assert not_started.get_json()["error"]["code"] == "not_started"


def test_only_the_rides_own_driver_can_start_it(client, ride, passenger):
    driver, offer_id = ride()
    other_driver, _ = ride()
    book(client, passenger, offer_id)

    assert start(client, other_driver, offer_id).status_code == 404
    assert start(client, passenger, offer_id).status_code == 403
    assert start(client, driver, offer_id).status_code == 200
    assert start(client, driver, offer_id).get_json()["error"]["code"] == "already_started"


def test_started_ride_cannot_be_cancelled(app, client, ride, passenger):
    driver, offer_id = ride()
    booking_id = book(client, passenger, offer_id)
    start(client, driver, offer_id)

    response = client.post(f"/api/bookings/{booking_id}/cancel", headers=passenger)

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "ride_started"


# ---- Where the ride went (the driver's phone location) ----

KIGALI = {"lat": -1.9441, "lng": 30.0619, "accuracy": 12}
MUHANGA = {"lat": -2.085, "lng": 29.756, "accuracy": 20}
HUYE = {"lat": -2.5967, "lng": 29.7394, "accuracy": 15}


def test_trip_is_recorded_from_start_to_end(client, ride, passenger, make_admin, monkeypatch):
    from app.services import ride_service

    monkeypatch.setattr(ride_service, "MIN_GAP", timedelta(0))
    driver, offer_id = ride()
    book(client, passenger, offer_id)

    client.post(f"/api/rides/{offer_id}/start", json=KIGALI, headers=driver)
    sent = client.post(f"/api/rides/{offer_id}/locations", json=MUHANGA, headers=driver)
    client.post(f"/api/rides/{offer_id}/end", json=HUYE, headers=driver)
    viewers = {"driver": driver, "passenger": passenger, "admin": make_admin()}
    seen_by = {who: client.get(f"/api/rides/{offer_id}/track", headers=h)
               for who, h in viewers.items()}

    assert sent.status_code == 201
    record = seen_by["driver"].get_json()
    assert [p["kind"] for p in record["points"]] == ["start", "track", "end"]
    assert record["points"][0]["lat"] == KIGALI["lat"]
    assert 70 < record["distance_km"] < 120  # Kigali, Muhanga, Huye as the crow flies
    assert record["started_at"] and record["ended_at"]
    assert seen_by["passenger"].status_code == seen_by["admin"].status_code == 200


def test_positions_are_spaced_out(client, ride, passenger):
    driver, offer_id = ride()
    book(client, passenger, offer_id)
    client.post(f"/api/rides/{offer_id}/start", json=KIGALI, headers=driver)

    # Right after the start point: too soon, skipped (the phone sends ~every 30 s).
    too_soon = client.post(f"/api/rides/{offer_id}/locations", json=MUHANGA, headers=driver)

    assert too_soon.status_code == 200 and too_soon.get_json()["saved"] is False


def test_location_rules(client, ride, passenger):
    driver, offer_id = ride()
    book(client, passenger, offer_id)

    before_start = client.post(f"/api/rides/{offer_id}/locations", json=KIGALI, headers=driver)
    abroad = client.post(f"/api/rides/{offer_id}/start", headers=driver,
                         json={"lat": 48.85, "lng": 2.35})  # Paris
    vague = client.post(f"/api/rides/{offer_id}/start", headers=driver,
                        json={**KIGALI, "accuracy": 5000})
    no_location = client.post(f"/api/rides/{offer_id}/start", headers=driver)

    assert before_start.get_json()["error"]["code"] == "ride_not_on"
    assert abroad.status_code == 400 and vague.status_code == 400
    # Location is optional: a driver who doesn't share it can still drive.
    assert no_location.status_code == 200


def test_only_people_on_the_ride_see_where_it_went(client, ride, passenger):
    driver, offer_id = ride()
    book(client, passenger, offer_id)
    other_passenger = auth_header(register(client))
    other_driver, _ = ride()

    assert client.get(f"/api/rides/{offer_id}/track", headers=other_passenger).status_code == 404
    assert client.get(f"/api/rides/{offer_id}/track", headers=other_driver).status_code == 404
    assert client.get(f"/api/rides/{offer_id}/track").status_code == 401
