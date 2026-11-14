from conftest import auth_header, register

from app.extensions import db
from app.models import BusCompany, BusTrip


def driver_id_of(response):
    return response.get_json()["user"]["driver"]["driver_id"]


def test_only_admins_can_use_admin_tools(client, passenger):
    driver = auth_header(register(client, role="driver"))

    for headers in (passenger, driver):
        assert client.get("/api/admin/drivers", headers=headers).status_code == 403
        assert client.post("/api/admin/drivers/1/approve", headers=headers).status_code == 403
        assert client.post("/api/admin/companies/1/verify", headers=headers).status_code == 403
    assert client.get("/api/admin/drivers").status_code == 401


def test_admin_approves_and_rejects_drivers(client, make_admin):
    admin = make_admin()
    first = driver_id_of(register(client, role="driver"))
    second = driver_id_of(register(client, role="driver"))

    pending = client.get("/api/admin/drivers?status=pending", headers=admin).get_json()["drivers"]
    approved = client.post(f"/api/admin/drivers/{first}/approve", headers=admin)
    rejected = client.post(f"/api/admin/drivers/{second}/reject", headers=admin)
    still_pending = client.get("/api/admin/drivers", headers=admin).get_json()["drivers"]

    assert {d["driver_id"] for d in pending} == {first, second}
    assert approved.get_json()["driver"]["status"] == "approved"
    assert rejected.get_json()["driver"]["status"] == "rejected"
    assert still_pending == []


def test_rejected_driver_rides_leave_search(client, make_admin, make_offer, app):
    admin = make_admin()
    make_offer(approved=True)
    with app.app_context():
        from app.models import Driver

        driver_id = db.session.query(Driver.driver_id).scalar()

    before = client.get("/api/rides?origin=Kigali&destination=Musanze").get_json()["rides"]
    client.post(f"/api/admin/drivers/{driver_id}/reject", headers=admin)
    after = client.get("/api/rides?origin=Kigali&destination=Musanze").get_json()["rides"]

    assert len(before) == 1
    assert after == []


def test_unverified_companies_are_hidden_until_verified(app, client, make_admin, make_trip,
                                                        passenger):
    admin = make_admin()
    trip_id = make_trip(verified=False)
    with app.app_context():
        company_id = db.session.get(BusTrip, trip_id).company_id

    hidden = client.get("/api/trips?origin=Kigali&destination=Huye").get_json()["trips"]
    direct = client.get(f"/api/trips/{trip_id}")
    booking = client.post("/api/bookings", json={"trip_id": trip_id}, headers=passenger)
    listed = client.get("/api/admin/companies", headers=admin).get_json()["companies"]
    client.post(f"/api/admin/companies/{company_id}/verify", headers=admin)
    shown = client.get("/api/trips?origin=Kigali&destination=Huye").get_json()["trips"]

    assert hidden == []
    assert direct.status_code == 404
    assert booking.status_code == 404
    assert [c["is_verified"] for c in listed] == [False]
    assert [t["trip_id"] for t in shown] == [trip_id]
    with app.app_context():
        assert db.session.get(BusCompany, company_id).is_verified is True


def test_create_admin_command(app, monkeypatch):
    monkeypatch.setenv("ADMIN_NAME", "Test Admin")
    monkeypatch.setenv("ADMIN_PHONE", "0789999999")
    monkeypatch.setenv("ADMIN_PASSWORD", "a-long-test-password")
    runner = app.test_cli_runner()

    first = runner.invoke(args=["create-admin"])
    again = runner.invoke(args=["create-admin"])
    monkeypatch.setenv("ADMIN_PHONE", "0789999998")
    monkeypatch.setenv("ADMIN_PASSWORD", "short")
    weak = runner.invoke(args=["create-admin"])

    assert "Admin account created" in first.output
    assert again.exit_code != 0 and "already exists" in again.output
    assert weak.exit_code != 0 and "at least 12" in weak.output
