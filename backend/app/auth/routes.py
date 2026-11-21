import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from flask import Blueprint, current_app, jsonify
from flask_jwt_extended import create_access_token
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from .. import validation as v
from ..errors import ApiError, bad_request, conflict
from ..extensions import db
from ..models import Driver, LoginCode, User
from ..models.user import utcnow
from ..services import sms_service
from .decorators import current_user, role_required

log = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)

MIN_PASSWORD = 8
MAX_PASSWORD = 128

# Logging in with a code sent by SMS.
CODE_MINUTES = 10
MAX_ATTEMPTS = 5
RESEND_SECONDS = 60
CODES_PER_HOUR = 5


@auth_bp.post("/register")
def register():
    data = v.json_body()
    full_name = v.text(data, "full_name", min_len=2, max_len=100)
    phone = v.phone(data.get("phone"))
    email = v.text(data, "email", min_len=3, max_len=255, required=False)
    if email and "@" not in email:
        raise bad_request("Enter a valid email address.", {"email": "Not a valid email address."})
    if email and email.lower().endswith(TEST_EMAIL_DOMAIN):
        # Reserved for the laptop-only test accounts (see demo_login).
        raise bad_request("Use your own email address.", {"email": "Use your own email address."})
    # Admin accounts are never created through the website.
    role = v.choice(data.get("role", "passenger"), "role", ("passenger", "driver"))

    password = data.get("password")
    if not isinstance(password, str) or not MIN_PASSWORD <= len(password) <= MAX_PASSWORD:
        msg = f"Must be {MIN_PASSWORD} to {MAX_PASSWORD} characters."
        raise bad_request(f"password: {msg}", {"password": msg})

    # Drivers sign up like everyone else. Once logged in, they fill in their
    # official details and upload their documents on the driver page, and an
    # admin approves them (see routes/drivers.py).
    if db.session.query(User.user_id).filter_by(phone=phone).first():
        raise conflict("An account with this phone number already exists.", "phone_taken")

    user = User(
        full_name=full_name,
        phone=phone,
        email=email,
        password_hash=generate_password_hash(password),
        role=role,
    )
    if role == "driver":
        user.driver = Driver()
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        # Someone registered the same phone a moment ago.
        db.session.rollback()
        raise conflict("An account with this phone number already exists.", "phone_taken") from None

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
    if (not user or not user.password_hash or not isinstance(password, str)
            or not check_password_hash(user.password_hash, password)):
        raise ApiError(401, "invalid_credentials", "Phone number or password is incorrect.")

    return jsonify({"user": user.to_dict(), "access_token": _token_for(user)})


@auth_bp.post("/code")
def send_code():
    """Text a one-time login code to a phone number.

    Works for new and existing numbers alike, so it never reveals whether a
    number has an account.
    """
    data = v.json_body()
    phone = v.phone(data.get("phone"))
    cfg = current_app.config
    sms_ready = bool(cfg.get("AT_USERNAME") and cfg.get("AT_API_KEY"))
    show_code = not sms_ready and cfg.get("SHOW_LOGIN_CODES")
    if not sms_ready and not show_code:
        raise ApiError(503, "code_login_unavailable",
                       "Logging in with a text message isn't available right now. "
                       "Use your password instead.")

    now = utcnow()
    recent = (db.session.query(LoginCode)
              .filter(LoginCode.phone == phone, LoginCode.created_at > now - timedelta(hours=1))
              .order_by(LoginCode.created_at.desc()).all())
    if recent and _as_utc(recent[0].created_at) > now - timedelta(seconds=RESEND_SECONDS):
        raise ApiError(429, "too_many_codes", "Wait a minute before asking for another code.")
    if len(recent) >= CODES_PER_HOUR:
        raise ApiError(429, "too_many_codes",
                       "Too many codes for this number. Try again in an hour.")

    code = f"{secrets.randbelow(10**6):06d}"
    # Only the newest code works.
    for old in recent:
        if old.used_at is None:
            old.used_at = now
    entry = LoginCode(phone=phone, code_hash=_hash_code(phone, code),
                      expires_at=now + timedelta(minutes=CODE_MINUTES))
    db.session.add(entry)
    db.session.commit()

    body = {"sent": True, "expires_in": CODE_MINUTES * 60}
    if show_code:
        log.info("Login code for %s shown on the page (no SMS configured).", phone[-3:])
        body["dev_code"] = code
    elif not sms_service.send(
        phone, f"Your ETIKE code is {code}. It expires in {CODE_MINUTES} minutes. "
               "Don't share it with anyone."
    ):
        db.session.delete(entry)
        db.session.commit()
        raise ApiError(502, "sms_failed", "We couldn't send the text message. Try again.")
    return jsonify(body)


@auth_bp.post("/verify")
def verify_code():
    """Log in with the code. A new number becomes a passenger account; it
    only needs a name, sent along with the code."""
    data = v.json_body()
    phone = v.phone(data.get("phone"))
    code = "".join(str(data.get("code") or "").split())
    wrong = ApiError(400, "invalid_code", "This code is wrong or has expired. Ask for a new one.",
                     {"code": "Wrong or expired code."})

    entry = (db.session.query(LoginCode)
             .filter(LoginCode.phone == phone, LoginCode.used_at.is_(None),
                     LoginCode.expires_at > utcnow())
             .order_by(LoginCode.created_at.desc())
             .with_for_update().first())
    if entry is None or entry.attempts >= MAX_ATTEMPTS:
        raise wrong
    if not hmac.compare_digest(entry.code_hash, _hash_code(phone, code)):
        entry.attempts += 1
        db.session.commit()
        raise wrong

    user = db.session.query(User).filter_by(phone=phone).first()
    new_user = user is None
    if new_user:
        # The code stays valid, so the page can ask for the name and resend.
        if not str(data.get("full_name") or "").strip():
            raise ApiError(400, "name_required", "Welcome! What's your name?",
                           {"full_name": "Your name, as on your ID."})
        user = User(full_name=v.text(data, "full_name", min_len=2, max_len=100),
                    phone=phone, role="passenger")
        db.session.add(user)

    entry.used_at = utcnow()
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise conflict("This phone number was just registered. Try again.") from None
    body = {"user": user.to_dict(), "access_token": _token_for(user), "new_user": new_user}
    return jsonify(body), 201 if new_user else 200


# Sample accounts (made by the local test data tool) are marked by an email on
# the reserved ".test" domain (RFC 2606), which no real person can have;
# sign-up refuses it too. One-click login only opens these two of them.
TEST_EMAIL_DOMAIN = "@etike.test"
DEMO_ACCOUNTS = {"passenger": "demo.passenger@etike.test", "driver": "demo.driver@etike.test"}


@auth_bp.post("/demo")
def demo_login():
    """Log in with one click as the Demo Traveller or the Demo Driver.

    Only when DEMO_LOGIN is on (never in production), and only into those two
    accounts, found by their reserved @etike.test emails.
    """
    if not current_app.config.get("DEMO_LOGIN"):
        raise ApiError(404, "not_found", "Test accounts are not available here.")
    role = v.choice(v.json_body().get("role"), "role", tuple(DEMO_ACCOUNTS))
    query = db.session.query(User).filter(User.role == role, User.email == DEMO_ACCOUNTS[role])
    if role == "driver":
        # An approved driver, so posting rides works in the demo.
        query = query.join(Driver).filter(Driver.is_approved.is_(True))
    user = query.order_by(User.user_id).first()
    if user is None:
        raise ApiError(404, "no_test_account",
                       f"There is no demo {role} account. Load the sample data first.")
    return jsonify({"user": user.to_dict(), "access_token": _token_for(user)})


def _hash_code(phone, code):
    key = current_app.config["SECRET_KEY"].encode()
    return hmac.new(key, f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def _as_utc(dt):
    # SQLite gives times back without a time zone; they are stored as UTC.
    return dt if dt.tzinfo else dt.replace(tzinfo=utcnow().tzinfo)


@auth_bp.get("/me")
@role_required()
def me():
    return jsonify({"user": current_user().to_dict()})


def _token_for(user):
    return create_access_token(identity=str(user.user_id), additional_claims={"role": user.role})
