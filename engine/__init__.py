"""Peapod plan engine. Pure Python, no web imports.

    from engine import load_dataset, plan
    ds = load_dataset("data/places.sqlite")
    result = plan(ds, pod, request, {"weights": {...}, "seed": 7})
"""

from .config import DEFAULT_BUDGET_TIERS, DEFAULT_CONFIG, DEFAULT_WEIGHTS, WEIGHT_SPECS, merged_config
from .dataset import Dataset, Place, is_open, load_dataset, load_dataset_postgres
from .planner import plan
from .taxonomy import ADULT_HUB, CHIP_TILE, HUBS, TILES, ZONES

__all__ = [
    "ADULT_HUB", "CHIP_TILE", "DEFAULT_BUDGET_TIERS", "DEFAULT_CONFIG", "DEFAULT_WEIGHTS", "Dataset",
    "HUBS", "Place", "TILES", "WEIGHT_SPECS", "ZONES", "is_open", "load_dataset", "load_dataset_postgres",
    "merged_config", "plan",
]
