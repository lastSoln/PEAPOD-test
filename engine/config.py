"""Tunable numbers. Every value here is a starting guess for the bench to adjust."""

from copy import deepcopy

# key, label, default, min, max, step, help, group
WEIGHT_SPECS = [
    ("chip_exact", "Favourite match", 1.0, 0.0, 2.0, 0.05, "The place has a chip the member favourited (or any chip of a tile they picked with no favourites).", "Taste"),
    ("chip_same_tile", "Same-interest match", 0.6, 0.0, 2.0, 0.05, "The place has another chip from an interest tile the member picked.", "Taste"),
    ("majority_share", "Majority-share weight", 2.0, 0.0, 6.0, 0.1, "Multiplies the share of counted members who match.", "Taste"),
    ("fairness_bonus", "Fairness bonus", 1.0, 0.0, 5.0, 0.1, "Scaled by the share of still-unmatched members this stop would serve.", "Taste"),
    ("no_chip_base", "No-chip base score", 0.3, 0.0, 2.0, 0.05, "Flat taste score for places with no chip (matched by kind only).", "Taste"),
    ("new_slot_bonus", "New-slot bonus", 3.0, 0.0, 8.0, 0.1, "Added in the one 'something new' slot to a kind or chip nobody picked.", "Taste"),
    ("price_closeness", "Price-closeness weight", 0.5, 0.0, 3.0, 0.05, "Rewards a price near the per-stop target for the pod's lowest budget.", "Taste"),

    ("style_flow", "Go with the flow", 0.5, 0.0, 3.0, 0.05, "Bonus for stops close to the last one, scaled by the share of easygoing members.", "Plan style (soft)"),
    ("style_planner", "The Planner", 0.5, 0.0, 3.0, 0.05, "Bonus for places whose hours are confirmed, not estimated, scaled by the share of planners.", "Plan style (soft)"),
    ("style_explorer", "The Explorer", 0.5, 0.0, 3.0, 0.05, "Bonus for one-off places and chips nobody picked, scaled by the share of explorers.", "Plan style (soft)"),
    ("style_foodie", "The Foodie", 0.5, 0.0, 3.0, 0.05, "Bonus for food and cafe stops, scaled by the share of foodies.", "Plan style (soft)"),

    ("n_stops", "Number of stops (Day out)", 4, 3, 5, 1, "A Moment is always one stop. An easygoing majority takes one off, a planner majority adds one.", "The walk"),
    ("variety_penalty", "Variety penalty (same kind twice)", 1.5, 0.0, 6.0, 0.1, "Subtracted when the kind repeats the previous stop's kind.", "The walk"),
    ("distance_penalty_per_km", "Distance penalty per km", 0.15, 0.0, 1.0, 0.01, "Subtracted per km from the previous stop (first stop: from the middle of the homes).", "The walk"),
    ("max_travel_minutes", "Max travel between stops (min)", 30, 5, 90, 1, "Hard limit on each leg while walking the plan.", "The walk"),
    ("seed_jitter", "Seed jitter", 0.05, 0.0, 1.0, 0.01, "Size of the seeded random tie-break added to every score.", "The walk"),

    ("travel_close_min", "'Close by' limit (min)", 15, 5, 60, 1, "Hard limit from home, by the fastest way, for a member who answered Close by.", "Distance (hard)"),
    ("travel_town_min", "'Across town' limit (min)", 45, 10, 120, 1, "Hard limit from home for Across town. Out of town has no limit.", "Distance (hard)"),

    ("rework_far_factor", "Rework: too far", 0.75, 0.3, 1.0, 0.05, "On 'Too far' the member's limit for this plan becomes their longest trip so far times this.", "Rework and learning"),
    ("rework_price_factor", "Rework: too pricey", 0.75, 0.3, 1.0, 0.05, "On 'Too pricey' the plan's budget becomes its current cost times this.", "Rework and learning"),
    ("rework_time_shift_min", "Rework: wrong time (min)", 120, 30, 360, 15, "On 'Wrong time' the start moves later by this much, or earlier if that would end too late.", "Rework and learning"),
    ("taste_down", "Not my thing: taste multiplier", 0.5, 0.0, 1.0, 0.05, "Multiplies the member's match on the chips of a plan they called 'Not my thing anymore'.", "Rework and learning"),
    ("taste_heart", "Heart: taste multiplier", 1.2, 1.0, 2.0, 0.05, "Multiplies the member's match on the chips of a stop they hearted.", "Rework and learning"),
]

DEFAULT_WEIGHTS = {spec[0]: spec[2] for spec in WEIGHT_SPECS}

# Whole-day SGD per person. The real values are undecided, so these are configurable.
# (The onboarding design shows "under $20 / $20 to $60 / $60 and up" a head.)
DEFAULT_BUDGET_TIERS = [
    {"key": "low", "label": "Keep it low", "min": 0, "max": 40},
    {"key": "mid", "label": "Flexible", "min": 40, "max": 100},
    {"key": "high", "label": "Splurge", "min": 100, "max": None},
]

DEFAULT_TRAVEL = {
    # leave-home estimates: straight-line km * detour / speed (km/h) + fixed overhead minutes
    "walk": {"label": "Walking", "speed_kmh": 4.8, "detour": 1.3, "overhead_min": 0},
    "transit": {"label": "Public transport", "speed_kmh": 18.0, "detour": 1.4, "overhead_min": 10},
    "car": {"label": "Car", "speed_kmh": 30.0, "detour": 1.35, "overhead_min": 5},
    "cab": {"label": "Cab", "speed_kmh": 30.0, "detour": 1.35, "overhead_min": 8},
    # between stops (plan rule book v64): up to 1.2 km is a walk at about 13 min per km
    "walk_leg_max_km": 1.2,
    "walk_min_per_km": 13,
}

DEFAULT_CONFIG = {
    "weights": DEFAULT_WEIGHTS,
    "budget_tiers": DEFAULT_BUDGET_TIERS,
    "travel": DEFAULT_TRAVEL,
    "seed": 1,
    "min_hub_places": 3,      # fewer eligible places than this makes a kind "empty"
    "alternatives": 4,        # 2 to 4 shown per stop
    "top_n": 10,              # candidates listed in the debug view
    "window_hours": 9,        # Day out window used for the "open that day" filter
    "flow_visit_factor": 1.25,  # an easygoing majority stays this much longer at each stop
    "max_rounds": 3,
    "min_going": 2,
    "max_missed": 3,
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
    for key, _label, default, lo, hi, *_ in WEIGHT_SPECS:
        try:
            w[key] = min(hi, max(lo, float(w.get(key, default))))
        except (TypeError, ValueError):
            w[key] = default
    w["n_stops"] = int(round(w["n_stops"]))
    cfg["seed"] = int(cfg.get("seed") or 0)
    return cfg
