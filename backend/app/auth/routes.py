from flask import Blueprint, jsonify
from flask_jwt_extended import create_access_token
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from .. import validation as v
from ..errors import ApiError, bad_request, conflict
from ..extensions import db
from ..models import Driver, User
from .decorators import current_user, role_required

auth_bp = Blueprint("auth", __name__)

MIN_PASSWORD = 8
MAX_PASSWORD = 128


@auth_bp.post("/register")
def register():
    data = v.json_body()
    full_name = v.text(data, "full_name", min_len=2, max_len=100)
    phone = v.phone(data.get("phone"))
    email = v.text(data, "email", min_len=3, max_len=255, required=False)
    if email and "@" not in email:
        raise bad_request("Enter a valid email address.", {"email": "Not a valid email address."})
    # Admin accounts are never created through the website.
    role = v.choice(data.get("role", "passenger"), "role", ("passenger", "driver"))

    password = data.get("password")
    if not isinstance(password, str) or not MIN_PASSWORD <= len(password) <= MAX_PASSWORD:
        msg = f"Must be {MIN_PASSWORD} to {MAX_PASSWORD} characters."
        raise bad_request(f"password: {msg}", {"password": msg})

    license_number = None
    if role == "driver":
        license_number = v.text(data, "license_number", min_len=5, max_len=30).upper()

    if db.session.query(User.user_id).filter_by(phone=phone).first():
        raise conflict("An account with this phone number already exists.", "phone_taken")
    if license_number and db.session.query(Driver.driver_id).filter_by(
        license_number=license_number
    ).first():
        raise conflict("This licence number is already registered.", "license_taken")

    user = User(
        full_name=full_name,
        phone=phone,
        email=email,
        password_hash=generate_password_hash(password),
        role=role,
    )
    if license_number:
        user.driver = Driver(license_number=license_number)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        # Someone registered the same phone or licence a moment ago.
        db.session.rollback()
        raise conflict("This phone number or licence is already registered.") from None

    return jsonify({"user": user.to_dict(), "access_token": _token_for(user)}), 201


@auth_bp.post("/login")
def login():
    data = v.json_body()
    password = data.get("password")
    try:
        phone = v.phone(data.get("phone"))
    except ApiError:
        phone = None

    user = db.session.query(User).filter_by(phone=phone).first() if phone else None
    # Same message whether the phone or the password is wrong, so nobody can
    # use this form to find out which phone numbers have accounts.
    if not user or not isinstance(password, str) or not check_password_hash(
        user.password_hash, password
    ):
        raise ApiError(401, "invalid_credentials", "Phone number or password is incorrect.")

    return jsonify({"user": user.to_dict(), "access_token": _token_for(user)})


@auth_bp.get("/me")
@role_required()
def me():
    return jsonify({"user": current_user().to_dict()})


def _token_for(user):
    return create_access_token(identity=str(user.user_id), additional_claims={"role": user.role})
