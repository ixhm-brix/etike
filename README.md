# ETIKE Intercity Travel Platform

ETIKE is a website for travelling between districts in Rwanda. Drivers post the trips they are making; passengers book a **private car** (the whole car, one price shown up front) or a **shared seat** in a car already going their way, and pay the driver during or after the ride. Users are passengers, drivers and admins.

**Current scope: private and shared rides between districts.** Bus booking is a future phase (see [Roadmap](#roadmap)); its code is kept but switched off with `FEATURE_BUS_BOOKING`.

It is a BSc Software Engineering project by Team 3 at African Leadership University (ALU), Kigali. The project uses **real collected data only** (see [data/](data/README.md)). Car rental is out of scope.

## Roadmap

**Bus booking (future phase).** Bus companies in Rwanda don't have booking software or open APIs, so supporting them properly means building a separate operator product: an operator portal for fleets and schedules, ticket scanning at boarding, and their payouts. The bus parts already built stay in the code, hidden behind `FEATURE_BUS_BOOKING` (off by default) and still covered by tests:

- bus trips, search and the bus seat map;
- MoMo payment before travel, with the 15-minute seat hold, and refunds for cancelled paid tickets;
- QR tickets and the ticket check page;
- verifying bus companies (admin);
- loading collected bus timetables (`data/scripts/`).

To try them locally, set `FEATURE_BUS_BOOKING=true` in `.env` and restart. Bus data collection is paused until this phase starts (see [data/README.md](data/README.md)).

## Tech stack

- Frontend: HTML, CSS, JavaScript (no frameworks)
- Backend: Python 3.12, Flask, Flask-SQLAlchemy, Flask-Migrate, Flask-JWT-Extended, Gunicorn
- Payments: MTN MoMo (Collections API, sandbox). SMS: Africa's Talking
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

## Logging in

People log in with their **phone number and password**, and sign up on the **Create an account** page as a passenger or a driver. Drivers also give their licence number, which an admin checks before they can post rides.

**Test accounts.** When `DEMO_LOGIN` is on, the login page also shows "Just looking around?" with **Passenger**, **Driver** and **Admin** buttons that log straight in to a test account. They only ever use accounts whose name starts with "TEST " (an approved driver for Driver). `DEMO_LOGIN` is on by default with `docker-compose.yml` (your laptop) and off with `docker-compose.prod.yml`: never switch it on for a public server, since it logs in without a password.

The API can also log people in with a one-time code sent by SMS (`POST /api/auth/code` and `/api/auth/verify`). It's kept for later and isn't shown on the website.

## Admin accounts

There are no built-in admin accounts or passwords. Create the first admin from the command line; it asks for a name, phone number and password (or reads `ADMIN_NAME`, `ADMIN_PHONE` and `ADMIN_PASSWORD`):

```bash
docker compose exec api flask --app wsgi create-admin
```

Admins log in on the website like anyone else and land on **Drivers** (approve or reject drivers after checking their licence), **Companies** (verify bus companies) and **Refunds** (send money back for cancelled paid tickets). Only approved drivers' rides and verified companies' trips appear in search or can be booked. A driver can also be approved from the command line: `flask --app wsgi approve-driver 0781234567`.

## Booking, payment and cancelling

**Shared and private rides** (current scope) are paid to the driver, in cash or by MoMo, during or after the ride. Nothing is paid on the website: the booking is **confirmed** straight away, and both the passenger and the driver get an SMS with the amount. Shared rides take a number of seats; a private ride takes the whole car.

**Bus tickets** (future phase, only with `FEATURE_BUS_BOOKING=true`) are paid before travel:

1. A passenger books: the booking is **pending** and holds its seats for `BOOKING_HOLD_MINUTES` (15 by default).
2. They pay with MTN MoMo: a request is sent to their phone and they approve it with their MoMo PIN. Success makes the booking **confirmed** and sends them an SMS.
3. A failed or declined payment, or a hold that runs out, makes it **cancelled** and returns the seats. Expired holds are released before every search and booking, and by `flask --app wsgi expire-bookings` (run it from cron on the server, see [docs/deployment.md](docs/deployment.md)).

**Cancelling.** A confirmed booking can be cancelled until `CANCEL_CUTOFF_HOURS` (2 by default) before departure; an unpaid one at any time. The seats go back on sale. Cancelling a paid bus ticket marks its payment as a **refund due**: admins see it under **Refunds**, send the money back to the passenger's MoMo number, and mark it as sent. Sending refunds automatically would need MoMo's Disbursements product and is not built.

After a shared or private ride has left, the passenger can rate the driver once, from 1 to 5.

**Seats.** On buses (future phase), passengers choose their seats on a seat map drawn as rows of 2 + aisle + 2. Shared rides just take a number of seats. The map is drawn from the number of seats, so it is a close guide, not each model's exact layout. A private ride takes every seat. Each seat is held in `booking_seats`, whose unique constraints make it impossible for two bookings to hold the same seat.

**Tickets.** Every confirmed booking has a ticket page with a QR code (made for bus boarding; rides have one too). Scanning it opens `/verify.html`, which says **Valid** or **Not valid** (cancelled, unpaid or already left) and shows the trip, seats and the passenger's first name and initial. The QR code holds a signed link, so it can't be forged, and validity is checked live, so a cancelled ticket stops working. The link uses the address the page was opened with: to scan with a phone on the same Wi-Fi, open the site on the laptop by its network address (for example `http://192.168.1.20`), not `localhost`.

**Car photos.** Drivers add up to 3 photos per car on the driver page (JPEG, PNG or WebP, under 3 MB; the server checks the file's content, not its name). Passengers see them on shared and private ride results and on the booking page. Files live in the `uploads` Docker volume and Nginx serves them at `/uploads/`.

## Payments with MTN MoMo (sandbox)

Only bus tickets are paid on the website, so MoMo payments are part of the bus phase: with `FEATURE_BUS_BOOKING` off they are not used. The integration is kept and tested.

Payments use the MTN MoMo Collections API ("request to pay"): the passenger gets a prompt on their phone and approves with their MoMo PIN.

We test on MTN's **global** sandbox, because MTN Rwanda's own sandbox (`sandbox.momodeveloper.mtn.co.rw`) currently fails on MTN's side. Production will use the Rwanda host with Rwanda live keys. Details are in [docs/deployment.md](docs/deployment.md#5-mtn-momo-payments).

1. Sign up at https://momodeveloper.mtn.com (the global portal), subscribe to the **Collections** product, and copy its **primary key** from your profile.
2. In `.env` (copy `.env.example` if you don't have one):
   ```
   MOMO_BASE_URL=https://sandbox.momodeveloper.mtn.com
   MOMO_TARGET_ENVIRONMENT=sandbox
   MOMO_SUBSCRIPTION_KEY=your Collections primary key
   MOMO_CURRENCY=EUR
   ```
3. Restart (`docker compose up -d`), then create your sandbox API user and key:
   ```bash
   docker compose exec api flask --app wsgi momo-create-user
   ```
   Copy the two lines it prints (`MOMO_API_USER=...` and `MOMO_API_KEY=...`) into `.env` and restart again. Every teammate can do this with their own key.

To test: book a trip and click **Pay with MoMo**. In the sandbox nobody's phone rings; the number you enter decides the result. A normal MTN number such as `0781234567` succeeds, `46733123450` fails and `46733123451` is declined (the full list is in [docs/deployment.md](docs/deployment.md#momo-sandbox-test-numbers)). The sandbox only accepts EUR, so the payment page shows a "Sandbox test currency" note. The page keeps checking until MoMo answers.

The server sets the amount from the booking, and before confirming it checks that MoMo's answer has the same amount, currency and booking ID. A callback from MoMo is never trusted on its own: the server always asks MoMo for the status first.

Without the MoMo settings, starting a payment returns **503** "Mobile money payments are not available right now". Nothing is ever marked paid without MoMo confirming it.

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
| `POST /api/auth/code` | anyone | Text a 6-digit login code to `phone` |
| `POST /api/auth/verify` | anyone | Log in with `phone` and `code` (and `full_name` for a new number, which becomes a passenger). Returns a token |
| `POST /api/auth/demo` | anyone, only with `DEMO_LOGIN` on | Log in as a test account (`role`: passenger, driver or admin) |
| `GET /api/auth/me` | logged in | The current user |
| `GET /api/config` | anyone | Which features are switched on, e.g. `{"features": {"bus_booking": false}}` |
| `GET /api/places` | anyone | Places you can travel between |
| `GET /api/routes` | anyone | Routes in the database |
| `GET /api/trips?origin=&destination=&date=` | anyone | Bus trips with seats left |
| `GET /api/trips/<id>` | anyone | One bus trip |
| `GET /api/trips/<id>/seats` | anyone | Seat map and taken seats of a bus trip |
| `GET /api/rides?origin=&destination=&date=&type=` | anyone | Open ride offers (`type` is `shared` or `private`) |
| `GET /api/rides/<id>` | anyone | One ride offer |
| `GET /api/rides/<id>/seats` | anyone | Seat map and taken seats of a ride |
| `GET /api/drivers/vehicles` | driver | My vehicles |
| `POST /api/drivers/vehicles` | driver | Add a vehicle (`plate_number`, `model`, `seats`) |
| `POST /api/drivers/vehicles/<id>/photos` | driver | Upload a car photo (form field `photo`) |
| `DELETE /api/drivers/vehicles/<id>/photos/<photo_id>` | driver | Remove a car photo |
| `POST /api/rides` | approved driver | Post a ride (`vehicle_id`, `origin`, `destination`, `ride_type`, `departure_time`, `price`, `seats_available`) |
| `POST /api/bookings` | passenger | Book (`trip_id` or `offer_id`, and `seat_numbers` chosen on the map, or `seats` for the lowest free ones). A bus booking starts `pending` with its seats held; a ride is `confirmed` at once. The price is worked out by the server |
| `GET /api/bookings/mine` | logged in | My bookings |
| `GET /api/bookings/<id>` | logged in | One of my bookings |
| `GET /api/bookings/<id>/ticket` | logged in | My confirmed booking's ticket and its check link |
| `GET /api/bookings/<id>/ticket/qr` | logged in | The ticket's QR code (SVG) |
| `GET /api/tickets/verify?t=` | anyone | Is this ticket valid right now? (what scanning the QR code shows) |
| `POST /api/bookings/<id>/cancel` | logged in | Cancel my booking and free its seats. Confirmed bookings only until the cut-off; a paid ticket becomes a refund due |
| `POST /api/payments` | passenger | Send a MoMo request to pay for a pending bus booking (`booking_id`, optional MTN `phone`). The amount comes from the booking |
| `GET /api/payments/<booking_id>/status` | logged in | Ask MoMo for the payment's status and update the booking |
| `POST /api/payments/callback` | MTN MoMo | Callback (POST or PUT). The status is always re-checked with MoMo; safe to receive twice |
| `POST /api/ratings` | passenger | Rate a driver (`booking_id`, `score` 1 to 5, optional `comment`) after a confirmed ride |
| `GET /api/drivers/<id>/ratings` | anyone | A driver's average and recent comments |
| `GET /api/admin/drivers?status=pending` | admin | Drivers by status: `pending`, `approved`, `rejected` or `all` |
| `POST /api/admin/drivers/<id>/approve` | admin | Approve a driver |
| `POST /api/admin/drivers/<id>/reject` | admin | Reject a driver (their rides leave search) |
| `GET /api/admin/companies` | admin | All bus companies |
| `POST /api/admin/companies/<id>/verify` | admin | Verify a company (its trips appear in search) |
| `GET /api/admin/refunds?status=due` | admin | Refunds owed for cancelled paid tickets (`due` or `refunded`) |
| `POST /api/admin/refunds/<payment_id>/done` | admin | Record that a refund was sent |

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
| `UPLOAD_DIR` | api | Where car photos are saved (default `/uploads`, a Docker volume Nginx also serves) |
| `DEMO_LOGIN` | api | `true` shows one-click test-account logins on the login page. On by default only in `docker-compose.yml`; never on a public server |
| `FEATURE_BUS_BOOKING` | api | `true` switches on bus booking, a future phase (default off: bus endpoints answer 404, bus bookings 400, and the website hides bus options) |
| `CANCEL_CUTOFF_HOURS` | api | A confirmed booking can be cancelled until this many hours before departure (default 2) |
| `CORS_ORIGINS` | api | Other sites allowed to call the API from a browser, comma separated. Empty by default (same-origin only) |
| `MOMO_BASE_URL` | api | MoMo API address (default: the global sandbox, `https://sandbox.momodeveloper.mtn.com`) |
| `MOMO_TARGET_ENVIRONMENT` | api | `sandbox` for testing (default), `mtnrwanda` in production |
| `MOMO_SUBSCRIPTION_KEY` | api | Primary key of the MoMo Collections product |
| `MOMO_API_USER`, `MOMO_API_KEY` | api | MoMo API user and key. In the sandbox, create them with `flask momo-create-user`. Without these three, payments return 503 |
| `MOMO_CURRENCY` | api | `EUR` in the sandbox (the only one it accepts), `RWF` in production |
| `MOMO_CALLBACK_URL` | api | Optional. Address MoMo calls when a payment finishes, e.g. `https://YOUR_DOMAIN/api/payments/callback` |
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
