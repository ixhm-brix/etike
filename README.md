# ETIKE Intercity Travel Platform

ETIKE is a website for travelling between districts in Rwanda. In one place, people can book bus tickets across several bus companies, book a private car with the price shown up front, or book a seat in a shared private car already going their way. Users are passengers, drivers, bus company staff and admins.

It is a BSc Software Engineering project by Team 3 at African Leadership University (ALU), Kigali. The project uses **real collected data only** (see [data/](data/README.md)). Car rental is out of scope.

## Tech stack

- Frontend: HTML, CSS, JavaScript (no frameworks)
- Backend: Python 3.12, Flask, Flask-SQLAlchemy, Flask-Migrate, Flask-JWT-Extended, Gunicorn
- Payments: Flutterwave (Rwanda mobile money, test mode). SMS: Africa's Talking
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

## Admin accounts

There are no built-in admin accounts or passwords. Create the first admin from the command line; it asks for a name, phone number and password (or reads `ADMIN_NAME`, `ADMIN_PHONE` and `ADMIN_PASSWORD`):

```bash
docker compose exec api flask --app wsgi create-admin
```

Admins log in on the website like anyone else and land on **Drivers** (approve or reject drivers after checking their licence) and **Companies** (verify bus companies). Only approved drivers' rides and verified companies' trips appear in search or can be booked. A driver can also be approved from the command line: `flask --app wsgi approve-driver 0781234567`.

## Booking and payment flow

1. A passenger books: the booking is **pending** and holds its seats for `BOOKING_HOLD_MINUTES` (15 by default).
2. They pay with mobile money through Flutterwave. Success makes the booking **confirmed** and sends an SMS to the passenger (and to the driver for a ride).
3. A failed payment, or a hold that runs out, makes it **cancelled** and returns the seats. Expired holds are released before every search and booking, and by `flask --app wsgi expire-bookings` (run it from cron on the server, see [docs/deployment.md](docs/deployment.md)).
4. After a shared or private ride has left, the passenger can rate the driver once, from 1 to 5.

Paid bookings can't be cancelled online yet, because refunds are not built.

## Payments with Flutterwave (test mode)

1. Create a Flutterwave account at https://dashboard.flutterwave.com and stay in **Test mode**.
2. **Settings > API keys**: copy the test secret key (`FLWSECK_TEST-...`) into `FLW_SECRET_KEY` in `.env`.
3. Set `FLW_REDIRECT_URL` to the payment page (`http://localhost/payment.html` locally, `https://YOUR_DOMAIN/payment.html` on the server). Customers come back there after paying.
4. Webhook (server only, Flutterwave can't reach `localhost`): **Settings > Webhooks**, URL `https://YOUR_DOMAIN/api/payments/webhook`, and a **secret hash** of your choice (long random text). Put the same text in `FLW_SECRET_HASH`.
5. Restart: `docker compose up -d`.

To test: book a trip, click **Pay with MoMo**. A Flutterwave page opens in a new tab; use the test OTP **123456**. The ETIKE payment page keeps checking and shows the result. The server always verifies the transaction with Flutterwave (`tx_ref`, amount and currency must match) before confirming, and never trusts the webhook's content on its own.

Without `FLW_SECRET_KEY`, starting a payment returns **503** "Mobile money payments are not available right now". Nothing is ever marked paid without Flutterwave confirming it.

## SMS with Africa's Talking (sandbox)

1. Create an account at https://account.africastalking.com and open the **Sandbox** app.
2. Generate an API key (Settings > API Key). In `.env`: `AT_USERNAME=sandbox` and `AT_API_KEY=` that key.
3. Open the sandbox **Simulator**, enter a phone number, and messages sent to that number appear there.

Without these settings, SMS is skipped and logged. An SMS failure never affects a booking.

## API

All responses are JSON. Errors always look like `{"error": {"code": "...", "message": "...", "fields": {...}}}`, with status 400 (bad input), 401 (not logged in), 403 (not allowed), 404 (not found), 409 (conflict, such as no seats left), 429 (too many login attempts, from Nginx), 502 (payment provider error) or 503 (payments not configured). Send the token from login as `Authorization: Bearer <token>`.

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
| `POST /api/bookings` | passenger | Book (`trip_id` or `offer_id`, and `seats`). Starts as `pending`, seats held. The price is worked out by the server |
| `GET /api/bookings/mine` | logged in | My bookings |
| `GET /api/bookings/<id>` | logged in | One of my bookings |
| `POST /api/bookings/<id>/cancel` | logged in | Cancel my unpaid booking and free its seats |
| `POST /api/payments` | passenger | Start paying a pending booking (`booking_id`, optional `phone` and `email`). Returns the Flutterwave `checkout_url` |
| `GET /api/payments/<booking_id>/status` | logged in | Verify the payment with Flutterwave and update the booking |
| `POST /api/payments/webhook` | Flutterwave | Webhook. Needs the `verif-hash` header; safe to receive twice |
| `POST /api/ratings` | passenger | Rate a driver (`booking_id`, `score` 1 to 5, optional `comment`) after a confirmed ride |
| `GET /api/drivers/<id>/ratings` | anyone | A driver's average and recent comments |
| `GET /api/admin/drivers?status=pending` | admin | Drivers by status: `pending`, `approved`, `rejected` or `all` |
| `POST /api/admin/drivers/<id>/approve` | admin | Approve a driver |
| `POST /api/admin/drivers/<id>/reject` | admin | Reject a driver (their rides leave search) |
| `GET /api/admin/companies` | admin | All bus companies |
| `POST /api/admin/companies/<id>/verify` | admin | Verify a company (its trips appear in search) |

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
| `BOOKING_HOLD_MINUTES` | api | How long an unpaid booking holds its seats (default 15) |
| `CORS_ORIGINS` | api | Other sites allowed to call the API from a browser, comma separated. Empty by default (same-origin only) |
| `FLW_SECRET_KEY` | api | Flutterwave secret key (test key: `FLWSECK_TEST-...`). Without it payments return 503 |
| `FLW_SECRET_HASH` | api | Secret hash set in the Flutterwave dashboard; checked on every webhook |
| `FLW_REDIRECT_URL` | api | Page customers return to after paying, e.g. `https://YOUR_DOMAIN/payment.html` |
| `FLW_BASE_URL` | api | Flutterwave API address (default `https://api.flutterwave.com`) |
| `AT_USERNAME`, `AT_API_KEY` | api | Africa's Talking SMS. `sandbox` and a sandbox key for testing. Without them SMS is skipped |
| `AT_SENDER_ID` | api | Optional registered SMS sender ID |
| `ADMIN_NAME`, `ADMIN_PHONE`, `ADMIN_PASSWORD` | `create-admin` | Optional; the command asks for anything not set. Remove after use |

Never commit `.env`.

## Project structure

```
backend/    Flask API: app/ (models, auth, routes, services), tests, migrations
frontend/   Static site served by Nginx: pages, css, js, assets, driver/
nginx/      Nginx config (and an HTTPS example for the server)
infra/      Server scripts (nightly database backup)
data/       Real collected data, its sources, rules and the clean/load scripts
docs/       Architecture, deployment, usability testing
.github/    CI, deploy workflow, pull request template
```

## Documentation

- [Architecture](docs/architecture.md)
- [Deploying to a server: HTTPS, backups, admin](docs/deployment.md)
- [Usability testing](docs/usability/test-plan.md)
- [Scrum process](docs/scrum/README.md), [Definition of Done](docs/scrum/definition-of-done.md), [Sprint 1](docs/scrum/sprints/sprint-1.md)
- [Data rules and sources](data/README.md)
