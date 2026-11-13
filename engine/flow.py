"""The life of a plan: Swiping (up to 3 rounds) -> Planning -> Approved, or Ended.

Pure functions over a JSON-friendly session dict. Each function returns the
events it produced; the caller appends them to the log (the log is append only).

Session shape:
  phase     "swiping" | "planning" | "approved" | "ended"
  round     1..3 while swiping
  pitcher   the member who started it (they are in and never swipe), or None for a Peapod pick
  pod       the frozen snapshot, including each member's learned taste
  request   the request as it stands (a rework can move the day or the start time)
  adjust    limits tightened for this plan only: {"cap": .., "limits": {name: minutes}}
  members   {name: {"status": "in" | "asked" | "out", "missed": n, "approved": bool,
                    "out_how": "cant" | "missed" | "left" | None}}
  plan      the current plan (engine.planner.plan result)
  rounds    [{round, changes, votes}] what each round changed and how people answered
  hearts    {name: [place ids]}
  edits     changes made by members in Planning, newest last
"""

from copy import deepcopy
from datetime import date as _date, timedelta

from .config import merged_config
from .geo import fastest_minutes, haversine_km
from .planner import _home, _parse_start, _hhmm, plan
from .taxonomy import ACTIVE_HUBS, CHILL_HUBS, NOT_FOR_ME, PRACTICAL


class FlowError(ValueError):
    """The action is not allowed in the plan's current state."""


def _ev(session, _type, actor=None, **data):
    return {"type": _type, "phase": session.get("phase"), "round": session.get("round"), "actor": actor, "data": data}


def going_pod(session):
    """The people still going. Anyone out no longer shapes the plan."""
    out = {n for n, s in session["members"].items() if s["status"] == "out"}
    pod = dict(session["pod"])
    pod["members"] = [m for m in session["pod"]["members"] if m["name"] not in out]
    return pod


def _counts(session):
    st = [s["status"] for s in session["members"].values()]
    return st.count("in"), st.count("asked"), st.count("out")


def _stops_brief(result):
    return [{"index": s["index"], "id": s["place"]["id"], "name": s["place"]["name"], "hub": s["place"]["hub"],
             "arrival": s["arrival"], "price_est": s["price_est"], "score": s["score"]} for s in result["stops"]]


def _built_event(session, result, why):
    d = result["debug"]
    return _ev(session, "plan_built", None, why=why, status=result["status"], message=result["message"],
               date=result["date"], start=result["start"], stops=_stops_brief(result),
               total_cost=result["total_cost"], budget_cap=result["budget_cap"],
               checks_passed=result["checks"]["passed"], checks_total=result["checks"]["total"],
               checks_failed=[c["key"] for c in result["checks"]["items"] if not c["pass"]],
               filter_funnel=d["funnel"], empty_hubs=d["empty_hubs"],
               per_stop=[{"index": p["index"], "slot": p["slot"], "funnel": p["funnel"], "kept": p.get("kept"),
                          "replaced": p.get("replaced"),
                          "top": [{"id": t["place"]["id"], "name": t["place"]["name"], "score": t["score"],
                                   "parts": t["parts"]} for t in p["top"][:5]]} for p in d["per_stop"]])


# ---------------------------------------------------------------- start

def start(ds, pod, request, config=None, pitcher=None):
    """Request -> first draft -> Swiping. The pitcher is in; everyone else is asked."""
    cfg = merged_config(config)
    names = [(m.get("name") or f"Member {i + 1}").strip() for i, m in enumerate(pod.get("members") or [])]
    if pitcher not in names:
        pitcher = None
    session = {
        "phase": "swiping", "round": 1, "pitcher": pitcher,
        "pod": deepcopy(pod), "request": dict(request),
        "config": {"weights": cfg["weights"], "budget_tiers": cfg["budget_tiers"], "seed": cfg["seed"]},
        "adjust": {"cap": None, "limits": {}},
        "members": {n: {"status": "in" if n == pitcher else "asked", "missed": 0, "approved": False, "out_how": None}
                    for n in names},
        "rounds": [], "hearts": {}, "edits": [], "message": "",
    }
    events = [_ev(session, "plan_requested", pitcher or "Peapod", request=dict(request), pitcher=pitcher,
                  pod=deepcopy(pod), weights=cfg["weights"], budget_tiers=cfg["budget_tiers"], seed=cfg["seed"])]
    result = plan(ds, pod, request, session["config"])
    session["plan"] = result
    events.append(_built_event(session, result, "first draft"))
    if result["status"] != "ok":
        session["phase"], session["message"] = "ended", result["message"]
        events.append(_ev(session, "phase_changed", None, to="ended", why="no plan fits"))
    else:
        session["rounds"].append({"round": 1, "changes": [], "votes": {}, "stops": _stops_brief(result)})
    return session, events


# ---------------------------------------------------------------- taste learning

def _learn(session, name, reason):
    """'Not for me' reasons move that member's taste a little. Practical reasons never do."""
    member = next((m for m in session["pod"]["members"] if m.get("name") == name), None)
    if member is None or reason not in NOT_FOR_ME:
        return []
    w = session["config"]["weights"]
    taste = member.setdefault("taste", {})
    stops = session["plan"]["stops"]
    ids = [s["place"]["id"] for s in stops]
    if reason == "not_my_thing":
        chips = sorted({c for s in stops for c in s["place"]["chips"]})
        down = taste.setdefault("down", {})
        for c in chips:
            down[c] = round(down.get(c, 1.0) * w["taste_down"], 4)
        return [_ev(session, "taste_nudge", name, reason=reason, effect="stops pitching things like it",
                    chips=chips, multiplier=w["taste_down"])]
    # done_lately: give these places a rest. not_with_group: keep them for other pods.
    rest = taste.setdefault("rest", [])
    rest.extend(i for i in ids if i not in rest)
    effect = "gives these places a rest for a while" if reason == "done_lately" else "keeps these places for other pods"
    return [_ev(session, "taste_nudge", name, reason=reason, effect=effect, places=ids)]


def _settle(session, events):
    """Everyone left has answered. Enough people in makes it a plan; otherwise it ends."""
    n_in, n_asked, _ = _counts(session)
    if n_asked:
        return
    cfg = merged_config(session["config"])
    if n_in >= cfg["min_going"]:
        session["phase"] = "planning"
        session["message"] = "It's a plan. Anyone going can change it; everyone going approves."
        events.append(_ev(session, "phase_changed", None, to="planning", going=n_in))
    else:
        session["phase"] = "ended"
        session["message"] = "Fewer than 2 people are in, so the plan has ended."
        events.append(_ev(session, "phase_changed", None, to="ended", why="fewer than 2 in", going=n_in))


# ---------------------------------------------------------------- a round of votes

def submit_votes(ds, session, votes):
    """Close the round. `votes` is {name: {"answer": "in"|"maybe"|"cant", "reason": key}}.
    A member who was asked and is missing from `votes` did not answer in 24 hours."""
    if session["phase"] != "swiping":
        raise FlowError("The plan is not being swiped.")
    cfg = merged_config(session["config"])
    final = session["round"] >= cfg["max_rounds"]
    events, reasons, record = [], [], {}
    for name, st in session["members"].items():
        if st["status"] != "asked":
            continue
        v = votes.get(name) or {}
        answer, reason = v.get("answer"), v.get("reason") or None
        if answer not in ("in", "maybe", "cant"):
            answer = None
        if answer == "maybe" and final:
            raise FlowError("The final round is I'm in or Can't only.")
        if reason and reason not in PRACTICAL and reason not in NOT_FOR_ME:
            raise FlowError(f"Unknown reason: {reason}")
        if answer == "maybe" and reason in NOT_FOR_ME:
            raise FlowError("A Maybe carries a practical reason; 'not for me' reasons go with Can't.")
        record[name] = {"answer": answer or "no_answer", "reason": reason}
        if answer is None:
            st["missed"] += 1
            gone = final or st["missed"] >= cfg["max_missed"]
            events.append(_ev(session, "no_answer", name, missed_in_a_row=st["missed"], counts_as="cant", out=gone))
            if gone:
                st["status"], st["out_how"] = "out", "missed"
                events.append(_ev(session, "member_out", name, how="missed"))
            continue
        st["missed"] = 0                                   # any swipe resets the count
        events.append(_ev(session, "vote", name, answer=answer, reason=reason))
        if answer == "in":
            st["status"] = "in"
        elif reason in PRACTICAL and not final:
            reasons.append((name, reason))                 # would go with a change: stays in the rounds
        elif answer == "maybe":
            pass                                           # a Maybe with no reason: asked again, nothing changes
        else:
            st["status"], st["out_how"] = "out", "cant"
            events.append(_ev(session, "member_out", name, how="cant", reason=reason))
            events.extend(_learn(session, name, reason))

    session["rounds"][-1]["votes"] = record
    n_in, n_asked, _ = _counts(session)
    if n_asked == 0:
        _settle(session, events)
        return events
    if n_in + n_asked < cfg["min_going"]:
        session["phase"] = "ended"
        session["message"] = "Fewer than 2 people could still be in, so the plan has ended."
        events.append(_ev(session, "phase_changed", None, to="ended", why="fewer than 2 left"))
        return events

    changes = _rework(ds, session, reasons, events) if reasons else []
    session["round"] += 1
    session["rounds"].append({"round": session["round"], "changes": changes, "votes": {},
                              "stops": _stops_brief(session["plan"])})
    events.append(_ev(session, "round_started", None, round=session["round"],
                      asked=[n for n, s in session["members"].items() if s["status"] == "asked"]))
    return events


# ---------------------------------------------------------------- rework between rounds

def _next_day(d):
    """'Busy that day': Saturday moves to Sunday, anything else to the same day next week."""
    return d + timedelta(days=1 if d.weekday() == 5 else 7)


def _rework(ds, session, reasons, events):
    """Change the smallest thing that answers every reason together. Stops stay unless they
    break a limit the reasons tightened. Only Peapod does this, and only between rounds."""
    cfg = merged_config(session["config"])
    w = cfg["weights"]
    old = session["plan"]
    stops = old["stops"]
    request = dict(session["request"])
    adjust = deepcopy(session["adjust"])
    keep = [s["place"]["id"] for s in stops]
    kinds = sorted({r for _, r in reasons})

    if "busy_that_day" in kinds:
        request["date"] = _next_day(_date.fromisoformat(request["date"])).isoformat()
    if "wrong_time" in kinds:
        shift = int(w["rework_time_shift_min"])
        start = _parse_start(request.get("start"))
        length = old["end_min"] - start
        new = start + shift if start + shift + length <= 23 * 60 + 30 else max(7 * 60, start - shift)
        request["start"] = _hhmm(new)
    if "too_pricey" in kinds:
        cap = round(old["total_cost"] * w["rework_price_factor"], 2)
        adjust["cap"] = cap if adjust.get("cap") is None else min(adjust["cap"], cap)
        order = sorted(range(len(stops)), key=lambda i: -stops[i]["price_est"])
        freed = 0
        for i in order:                                    # let go of the priciest until the rest fits
            kept_cost = sum(stops[j]["price_est"] for j in range(len(stops)) if keep[j])
            if freed and kept_cost <= adjust["cap"]:
                break
            keep[i], freed = None, freed + 1
    for name, reason in reasons:
        if reason != "too_far":
            continue
        member = next(m for m in session["pod"]["members"] if m.get("name") == name)
        home = _home(member, ds)
        if not home:
            continue
        mins = [fastest_minutes(haversine_km(home[0], home[1], s["place"]["lat"], s["place"]["lng"]), cfg["travel"])
                for s in stops]
        limit = round(max(mins) * w["rework_far_factor"], 1)
        adjust["limits"][name] = min(adjust["limits"].get(name, limit), limit)
        for i, m in enumerate(mins):
            if m > limit:
                keep[i] = None

    call = dict(adjust, slot_hubs={i: stops[i]["place"]["hub"] for i, k in enumerate(keep) if k is None})
    new = plan(ds, going_pod(session), request, session["config"], keep=keep, adjust=call)
    tally = {k: sum(1 for _, r in reasons if r == k) for k in kinds}
    if new["status"] != "ok":
        events.append(_ev(session, "rework", "Peapod", reasons=[{"member": n, "reason": r} for n, r in reasons],
                          outcome="no way to answer the reasons within the limits; plan unchanged", changes=[]))
        return [{"kind": "No change", "note": "Peapod could not rework it within everyone's limits."}]

    changes = []
    if new["date"] != old["date"]:
        changes.append({"kind": "Day changed", "from": old["date"], "to": new["date"], "why": "A different day"})
    if new["start"] != old["start"]:
        changes.append({"kind": "Time changed", "from": old["start"], "to": new["start"], "why": "A different time"})
    old_ids = [s["place"]["id"] for s in stops]
    new_by_slot = {i: s for i, s in enumerate(new["stops"])}
    for i, s in enumerate(stops):
        t = new_by_slot.get(i)
        if t is None or t["place"]["id"] in old_ids:
            if t is None and len(new["stops"]) < len(stops) and s["place"]["id"] not in {x["place"]["id"] for x in new["stops"]}:
                changes.append({"kind": "Removed", "slot": i, "from": s["place"]["name"], "to": None, "why": "Nothing else fitted"})
            continue
        if t["price_est"] < s["price_est"] and "too_pricey" in kinds:
            why = f"Cheaper: ${t['price_est']:g} each instead of ${s['price_est']:g}"
        elif "too_far" in kinds:
            why = "Closer for the pod"
        elif "busy_that_day" in kinds or "wrong_time" in kinds:
            why = "Open at the new time"
        else:
            why = "A better fit"
        changes.append({"kind": "Stop changed", "slot": i, "from": s["place"]["name"], "to": t["place"]["name"], "why": why})

    session["plan"], session["request"], session["adjust"] = new, request, adjust
    # the log keeps who asked for what; the pod only ever sees the neutral "why" above
    events.append(_ev(session, "rework", "Peapod", reasons=[{"member": n, "reason": r} for n, r in reasons],
                      reason_tally=tally, adjust=adjust, new_date=request["date"], new_start=request["start"],
                      changes=changes, outcome="reworked"))
    events.append(_built_event(session, new, "rework"))
    return changes or [{"kind": "No change", "note": "The plan already answered the reasons."}]


# ---------------------------------------------------------------- Planning: anyone changes anything

def _rebuild(ds, session, ids):
    """Re-time the plan around the members' own edits. Their stops are kept as they are;
    the sanity checks then show whatever the edit broke."""
    new = plan(ds, going_pod(session), session["request"], session["config"], keep=ids,
               adjust=session["adjust"], force=True)
    if new["status"] != "ok":
        raise FlowError("That would leave the plan with no stops.")
    session["plan"] = new
    return new


def _require_going(session, name):
    st = session["members"].get(name)
    if not st or st["status"] != "in":
        raise FlowError(f"{name} is not going, so cannot do that.")
    return st


def _check_all_approved(session, events):
    going = [s for s in session["members"].values() if s["status"] == "in"]
    cfg = merged_config(session["config"])
    if len(going) < cfg["min_going"]:
        session["phase"] = "ended"
        session["message"] = "Fewer than 2 people are in, so the plan has ended."
        events.append(_ev(session, "phase_changed", None, to="ended", why="fewer than 2 in"))
    elif all(s["approved"] for s in going):
        session["phase"] = "approved"
        session["message"] = "Everyone going approved. The plan is locked."
        events.append(_ev(session, "phase_changed", None, to="approved", going=len(going)))


def act(ds, session, action):
    """One action on a plan that has left Swiping (or a heart at any time)."""
    kind, name = action.get("type"), action.get("name")
    events = []
    stops = session["plan"]["stops"]
    ids = [s["place"]["id"] for s in stops]

    if kind == "heart":
        if session["phase"] == "approved":
            raise FlowError("Hearts are off once the plan is approved.")
        _require_going(session, name)
        s = stops[int(action["stop"])]
        mine = session["hearts"].setdefault(name, [])
        on = s["place"]["id"] not in mine
        (mine.append if on else mine.remove)(s["place"]["id"])
        events.append(_ev(session, "heart", name, place=s["place"]["name"], place_id=s["place"]["id"], on=on))
        if on:                                             # a heart moves that member's taste a little
            w = session["config"]["weights"]
            member = next(m for m in session["pod"]["members"] if m.get("name") == name)
            up = member.setdefault("taste", {}).setdefault("up", {})
            for c in s["place"]["chips"]:
                up[c] = round(min(2.0, up.get(c, 1.0) * w["taste_heart"]), 4)
            events.append(_ev(session, "taste_nudge", name, reason="heart", effect="likes things like it a bit more",
                              chips=s["place"]["chips"], multiplier=w["taste_heart"]))
        return events

    if session["phase"] != "planning":
        raise FlowError("That is only possible once it's a plan (Planning).")

    if kind == "rejoin":
        st = session["members"].get(name)
        if not st or st["status"] != "out":
            raise FlowError(f"{name} is not out.")
        st.update(status="in", approved=False, out_how=None, missed=0)
        events.append(_ev(session, "rejoin", name, note="plan as it is, no rework"))
        _rebuild(ds, session, ids)                         # same stops; checks now include them
        return events

    st = _require_going(session, name)
    if kind == "approve":
        st["approved"] = True
        events.append(_ev(session, "approve", name))
        _check_all_approved(session, events)
    elif kind == "unapprove":
        st["approved"] = False
        events.append(_ev(session, "unapprove", name))
    elif kind == "leave":
        reason = action.get("reason") or None
        st.update(status="out", out_how="left", approved=False)
        events.append(_ev(session, "leave", name, reason=reason))
        events.append(_ev(session, "member_out", name, how="left", reason=reason))
        events.extend(_learn(session, name, reason))
        _rebuild(ds, session, ids)
        _check_all_approved(session, events)
    elif kind in ("change", "remove", "move", "add"):
        i = int(action.get("stop", len(ids)))
        entry = {"by": name}
        if kind == "change":
            new_id = action["place_id"]
            if new_id not in ds.by_id:
                raise FlowError("Unknown place.")
            entry.update(kind="Stop changed", **{"from": stops[i]["place"]["name"]}, to=ds.by_id[new_id].name,
                         tag=action.get("tag"))
            for mine in session["hearts"].values():        # a heart belongs to the stop it was given to
                if ids[i] in mine:
                    mine.remove(ids[i])
            ids[i] = new_id
        elif kind == "remove":
            if len(ids) <= 1:
                raise FlowError("A plan needs at least one stop.")
            entry.update(kind="Removed", **{"from": stops[i]["place"]["name"]}, to=None)
            ids.pop(i)
        elif kind == "move":
            j = i + (-1 if action.get("dir") == "up" else 1)
            if not 0 <= j < len(ids):
                raise FlowError("That stop cannot move further.")
            ids[i], ids[j] = ids[j], ids[i]
            entry.update(kind="Order changed", **{"from": f"stop {i + 1}"}, to=f"stop {j + 1}",
                         place=stops[i]["place"]["name"])
        else:
            new_id = action["place_id"]
            if new_id not in ds.by_id or new_id in ids:
                raise FlowError("That place cannot be added.")
            entry.update(kind="New stop", **{"from": None}, to=ds.by_id[new_id].name)
            ids.append(new_id)                             # every new stop goes at the end of the day
        new = _rebuild(ds, session, ids)
        session["edits"].append(entry)
        events.append(_ev(session, "edit", name, **{k: v for k, v in entry.items() if k != "by"},
                          checks_passed=new["checks"]["passed"], checks_total=new["checks"]["total"],
                          checks_failed=[c["key"] for c in new["checks"]["items"] if not c["pass"]]))
        events.append(_built_event(session, new, "member edit"))
    else:
        raise FlowError(f"Unknown action: {kind}")
    return events


def options(ds, session, stop=None):
    """'Change it to': 2 to 4 options, each with a reason tag and a few words of fact.
    With stop=None: three quick picks for a new stop at the end of the day."""
    stops = session["plan"]["stops"]
    ids = [s["place"]["id"] for s in stops]
    cfg = dict(session["config"], top_n=80, alternatives=0)
    if stop is None:
        res = plan(ds, going_pod(session), session["request"], cfg, keep=ids + [None],
                   adjust=session["adjust"], force=True, free_hubs_at=len(ids))
        rows = res["debug"]["per_stop"][-1]["top"] if res["status"] == "ok" else []
        picks, hubs = [], set()
        for r in rows:                                     # three picks of three different kinds
            if r["place"]["hub"] in hubs or r["place"]["id"] in ids:
                continue
            hubs.add(r["place"]["hub"])
            picks.append({"tag": r["place"]["hub"], "fact": f"~${r['place']['price_est']:g} each · {r['km']} km on",
                          "place": r["place"], "score": r["score"]})
            if len(picks) == 3:
                break
        for r in rows:                                     # not enough kinds: fill with the next best
            if len(picks) >= 3:
                break
            if r["place"]["id"] in ids or any(p["place"]["id"] == r["place"]["id"] for p in picks):
                continue
            picks.append({"tag": r["place"]["hub"], "fact": f"~${r['place']['price_est']:g} each · {r['km']} km on",
                          "place": r["place"], "score": r["score"]})
        return picks

    cur = stops[int(stop)]
    keep = list(ids)
    keep[int(stop)] = None
    res = plan(ds, going_pod(session), session["request"], cfg, keep=keep, adjust=session["adjust"],
               force=True, free_hubs_at=int(stop))
    if res["status"] != "ok" or len(res["debug"]["per_stop"]) <= int(stop):
        return []
    rows = [r for r in res["debug"]["per_stop"][int(stop)]["top"] if r["place"]["id"] not in ids]
    cur_km = (cur["leg"] or {}).get("km")
    tests = [
        ("Cheaper", lambda r: r["place"]["price_est"] < cur["price_est"] - 0.5,
         lambda r: f"${r['place']['price_est']:g} each instead of ${cur['price_est']:g}"),
        ("Closer", lambda r: cur_km is not None and r["km"] < cur_km - 0.2,
         lambda r: f"{r['km']} km from the last stop instead of {cur_km}"),
        ("Quicker", lambda r: r["visit"] < cur["duration"],
         lambda r: f"{r['visit']} min instead of {cur['duration']}"),
        ("More chill", lambda r: r["place"]["hub"] in CHILL_HUBS and r["place"]["hub"] != cur["place"]["hub"],
         lambda r: r["place"]["hub"]),
        ("More active", lambda r: r["place"]["hub"] in ACTIVE_HUBS and r["place"]["hub"] != cur["place"]["hub"],
         lambda r: r["place"]["hub"]),
        ("Something different", lambda r: r["place"]["hub"] != cur["place"]["hub"],
         lambda r: r["place"]["hub"]),
    ]
    out, used = [], set()
    for tag, test, fact in tests:
        r = next((r for r in rows if r["place"]["id"] not in used and test(r)), None)
        if r is None:
            continue
        used.add(r["place"]["id"])
        out.append({"tag": tag, "fact": fact(r), "place": r["place"], "score": r["score"]})
        if len(out) == 4:
            break
    return out
