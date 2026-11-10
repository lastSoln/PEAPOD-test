"""Build the small bundled dataset from the full scraper database.

The scraper file is about 1.4 GB because of raw_records and web pages. The
bench only needs the active rows of `places`, so this copies those (about
36,000 rows, a few tens of MB) into data/places.sqlite for the container.

The source is opened read-only and is never written to.

    python scripts/build_dataset.py "C:/Users/srishti/Desktop/peapod_scraper/data/peapod_places.sqlite"
"""

import sqlite3
import sys
from pathlib import Path

COLS = ["place_id", "name", "address", "latitude", "longitude", "zone", "hub", "chips",
        "price_min", "price_max", "hours", "visit_minutes", "indoor_outdoor", "website",
        "phone", "basis", "status"]


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent.parent / "data" / "places.sqlite"
    if not src.exists():
        sys.exit(f"Source not found: {src}")
    if out.resolve() == src.resolve():
        sys.exit("Refusing to write over the source dataset.")
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    con = sqlite3.connect("file:" + src.resolve().as_posix() + "?mode=ro", uri=True)
    rows = con.execute(f"SELECT {', '.join(COLS)} FROM places WHERE status='active'").fetchall()
    con.close()

    dst = sqlite3.connect(out)
    dst.execute(
        "CREATE TABLE places (place_id TEXT PRIMARY KEY, name TEXT NOT NULL, address TEXT, latitude REAL, "
        "longitude REAL, zone TEXT, hub TEXT NOT NULL, chips TEXT, price_min REAL, price_max REAL, hours TEXT, "
        "visit_minutes INTEGER, indoor_outdoor TEXT, website TEXT, phone TEXT, basis TEXT, status TEXT NOT NULL)")
    dst.executemany(f"INSERT INTO places VALUES ({', '.join('?' * len(COLS))})", rows)
    dst.commit()
    dst.execute("VACUUM")
    dst.close()
    print(f"Wrote {len(rows)} active places to {out} ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
