# Peapod plan test bench

A small web app for testing the Peapod plan engine and the place dataset: build a fake pod, ask for a
plan, read the debug view, change the weights, compare two runs, and record feedback. It is not the
real UI. The engine in `engine/` has no web imports and is meant to be lifted into the real service.

## What the dataset looks like (inspected 10 Nov 2026, before any code)

Source: `peapod_scraper/data/peapod_places.sqlite`, table `places`, opened read-only.

- **Rows:** 35,861 in `places`; **35,856 active**, 5 closed. Only active rows are used. `raw_records`,
  `web_pages`, `web_extractions`, `runs` and `tiles` (scraper map tiles, not interest tiles) are ignored.
- **The file is 1.4 GB**, almost all of it scraper tables. The bench bundles a 21 MB copy with only the
  active `places` rows and the columns it uses (`scripts/build_dataset.py`).
- **Zones (6):** Central 16,659 · West 5,642 · South 5,159 · East 4,786 · North 2,035 · North-East 1,575.
  Nearly half of everything is Central.
- **Hubs (8):** Food 19,580 · Cafes, sweets and soft drinks 7,268 · Outdoors and active 2,180 ·
  Bars and nightlife 1,689 · Culture and shows 1,550 · Make and browse 1,510 · Wellness 1,479 ·
  Play and attractions 600. Food and cafes are 75% of the data.
- **Chips:** 60 distinct. Most common: Asian 9,688 · Local & street food 4,439 · Specialty coffee 3,735 ·
  Western & European 2,474 · Bakeries & pastries 1,508 · Gardens & parks 1,418 · Massage & spa 1,140 ·
  Cocktail bars 1,020. The tail is thin: 12 chips have fewer than 20 places (Rooftop bars 1,
  Drinks-making 1, Festivals & fairs 1, Live-music bars 3, Snow & ice sports 4, Comedy 5, Fine dining 8).
  A place has 1 chip in 85% of rows, 2 or more in 5%.
- **No chip: 3,809 places (10.6%)**, of which 3,544 are Food. These are matched by hub only.
- **Chips do not always sit in one hub** (a few Food places carry "Specialty coffee", for example). The
  engine maps each chip to the hub most of its places are in.
- **Hours:** JSON keyed by weekday, each a list of `"HH:MM-HH:MM"` spans, e.g.
  `{"Mon": ["10:30-22:30"], ...}`. A missing weekday means closed that day (about 3% of rows miss a day).
  Spans can pass midnight (`"18:00-01:00"`) and can end at `"24:00"`. Never null.
  **`basis.hours` is `estimated` for 89%** (31,904); the rest come from OSM, web pages or chain feeds.
- **Prices:** `price_min` and `price_max` never null; medians 12 and 35 SGD, maximum 1,000.
  **`basis.price` is `estimated` for 97.5%.** The engine uses the midpoint as the per-person estimate.
- **Visit length:** never null, 60 to 150 minutes, median 75.
- **Null rates of the columns used:** name, latitude, longitude, zone, hub, price, hours,
  visit_minutes 0% · indoor_outdoor 2% · phone 37% · website 53% · address 14.5%.
- **Empty, so not used:** rating 100% null, wheelchair 94%, halal 97%, vegetarian 96%.
- **Three chips in the app design have no places** (Pottery & ceramics, Board-game cafés,
  Pool & beach-club days), so the pod builder does not offer them.

## What the bench does

Five tabs, built for a phone first (on a wide screen the pod sits beside the rest):

- **Pod.** 3 to 10 fake peas. Each answers the app's four onboarding questions: interests (3 to 5
  tiles, with optional favourites inside them), spend, how far they usually go, and plan style. Plus
  over 18, home and needs.
- **Plan.** Start a Moment or a Day out, choose who pitches it, then play the whole life of the plan:
  swipe as each pea (I'm in, Maybe, Can't, or no answer, with reasons), close the round, see what
  Peapod reworked, and after the rounds edit, heart, leave, rejoin and approve.
- **Inspect.** The sanity checks, the map, what survived each filter, each pea's limits, and the top
  candidates for every stop with the score broken into parts.
- **Tune.** Every weight, the seed, the budget tiers, and a side-by-side compare of two weight sets.
- **Log.** The plan's append-only log, the full list of rules, and every saved run with CSV exports.

## The rules

All 71 rules are in `engine/rules.py` and on the Log tab, each marked **manual** (from the engine
manual), **design** (from the app design) or **guess** (my choice where neither says). In short:

**Hard limits (filter, never loosened).** Active places only; a fixed Area; bars only if everyone is
over 18; the plan's total cost within the lowest spend tier; every stop within each pea's travel
answer from their home (Close by 15 min, Across town 45 min, Out of town no limit, by the fastest of
walk, public transport, car or cab); nothing a pea said they had "Done lately"; open for the whole
visit at the real arrival time. A kind with fewer than 3 eligible places is empty, and a Kind row that
needs it fails by naming the row.

**Taste (ranking).** A favourite is an exact match (1), another chip from a picked interest is a near
match (0.6). Majority first: the share of counted peas who match, then the sum of their matches. A pea
with no pick for that kind of stop is not counted. A fairness bonus pulls in a stop for anyone not yet
matched. Places with no chip are matched by kind only, at a lower flat score.

**Plan style (soft).** Go with the flow favours short hops (and, as a majority, one stop fewer and
longer visits). The Planner favours confirmed hours (as a majority, one stop more). The Explorer
favours one-off places and chips nobody picked. The Foodie favours food and cafe stops and makes Food
a kind the pod wants. Style never filters anything out.

**Walk.** Stops are chosen one at a time: a kind the pod still wants, not the same kind twice in a
row, a penalty per km, a hard cap on each leg, and the last slot kept for something new.

**Swiping.** The pitcher is in. Everyone else answers each round. Maybe, or Can't with a practical
reason (Too far, Too pricey, Wrong time, Busy that day), keeps them in the rounds and Peapod reworks
the plan. Can't with a "not for me" reason puts them out. No answer counts as Can't with no reason;
three in a row is out. Three rounds at most, and round 3 is I'm in or Can't only. Everyone left in,
with at least 2, makes it a plan; fewer than 2 ends it.

**Rework.** The smallest change that answers all the reasons together, inside everyone's hard limits.
Too far tightens that pea's limit for this plan; Too pricey lowers this plan's budget; Wrong time moves
the start 2 hours; Busy that day moves a Saturday to Sunday and anything else a week on. Only stops
that break the tightened limits are replaced, same kind first. The pod sees what changed and a neutral
why, never who asked.

**Planning.** Anyone going can change, remove, add or reorder stops. "Change it to" offers 2 to 4
options with a tag (Cheaper, Closer, Quicker, More chill, More active, Something different). Anyone
out can rejoin; anyone going can leave. When everyone going approves, the plan is locked.

**Learning.** "Not my thing anymore" halves that pea's match on the plan's chips. "Done it lately" and
"Not with this group" rest the plan's places. A heart raises the match on that stop's chips. Practical
reasons, silence and limits never move taste.

### Where the manual and the design disagree

- **Maybe versus Can't.** The manual gives Maybe the practical reasons and Can't the "not for me"
  ones. The design's rule book (v64) puts both groups under Can't, and has Maybe "pick what to
  change". The bench accepts both: a practical reason with Maybe or Can't keeps the pea in the rounds.
- **Rounds.** The rule book says "no limit on rounds"; the alpha flow and the manual say three. The
  bench uses three (`max_rounds`).
- **Spend tiers.** The onboarding design shows under $20, $20 to $60 and $60 and up "a head"; the
  brief says whole-day tiers starting at under 40, 40 to 100 and 100 and over. The bench uses the
  brief's numbers with the design's names, and both cut-offs are editable on the Tune tab.

### Not in the bench

The 24-hour clock, nudges and notifications, the 2-days-before close of swiping, drag to reorder
(the bench has up and down buttons), typing a place name to add your own stop, and the need state
(preferring food at mealtimes). Trips, pay and booking are not part of alpha.

## What gets logged

Every step is appended to the `events` table in `bench.sqlite` and never edited. Each event has a
time (Singapore), the plan, the round, the phase, who did it, a type and the full detail as JSON.

| Event | What it records |
|---|---|
| `plan_requested` | The request, who pitched it, the whole pod snapshot, the weights, tiers and seed |
| `plan_built` | Why it was built (first draft, rework, member edit), every stop with its score, the cost, the checks, how many places survived each filter, and the top 5 candidates per stop with score parts |
| `vote` | The pea, the answer (in, maybe, cant) and the reason |
| `no_answer` | The pea, how many rounds missed in a row, and whether that put them out |
| `member_out` | The pea and how: cant, missed, or left |
| `rework` | Every reason and who gave it, what was tightened, and each change (from, to, why) |
| `round_started` | The round number and who it goes to |
| `phase_changed` | Swiping to Planning, Planning to Approved, or Ended, and why |
| `edit` | Who changed what in Planning (from, to, tag) and the checks afterwards |
| `heart`, `approve`, `unapprove`, `leave`, `rejoin` | The pea and the stop or reason |
| `taste_nudge` | The pea, the reason, and exactly which chips or places changed and by how much |

Acceptance is an `in` vote (the pitcher counts as in from `plan_requested`) and then an `approve`.
Rejection is a `cant` vote with its reason, a `no_answer`, or a `leave`; each produces a `member_out`,
and a "not for me" reason also produces a `taste_nudge`. A practical reason produces a `rework`
instead. Reasons are in the log but never in anything the pod is shown.

Each plan the engine builds is also saved as a run (with the tester's Good, OK or Bad per stop and
the 1 to 5 score), so the three CSV exports are: one row per stop, one row per run, and the log.

## Run it locally

Needs Python 3.11 or newer.

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # macOS/Linux: .venv/bin/pip
.venv/Scripts/python scripts/dev.py               # http://127.0.0.1:8000, no password
```

`scripts/dev.py` turns the password off and writes runs to `bench.dev.sqlite`. To run it the way it
is deployed, set a password instead:

```bash
BENCH_PASSWORD=choose-one .venv/Scripts/python -m uvicorn app.main:app --port 8000
```

Tests: `python -m unittest discover tests`

### Refreshing the bundled dataset

```bash
python scripts/build_dataset.py "C:/Users/srishti/Desktop/peapod_scraper/data/peapod_places.sqlite"
```

This opens the scraper file read-only and rewrites `data/places.sqlite`. The copy in this folder was
taken on 10 Nov 2026 while the scraper's `web-render` step was still running, so rebuild it once
that finishes.

### Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `BENCH_PASSWORD` | none | The shared password. The app will not start without it. |
| `BENCH_NO_AUTH` | unset | `1` turns the password off. Local use only. |
| `PEAPOD_PLACES_DB` | `data/places.sqlite` | The places file. Opened with `file:...?mode=ro`. |
| `PEAPOD_PLACES_URL` | unset | Postgres (Supabase) connection string. When set, places are read from there instead of the file. |
| `PEAPOD_PLACES_TABLE` | `public.places` | The table to read when `PEAPOD_PLACES_URL` is set. |
| `BENCH_DB` | `bench.sqlite` | Saved runs and feedback. The only file the app writes. |

## Reading places from Supabase

Set `PEAPOD_PLACES_URL` and the bench reads `public.places` from Supabase once at startup, in a
read-only session, instead of the bundled file. The top bar and `/healthz` say which source is in
use. If Supabase cannot be read, the bench starts on the bundled file and says "Supabase failed"
(hover the top bar for the reason).

The table needs the same column names as the SQLite `places` table: `place_id, name, address,
latitude, longitude, zone, hub, chips, price_min, price_max, hours, visit_minutes, indoor_outdoor,
website, phone, basis, status`. `chips`, `hours` and `basis` may be `text` or `jsonb`.

Give the bench its own read-only role, so the database itself enforces "never write to the dataset".
Run this once in the Supabase SQL editor, with a password of your own:

```sql
create role bench_reader login password 'choose-a-long-password';
grant usage on schema public to bench_reader;
grant select on public.places to bench_reader;
```

Then take the **Session pooler** connection string from Supabase's Connect panel (Render's free
tier cannot reach the direct IPv6 address) and replace the user and password. A pooler user name
has the project ref after a dot:

```
postgresql://bench_reader.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
```

Put that in `PEAPOD_PLACES_URL` in Render's Environment tab. To try it locally first, put the same
line in a `.env` file in this folder (`PEAPOD_PLACES_URL=postgresql://...`); `scripts/dev.py` reads
it and Git ignores it.

## Deploy (one container)

The `Dockerfile` bundles the engine, the page and `data/places.sqlite`. Runs and feedback live in
`/data/bench.sqlite`, so mount a persistent disk at `/data` or they are lost on every redeploy.

**Render.** Push this folder to a Git repository, then New > Blueprint and pick the repository;
`render.yaml` creates the service and a 1 GB disk in Singapore. Set `BENCH_PASSWORD` when asked.

**Fly.io.**

```bash
fly launch --copy-config --no-deploy
fly volumes create bench_data --size 1 --region sin
fly secrets set BENCH_PASSWORD=choose-one
fly deploy
```

**Railway.** New project from the repository (it finds the Dockerfile), add a volume mounted at
`/data`, and set `BENCH_PASSWORD`.

The app loads all places into memory at start (about 3 seconds, roughly 300 MB), so give it 512 MB.
A Day out takes 1 to 3 seconds to plan, and so does each rework or edit.

## Layout

```
engine/      the plan engine: pure functions, no web imports
  taxonomy.py  zones, hubs, interest tiles, travel answers, plan styles, vote reasons
  config.py    default weights, budget tiers, travel speeds
  dataset.py   read-only loaders (SQLite file or Supabase), opening-hours parsing
  geo.py       distance and travel time
  planner.py   filter, taste, plan style, walk, assemble
  checks.py    automatic sanity checks
  flow.py      swiping rounds, rework, planning edits, approval, taste learning
  rules.py     every rule in plain words
app/         FastAPI layer: password, API, bench.sqlite store (runs, sessions, log), example pods
static/      the single page (plain JS)
scripts/     build_dataset.py, dev.py
tests/       engine and flow tests against the bundled dataset
data/        places.sqlite (bundled, read-only)
```

Using the engine on its own:

```python
from engine import load_dataset, plan, flow
ds = load_dataset("data/places.sqlite")
result = plan(ds, pod, request, {"weights": {"fairness_bonus": 2}, "seed": 7})

session, events = flow.start(ds, pod, request, config, pitcher="Mara")
events = flow.submit_votes(ds, session, {"Jun": {"answer": "maybe", "reason": "too_far"}})
events = flow.act(ds, session, {"type": "approve", "name": "Mara"})
```

## API

| Route | What it does |
|---|---|
| `POST /api/session` | `{pod, request, config, pitcher, tester, label}`; builds the first draft and starts swiping |
| `POST /api/session/{id}/votes` | `{votes: {name: {answer, reason}}}`; closes the round, reworks if asked |
| `POST /api/session/{id}/act` | `{type, name, ...}`: approve, unapprove, leave, rejoin, heart, change, remove, move, add |
| `GET /api/session/{id}/options?stop=` | "Change it to" options for a stop, or quick picks for a new one |
| `GET /api/session/{id}`, `GET /api/events` | A plan with its log; the log across plans |
| `POST /api/compare` | Same pod and request with `config_a` and `config_b`; saves both first drafts |
| `POST /api/runs/{id}/feedback` | `{plan_score, plan_note, stops: [{index, verdict, reason, note}]}` |
| `GET /api/runs`, `GET /api/runs/{id}` | Saved runs and pass-rate totals; one run in full |
| `GET /api/export.csv?level=stops\|runs\|events` | CSV exports |
| `GET /api/meta`, `GET /api/rules`, `GET /api/random-pod` | Options and weights; the rules; a random pod |
