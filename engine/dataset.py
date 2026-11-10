"""Read-only access to the Peapod places dataset.

Two sources, same result: a SQLite file opened in URI mode with mode=ro, or a
Postgres table (Supabase) read in a read-only session. Nothing here writes. Only
the `places` table is read, and only rows with status='active'.
"""

import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .taxonomy import CHIP_TILE, HUBS, ZONES

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

COLUMNS = (
    "place_id, name, address, latitude, longitude, zone, hub, chips, price_min, price_max, "
    "hours, visit_minutes, indoor_outdoor, website, phone, basis"
)


@dataclass(slots=True)
class Place:
    id: str
    name: str
    address: str
    lat: float
    lng: float
    zone: str
    hub: str
    chips: tuple
    tiles: frozenset
    price_min: float
    price_max: float
    price: float            # estimate used by the engine: midpoint of min and max
    hours: dict             # weekday 0..6 -> [(start_min, end_min)], end may pass 1440
    hours_raw: dict         # as stored, for display
    visit: int
    indoor_outdoor: str
    website: str
    phone: str
    basis: dict


@dataclass
class Dataset:
    places: list
    by_id: dict
    chip_hub: dict           # chip -> the hub most of its places sit in
    chip_counts: dict
    zone_centroids: dict
    hubs: list = field(default_factory=lambda: list(HUBS))
    zones: list = field(default_factory=lambda: list(ZONES))


def _hm(text):
    h, m = text.split(":")
    return int(h) * 60 + int(m)


def parse_hours(raw):
    """{"Mon": ["10:30-22:30"], ...} -> {0: [(630, 1350)], ...}. Missing day = closed."""
    out = {}
    for day, spans in (raw or {}).items():
        if day not in DAYS:
            continue
        intervals = []
        for span in spans or []:
            try:
                a, b = span.split("-")
                s, e = _hm(a), _hm(b)
            except (ValueError, AttributeError):
                continue
            if e <= s:          # runs past midnight
                e += 1440
            intervals.append((s, e))
        if intervals:
            out[DAYS.index(day)] = intervals
    return out


def is_open(place, weekday, minute, duration):
    """Open for the whole visit starting at `minute` (minutes after 00:00) on `weekday`."""
    weekday = (weekday + minute // 1440) % 7
    minute = minute % 1440
    for s, e in place.hours.get(weekday, ()):
        if s <= minute and minute + duration <= e:
            return True
    for s, e in place.hours.get((weekday - 1) % 7, ()):   # yesterday's late session
        if e > 1440 and s <= minute + 1440 and minute + 1440 + duration <= e:
            return True
    return False


def _json(value, default):
    """Accepts JSON text (SQLite, Postgres text) or an already-decoded value (Postgres jsonb)."""
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


def _build(rows):
    """Rows in COLUMNS order -> Dataset. Shared by every source."""
    places = []
    chip_hub_counts = defaultdict(Counter)
    chip_counts = Counter()
    zsum = defaultdict(lambda: [0.0, 0.0, 0])
    for (pid, name, address, lat, lng, zone, hub, chips, pmin, pmax, hours, visit,
         io, website, phone, basis) in rows:
        if lat is None or lng is None or not hub:
            continue
        chips_t = tuple(c for c in _json(chips, []) if isinstance(c, str))
        hours_raw = _json(hours, {})
        if not isinstance(hours_raw, dict):
            hours_raw = {}
        basis_d = _json(basis, {})
        pmin = float(pmin or 0)
        pmax = float(pmax if pmax is not None else pmin)
        p = Place(
            id=str(pid), name=name or "", address=address or "", lat=float(lat), lng=float(lng),
            zone=zone or "", hub=hub, chips=chips_t,
            tiles=frozenset(CHIP_TILE[c] for c in chips_t if c in CHIP_TILE),
            price_min=pmin, price_max=pmax, price=round((pmin + pmax) / 2, 2),
            hours=parse_hours(hours_raw), hours_raw=hours_raw, visit=int(visit or 60),
            indoor_outdoor=io or "", website=website or "", phone=phone or "",
            basis=basis_d if isinstance(basis_d, dict) else {},
        )
        places.append(p)
        for c in chips_t:
            chip_hub_counts[c][p.hub] += 1
            chip_counts[c] += 1
        z = zsum[p.zone]
        z[0] += p.lat; z[1] += p.lng; z[2] += 1

    places.sort(key=lambda p: p.id)   # stable order so a seed repeats exactly
    return Dataset(
        places=places,
        by_id={p.id: p for p in places},
        chip_hub={c: cnt.most_common(1)[0][0] for c, cnt in chip_hub_counts.items()},
        chip_counts=dict(chip_counts),
        zone_centroids={z: (v[0] / v[2], v[1] / v[2]) for z, v in zsum.items() if v[2]},
    )


def load_dataset(path):
    """Load from a SQLite file, opened read-only."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Places dataset not found: {path}")
    uri = "file:" + path.resolve().as_posix() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        rows = con.execute(f"SELECT {COLUMNS} FROM places WHERE status='active'").fetchall()
    finally:
        con.close()
    return _build(rows)


_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*([.][A-Za-z_][A-Za-z0-9_]*)?$")


def load_dataset_postgres(url, table="public.places", timeout=20):
    """Load from Postgres (Supabase). The session is read-only, so nothing here can write.

    The table needs the same column names as the SQLite `places` table. `chips`, `hours`
    and `basis` may be text or jsonb. Needs the `psycopg` package.
    """
    if not _IDENT.match(table):
        raise ValueError(f"Not a plain table name: {table!r}")
    import psycopg  # imported here so the SQLite path has no extra dependency

    # prepare_threshold=None keeps this working through Supabase's transaction pooler too
    with psycopg.connect(url, connect_timeout=timeout, prepare_threshold=None) as con:
        con.read_only = True
        with con.cursor() as cur:
            cur.execute(f"SELECT {COLUMNS} FROM {table} WHERE status = 'active'")
            rows = cur.fetchall()
    if not rows:
        raise ValueError(f"{table} has no rows with status = 'active'")
    return _build(rows)
