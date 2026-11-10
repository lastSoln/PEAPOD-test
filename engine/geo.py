"""Distance and travel-time estimates. Straight line * detour factor / speed."""

from math import asin, ceil, cos, radians, sin, sqrt


_KM_PER_DEG = 111.195
_COS_SG = cos(radians(1.35))    # Singapore sits on the equator: a flat-earth distance is within 0.1%


def haversine_km(lat1, lng1, lat2, lng2):
    """Straight-line km. Uses the fast local approximation inside Singapore, haversine elsewhere."""
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    if abs(dlat) < 1 and abs(dlng) < 1 and abs(lat1) < 3:
        return _KM_PER_DEG * sqrt(dlat * dlat + (dlng * _COS_SG) ** 2)
    a = sin(radians(dlat) / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(radians(dlng) / 2) ** 2
    return 6371.0088 * 2 * asin(sqrt(a))


def mode_minutes(km, mode_cfg):
    return km * mode_cfg["detour"] / mode_cfg["speed_kmh"] * 60 + mode_cfg["overhead_min"]


def leg_estimate(km, travel):
    """Travel between two stops: walk when the walk is short, else public transport."""
    walk = mode_minutes(km, travel["walk"])
    if walk <= travel["walk_leg_max_min"]:
        return "walk", int(ceil(walk))
    return "transit", int(ceil(mode_minutes(km, travel["transit"])))
