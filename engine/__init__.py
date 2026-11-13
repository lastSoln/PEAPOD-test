"""Peapod plan engine. Pure Python, no web imports.

    from engine import load_dataset, plan
    ds = load_dataset("data/places.sqlite")
    result = plan(ds, pod, request, {"weights": {...}, "seed": 7})
"""

from .config import DEFAULT_BUDGET_TIERS, DEFAULT_CONFIG, DEFAULT_WEIGHTS, WEIGHT_SPECS, merged_config
from .dataset import Dataset, Place, is_open, load_dataset, load_dataset_postgres
from . import flow
from .planner import plan
from .rules import RULES
from .taxonomy import (ADULT_HUB, CHIP_TILE, HUBS, NOT_FOR_ME_REASONS, PRACTICAL_REASONS, STYLES, TILES,
                       TRAVEL_PREFS, ZONES)

__all__ = [
    "ADULT_HUB", "CHIP_TILE", "DEFAULT_BUDGET_TIERS", "DEFAULT_CONFIG", "DEFAULT_WEIGHTS", "Dataset",
    "HUBS", "NOT_FOR_ME_REASONS", "PRACTICAL_REASONS", "Place", "RULES", "STYLES", "TILES", "TRAVEL_PREFS",
    "WEIGHT_SPECS", "ZONES", "flow", "is_open", "load_dataset", "load_dataset_postgres",
    "merged_config", "plan",
]
