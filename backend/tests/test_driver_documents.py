"""Drivers upload their legal documents; admins approve only complete sets."""

import io
from datetime import timedelta
from pathlib import Path

import pytest
from conftest import PDF, auth_header, register

from app.extensions import db
from app.models import Driver
from app.validation import local_now

NEXT_YEAR = (local_now() + timedelta(days=365)).date().isoformat()


@pytest.fixture
def driver(client, documents):
    """(auth headers, driver_id) of a new, unapproved driver."""
    response = register(client, role="driver")
    return auth_header(response), response.get_json()["user"]["driver"]["driver_id"]


def upload(client, headers, doc_type="driving_licence", data=PDF, expires_on=NEXT_YEAR):
    form = {"document": (io.BytesIO(data), "file")}
    if expires_on:
        form["expires_on"] = expires_on
    return client.post(f"/api/drivers/documents/{doc_type}", data=form, headers=headers,
                       content_type="multipart/form-data")


def test_new_driver_sees_every_document_missing(client, driver):
    headers, _ = driver

    body = client.get("/api/drivers/documents", headers=headers).get_json()

    assert [d["type"] for d in body["documents"]] == [
        "national_id", "driving_licence", "rura_authorisation",
        "vehicle_registration", "insurance", "inspection",
    ]
    assert not any(d["uploaded"] for d in body["documents"])
    assert body["complete"] is False
    assert len(body["problems"]) == 7  # the details, then the 6 documents


def test_upload_checks_content_size_and_expiry(client, driver):
    headers, _ = driver

    script = upload(client, headers, data=b"<script>alert(1)</script>")
    too_big = upload(client, headers, data=PDF + b"x" * (5 * 1024 * 1024))
    no_expiry = upload(client, headers, expires_on=None)
    expired = upload(client, headers, expires_on="2020-01-01")
    unknown = upload(client, headers, doc_type="passport")

    assert script.status_code == 400 and "document" in script.get_json()["error"]["fields"]
    assert too_big.status_code == 400
    assert no_expiry.status_code == 400 and "expires_on" in no_expiry.get_json()["error"]["fields"]
    assert expired.status_code == 400
    assert unknown.status_code == 404


def test_national_id_needs_no_expiry_and_upload_replaces(client, driver, app):
    headers, _ = driver

    first = upload(client, headers, doc_type="national_id", expires_on=None)
    jpeg = b"\xff\xd8\xff\xe0" + b"0" * 20
    second = upload(client, headers, doc_type="national_id", data=jpeg, expires_on=None)
    files = list(Path(app.config["DOCUMENT_DIR"]).iterdir())

    assert first.status_code == second.status_code == 201
    assert len(files) == 1 and files[0].suffix == ".jpg"  # the old file is gone


def test_admin_cannot_approve_until_every_document_is_in(client, driver, documents, make_admin):
    headers, driver_id = driver
    admin = make_admin()
    documents(headers, skip=("rura_authorisation",))

    refused = client.post(f"/api/admin/drivers/{driver_id}/approve", headers=admin)
    documents(headers)
    approved = client.post(f"/api/admin/drivers/{driver_id}/approve", headers=admin)

    assert refused.status_code == 409
    assert refused.get_json()["error"]["code"] == "documents_incomplete"
    assert "RURA" in refused.get_json()["error"]["message"]
    assert approved.status_code == 200


def test_expired_document_blocks_approval(client, driver, documents, make_admin, app):
    headers, driver_id = driver
    documents(headers)
    with app.app_context():
        doc = next(d for d in db.session.get(Driver, driver_id).documents
                   if d.doc_type == "insurance")
        doc.expires_on = (local_now() - timedelta(days=1)).date()
        db.session.commit()

    response = client.post(f"/api/admin/drivers/{driver_id}/approve", headers=make_admin())

    assert response.status_code == 409
    assert "Expired" in response.get_json()["error"]["message"]


def test_only_the_driver_and_admins_can_open_a_document(client, driver, make_admin):
    headers, driver_id = driver
    upload(client, headers)
    other_driver = auth_header(register(client, role="driver"))
    passenger = auth_header(register(client))
    path = f"/api/admin/drivers/{driver_id}/documents/driving_licence/file"

    own = client.get("/api/drivers/documents/driving_licence/file", headers=headers)
    by_admin = client.get(path, headers=make_admin())

    assert own.status_code == 200 and own.data == PDF
    assert own.headers["Cache-Control"] == "no-store"
    assert by_admin.status_code == 200 and by_admin.mimetype == "application/pdf"
    assert client.get(path, headers=passenger).status_code == 403
    assert client.get(path, headers=other_driver).status_code == 403
    assert client.get(path).status_code == 401
    other_own = client.get("/api/drivers/documents/driving_licence/file", headers=other_driver)
    assert other_own.status_code == 404


def test_rejection_reason_reaches_driver_and_new_upload_resubmits(client, driver, make_admin):
    headers, driver_id = driver
    admin = make_admin()

    client.post(f"/api/admin/drivers/{driver_id}/reject",
                json={"reason": "Insurance photo is blurry"}, headers=admin)
    seen = client.get("/api/drivers/documents", headers=headers).get_json()["driver"]
    upload(client, headers, doc_type="insurance")
    after = client.get("/api/drivers/documents", headers=headers).get_json()["driver"]

    assert seen["status"] == "rejected"
    assert seen["rejection_reason"] == "Insurance photo is blurry"
    assert after["status"] == "pending" and after["rejection_reason"] is None


def test_passengers_cannot_upload_documents(client, passenger):
    assert upload(client, passenger).status_code == 403


def test_approve_driver_command_checks_documents_too(app, client, documents):
    response = register(client, role="driver")
    phone = response.get_json()["user"]["phone"]
    runner = app.test_cli_runner()

    refused = runner.invoke(args=["approve-driver", phone])
    documents(auth_header(response))
    approved = runner.invoke(args=["approve-driver", phone])

    assert refused.exit_code != 0 and "Missing" in refused.output
    assert approved.exit_code == 0
