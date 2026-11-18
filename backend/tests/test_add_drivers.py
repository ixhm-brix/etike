"""data/scripts/add_drivers.py: real drivers added by an admin start unapproved."""

import importlib.util
from datetime import date
from pathlib import Path

import pytest
from werkzeug.security import check_password_hash

from app.extensions import db
from app.models import User

# ../data/scripts from the repo, /data/scripts inside the api container.
SCRIPT = Path(__file__).resolve().parents[2] / "data" / "scripts" / "add_drivers.py"
spec = importlib.util.spec_from_file_location("add_drivers", SCRIPT)
add_drivers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(add_drivers)

ROW = {"full_name": "  Jean  Bosco ", "phone": "078 555 1234", "license_number": "rw12345",
       "national_id_number": "1 1985 8 0012345 0 67", "date_of_birth": "1985-03-02",
       "gender": "Male", "home_district": "Butare", "home_sector": "Tumba",
       "plate_number": "rad 123 b", "model": "Toyota RAV4", "seats": "4"}


def test_clean_matches_the_website_rules():
    d = add_drivers.clean(ROW)

    assert d == {"full_name": "Jean Bosco", "phone": "+250785551234",
                 "license_number": "RW12345", "plate_number": "RAD123B",
                 "model": "Toyota RAV4", "seats": 4,
                 "national_id_number": "1198580012345067", "date_of_birth": date(1985, 3, 2),
                 "gender": "male", "home_district": "Huye", "home_sector": "Tumba"}


@pytest.mark.parametrize("change", [
    {"phone": "12345"}, {"seats": "0"}, {"seats": "four"}, {"license_number": "x"},
    {"plate_number": ""}, {"full_name": ""}, {"national_id_number": "123"},
    {"date_of_birth": "2015-01-01"}, {"gender": "other"}, {"home_district": "Atlantis"},
])
def test_bad_rows_are_refused(change):
    with pytest.raises(add_drivers.RowError):
        add_drivers.clean({**ROW, **change})


def test_driver_starts_unapproved_with_car(app):
    with app.app_context():
        password = add_drivers.add_driver(add_drivers.clean(ROW))
        user = db.session.query(User).filter_by(phone="+250785551234").one()

        assert user.role == "driver"
        assert user.driver.is_approved is False
        assert [v.plate_number for v in user.driver.vehicles] == ["RAD123B"]
        assert check_password_hash(user.password_hash, password)
        assert user.driver.national_id_number == "1198580012345067"


def test_existing_phone_or_plate_is_skipped(app):
    with app.app_context():
        add_drivers.add_driver(add_drivers.clean(ROW))
        same_plate = {**ROW, "phone": "0785559999", "license_number": "RW99999"}

        with pytest.raises(add_drivers.RowError, match="already exists"):
            add_drivers.add_driver(add_drivers.clean(ROW))
        with pytest.raises(add_drivers.RowError, match="plate"):
            add_drivers.add_driver(add_drivers.clean(same_plate))
