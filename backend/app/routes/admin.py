"""Admin tools: approve or reject drivers, verify bus companies, send refunds."""

from flask import Blueprint, jsonify, request

from .. import driver_documents as docs
from .. import validation as v
from ..auth import role_required
from ..errors import ApiError, not_found
from ..extensions import db
from ..features import require_bus
from ..models import Booking, BusCompany, Driver, Payment
from ..models.user import utcnow
from .drivers import send_document

admin_bp = Blueprint("admin", __name__)


def _driver_dict(driver):
    user = driver.user
    return {
        **driver.to_dict(),
        "full_name": user.full_name,
        "phone": user.phone,
        "email": user.email,
        "registered_at": user.created_at.isoformat(),
        "vehicles": [x.to_dict() for x in driver.vehicles],
        "details": driver.details_dict(),
        "documents": docs.checklist(driver),
        "document_problems": docs.problems(driver),
    }


@admin_bp.get("/admin/drivers")
@role_required("admin")
def list_drivers():
    status = v.choice(request.args.get("status", "pending"), "status",
                      ("pending", "approved", "rejected", "all"))
    query = db.session.query(Driver)
    if status == "approved":
        query = query.filter(Driver.is_approved.is_(True))
    elif status == "rejected":
        query = query.filter(Driver.is_approved.is_(False), Driver.rejected_at.isnot(None))
    elif status == "pending":
        query = query.filter(Driver.is_approved.is_(False), Driver.rejected_at.is_(None))
    drivers = query.order_by(Driver.driver_id).all()
    return jsonify({"drivers": [_driver_dict(d) for d in drivers]})


@admin_bp.post("/admin/drivers/<int:driver_id>/approve")
@role_required("admin")
def approve_driver(driver_id):
    driver = _get_driver(driver_id)
    problems = docs.problems(driver)
    if problems:
        # Carrying paying passengers needs these documents (see driver_documents.py).
        raise ApiError(409, "documents_incomplete",
                       "This driver can't be approved yet. " + "; ".join(problems) + ".")
    driver.is_approved = True
    driver.rejected_at = None
    driver.rejection_reason = None
    db.session.commit()
    return jsonify({"driver": _driver_dict(driver)})


@admin_bp.post("/admin/drivers/<int:driver_id>/reject")
@role_required("admin")
def reject_driver(driver_id):
    # Rejecting an approved driver also hides their rides from search.
    driver = _get_driver(driver_id)
    data = request.get_json(silent=True) or {}
    reason = v.text(data, "reason", min_len=3, max_len=300, required=False)
    driver.is_approved = False
    driver.rejected_at = utcnow()
    driver.rejection_reason = reason
    db.session.commit()
    return jsonify({"driver": _driver_dict(driver)})


@admin_bp.get("/admin/drivers/<int:driver_id>/documents/<doc_type>/file")
@role_required("admin")
def driver_document_file(driver_id, doc_type):
    driver = _get_driver(driver_id)
    doc = next((d for d in driver.documents if d.doc_type == doc_type), None)
    if doc is None:
        raise not_found("This driver has not uploaded that document.")
    return send_document(doc)


@admin_bp.get("/admin/companies")
@role_required("admin")
def list_companies():
    require_bus()
    companies = db.session.query(BusCompany).order_by(BusCompany.is_verified, BusCompany.name).all()
    return jsonify({"companies": [c.admin_dict() for c in companies]})


@admin_bp.post("/admin/companies/<int:company_id>/verify")
@role_required("admin")
def verify_company(company_id):
    require_bus()
    company = db.session.get(BusCompany, company_id)
    if company is None:
        raise not_found("Bus company not found.")
    company.is_verified = True
    db.session.commit()
    return jsonify({"company": company.admin_dict()})


def _refund_dict(payment):
    booking = payment.booking
    return {
        "payment_id": payment.payment_id,
        "booking_id": booking.booking_id,
        "amount": payment.amount,
        "refund_status": payment.refund_status,
        "refunded_at": payment.refunded_at.isoformat() if payment.refunded_at else None,
        "passenger_name": booking.user.full_name,
        "passenger_phone": booking.user.phone,
        "trip": f"{booking.trip.route.origin} to {booking.trip.route.destination}",
        "departure_time": booking.trip.departure_time.isoformat(timespec="minutes"),
        "operator": booking.trip.company.name,
    }


@admin_bp.get("/admin/refunds")
@role_required("admin")
def list_refunds():
    """Payments for cancelled bookings that are owed back, oldest first."""
    status = v.choice(request.args.get("status", "due"), "status", ("due", "refunded"))
    payments = (
        db.session.query(Payment)
        .join(Booking, Payment.booking_id == Booking.booking_id)
        .filter(Payment.refund_status == status)
        .order_by(Payment.updated_at)
        .all()
    )
    return jsonify({"refunds": [_refund_dict(p) for p in payments]})


@admin_bp.post("/admin/refunds/<int:payment_id>/done")
@role_required("admin")
def mark_refunded(payment_id):
    """Record that the money was sent back to the passenger's MoMo."""
    payment = db.session.get(Payment, payment_id, with_for_update=True)
    if payment is None or payment.refund_status is None:
        raise not_found("No refund is due for this payment.")
    if payment.refund_status == "due":
        payment.refund_status = "refunded"
        payment.refunded_at = utcnow()
        db.session.commit()
    return jsonify({"refund": _refund_dict(payment)})


def _get_driver(driver_id):
    driver = db.session.get(Driver, driver_id)
    if driver is None:
        raise not_found("Driver not found.")
    return driver
