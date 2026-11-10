"""The plan engine: Filter -> Taste -> Walk -> Assemble.

Pure functions over a loaded Dataset. No web imports, no I/O, no clock: the
same pod, request, config and seed always return the same plan.

Inputs are plain dicts so the same code can sit behind any service:

pod      {"members": [{"name", "chips": [...], "budget_tier": "low|mid|high",
                       "over18": bool, "home": {"zone": ..} | {"lat":.., "lng":..},
                       "needs": "stored, unused"}]}
request  {"kind": "moment" | "dayout", "date": "YYYY-MM-DD", "start": "HH:MM",
          "area": zone | None, "budget": tier key | None, "hub": hub | None}
config   see engine.config.DEFAULT_CONFIG (weights, budget_tiers, travel, seed)
"""

import random
from datetime import date as _date
from math import ceil
from urllib.parse import quote

from .checks import run_checks
from .config import merged_config
from .dataset import DAYS, is_open
from .geo import haversine_km, leg_estimate, mode_minutes
from .taxonomy import ADULT_HUB, CHIP_TILE

NO_PLAN = "No plan fits this request. Try another time, area or kind."


def _hhmm(minute):
    minute = int(minute)
    return f"{(minute // 60) % 24:02d}:{minute % 60:02d}"


def _parse_start(text):
    h, m = (text or "11:00").split(":")[:2]
    return int(h) * 60 + int(m)


def _home(member, ds):
    home = member.get("home") or {}
    if home.get("lat") not in (None, "") and home.get("lng") not in (None, ""):
        return float(home["lat"]), float(home["lng"])
    zone = home.get("zone")
    if zone in ds.zone_centroids:
        return ds.zone_centroids[zone]
    return None


def _place_brief(p):
    return {
        "id": p.id, "name": p.name, "hub": p.hub, "zone": p.zone, "chips": list(p.chips),
        "lat": p.lat, "lng": p.lng, "price_est": p.price, "price_min": p.price_min,
        "price_max": p.price_max, "visit_minutes": p.visit,
    }


def _place_full(p, weekday):
    d = _place_brief(p)
    d.update({
        "address": p.address, "indoor_outdoor": p.indoor_outdoor, "website": p.website,
        "phone": p.phone, "hours_today": p.hours_raw.get(DAYS[weekday % 7], []),
        "basis": p.basis,
    })
    return d


def _prep_members(pod, ds):
    members = []
    for i, m in enumerate(pod.get("members") or []):
        chips = [c for c in (m.get("chips") or []) if isinstance(c, str)]
        members.append({
            "name": (m.get("name") or f"Member {i + 1}").strip(),
            "chips": frozenset(chips),
            "tiles": frozenset(CHIP_TILE[c] for c in chips if c in CHIP_TILE),
            "hubs": frozenset(ds.chip_hub[c] for c in chips if c in ds.chip_hub),
            "tier": m.get("budget_tier") or None,
            "over18": bool(m.get("over18")),
            "home": _home(m, ds),
        })
    return members


def _budget(members, request, tiers):
    """Lowest budget among the people going, and the request's Budget row if lower."""
    by_key = {t["key"]: t for t in tiers}
    order = {t["key"]: i for i, t in enumerate(tiers)}
    keys = [m["tier"] for m in members if m["tier"] in by_key]   # unanswered counts as none
    if request.get("budget") in by_key:
        keys.append(request["budget"])
    if not keys:
        return None, None
    tier = by_key[min(keys, key=lambda k: order[k])]
    return tier, (float(tier["max"]) if tier.get("max") is not None else None)


def _match(p, members, w):
    """Taste match of one place against the pod. Independent of the slot, so cached per plan."""
    matched, counted, total_match = [], 0, 0.0
    if p.chips:
        for i, m in enumerate(members):
            exact = [c for c in p.chips if c in m["chips"]]
            if exact:
                s, level, chips = w["chip_exact"], "exact", exact
            elif p.tiles & m["tiles"]:
                s, level = w["chip_same_tile"], "tile"
                chips = [c for c in p.chips if CHIP_TILE.get(c) in m["tiles"]]
            else:
                s, level, chips = 0.0, None, []
            # a member with no pick for this kind of stop does not count against it
            if level or p.hub in m["hubs"]:
                counted += 1
            if level:
                total_match += s
                matched.append({"i": i, "name": m["name"], "level": level, "chips": chips, "score": s})
        share = len(matched) / counted if counted else 0.0
        # majority first (share of counted members who match), then the sum of match scores
        return matched, share, {"majority": w["majority_share"] * share,
                                "match_sum": total_match / counted if counted else 0.0, "no_chip": 0.0}
    # no chip: matched by hub only, flat lower base score
    for i, m in enumerate(members):
        if p.hub in m["hubs"]:
            matched.append({"i": i, "name": m["name"], "level": "hub", "chips": [], "score": 0.0})
    return matched, 0.0, {"majority": 0.0, "match_sum": 0.0, "no_chip": w["no_chip_base"]}


def _score(p, ctx, prev, unserved, is_new_slot):
    """Score one candidate. Returns (total, parts, matched members)."""
    w = ctx["w"]
    hit = ctx["match_cache"].get(p.id)
    if hit is None:
        hit = ctx["match_cache"][p.id] = _match(p, ctx["members"], w)
    matched, share, base_parts = hit
    parts = dict(base_parts)

    newly = [x for x in matched if x["level"] != "hub" and x["i"] in unserved]
    parts["fairness"] = w["fairness_bonus"] * len(newly) / len(unserved) if unserved else 0.0

    parts["variety"] = -w["variety_penalty"] if prev and prev["place"].hub == p.hub else 0.0

    origin = (prev["place"].lat, prev["place"].lng) if prev else ctx["centre"]
    km = haversine_km(origin[0], origin[1], p.lat, p.lng) if origin else 0.0
    parts["distance"] = -w["distance_penalty_per_km"] * km

    target = ctx["price_target"]
    closeness = max(0.0, 1.0 - abs(p.price - target) / max(target, 1.0)) if target else 0.0
    parts["price"] = w["price_closeness"] * closeness

    novel = p.hub not in ctx["wanted_hubs"] or (bool(p.chips) and not any(c in ctx["picked"] for c in p.chips))
    parts["new_slot"] = w["new_slot_bonus"] if (is_new_slot and novel) else 0.0

    parts["jitter"] = w["seed_jitter"] * ctx["jitter"][p.id]
    total = sum(parts.values())
    return total, parts, matched, km, share, novel


def _why(p, matched, n_members, novel_slot, leg):
    taste = [x for x in matched if x["level"] in ("exact", "tile")]
    if novel_slot:
        what = p.chips[0] if p.chips else p.hub
        line = f"Something new for the pod: {what}"
    elif taste:
        chips = []
        for x in taste:
            for c in x["chips"]:
                if c not in chips:
                    chips.append(c)
        names = ", ".join(x["name"] for x in taste[:4]) + ("…" if len(taste) > 4 else "")
        line = f"{len(taste)} of {n_members} like {' / '.join(chips[:2]) or p.hub} ({names})"
    elif matched:
        line = f"Fits the kind of stop the pod wants ({p.hub})"
    else:
        line = f"A change of pace: {p.hub}"
    if leg:
        line += f" · {leg['minutes']} min {'walk' if leg['mode'] == 'walk' else 'by public transport'} from the last stop"
    return line


def _fail(message, base, debug):
    out = dict(base)
    out.update({"status": "no_plan", "message": message, "stops": [], "total_cost": 0,
                "leave_home": [], "map_url": None, "end": None, "debug": debug,
                "checks": {"passed": 0, "total": 0, "items": []}})
    return out


def plan(ds, pod, request, config=None):
    cfg = merged_config(config)
    w = cfg["weights"]
    travel = cfg["travel"]
    rng = random.Random(cfg["seed"])

    members = _prep_members(pod, ds)
    kind = "moment" if request.get("kind") == "moment" else "dayout"
    day = _date.fromisoformat(request["date"])
    weekday = day.weekday()
    start = _parse_start(request.get("start"))
    area = request.get("area") or None
    fixed_hub = request.get("hub") or None
    n_stops = 1 if kind == "moment" else w["n_stops"]

    tier, cap = _budget(members, request, cfg["budget_tiers"])
    all18 = bool(members) and all(m["over18"] for m in members)
    picked = frozenset(c for m in members for c in m["chips"])
    wanted_hubs = {h for m in members for h in m["hubs"]}
    if not all18:
        wanted_hubs.discard(ADULT_HUB)
    homes = [m["home"] for m in members if m["home"]]
    centre = (sum(h[0] for h in homes) / len(homes), sum(h[1] for h in homes) / len(homes)) if homes else None

    if tier is None:
        price_target = 0.0
    elif tier.get("max") is not None:
        price_target = (float(tier.get("min") or 0) + float(tier["max"])) / 2 / n_stops
    else:
        price_target = float(tier.get("min") or 0) * 1.5 / n_stops

    base = {
        "kind": kind, "date": request["date"], "start": _hhmm(start), "weekday": DAYS[weekday],
        "seed": cfg["seed"], "area": area, "fixed_hub": fixed_hub,
        "budget_cap": cap, "budget_label": tier["label"] if tier else "No budget set",
        "hours_note": "Hours and prices are typical estimates, not confirmed.",
    }

    # ---- Filter: hard limits, never relaxed -------------------------------------------
    funnel = [{"label": "Active places", "count": len(ds.places)}]
    pool = ds.places
    if area:
        pool = [p for p in pool if p.zone == area]
    funnel.append({"label": f"In area ({area})" if area else "In area (any)", "count": len(pool)})
    pool = [p for p in pool if all18 or p.hub != ADULT_HUB]
    funnel.append({"label": "18+ rule (bars only if everyone is over 18)", "count": len(pool)})
    if cap is not None:
        pool = [p for p in pool if p.price <= cap]
    funnel.append({"label": "Affordable on the lowest budget", "count": len(pool)})
    if kind == "moment":
        pool = [p for p in pool if is_open(p, weekday, start, p.visit)]
        funnel.append({"label": f"Open at {_hhmm(start)} for the visit length", "count": len(pool)})
    else:
        steps = range(start, start + int(cfg["window_hours"]) * 60 + 1, 30)
        pool = [p for p in pool if any(is_open(p, weekday, t, p.visit) for t in steps)]
        funnel.append({"label": f"Open some time in the {cfg['window_hours']} h window", "count": len(pool)})

    hub_counts = {h: 0 for h in ds.hubs}
    for p in pool:
        hub_counts[p.hub] = hub_counts.get(p.hub, 0) + 1
    empty = sorted(h for h, n in hub_counts.items() if n < cfg["min_hub_places"])
    live_hubs = {h for h in hub_counts if h not in empty}

    debug = {
        "funnel": funnel, "hub_counts": hub_counts, "empty_hubs": empty,
        "wanted_hubs": sorted(wanted_hubs), "weights": dict(w), "budget_tiers": cfg["budget_tiers"],
        "per_stop": [], "coverage": [], "notes": [],
        "price_target_per_stop": round(price_target, 2), "all_over_18": all18,
    }

    if fixed_hub and fixed_hub not in live_hubs:
        return _fail(f"No plan fits: the Kind row ({fixed_hub}) has too few places that fit this request.",
                     base, debug)
    if not live_hubs:
        return _fail(NO_PLAN, base, debug)

    ctx = {
        "w": w, "members": members, "centre": centre, "price_target": price_target,
        "wanted_hubs": wanted_hubs, "picked": picked,
        "jitter": {p.id: rng.random() for p in pool}, "match_cache": {},
    }
    reserve = min(8.0, cap / n_stops / 2) if cap is not None else 0.0
    new_slot_index = n_stops - 1 if kind == "dayout" else -1

    # ---- Walk: choose stops one at a time ----------------------------------------------
    stops, used_ids, used_names, used_hubs = [], set(), set(), set()
    unserved = {i for i, m in enumerate(members) if m["chips"]}
    spent = 0.0
    clock = start
    for i in range(n_stops):
        prev = stops[-1] if stops else None
        is_new = i == new_slot_index
        if i == 0 and fixed_hub:
            hub_sets, slot = [{fixed_hub}], f"Kind row: {fixed_hub}"
        elif kind == "moment":
            hub_sets, slot = [wanted_hubs & live_hubs, live_hubs], "Hubs the pod wants"
        elif is_new:
            hub_sets, slot = [live_hubs], "Something-new slot: every hub allowed"
        else:
            still = (wanted_hubs - used_hubs) & live_hubs
            hub_sets = [still, (wanted_hubs & live_hubs) - ({prev["place"].hub} if prev else set()), live_hubs]
            slot = "Hubs the pod still wants"
        hub_sets = [h for h in hub_sets if h]

        remaining = None if cap is None else cap - spent - reserve * (n_stops - i - 1)
        chosen_set, cands, sfunnel, loosened = None, [], [], False
        for level, hubs in enumerate(hub_sets):
            c1 = [p for p in pool if p.hub in hubs]
            c2 = [p for p in c1 if p.id not in used_ids and p.name.lower() not in used_names]
            c3, c4 = [], []
            for p in c2:
                if prev:
                    km = haversine_km(prev["place"].lat, prev["place"].lng, p.lat, p.lng)
                    mode, mins = leg_estimate(km, travel)
                    if mins > w["max_travel_minutes"]:
                        continue
                    arrive = int(ceil((clock + mins) / 5.0) * 5)
                    leg = {"km": round(km, 2), "minutes": mins, "mode": mode}
                else:
                    arrive, leg = clock, None
                c3.append(p)
                if is_open(p, weekday, arrive, p.visit):
                    c4.append((p, arrive, leg))
            c5 = [c for c in c4 if remaining is None or c[0].price <= remaining]
            sfunnel = [
                {"label": "Hub allowed in this slot", "count": len(c1)},
                {"label": "Not already in the plan", "count": len(c2)},
                {"label": "Within max travel from the last stop", "count": len(c3)},
                {"label": "Open at arrival for the visit length", "count": len(c4)},
                {"label": "Fits the budget left", "count": len(c5)},
            ]
            if c5:
                chosen_set, cands, loosened = hubs, c5, level > 0
                break

        stop_debug = {"index": i, "slot": slot, "is_new_slot": is_new, "loosened_hub_mix": loosened,
                      "allowed_hubs": sorted(chosen_set or (hub_sets[-1] if hub_sets else [])),
                      "funnel": sfunnel, "top": []}
        debug["per_stop"].append(stop_debug)
        if not cands:
            if i == 0 and fixed_hub:
                return _fail(f"No plan fits: the Kind row ({fixed_hub}) has no place that fits this request.",
                             base, debug)
            break

        scored = []
        for p, arrive, leg in cands:
            total, parts, matched, km, share, novel = _score(p, ctx, prev, unserved, is_new)
            scored.append((total, p, arrive, leg, parts, matched, km, share, novel))
        scored.sort(key=lambda s: (-s[0], s[1].id))
        total, p, arrive, leg, parts, matched, km, share, novel = scored[0]

        def row(s, rank):
            return {"rank": rank, "place": _place_brief(s[1]), "score": round(s[0], 4), "parts": {k: round(v, 4) for k, v in s[4].items()},
                    "matched": [{"name": x["name"], "level": x["level"], "chips": x["chips"]} for x in s[5]],
                    "share": round(s[7], 3), "km": round(s[6], 2), "arrival": _hhmm(s[2]), "chosen": rank == 1}

        stop_debug["top"] = [row(s, r + 1) for r, s in enumerate(scored[:int(cfg["top_n"])])]

        alts, seen = [], {p.name.lower()}
        for prefer_same_hub in (True, False):
            for s in scored[1:]:
                if len(alts) >= int(cfg["alternatives"]):
                    break
                q = s[1]
                if q.name.lower() in seen or (prefer_same_hub and q.hub != p.hub):
                    continue
                seen.add(q.name.lower())
                a = row(s, 0)
                a.pop("rank"); a.pop("chosen")
                a["place"] = _place_full(q, weekday)
                a["why"] = _why(q, s[5], len(members), is_new and s[8], s[3])
                alts.append(a)
        alts.sort(key=lambda a: -a["score"])

        stops.append({
            "place": p, "arrive": arrive, "leg": leg, "score": total, "parts": parts,
            "matched": matched, "alts": alts, "is_new": is_new, "novel": novel, "km": km,
        })
        used_ids.add(p.id); used_names.add(p.name.lower()); used_hubs.add(p.hub)
        unserved -= {x["i"] for x in matched if x["level"] != "hub"}
        spent += p.price
        clock = arrive + p.visit

    if len(stops) < (1 if kind == "moment" else 3):
        debug["notes"].append(f"The walk stopped after {len(stops)} stop(s).")
        return _fail(NO_PLAN, base, debug)

    # ---- Assemble ----------------------------------------------------------------------
    out_stops = []
    for i, s in enumerate(stops):
        p = s["place"]
        out_stops.append({
            "index": i, "place": _place_full(p, weekday),
            "arrival": _hhmm(s["arrive"]), "depart": _hhmm(s["arrive"] + p.visit),
            "arrival_min": s["arrive"], "duration": p.visit, "price_est": p.price,
            "leg": s["leg"], "score": round(s["score"], 4), "parts": {k: round(v, 4) for k, v in s["parts"].items()},
            "matched": [{"name": x["name"], "level": x["level"], "chips": x["chips"]} for x in s["matched"]],
            "matched_chips": sorted({c for x in s["matched"] for c in x["chips"]}),
            "is_new_slot": s["is_new"],
            "why": _why(p, s["matched"], len(members), s["is_new"] and s["novel"], s["leg"]),
            "alternatives": s["alts"],
        })

    first = stops[0]["place"]
    leave = []
    for m in members:
        if not m["home"]:
            leave.append({"name": m["name"], "km": None, "modes": None})   # no saved home: show nothing
            continue
        km = haversine_km(m["home"][0], m["home"][1], first.lat, first.lng)
        modes = {}
        for key in ("walk", "transit", "car", "cab"):
            mins = int(ceil(mode_minutes(km, travel[key])))
            modes[key] = {"label": travel[key]["label"], "minutes": mins, "leave": _hhmm(start - mins)}
        leave.append({"name": m["name"], "km": round(km, 1), "modes": modes})

    pts = [f"{s['place'].lat:.6f},{s['place'].lng:.6f}" for s in stops]
    if len(pts) == 1:
        map_url = "https://www.google.com/maps/search/?api=1&query=" + quote(pts[0])
    else:
        map_url = ("https://www.google.com/maps/dir/?api=1&travelmode=transit&origin=" + quote(pts[0])
                   + "&destination=" + quote(pts[-1])
                   + ("&waypoints=" + quote("|".join(pts[1:-1])) if len(pts) > 2 else ""))

    for i, m in enumerate(members):
        debug["coverage"].append({
            "name": m["name"],
            "stops": [next((x["level"] for x in s["matched"] if x["i"] == i), None) for s in stops],
        })

    result = dict(base)
    result.update({
        "status": "ok",
        "message": "Day out planned." if kind == "dayout" else "Moment planned.",
        "stops": out_stops, "total_cost": round(spent, 2),
        "end": _hhmm(stops[-1]["arrive"] + stops[-1]["place"].visit),
        "leave_home": leave, "map_url": map_url, "debug": debug,
    })
    result["checks"] = run_checks(ds, result, members, pool, cfg)
    return result
