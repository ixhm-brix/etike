"""Load the cleaned CSVs from data/processed/ into the database.

    python data/scripts/load_data.py

Safe to run more than once: rows that are already in the database are
matched and updated, never added twice. Run clean_data.py first. A missing
file is reported and skipped; nothing is invented to fill the gap.

Uses DATABASE_URL like the API does. With Docker:

    docker compose exec api python /data/scripts/load_data.py
"""

import csv
import sys
from datetime import datetime
from pathlib import Path

DATA = Path(__file__).resolve().parents[1]
PROCESSED = DATA / "processed"

_backend = DATA.parent / "backend"
sys.path.insert(0, str(_backend if _backend.exists() else Path.cwd()))
from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import BusCompany, BusTrip, Route  # noqa: E402


def main():
    app = create_app()
    with app.app_context():
        companies = load_companies()
        routes = load_routes()
        load_trips(companies, routes)
        db.session.commit()
    print("Done.")


def read(name):
    path = PROCESSED / name
    if not path.exists():
        print(f"Skipped {name}: data/processed/{name} not found. Run clean_data.py first.")
        return None
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_companies():
    """Returns {registration_number: BusCompany} for everything in the database."""
    rows = read("bus_companies.csv")
    by_reg = {c.registration_number: c for c in db.session.query(BusCompany)}
    if rows is None:
        return by_reg
    added = updated = 0
    for row in rows:
        company = by_reg.get(row["registration_number"])
        if company is None:
            company = BusCompany(registration_number=row["registration_number"])
            db.session.add(company)
            by_reg[company.registration_number] = company
            added += 1
        else:
            updated += 1
        company.name = row["name"]
        company.contact_phone = row["contact_phone"] or None
        company.licence_number = row["licence_number"] or None
    db.session.flush()
    print(f"Bus companies: {added} added, {updated} already there (updated).")
    return by_reg


def load_routes():
    """Returns {(origin, destination): Route} for everything in the database."""
    rows = read("routes.csv")
    by_pair = {(r.origin, r.destination): r for r in db.session.query(Route)}
    if rows is None:
        return by_pair
    added = 0
    for row in rows:
        pair = (row["origin"], row["destination"])
        if pair not in by_pair:
            by_pair[pair] = Route(origin=pair[0], destination=pair[1])
            db.session.add(by_pair[pair])
            added += 1
    db.session.flush()
    print(f"Routes: {added} added, {len(rows) - added} already there.")
    return by_pair


def load_trips(companies, routes):
    rows = read("bus_trips.csv")
    if rows is None:
        return
    added = existing = skipped = 0
    for row in rows:
        company = companies.get(row["company_registration_number"])
        route = routes.get((row["origin"], row["destination"]))
        if company is None or route is None:
            print(f"  Skipped trip {row['origin']} to {row['destination']} on "
                  f"{row['departure_date']} {row['departure_time']}: company or route not loaded.")
            skipped += 1
            continue
        departure = datetime.fromisoformat(f"{row['departure_date']}T{row['departure_time']}")
        # The same company, route and departure time is the same trip.
        trip = (
            db.session.query(BusTrip)
            .filter_by(company_id=company.company_id, route_id=route.route_id,
                       departure_time=departure)
            .first()
        )
        if trip:
            # Keep seats already sold; only the published fare is refreshed.
            trip.price_rwf = int(row["price_rwf"])
            existing += 1
            continue
        seats = int(row["total_seats"])
        db.session.add(BusTrip(
            company_id=company.company_id,
            route_id=route.route_id,
            departure_time=departure,
            price_rwf=int(row["price_rwf"]),
            total_seats=seats,
            available_seats=seats,
        ))
        added += 1
    print(f"Bus trips: {added} added, {existing} already there, {skipped} skipped.")


if __name__ == "__main__":
    main()
