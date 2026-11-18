# Progress documentation (Sprint 1)

Taken from the running project on 2026-11-03. Only work that exists is shown here.

## Figma

Not available. There is no Figma file for ETIKE. The design was made straight in
HTML/CSS; see the frontend screenshots below.

## Database

Not available yet. Sprint 1 has no tables. PostgreSQL 16 runs and the API connects
to it (see `backend-1-api-health-response.png`), but no models or migrations exist
(`backend/migrations/versions/` is empty). There is no ER diagram or schema to show yet.

## Frontend

Screenshots (desktop, 1456 px wide):

- `screenshots/frontend-1-landing-route-map.jpg`: landing page with the trip form and
  the district map showing the road route Rusizi to Nyagatare (about 361 km).
- `screenshots/frontend-2-ways-to-travel.jpg`: "Ways to travel" and "Book a trip in three steps".
- `screenshots/frontend-3-steps-drivers-footer.jpg`: "Drive or run buses with ETIKE" and footer.

Code: https://github.com/ixhm-brix/etike/tree/main/frontend

Note: the district map in the screenshots is not pushed to GitHub yet. The GitHub
version still has the earlier map.

## Backend / API

Screenshots:

- `screenshots/backend-1-api-health-response.png`: `GET /api/health` returning
  `{"database": "ok", "status": "ok"}`.
- `screenshots/backend-2-health-endpoint-code.jpg`: the health endpoint code on GitHub.
- `screenshots/backend-3-ci-passing.jpg`: GitHub Actions CI, both runs passing.

`backend-test-output.txt`: ruff (lint) and pytest output, 2 tests passing.

Links:

- Backend code: https://github.com/ixhm-brix/etike/tree/main/backend
- Health endpoint: https://github.com/ixhm-brix/etike/blob/main/backend/app/routes/health.py
- Tests: https://github.com/ixhm-brix/etike/blob/main/backend/tests/test_health.py
- CI runs: https://github.com/ixhm-brix/etike/actions/workflows/ci.yml
- Endpoint: `GET /api/health` (only on a local machine for now; the staging server
  is not set up yet, so there is no public URL)
