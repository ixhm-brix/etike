# Data

ETIKE uses **only real, collected data**: routes between districts, departure times, fares and bus companies. There is no dummy, fake or sample data anywhere in this project, in code, tests, seeds or the frontend.

## How data gets here

1. The team collects data from real sources (company websites, printed timetables, interviews, observation at terminals).
2. Every source is recorded in [`sources.md`](sources.md): what was collected, when, and by whom.
3. Raw files go in `raw/`. They are kept as collected, never edited by hand.
4. Raw data is cleaned: consistent district names, times in 24-hour format, fares in RWF as whole numbers, duplicates removed, and anything we could not confirm is marked as unconfirmed rather than guessed.
5. Cleaned data is loaded into the database through a migration or import script that lives in the backend, so anyone can repeat it.

## Personal data never goes in this repository

Do not commit names, phone numbers, ID numbers or photos of people, including from interviews. Summarise what you learned instead. The `.gitignore` excludes `raw/*` by default; only add a raw file to Git (with `git add -f`) after checking it contains no personal details, and record it in `sources.md`.
