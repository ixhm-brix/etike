"""After signing up, a driver fills in their official details (as on their
national ID and licence). Only the driver and admins see them; approval
needs them."""

from conftest import auth_header, details_for, new_national_id, register

from app.extensions import db
from app.models import Driver


def new_driver(client):
    """(auth headers, driver_id) of a driver who has only signed up."""
    response = register(client, role="driver")
    return auth_header(response), response.get_json()["user"]["driver"]["driver_id"]


def put_details(client, headers, **change):
    return client.put("/api/drivers/details", json={**details_for(), **change}, headers=headers)


def test_new_driver_has_no_details_yet(client):
    headers, _ = new_driver(client)

    body = client.get("/api/drivers/documents", headers=headers).get_json()

    assert set(body["details"].values()) == {None}
    assert "personal details" in body["problems"][0]


def test_every_detail_is_needed(client):
    headers, _ = new_driver(client)
    for field in details_for():
        response = put_details(client, headers, **{field: ""})

        assert response.status_code == 400, field
        assert field in response.get_json()["error"]["fields"]


def test_details_are_checked(client):
    headers, _ = new_driver(client)
    bad = [
        {"national_id_number": "12345"},
        {"date_of_birth": "2015-06-01"},  # under 18
        {"gender": "unknown"},
        {"home_district": "Atlantis"},
        {"license_number": "x"},
    ]
    for change in bad:
        assert put_details(client, headers, **change).status_code == 400, change


def test_id_and_licence_numbers_are_unique(client):
    first, _ = new_driver(client)
    second, _ = new_driver(client)
    number = new_national_id()
    put_details(client, first, national_id_number=number, license_number="RW 123 456")

    # Typed with spaces, it is still the same number.
    spaced = " ".join([number[:1], number[1:5], number[5:]])
    same_id = put_details(client, second, national_id_number=spaced)
    same_licence = put_details(client, second, license_number="rw123456")

    assert same_id.status_code == 409
    assert same_id.get_json()["error"]["code"] == "national_id_taken"
    assert same_licence.status_code == 409
    assert same_licence.get_json()["error"]["code"] == "license_taken"


def test_details_stay_private(client, make_admin):
    headers, driver_id = new_driver(client)
    put_details(client, headers)

    me = client.get("/api/auth/me", headers=headers).get_json()["user"]
    own = client.get("/api/drivers/documents", headers=headers).get_json()["details"]
    admin_view = client.get("/api/admin/drivers", headers=make_admin()).get_json()["drivers"]

    # What /me returns is kept in the browser, so it holds none of them.
    assert "national_id_number" not in str(me)
    assert own["gender"] == "female" and own["home_district"] == "Huye"
    assert next(d for d in admin_view if d["driver_id"] == driver_id)["details"] == own


def test_driver_corrects_details_until_approved(client, make_admin, documents):
    headers, driver_id = new_driver(client)
    documents(headers)

    changed = put_details(client, headers, home_sector="Tumba")
    client.post(f"/api/admin/drivers/{driver_id}/approve", headers=make_admin())
    locked = put_details(client, headers)

    assert changed.status_code == 200
    assert changed.get_json()["details"]["home_sector"] == "Tumba"
    assert locked.status_code == 409


def test_approval_needs_details(client, app, documents, make_admin):
    headers, driver_id = new_driver(client)
    documents(headers)
    with app.app_context():
        # A driver who signed up before details were asked for.
        db.session.get(Driver, driver_id).national_id_number = None
        db.session.commit()

    response = client.post(f"/api/admin/drivers/{driver_id}/approve", headers=make_admin())

    assert response.status_code == 409
    assert "personal details" in response.get_json()["error"]["message"]
