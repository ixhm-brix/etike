# ETIKE Intercity Travel Platform

ETIKE is a website for travelling between districts in Rwanda. In one place, people can book bus tickets across several bus companies, book a private car with the price shown up front, or book a seat in a shared private car already going their way. Users are passengers, drivers, bus company staff and admins.

It is a BSc Software Engineering project by Team 3 at African Leadership University (ALU), Kigali. The project uses **real collected data only** (see [data/](data/README.md)). Car rental is out of scope.

## Tech stack

- Frontend: HTML, CSS, JavaScript (no frameworks)
- Backend: Python 3.12, Flask, Flask-SQLAlchemy, Flask-Migrate, Gunicorn
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

Stop with `Ctrl+C`, or `docker compose down` (add `-v` to also delete the database volume).

## Run tests and lint

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
ruff check .
pytest
```

Tests use in-memory SQLite by default. To test against Postgres like CI does, set `TEST_DATABASE_URL`.

## Environment variables

| Variable | Used by | Purpose |
|----------|---------|---------|
| `FLASK_ENV` | api | `development`, `testing` or `production` (default `production`) |
| `SECRET_KEY` | api | Signs sessions and tokens. Required in production |
| `DATABASE_URL` | api | SQLAlchemy URL, e.g. `postgresql+psycopg://user:pass@db:5432/etike`. Required in production |
| `TEST_DATABASE_URL` | tests | Separate database for tests (default in-memory SQLite) |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | db | Credentials for the Postgres container |
| `GUNICORN_WORKERS` | api | Worker processes in production (default 3) |

Never commit `.env`.

## Project structure

```
backend/    Flask API (app factory, config, routes, tests, migrations)
frontend/   Static site served by Nginx (index.html, css, js, assets)
nginx/      Nginx config (and an HTTPS example for the server)
data/       Real collected data, its sources and rules
docs/       Architecture and Scrum documents
.github/    CI, deploy workflow, pull request template
```

## Documentation

- [Architecture, VPS setup and HTTPS](docs/architecture.md)
- [Scrum process](docs/scrum/README.md), [Definition of Done](docs/scrum/definition-of-done.md), [Sprint 1](docs/scrum/sprints/sprint-1.md)
- [Data rules and sources](data/README.md)
