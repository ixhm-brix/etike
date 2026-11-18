"""Create real driver accounts, each with their car, from a CSV or prompts.

    python data/scripts/add_drivers.py data/raw/drivers.csv   # from a CSV
    python data/scripts/add_drivers.py                        # asks for one driver

With Docker (the data folder is mounted at /data):

    docker compose exec api python /data/scripts/add_drivers.py /data/raw/drivers.csv

Only for drivers who agreed to be added: record their consent in
data/sources.md first (the signed record itself stays outside Git).

Every new driver starts NOT approved, exactly like signing up on the website.
They log in and upload their legal documents on the driver page; an admin
approves them once every document is uploaded and checked. Each driver gets
a temporary password, printed once here: give it to the driver privately,
never by group chat or email.

A row that fails a check, or whose phone, licence or plate is already
registered, is reported and skipped. Nothing is guessed or filled in.
The CSV has personal details: keep it in data/raw/ (ignored by Git).
"""

import csv
import secrets
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parents[1]
_backend = DATA.parent / "backend"
sys.path.insert(0, str(_backend if _backend.exists() else Path.cwd()))
from werkzeug.security import generate_password_hash  # noqa: E402

from app import create_app  # noqa: E402
from app import validation as v  # noqa: E402
from app.errors import ApiError  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Driver, User, Vehicle  # noqa: E402
from app.routes.drivers import MAX_VEHICLE_SEATS  # noqa: E402

COLUMNS = ["full_name", "phone", "license_number", "national_id_number", "date_of_birth",
           "gender", "home_district", "home_sector", "plate_number", "model", "seats"]


class RowError(ValueError):
    pass


def clean(row):
    """Check one driver the same way the website does; return clean values."""
    row = {k: (row.get(k) or "").strip() for k in COLUMNS}
    name = " ".join(row["full_name"].split())
    if not 2 <= len(name) <= 100:
        raise RowError("full_name must be 2 to 100 characters")
    try:
        phone = v.phone(row["phone"])
    except ApiError:
        raise RowError(f"phone {row['phone']!r} is not a Rwandan mobile number") from None
    licence = row["license_number"].upper()
    if not 5 <= len(licence) <= 30:
        raise RowError("license_number must be 5 to 30 characters")
    plate = "".join(row["plate_number"].split()).upper()
    if not 4 <= len(plate) <= 12:
        raise RowError("plate_number must be 4 to 12 characters")
    model = " ".join(row["model"].split())
    if not 2 <= len(model) <= 60:
        raise RowError("model must be 2 to 60 characters")
    if not row["seats"].isdigit() or not 1 <= int(row["seats"]) <= MAX_VEHICLE_SEATS:
        raise RowError(f"seats must be a whole number from 1 to {MAX_VEHICLE_SEATS}")
    try:
        # The same checks as the sign-up form (16-digit ID, age, district...).
        details = v.driver_details({**row, "gender": row["gender"].lower()})
    except ApiError as err:
        fields = "; ".join(f"{k}: {m}" for k, m in (err.fields or {}).items())
        raise RowError(fields or err.message) from None
    return {"full_name": name, "phone": phone, "license_number": licence,
            "plate_number": plate, "model": model, "seats": int(row["seats"]), **details}


def add_driver(d):
    """Create the account (not approved) and its car. Returns the temporary
    password, or raises RowError if something is already registered."""
    if db.session.query(User.user_id).filter_by(phone=d["phone"]).first():
        raise RowError(f"an account with phone {d['phone']} already exists")
    if db.session.query(Driver.driver_id).filter_by(license_number=d["license_number"]).first():
        raise RowError(f"licence {d['license_number']} is already registered")
    if db.session.query(Vehicle.vehicle_id).filter_by(plate_number=d["plate_number"]).first():
        raise RowError(f"plate {d['plate_number']} is already registered")
    if db.session.query(Driver.driver_id).filter_by(
            national_id_number=d["national_id_number"]).first():
        raise RowError("this national ID number is already registered")

    password = secrets.token_urlsafe(9)  # 12 characters
    user = User(full_name=d["full_name"], phone=d["phone"], role="driver",
                password_hash=generate_password_hash(password))
    details = {f: d[f] for f in Driver.DETAIL_FIELDS}
    user.driver = Driver(is_approved=False, **details)
    user.driver.vehicles.append(
        Vehicle(plate_number=d["plate_number"], model=d["model"], seats=d["seats"]))
    db.session.add(user)
    db.session.commit()
    return password


def rows_from_csv(path):
    path = Path(path)
    if not path.exists():
        sys.exit(f"{path} not found. Nothing was added. Columns: {', '.join(COLUMNS)}")
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            sys.exit(f"{path} is missing column(s) {', '.join(missing)}. Nothing was added.")
        return [(line, row) for line, row in enumerate(reader, start=2) if any(row.values())]


def row_from_prompts():
    print("New driver (they still need admin approval after this).")
    labels = {"full_name": "Full name", "phone": "Phone (078...)",
              "license_number": "Driving licence number",
              "national_id_number": "National ID number (16 digits)",
              "date_of_birth": "Date of birth (YYYY-MM-DD)", "gender": "Gender (female/male)",
              "home_district": "Home district", "home_sector": "Home sector",
              "plate_number": "Car plate",
              "model": "Car model", "seats": "Passenger seats (driver not counted)"}
    return [("input", {c: input(f"{labels[c]}: ") for c in COLUMNS})]


def main():
    rows = rows_from_csv(sys.argv[1]) if len(sys.argv) > 1 else row_from_prompts()
    app = create_app()
    added = 0
    with app.app_context():
        for line, row in rows:
            try:
                d = clean(row)
                password = add_driver(d)
            except RowError as err:
                db.session.rollback()
                print(f"  Skipped line {line}: {err}.")
                continue
            added += 1
            print(f"  Added {d['full_name']} ({d['phone']}), {d['plate_number']} {d['model']}. "
                  f"Temporary password: {password}")
    print(f"\n{added} driver(s) added, waiting for admin approval. "
          "Give each driver their password privately.")


if __name__ == "__main__":
    main()
