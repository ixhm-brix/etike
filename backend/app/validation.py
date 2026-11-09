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
