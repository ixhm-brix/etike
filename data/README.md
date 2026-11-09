# Data

ETIKE uses **only real, collected data**: routes between districts, departure times, fares and bus companies. There is no dummy, fake or sample data anywhere in this project, in code, tests, seeds or the frontend.

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

`clean_data.py` writes the same columns to `processed/`, plus `districts.csv`, the list of official place names and the other spellings it accepts. Duplicates (same company, route, date and time) are removed.

`load_data.py` matches what is already in the database: companies by registration number, routes by origin and destination, trips by company, route and departure time. Running it twice adds nothing new. For a trip that is already loaded it only updates the fare, so seats already booked are kept.

## Personal data never goes in this repository

Do not commit names, phone numbers, ID numbers or photos of people, including from interviews. Summarise what you learned instead. The `.gitignore` excludes `raw/*` by default; only add a raw file to Git (with `git add -f`) after checking it contains no personal details, and record it in `sources.md`.
