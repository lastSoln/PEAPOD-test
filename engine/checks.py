"""Automatic sanity checks, re-derived from the finished plan rather than trusted
from the walk, so a planner bug (or a member's own edit) shows up as a failed check."""

from datetime import date as _date
from math import ceil

from .dataset import is_open
from .geo import fastest_minutes, haversine_km, leg_estimate


def run_checks(ds, result, members, pool, cfg):
    stops = result["stops"]
    weekday = _date.fromisoformat(result["date"]).weekday()
    places = [ds.by_id[s["place"]["id"]] for s in stops]
    items = []

    def add(key, label, ok, detail):
        items.append({"key": key, "label": label, "pass": bool(ok), "detail": detail})

    closed = [p.name for s, p in zip(stops, places) if not is_open(p, weekday, s["arrival_min"], s["duration"])]
    add("open", "Every stop open at arrival", not closed,
        "All open for the visit length (estimated hours)." if not closed else "Closed: " + ", ".join(closed))

    cap = result.get("budget_cap")
    total = round(sum(p.price for p in places), 2)
    add("budget", "Total cost within the lowest budget", cap is None or total <= cap,
        f"${total:g} per person" + (f" against a ${cap:g} limit." if cap is not None else ", no upper limit."))

    ids = [p.id for p in places]
    add("unique", "No repeated place", len(set(ids)) == len(ids), f"{len(set(ids))} distinct of {len(ids)} stops.")

    pairs = [f"{a.hub} (stops {i + 1}-{i + 2})" for i, (a, b) in enumerate(zip(places, places[1:])) if a.hub == b.hub]
    add("variety", "No two stops of the same kind back to back", not pairs,
        "Kinds alternate." if not pairs else "Repeated: " + "; ".join(pairs))

    limit = cfg["weights"]["max_travel_minutes"]
    legs = [leg_estimate(haversine_km(a.lat, a.lng, b.lat, b.lng), cfg["travel"])[1] for a, b in zip(places, places[1:])]
    add("travel", f"Every leg under {limit:g} min", all(m <= limit for m in legs),
        ("Longest leg " + str(max(legs)) + " min.") if legs else "One stop, no legs.")

    over = []
    for m in members:
        if m["limit_min"] is None or not m["home"]:
            continue
        far = max(haversine_km(m["home"][0], m["home"][1], p.lat, p.lng) for p in places)
        mins = int(ceil(fastest_minutes(far, cfg["travel"])))
        if mins > m["limit_min"] + 0.5:
            over.append(f"{m['name']} ({mins} min, limit {m['limit_min']:g})")
    add("distance", "Every stop within every member's travel limit", not over,
        "Nobody travels further than they said they would." if not over else "Too far for: " + ", ".join(over))

    missed = []
    for m in members:
        if not m["chips"]:
            continue    # no picks: nothing to match

        def hit(p):
            return any(c in m["chips"] for c in p.chips) or bool(p.tiles & m["tiles"])
        if any(hit(p) for p in places):
            continue
        if any(hit(p) for p in pool):   # "where possible": a matching place survived the filter
            missed.append(m["name"])
    if result["kind"] == "moment" or len(places) == 1:
        # one stop cannot serve everyone: only fail if it serves nobody although it could
        with_picks = [m for m in members if m["chips"]]
        ok = not with_picks or len(missed) < len(with_picks)
        add("fairness", "At least one match per member where possible", ok,
            "One stop: it matches at least one member's picks." if ok else "The stop matches nobody's picks.")
    else:
        add("fairness", "At least one match per member where possible", not missed,
            "Every member has a stop from their own picks." if not missed else "No match for: " + ", ".join(missed))

    return {"passed": sum(1 for i in items if i["pass"]), "total": len(items), "items": items}
