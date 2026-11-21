# Usability test plan

## Goals

Find out whether real travellers and drivers can use ETIKE without help, and where they get stuck. Specifically:

ETIKE's current scope is shared and private rides between districts. A ride is confirmed as soon as it is booked; the driver starts and ends the ride in the app, and the passenger then pays with MTN MoMo in the app, like a taxi app.

1. Can a traveller find a ride, book it, and understand that they pay with MoMo after the ride?
2. Can a traveller cancel a booking, and do they understand the cancellation deadline?
3. Can a traveller rate a driver after a ride?
4. Can a driver add a vehicle and post a ride?
5. How usable do people find the site overall (System Usability Scale score)?

## Participants

5 to 8 people, recruited in person in Kigali (for example at Nyabugogo bus park and on campus):

- 4 to 6 travellers who travel between districts at least once a month, with a mix of ages and of how often they use smartphones.
- 1 to 2 drivers who already drive between districts.

Nobody from the team, and nobody who has seen ETIKE before.

## Consent

Before each session, read the participant this (in Kinyarwanda or English, their choice) and get a spoken or written yes:

- We are testing the website, not you. There are no wrong answers.
- The session takes about 20 minutes and you can stop at any time without giving a reason.
- We will take notes and time the tasks. We will not record your face, voice or screen unless you agree separately.
- We do not keep your name or phone number with the results. You get an ID like P3.
- No real money moves: MoMo runs on its sandbox during sessions, and no real ride takes place.

Keep signed consent forms (or a note that consent was given) separate from the results, and destroy them when the project ends. Do not put them in the repository.

## Set-up

- A test phone with the site open, logged out, on mobile data (not office Wi-Fi), so the speed is realistic.
- At least two real rides posted on the test server for Kigali to Huye next Friday (one shared, one private), by a test driver account the facilitator controls. Never use the live database for sessions.
- For the rating task, a confirmed test ride booking that has already departed, made by the facilitator beforehand on the test server (not the live database).
- For the driver task, a test driver account already approved by the facilitator.
- One facilitator who gives the tasks and stays quiet, and one note-taker with a stopwatch.

## Tasks

Read each task out as written. Don't explain the screen or point.

| # | Who | Task | Done when |
|---|-----|------|-----------|
| T1 | Traveller | "You want to travel from Kigali to Huye next Friday. Find what is available." | Results page for Kigali to Huye on that date is showing |
| T2 | Traveller | "Book one seat in a shared ride you like." (creates an account if asked) | The booking shows as confirmed in My bookings |
| T3 | Traveller | "How and when will you pay for this ride?" (answer out loud) | Says they pay with MTN MoMo after the ride |
| T4 | Traveller | "Your plans changed. Cancel that booking." | Booking shows as cancelled |
| T5 | Traveller | "You took a shared ride yesterday. Rate the driver." | Rating saved |
| T6 | Driver | "Add your car, then offer 3 seats from Kigali to Musanze tomorrow at 7:00 for 3,000 francs each." | Ride posted message shows |

Ask participants to think aloud: "say what you are looking for and what you expect to happen".

## What to measure

For every task, the note-taker records:

- **Completed**: yes, with help, or no. "With help" means the facilitator had to say anything beyond repeating the task.
- **Time on task**: from the end of reading the task to the "done when" moment, in seconds. Stop at 5 minutes and mark it not completed.
- **Errors**: each wrong turn, for example a wrong menu, going back, a form error message, or tapping something that isn't a button. Write what happened in a few words.
- **Comments**: anything the participant says that shows confusion or a strong reaction, quoted briefly.

After all tasks, the participant fills in the [SUS questionnaire](sus-questionnaire.md) on paper.

## After the sessions

1. Enter results in [results.md](results.md), using participant IDs only.
2. For each task, calculate the completion rate, median time and total errors.
3. Calculate the average SUS score. 68 is roughly average; aim for above 68.
4. Log every problem in [bug-log.md](bug-log.md). Problems that blocked or slowed more than one person are severity High or above.
