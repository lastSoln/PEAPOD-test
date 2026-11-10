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

## How the engine works

`engine/planner.py` follows the Peapod Engine Manual: **Filter, Taste, Walk, Assemble**.

**Filter (hard limits, never relaxed).** Active only; fixed Area means that zone only; bars and
nightlife only if every member ticked over 18; open for the whole visit at the arrival time; and the
plan's total estimated cost must fit the lowest budget tier among the members (a fixed Budget row can
lower it). A hub with fewer than 3 eligible places is "empty"; if the Kind row needs it the engine
fails and names the row. Diet, allergies, ratings and "needs" are ignored.

**Taste (ranks what survived).** Each candidate's score is the sum of these parts, all shown in the
debug view:

| Part | Formula | Weight |
|---|---|---|
| Majority | weight × share of counted members who match | `majority_share` |
| Match sum | sum of per-member match ÷ counted members (exact chip 1, same tile 0.6) | `chip_exact`, `chip_same_tile` |
| No chip | flat score for a place with no chip, instead of the two above | `no_chip_base` |
| Fairness | bonus × share of still-unmatched members this stop would serve | `fairness_bonus` |
| Variety | minus the penalty if the hub repeats the previous stop's hub | `variety_penalty` |
| Distance | minus the penalty × km from the previous stop | `distance_penalty_per_km` |
| Price | weight × closeness of the price to the per-stop target for the budget tier | `price_closeness` |
| New slot | bonus, in the last stop only, for a hub or chip nobody picked | `new_slot_bonus` |
| Jitter | seeded random tie-break | `seed_jitter` |

A member with no pick in a candidate's hub is not counted, so they do not pull its share down.
Interest tiles (which chips are "the same tile") are the 12 tiles from the alpha onboarding design,
in `engine/taxonomy.py`.

**Walk.** Stops are chosen one at a time. Each slot first allows only hubs the pod still wants and has
not had yet; if nothing fits, it loosens the hub mix (and says so in the debug view). Every candidate
must be within the max travel time of the previous stop, open at its own real arrival time, and
affordable with what is left of the budget. Travel between stops is walking if the walk is 15 minutes
or less, otherwise public transport.

**Assemble.** Times, legs, cost per person, a why-line, and up to 4 alternatives per stop. If nothing
fits, the message says so plainly and never says whose limit blocked it.

**Sanity checks** (`engine/checks.py`) are recomputed from the finished plan, not taken from the walk:
every stop open at arrival, total cost within the lowest budget, no repeated place, no same hub back
to back, every leg under the limit, at least one match per member where a matching place exists.

### Choices I made where the manual is silent

These are the first things to argue with:

- **The "something new" slot is the last stop.** Any hub is allowed there. "New" means a hub nobody
  wants, or a place none of whose chips anybody picked.
- **A fixed Kind on a Day out** fixes the first stop's hub; the rest of the day is free.
- **The first stop's distance** is measured from the middle of the members' homes.
- **No need state.** The engine does not yet prefer food at mealtimes or bars in the evening; only
  opening hours steer that.
- **Budget reserve.** While walking, each remaining stop keeps a small reserve (up to $8) so an early
  stop cannot spend the whole budget.
- **Soft loosening is hub mix only.** Area and time are treated as fixed, as the brief asks.
- **Fairness on a Moment** passes if the single stop matches at least one member.
- **Leave-home speeds** are guesses in `engine/config.py`: walk 4.8 km/h, public transport 18 km/h
  plus 10 min, car 30 km/h plus 5 min, cab 30 km/h plus 8 min, each with a detour factor.

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
A Day out takes 1 to 3 seconds to plan.

## Layout

```
engine/      the plan engine: pure functions, no web imports
  taxonomy.py  zones, hubs, interest tiles
  config.py    default weights, budget tiers, travel speeds
  dataset.py   read-only loader, opening-hours parsing
  geo.py       distance and travel time
  planner.py   filter, taste, walk, assemble
  checks.py    automatic sanity checks
app/         FastAPI layer: password, API, bench.sqlite store, example pods
static/      the single page (plain JS)
scripts/     build_dataset.py, dev.py
tests/       engine tests against the bundled dataset
data/        places.sqlite (bundled, read-only)
```

Using the engine on its own:

```python
from engine import load_dataset, plan
ds = load_dataset("data/places.sqlite")
result = plan(ds, pod, request, {"weights": {"fairness_bonus": 2}, "seed": 7})
```

## API

| Route | What it does |
|---|---|
| `POST /api/plan` | `{pod, request, config, tester, label}`; plans, saves the run, returns it with `run_id` |
| `POST /api/compare` | Same pod and request with `config_a` and `config_b`; saves both |
| `POST /api/runs/{id}/feedback` | `{plan_score, plan_note, stops: [{index, verdict, reason, note}]}` |
| `GET /api/runs`, `GET /api/runs/{id}` | Saved runs and pass-rate totals; one run in full |
| `GET /api/export.csv?level=stops\|runs` | CSV with inputs, weights, output and feedback together |
| `GET /api/meta`, `GET /api/random-pod` | Chips, zones, hubs, weights, example pods; a random pod |
