"""Small input checks shared by the endpoints. Each one returns the clean
value or raises a 400 ApiError naming the field."""

import re
from datetime import date, datetime, timedelta, timezone

from flask import request

from .errors import bad_request
from .places import PLACES, normalise_place

# Rwandan mobile numbers: MTN 078/079, Airtel 072/073. Stored as +2507XXXXXXXX.
PHONE_RE = re.compile(r"^(?:\+?250|0)?(7[2389]\d{7})$")

# Rwanda is UTC+2 all year. Departure times are stored as local time.
RWANDA = timezone(timedelta(hours=2))


def local_now():
    return datetime.now(RWANDA).replace(tzinfo=None)


def json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise bad_request("Send the request body as a JSON object.")
    return data


def phone(value, field="phone"):
    digits = re.sub(r"[\s-]", "", str(value or ""))
    match = PHONE_RE.match(digits)
    if not match:
        raise bad_request(
            "Enter a Rwandan mobile number, like 078 123 4567.",
            {field: "Must be a Rwandan mobile number (072, 073, 078 or 079)."},
        )
    return "+250" + match.group(1)


# MTN Rwanda numbers start with 078 or 079. The MoMo sandbox has its own
# made-up test numbers (46733123450 to 46733123454, see docs/deployment.md).
MTN_RE = re.compile(r"^(?:\+?250|0)?(7[89]\d{7})$")
SANDBOX_MSISDN_RE = re.compile(r"^\+?(46733123\d{3})$")


def momo_phone(value, field="phone", sandbox=False):
    """A number MoMo can charge, as an MSISDN without "+" (250781234567)."""
    digits = re.sub(r"[\s-]", "", str(value or ""))
    match = MTN_RE.match(digits)
    if match:
        return "250" + match.group(1)
    if sandbox and SANDBOX_MSISDN_RE.match(digits):
        return digits.lstrip("+")
    raise bad_request(
        "Enter an MTN MoMo number, like 078 123 4567.",
        {field: "Must be an MTN Rwanda number (078 or 079)."},
    )


def text(data, field, min_len=1, max_len=100, required=True):
    value = " ".join(str(data.get(field) or "").split())
    if not value:
        if required:
            raise bad_request(f"{field} is required.", {field: "This field is required."})
        return None
    if not min_len <= len(value) <= max_len:
        msg = f"Must be {min_len} to {max_len} characters."
        raise bad_request(f"{field}: {msg}", {field: msg})
    return value


def integer(data, field, minimum=None, maximum=None, default=None):
    value = data.get(field, default)
    # bool is a subclass of int in Python; reject it explicitly.
    if isinstance(value, bool) or value is None:
        raise bad_request(f"{field} must be a whole number.", {field: "Must be a whole number."})
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise bad_request(
            f"{field} must be a whole number.", {field: "Must be a whole number."}
        ) from None
    if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        if maximum is not None:
            msg = f"Must be between {minimum} and {maximum}."
        else:
            msg = f"Must be {minimum} or more."
        raise bad_request(f"{field}: {msg}", {field: msg})
    return value


def choice(value, field, options):
    if value not in options:
        msg = f"Must be one of: {', '.join(options)}."
        raise bad_request(f"{field}: {msg}", {field: msg})
    return value


def place(value, field):
    name = normalise_place(value)
    if not name:
        raise bad_request(
            f"Unknown place for {field}.",
            {field: f"Must be one of Rwanda's districts: {', '.join(PLACES)}."},
        )
    return name


def route_places(origin, destination):
    origin = place(origin, "origin")
    destination = place(destination, "destination")
    if origin == destination:
        raise bad_request(
            "Origin and destination must be different places.",
            {"destination": "Must differ from origin."},
        )
    return origin, destination


# Rwandan national ID numbers have 16 digits (spaces allowed when typed).
NATIONAL_ID_RE = re.compile(r"^\d{16}$")
GENDERS = ("female", "male")
MIN_DRIVER_AGE = 18  # minimum age for a car driving licence


def driver_details(data):
    """The official details a driver fills in after signing up, as on their
    national ID and driving licence.
    The admin checks them against the uploaded ID before approving."""
    national_id = re.sub(r"[\s-]", "", str(data.get("national_id_number") or ""))
    if not NATIONAL_ID_RE.match(national_id):
        raise bad_request("Enter your 16-digit national ID number.",
                          {"national_id_number": "Must be the 16 digits on your ID."})
    if not data.get("date_of_birth"):
        raise bad_request("Enter your date of birth.",
                          {"date_of_birth": "Enter your date of birth."})
    born = iso_date(data.get("date_of_birth"), "date_of_birth")
    today = local_now().date()
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    if not MIN_DRIVER_AGE <= age <= 100:
        raise bad_request(f"Drivers must be at least {MIN_DRIVER_AGE} years old.",
                          {"date_of_birth": f"You must be at least {MIN_DRIVER_AGE}."})
    return {
        "national_id_number": national_id,
        "date_of_birth": born,
        "gender": choice(data.get("gender"), "gender", GENDERS),
        "home_district": place(data.get("home_district"), "home_district"),
        "home_sector": text(data, "home_sector", min_len=2, max_len=60),
        "license_number": "".join(text(data, "license_number", min_len=5,
                                       max_len=30).split()).upper(),
    }


def iso_date(value, field="date"):
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise bad_request(
            f"{field} must be a date like 2026-12-24.", {field: "Use the format YYYY-MM-DD."}
        ) from None


def iso_datetime(value, field):
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        raise bad_request(
            f"{field} must be a date and time like 2026-12-24T07:30.",
            {field: "Use the format YYYY-MM-DDTHH:MM."},
        ) from None
    if parsed.tzinfo:
        parsed = parsed.astimezone(RWANDA)
    return parsed.replace(tzinfo=None, second=0, microsecond=0)
