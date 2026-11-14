"""Admin tools: approve or reject drivers, verify bus companies."""

from flask import Blueprint, jsonify, request

from .. import validation as v
from ..auth import role_required
from ..errors import not_found
from ..extensions import db
from ..models import BusCompany, Driver
from ..models.user import utcnow

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
    driver.is_approved = True
    driver.rejected_at = None
    db.session.commit()
    return jsonify({"driver": _driver_dict(driver)})


@admin_bp.post("/admin/drivers/<int:driver_id>/reject")
@role_required("admin")
def reject_driver(driver_id):
    # Rejecting an approved driver also hides their rides from search.
    driver = _get_driver(driver_id)
    driver.is_approved = False
    driver.rejected_at = utcnow()
    db.session.commit()
    return jsonify({"driver": _driver_dict(driver)})


@admin_bp.get("/admin/companies")
@role_required("admin")
def list_companies():
    companies = db.session.query(BusCompany).order_by(BusCompany.is_verified, BusCompany.name).all()
    return jsonify({"companies": [c.admin_dict() for c in companies]})


@admin_bp.post("/admin/companies/<int:company_id>/verify")
@role_required("admin")
def verify_company(company_id):
    company = db.session.get(BusCompany, company_id)
    if company is None:
        raise not_found("Bus company not found.")
    company.is_verified = True
    db.session.commit()
    return jsonify({"company": company.admin_dict()})


def _get_driver(driver_id):
    driver = db.session.get(Driver, driver_id)
    if driver is None:
        raise not_found("Driver not found.")
    return driver
