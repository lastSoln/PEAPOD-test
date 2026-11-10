"""Tunable numbers. Every value here is a starting guess for the bench to adjust."""

from copy import deepcopy

# key, label, default, min, max, step, help
WEIGHT_SPECS = [
    ("chip_exact", "Chip exact match", 1.0, 0.0, 2.0, 0.05, "A place has a chip the member picked."),
    ("chip_same_tile", "Chip same-tile match", 0.6, 0.0, 2.0, 0.05, "A place has another chip from the same interest tile."),
    ("majority_share", "Majority-share weight", 2.0, 0.0, 6.0, 0.1, "Multiplies the share of counted members who match."),
    ("fairness_bonus", "Fairness bonus", 1.0, 0.0, 5.0, 0.1, "Scaled by the share of still-unmatched members this stop would serve."),
    ("variety_penalty", "Variety penalty (same hub twice)", 1.5, 0.0, 6.0, 0.1, "Subtracted when the hub repeats the previous stop's hub."),
    ("distance_penalty_per_km", "Distance penalty per km", 0.15, 0.0, 1.0, 0.01, "Subtracted per km from the previous stop (first stop: from the middle of the homes)."),
    ("price_closeness", "Price-closeness weight", 0.5, 0.0, 3.0, 0.05, "Rewards a price near the per-stop target for the group's budget tier."),
    ("no_chip_base", "No-chip base score", 0.3, 0.0, 2.0, 0.05, "Flat taste score for places with no chip (matched by hub only)."),
    ("new_slot_bonus", "New-slot bonus", 3.0, 0.0, 8.0, 0.1, "Added in the one 'something new' slot to a hub or chip nobody picked."),
    ("n_stops", "Number of stops (Day out)", 4, 3, 5, 1, "A Moment is always one stop."),
    ("max_travel_minutes", "Max travel between stops (min)", 30, 5, 90, 1, "Hard limit on each leg while walking the plan."),
    ("seed_jitter", "Seed jitter", 0.05, 0.0, 1.0, 0.01, "Size of the seeded random tie-break added to every score."),
]

DEFAULT_WEIGHTS = {k: d for k, _l, d, *_ in WEIGHT_SPECS}

# Whole-day SGD per person. The real values are undecided, so these are configurable.
DEFAULT_BUDGET_TIERS = [
    {"key": "low", "label": "Under $40", "min": 0, "max": 40},
    {"key": "mid", "label": "$40 to $100", "min": 40, "max": 100},
    {"key": "high", "label": "$100 and over", "min": 100, "max": None},
]

DEFAULT_TRAVEL = {
    # straight-line km * detour / speed (km/h) + fixed overhead minutes
    "walk": {"label": "Walking", "speed_kmh": 4.8, "detour": 1.3, "overhead_min": 0},
    "transit": {"label": "Public transport", "speed_kmh": 18.0, "detour": 1.4, "overhead_min": 10},
    "car": {"label": "Car", "speed_kmh": 30.0, "detour": 1.35, "overhead_min": 5},
    "cab": {"label": "Cab", "speed_kmh": 30.0, "detour": 1.35, "overhead_min": 8},
    # between stops: walk if the walk is this short, else public transport
    "walk_leg_max_min": 15,
}

DEFAULT_CONFIG = {
    "weights": DEFAULT_WEIGHTS,
    "budget_tiers": DEFAULT_BUDGET_TIERS,
    "travel": DEFAULT_TRAVEL,
    "seed": 1,
    "min_hub_places": 3,      # fewer eligible places than this makes a hub "empty"
    "alternatives": 4,        # 2 to 4 shown per stop
    "top_n": 10,              # candidates listed in the debug view
    "window_hours": 9,        # Day out window used for the "open that day" filter
}


def merged_config(overrides=None):
    cfg = deepcopy(DEFAULT_CONFIG)
    for k, v in (overrides or {}).items():
        if v is None:
            continue
        if k in ("weights", "travel") and isinstance(v, dict):
            cfg[k].update({kk: vv for kk, vv in v.items() if vv is not None})
        else:
            cfg[k] = v
    w = cfg["weights"]
    for k, _l, d, lo, hi, *_ in WEIGHT_SPECS:
        try:
            w[k] = min(hi, max(lo, float(w.get(k, d))))
        except (TypeError, ValueError):
            w[k] = d
    w["n_stops"] = int(round(w["n_stops"]))
    cfg["seed"] = int(cfg.get("seed") or 0)
    return cfg
