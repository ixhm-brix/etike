"""Clean the raw collected data and write CSVs to data/processed/.

    python data/scripts/clean_data.py

Reads (each one optional; a missing file is reported and skipped):
    data/raw/bus_companies.csv
    data/raw/bus_trips.csv
    data/raw/routes.csv

Writes:
    data/processed/districts.csv      the official place names used
    data/processed/bus_companies.csv
    data/processed/routes.csv
    data/processed/bus_trips.csv

Rows that fail a check are listed and left out, never guessed or filled in.
This script never invents data: with no raw files it writes no rows.
See data/README.md for the columns.
"""

import csv
import re
import sys
from datetime import date, datetime
from pathlib import Path

DATA = Path(__file__).resolve().parents[1]
RAW = DATA / "raw"
PROCESSED = DATA / "processed"

# Share the place list with the API. Run from the repo, or inside the api
# container (where the backend is the working directory).
_backend = DATA.parent / "backend"
sys.path.insert(0, str(_backend if _backend.exists() else Path.cwd()))
from app.places import ALIASES, PLACES, normalise_place  # noqa: E402

COMPANY_COLUMNS = ["name", "contact_phone", "registration_number", "licence_number", "source"]
ROUTE_COLUMNS = ["origin", "destination", "source"]
TRIP_COLUMNS = [
    "company_registration_number",
    "origin",
    "destination",
    "departure_date",
    "departure_time",
    "price_rwf",
    "total_seats",
    "source",
]


class RowError(ValueError):
    pass


def main():
    PROCESSED.mkdir(exist_ok=True)
    problems = []

    write_districts()

    companies = clean_file("bus_companies.csv", COMPANY_COLUMNS, clean_company, problems)
    trips = clean_file("bus_trips.csv", TRIP_COLUMNS, clean_trip, problems)
    routes = clean_file("routes.csv", ROUTE_COLUMNS, clean_route, problems)

    if companies is not None:
        companies = unique(companies, key=lambda r: r["registration_number"], label="bus company")
        write("bus_companies.csv", COMPANY_COLUMNS, companies)

    if trips is not None:
        trips = unique(
            trips,
            key=lambda r: (r["company_registration_number"], r["origin"], r["destination"],
                           r["departure_date"], r["departure_time"]),
            label="bus trip",
        )
        if companies is not None:
            known = {c["registration_number"] for c in companies}
            for reg in sorted({t["company_registration_number"] for t in trips} - known):
                print(f"  Note: company {reg} has trips but is not in bus_companies.csv. "
                      "Its trips load only if it is already in the database.")
        write("bus_trips.csv", TRIP_COLUMNS, trips)

    # Every trip's route is a route too, so the route list is complete.
    if routes is not None or trips is not None:
        all_routes = (routes or []) + [
            {"origin": t["origin"], "destination": t["destination"], "source": t["source"]}
            for t in trips or []
        ]
        all_routes = unique(all_routes, key=lambda r: (r["origin"], r["destination"]), label=None)
        write("routes.csv", ROUTE_COLUMNS, all_routes)

    if problems:
        print(f"\n{len(problems)} problem(s), those rows were left out:")
        for p in problems:
            print(f"  - {p}")
    print("\nDone. Check the files in data/processed/ before loading them.")


def clean_file(name, columns, clean_row, problems):
    """Return the cleaned rows of one raw file, or None if the file is missing."""
    path = RAW / name
    if not path.exists():
        print(f"Skipped {name}: data/raw/{name} not found. Nothing was made up to replace it.")
        return None

    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = [h.strip() for h in reader.fieldnames or []]
        missing = [c for c in columns if c not in header]
        if missing:
            print(f"Skipped {name}: missing column(s) {', '.join(missing)}.")
            return None
        rows = []
        for line, raw in enumerate(reader, start=2):
            raw = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
            if not any(raw.values()):
                continue  # blank line
            try:
                rows.append(clean_row(raw))
            except RowError as err:
                problems.append(f"{name} line {line}: {err}")
    print(f"Read {name}: {len(rows)} good row(s).")
    return rows


def clean_company(row):
    if not row["name"]:
        raise RowError("company name is empty")
    if not row["registration_number"]:
        raise RowError("registration_number is empty")
    if not row["source"]:
        raise RowError("source is empty (say where this came from, see sources.md)")
    return {
        "name": " ".join(row["name"].split()),
        "contact_phone": clean_phone(row["contact_phone"]) if row["contact_phone"] else "",
        "registration_number": row["registration_number"].upper().replace(" ", ""),
        "licence_number": row["licence_number"].upper().replace(" ", ""),
        "source": row["source"],
    }


def clean_route(row):
    origin, destination = clean_places(row["origin"], row["destination"])
    if not row["source"]:
        raise RowError("source is empty")
    return {"origin": origin, "destination": destination, "source": row["source"]}


def clean_trip(row):
    if not row["company_registration_number"]:
        raise RowError("company_registration_number is empty")
    if not row["source"]:
        raise RowError("source is empty")
    origin, destination = clean_places(row["origin"], row["destination"])
    return {
        "company_registration_number": row["company_registration_number"].upper().replace(" ", ""),
        "origin": origin,
        "destination": destination,
        "departure_date": clean_date(row["departure_date"]),
        "departure_time": clean_time(row["departure_time"]),
        "price_rwf": clean_whole_number(row["price_rwf"], "price_rwf", minimum=1),
        "total_seats": clean_whole_number(row["total_seats"], "total_seats", minimum=1),
        "source": row["source"],
    }


def clean_places(origin, destination):
    o, d = normalise_place(origin), normalise_place(destination)
    if not o:
        raise RowError(f"unknown place {origin!r}")
    if not d:
        raise RowError(f"unknown place {destination!r}")
    if o == d:
        raise RowError(f"origin and destination are both {o}")
    return o, d


def clean_date(value):
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise RowError(f"date {value!r} is not YYYY-MM-DD") from None


def clean_time(value):
    """Accept 6:30, 06:30, 6.30, 6h30 and 6:30 AM; return 24-hour HH:MM."""
    text = value.strip().upper().replace(".", ":").replace("H", ":")
    for fmt in ("%H:%M", "%I:%M %p", "%I:%M%p"):
        try:
            return datetime.strptime(text, fmt).strftime("%H:%M")
        except ValueError:
            pass
    raise RowError(f"time {value!r} is not a clock time like 06:30")


def clean_whole_number(value, field, minimum):
    # Allow "5,000", "5 000" and "5000 RWF"; anything else is an error.
    digits = re.sub(r"(?i)\s*(rwf|frw)$", "", value).replace(",", "").replace(" ", "")
    if not digits.isdigit():
        raise RowError(f"{field} {value!r} is not a whole number")
    number = int(digits)
    if number < minimum:
        raise RowError(f"{field} must be at least {minimum}")
    return number


def clean_phone(value):
    digits = re.sub(r"[\s-]", "", value)
    match = re.match(r"^(?:\+?250|0)?(7[2389]\d{7})$", digits)
    if not match:
        raise RowError(f"phone {value!r} is not a Rwandan mobile number")
    return "+250" + match.group(1)


def unique(rows, key, label):
    seen, out = set(), []
    for row in rows:
        k = key(row)
        if k in seen:
            if label:
                print(f"  Removed duplicate {label}: {k}")
            continue
        seen.add(k)
        out.append(row)
    return out


def write(name, columns, rows):
    with (PROCESSED / name).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote data/processed/{name}: {len(rows)} row(s).")


def write_districts():
    """The official place names and the other names we accept for each."""
    other_names = {}
    for alias, place in ALIASES.items():
        other_names.setdefault(place, []).append(alias.title())
    rows = [{"name": p, "also_written_as": "; ".join(other_names.get(p, []))} for p in PLACES]
    write("districts.csv", ["name", "also_written_as"], rows)


if __name__ == "__main__":
    main()
