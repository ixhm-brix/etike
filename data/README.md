# Data

ETIKE uses **only real, collected data**: routes between districts, departure times, fares and bus companies.

> **Bus data collection is paused.** Bus booking moved to a future phase (see the main README's Roadmap), because bus companies would first need an operator system. The bus formats below and the scripts' bus loaders are kept for that phase; while `FEATURE_BUS_BOOKING` is off, `clean_data.py` and `load_data.py` skip `bus_companies.csv` and `bus_trips.csv` with a message. Rides are posted by drivers on the website, so they need no collected data. There is no dummy, fake or sample data anywhere in this project, in code, tests, seeds or the frontend.

## How data gets here

1. The team collects data from real sources (company websites, printed timetables, interviews, observation at terminals).
2. Every source is recorded in [`sources.md`](sources.md): what was collected, when, and by whom.
3. Raw files go in `raw/`. They are kept as collected, never edited by hand.
4. Raw data is cleaned: consistent district names, times in 24-hour format, fares in RWF as whole numbers, duplicates removed, and anything we could not confirm is marked as unconfirmed rather than guessed.
5. `scripts/clean_data.py` does the cleaning and writes `processed/`. `scripts/load_data.py` loads `processed/` into the database. Both can be run again at any time (see the main README for the commands).

## The CSV files

Put these in `raw/` as UTF-8 CSV with a header row. Every file is optional: the scripts skip a missing one and say so. A row that fails a check is listed and left out; it is never guessed or filled in.

**`bus_companies.csv`**

| Column | Example of the format | Required |
|--------|-----------------------|----------|
| `name` | as printed by the company | yes |
| `contact_phone` | `078 123 4567` or `+250781234567` | no |
| `registration_number` | the company's RDB registration number | yes, it identifies the company |
| `licence_number` | RURA operating licence number | no |
| `source` | where it came from, matching a row in `sources.md` | yes |

**`bus_trips.csv`**: one row per departure on a date.

| Column | Example of the format | Required |
|--------|-----------------------|----------|
| `company_registration_number` | must match `bus_companies.csv` (or a company already loaded) | yes |
| `origin`, `destination` | district names; Nyarugenge, Gasabo, Kicukiro and Nyabugogo become Kigali, and old town names such as Butare (Huye) or Gisenyi (Rubavu) are converted | yes |
| `departure_date` | `2026-12-01` | yes |
| `departure_time` | `06:30`, `6h30` or `6:30 AM`, saved as 24-hour `HH:MM`, Rwanda time | yes |
| `price_rwf` | whole francs: `3500`, `3,500` or `3500 RWF` | yes |
| `total_seats` | seats on that bus | yes |
| `source` | as above | yes |

**`routes.csv`** (optional): `origin`, `destination`, `source`. Routes are also taken from the trips, so this is only needed for routes that have no dated trips yet.

## Districts and routes (what the live site uses now)

Rides need only two files, both in `processed/`. `clean_data.py` writes them; `load_data.py` reads them.

**`processed/districts.csv`**: the place names passengers can choose. `clean_data.py` writes it from the API's own list (`backend/app/places.py`: Kigali plus the 27 other districts), so it never needs hand-editing. `load_data.py` checks that it matches the API's list and warns if not.

| Column | What it holds |
|--------|---------------|
| `name` | official name, e.g. `Huye` |
| `also_written_as` | other spellings accepted in searches and raw files, separated by `; `, e.g. `Butare` |

**`processed/routes.csv`**: one row per direction travelled (Kigali to Huye and Huye to Kigali are two rows). Made by `clean_data.py` from `raw/routes.csv` (same columns).

| Column | What it holds | Required |
|--------|---------------|----------|
| `origin` | a `name` from `districts.csv` | yes |
| `destination` | a different `name` from `districts.csv` | yes |
| `source` | where we learned this route is travelled, matching a row in `sources.md` | yes |

`load_data.py` adds routes that are not in the database yet and skips (with a message) any row whose places are not two different known districts. Drivers can also create a route by posting a ride on it.

## Real drivers

Drivers normally sign up on the website. To add drivers the team has met (with their consent), use `scripts/add_drivers.py` with a CSV kept in `raw/` (ignored by Git) or answer its prompts:

| Column | Example of the format |
|--------|-----------------------|
| `full_name` | as on their licence |
| `phone` | `078 123 4567` |
| `license_number` | driving licence number |
| `plate_number` | `RAD 123 B` |
| `model` | `Toyota RAV4` |
| `seats` | passenger seats, driver not counted (1 to 30) |
| `national_id_number` | 16 digits, as on their ID |
| `date_of_birth` | `1988-04-21` (18 or older) |
| `gender` | `female` or `male` |
| `home_district`, `home_sector` | where they live, e.g. `Musanze`, `Muhoza` |

```bash
docker compose exec api python /data/scripts/add_drivers.py /data/raw/drivers.csv
```

Each driver starts **not approved**. They log in with the temporary password, check their details and upload their six documents (national ID, driving licence, RURA authorisation, vehicle registration card, insurance, inspection certificate) on the driver page; an admin approves them once all are uploaded and checked. Documents are never put in this folder or in Git. The script prints a temporary password for each driver, once; give it to the driver privately. Rows that fail a check or are already registered are skipped with a message.

## Consent

Before using anything a person told us (an interview, a driver's details), ask for their consent and record in `sources.md` whether it was given and when. The signed or recorded consent itself goes in `data/consent/`, which Git ignores: never commit it. Keep a copy somewhere the team controls (for example a shared drive with restricted access).

## Bus files (future phase)

`clean_data.py` writes the same columns to `processed/`, plus `districts.csv`, the list of official place names and the other spellings it accepts. Duplicates (same company, route, date and time) are removed.

`load_data.py` matches what is already in the database: companies by registration number, routes by origin and destination, trips by company, route and departure time. Running it twice adds nothing new. For a trip that is already loaded it only updates the fare, so seats already booked are kept.

## Personal data never goes in this repository

Do not commit names, phone numbers, ID numbers or photos of people, including from interviews. Summarise what you learned instead. The `.gitignore` excludes `raw/*` by default; only add a raw file to Git (with `git add -f`) after checking it contains no personal details, and record it in `sources.md`.
