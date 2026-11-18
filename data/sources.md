# Data sources

Add one row for every source, before its data is used.

For anything that came from a person (an interview, a driver's details), ask for their consent first. Fill in **Consent obtained** (`yes` or `no`) and **Consent date**. Data with `no` is not used. The consent records themselves (forms, recordings) stay outside the repository, in `data/consent/` (ignored by Git) or the team's restricted shared drive. Public sources need no consent: write `n/a`.

| Source | Type (website / timetable / interview / observation) | What was collected | Date collected | Collected by | Consent obtained | Consent date |
|--------|------------------------------------------------------|--------------------|----------------|--------------|------------------|--------------|
| geoBoundaries, RWA ADM2 (Open Data Rwanda 2012), CC BY 4.0 | website | District boundaries for the landing-page map (`frontend/assets/rwanda-districts.geojson`, simplified) | 2026-11-02 | Team 3 | n/a | n/a |
| OpenStreetMap via the OSRM demo router, ODbL | website | Road routes, distances and driving times, fetched live in the browser (not stored) | 2026-11-02 | Team 3 | n/a | n/a |
