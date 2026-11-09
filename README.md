# ETIKE Intercity Travel Platform

ETIKE is a website for travelling between districts in Rwanda. In one place, people can book bus tickets across several bus companies, book a private car with the price shown up front, or book a seat in a shared private car already going their way. Users are passengers, drivers, bus company staff and admins.

It is a BSc Software Engineering project by Team 3 at African Leadership University (ALU), Kigali. The project uses **real collected data only** (see [data/](data/README.md)). Car rental is out of scope.

## Tech stack

- Frontend: HTML, CSS, JavaScript (no frameworks)
- Backend: Python 3.12, Flask, Flask-SQLAlchemy, Flask-Migrate, Flask-JWT-Extended, Gunicorn
- Database: PostgreSQL 16
- Nginx, Docker, Docker Compose
- GitHub Actions for CI/CD, pytest for tests, ruff for linting

## Run locally

You need Docker with Compose.

```bash
git clone <repo-url> etike && cd etike
docker compose up --build
```

- Site: http://localhost
- API health check: http://localhost/api/health

The defaults work with no setup. To change them, `cp .env.example .env` and edit it.

The first time, and after pulling new migrations, create the tables:

```bash
docker compose exec api flask --app wsgi db upgrade
```

Stop with `Ctrl+C`, or `docker compose down` (add `-v` to also delete the database volume).

## Run tests and lint

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
ruff check .
pytest
```

Tests use in-memory SQLite by default. The test that two people booking the last seat at once can't both get it needs PostgreSQL, so on SQLite it is skipped. To run everything like CI does, point `TEST_DATABASE_URL` at an empty Postgres database (the tests apply the migrations themselves):

```bash
docker compose exec db createdb -U etike etike_test
docker compose exec -e TEST_DATABASE_URL=postgresql+psycopg://etike:etike_dev_password@db:5432/etike_test api pytest
```

Tests create their own data and clean it up afterwards. No test data is ever committed or loaded into the real database.

## Database migrations

Models live in `backend/app/models/`. After changing one, generate and apply a migration:

```bash
docker compose exec api flask --app wsgi db migrate -m "describe the change"
docker compose exec api flask --app wsgi db upgrade
```

Read the generated file in `backend/migrations/versions/` before committing it. On the server, run the same `upgrade` with `-f docker-compose.prod.yml`.

## Loading real data

Collected data goes in `data/raw/` (see [data/README.md](data/README.md) for the CSV columns). Then:

```bash
docker compose exec api python /data/scripts/clean_data.py   # checks it, writes data/processed/
docker compose exec api python /data/scripts/load_data.py    # loads it; safe to run twice
```

Missing files are reported and skipped. The scripts never make up data to fill a gap.

## Approving drivers

New drivers can add vehicles but cannot post rides until an admin has checked their licence. Until there is an admin dashboard, approve them from the command line:

```bash
docker compose exec api flask --app wsgi approve-driver 0781234567
```

## API

All responses are JSON. Errors always look like `{"error": {"code": "...", "message": "...", "fields": {...}}}`, with status 400 (bad input), 401 (not logged in), 403 (not allowed), 404 (not found) or 409 (conflict, such as no seats left). Send the token from login as `Authorization: Bearer <token>`.

| Method and path | Who | What it does |
|-----------------|-----|--------------|
| `GET /api/health` | anyone | API and database status |
| `POST /api/auth/register` | anyone | Create a passenger or driver account (`full_name`, `phone`, `password`, `role`, plus `license_number` for drivers). Returns a token |
| `POST /api/auth/login` | anyone | `phone` and `password`. Returns a token |
| `GET /api/auth/me` | logged in | The current user |
| `GET /api/places` | anyone | Places you can travel between |
| `GET /api/routes` | anyone | Routes in the database |
| `GET /api/trips?origin=&destination=&date=` | anyone | Bus trips with seats left |
| `GET /api/trips/<id>` | anyone | One bus trip |
| `GET /api/rides?origin=&destination=&date=&type=` | anyone | Open ride offers (`type` is `shared` or `private`) |
| `GET /api/rides/<id>` | anyone | One ride offer |
| `GET /api/drivers/vehicles` | driver | My vehicles |
| `POST /api/drivers/vehicles` | driver | Add a vehicle (`plate_number`, `model`, `seats`) |
| `POST /api/rides` | approved driver | Post a ride (`vehicle_id`, `origin`, `destination`, `ride_type`, `departure_time`, `price`, `seats_available`) |
| `POST /api/bookings` | passenger | Book (`trip_id` or `offer_id`, and `seats`). The price is worked out by the server |
| `GET /api/bookings/mine` | logged in | My bookings |
| `POST /api/bookings/<id>/cancel` | logged in | Cancel my booking and free its seats |

Dates and times are Rwanda local time, written like `2026-12-24` and `2026-12-24T07:30`.

## Environment variables

| Variable | Used by | Purpose |
|----------|---------|---------|
| `FLASK_ENV` | api | `development`, `testing` or `production` (default `production`) |
| `SECRET_KEY` | api | Flask's secret key. Required in production |
| `JWT_SECRET_KEY` | api | Signs login tokens. Use a different random value from `SECRET_KEY`. Required in production |
| `DATABASE_URL` | api | SQLAlchemy URL, e.g. `postgresql+psycopg://user:pass@db:5432/etike`. Required in production |
| `TEST_DATABASE_URL` | tests | Separate database for tests (default in-memory SQLite) |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | db | Credentials for the Postgres container |
| `GUNICORN_WORKERS` | api | Worker processes in production (default 3) |

Never commit `.env`.

## Project structure

```
backend/    Flask API: app/ (models, auth, routes, services), tests, migrations
frontend/   Static site served by Nginx: pages, css, js, assets, driver/
nginx/      Nginx config (and an HTTPS example for the server)
data/       Real collected data, its sources, rules and the clean/load scripts
docs/       Architecture and Scrum documents
.github/    CI, deploy workflow, pull request template
```

## Documentation

- [Architecture, VPS setup and HTTPS](docs/architecture.md)
- [Scrum process](docs/scrum/README.md), [Definition of Done](docs/scrum/definition-of-done.md), [Sprint 1](docs/scrum/sprints/sprint-1.md)
- [Data rules and sources](data/README.md)
