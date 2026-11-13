"""Web layer for the Peapod plan test bench. All planning logic lives in engine/."""

import hashlib
import hmac
import logging
import os
import uuid
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from engine import (DEFAULT_BUDGET_TIERS, DEFAULT_CONFIG, HUBS, NOT_FOR_ME_REASONS, PRACTICAL_REASONS, RULES, STYLES,
                    TILES, TRAVEL_PREFS, WEIGHT_SPECS, ZONES, flow, load_dataset, load_dataset_postgres,
                    merged_config, plan)

from .pods import EXAMPLE_PODS, random_pod
from .store import Store, now_sgt

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
PLACES_DB = Path(os.environ.get("PEAPOD_PLACES_DB", ROOT / "data" / "places.sqlite"))
PLACES_URL = os.environ.get("PEAPOD_PLACES_URL", "").strip()          # Postgres (Supabase) connection string
PLACES_TABLE = os.environ.get("PEAPOD_PLACES_TABLE", "public.places")
log = logging.getLogger("uvicorn.error")
BENCH_DB = Path(os.environ.get("BENCH_DB", ROOT / "bench.sqlite"))
PASSWORD = os.environ.get("BENCH_PASSWORD", "")
NO_AUTH = os.environ.get("BENCH_NO_AUTH") == "1"
COOKIE = "peapod_bench"

if not PASSWORD and not NO_AUTH:
    raise RuntimeError("Set BENCH_PASSWORD (the shared password), or BENCH_NO_AUTH=1 for local use only.")

app = FastAPI(title="Peapod plan test bench", docs_url=None, redoc_url=None, openapi_url=None)


def _load_places():
    """Supabase when PEAPOD_PLACES_URL is set, else the bundled file. Read-only either way.

    If Supabase cannot be read the bench still starts on the bundled file, and says so on
    the page, so a database hiccup does not take the team's URL down.
    """
    if PLACES_URL:
        try:
            return load_dataset_postgres(PLACES_URL, PLACES_TABLE), f"Supabase {PLACES_TABLE}", ""
        except Exception as exc:          # noqa: BLE001 - any failure falls back
            text = str(exc).strip().splitlines()
            problem = f"{type(exc).__name__}: {text[0][:200] if text else ''}"
            log.warning("Could not load places from Supabase (%s). Using the bundled file.", problem)
            return load_dataset(PLACES_DB), "bundled file (Supabase failed)", problem
    return load_dataset(PLACES_DB), "bundled file", ""


ds, DATA_SOURCE, DATA_PROBLEM = _load_places()   # loaded once into memory
log.info("Places: %s from %s", len(ds.places), DATA_SOURCE)
store = Store(BENCH_DB)


def _token():
    return hmac.new(PASSWORD.encode(), b"peapod-bench-session", hashlib.sha256).hexdigest()


def _authed(request):
    return NO_AUTH or hmac.compare_digest(request.cookies.get(COOKIE, ""), _token())


LOGIN_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Peapod test bench</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fredoka:wght@500;600&family=Nunito:wght@400;700;800&display=swap">
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#FBF6EA;color:#1E3A26;font-family:Nunito,system-ui,sans-serif}
form{background:#fff;border:1.5px solid #E6DECA;border-radius:22px;padding:32px;width:min(360px,calc(100vw - 32px));box-sizing:border-box}
h1{font:600 26px Fredoka,Nunito,sans-serif;margin:0 0 6px}p{margin:0 0 20px;color:#5F6E5C}
input{width:100%;box-sizing:border-box;height:46px;border-radius:14px;border:1.5px solid #E6DECA;padding:0 14px;font:700 16px Nunito,sans-serif;color:#1E3A26}
button{margin-top:12px;width:100%;height:46px;border:0;border-radius:999px;background:#1E3A26;color:#FBF6EA;font:800 16px Nunito,sans-serif;cursor:pointer}
.err{color:#BF3B25;font-weight:700;margin:12px 0 0}</style></head><body>
<form method="post" action="/login"><h1>Peapod test bench</h1><p>Enter the shared team password.</p>
<input type="password" name="password" placeholder="Password" autofocus required aria-label="Password">
<button type="submit">Open the bench</button>__ERR__</form></body></html>"""


@app.middleware("http")
async def guard(request: Request, call_next):
    path = request.url.path
    if path in ("/login", "/healthz") or _authed(request):
        return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse({"detail": "Not signed in."}, status_code=401)
    return RedirectResponse("/login", status_code=303)


@app.get("/healthz")
def healthz():
    return {"ok": True, "places": len(ds.places), "source": DATA_SOURCE}


@app.get("/login", response_class=HTMLResponse)
def login_page():
    return LOGIN_HTML.replace("__ERR__", "")


@app.post("/login")
async def login(request: Request):
    form = parse_qs((await request.body()).decode("utf-8", "replace"))
    given = (form.get("password") or [""])[0]
    if not PASSWORD or not hmac.compare_digest(given.encode(), PASSWORD.encode()):
        return HTMLResponse(LOGIN_HTML.replace("__ERR__", '<p class="err">Wrong password.</p>'), status_code=401)
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(COOKIE, _token(), max_age=30 * 86400, httponly=True, samesite="lax",
                    secure=request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https")
    return resp


@app.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(COOKIE)
    return resp


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


def _tiles():
    known = set(ds.chip_counts)
    return [{"key": t["key"], "label": t["label"],
             "chips": [{"name": c, "count": ds.chip_counts[c], "hub": ds.chip_hub[c]} for c in t["chips"] if c in known]}
            for t in TILES]


@app.get("/api/meta")
def meta():
    today = now_sgt().date()
    saturday = today + timedelta(days=(5 - today.weekday()) % 7 or 7)
    return {
        "zones": ZONES, "hubs": HUBS, "tiles": _tiles(),
        "travel_prefs": TRAVEL_PREFS, "styles": STYLES,
        "practical_reasons": PRACTICAL_REASONS, "not_for_me_reasons": NOT_FOR_ME_REASONS,
        "zone_centroids": {z: [round(v[0], 5), round(v[1], 5)] for z, v in ds.zone_centroids.items()},
        "weights": [{"key": k, "label": l, "default": d, "min": lo, "max": hi, "step": st, "help": h, "group": g}
                    for k, l, d, lo, hi, st, h, g in WEIGHT_SPECS],
        "budget_tiers": DEFAULT_BUDGET_TIERS, "seed": DEFAULT_CONFIG["seed"],
        "max_rounds": DEFAULT_CONFIG["max_rounds"],
        "examples": EXAMPLE_PODS,
        "defaults": {"date": saturday.isoformat(), "start": "11:00", "today": today.isoformat()},
        "dataset": {"places": len(ds.places), "chips": len(ds.chip_counts), "source": DATA_SOURCE,
                    "problem": DATA_PROBLEM, "no_chip": sum(1 for p in ds.places if not p.chips)},
        "reasons": ["wrong vibe", "closed", "too far", "too pricey", "repeat", "other"],
    }


@app.get("/api/rules")
def api_rules():
    return {"rules": RULES}


@app.get("/api/random-pod")
def api_random_pod(seed: int | None = None):
    seed = seed if seed is not None else int(uuid.uuid4().int % 100000)
    return random_pod(_tiles(), ZONES, DEFAULT_BUDGET_TIERS, seed)


def _validate(pod, request):
    members = (pod or {}).get("members") or []
    if not 3 <= len(members) <= 10:
        raise HTTPException(422, "A pod needs 3 to 10 members.")
    names = [(m.get("name") or "").strip() for m in members]
    if len(set(names)) != len(names) or not all(names):
        raise HTTPException(422, "Every member needs a different name.")
    for m in members:
        n = len(m.get("interests") or m.get("chips") or [])
        if not 3 <= n <= 5:
            raise HTTPException(422, f"{m.get('name')} needs 3 to 5 interests (has {n}).")
    if not (request or {}).get("date"):
        raise HTTPException(422, "Pick a date.")


def _saved_config(config):
    cfg = merged_config(config)
    return {"weights": cfg["weights"], "budget_tiers": cfg["budget_tiers"], "seed": cfg["seed"]}


def _run(pod, request, config, tester, label, group=None):
    saved_cfg = _saved_config(config)
    try:
        result = plan(ds, pod, request, saved_cfg)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, f"Could not read the request: {exc}")
    result["run_id"] = store.save_run(pod, request, saved_cfg, result, tester, label, group)
    result["config"] = saved_cfg
    return result


@app.post("/api/compare")
def api_compare(body: dict = Body(...)):
    """Same pod and request, two configs (weight sets). Both runs are saved and linked."""
    _validate(body.get("pod"), body.get("request"))
    group = uuid.uuid4().hex[:8]
    tester, label = body.get("tester", ""), body.get("label", "")
    return {"group": group,
            "a": _run(body["pod"], body["request"], body.get("config_a"), tester, (label + " [A]").strip(), group),
            "b": _run(body["pod"], body["request"], body.get("config_b"), tester, (label + " [B]").strip(), group)}


# ---- one plan, from request to approved -------------------------------------------------

def _commit(session_id, state, events):
    """Save the session, append its events to the log, and save a run for every plan built."""
    meta_keys = ("id", "tester", "label", "created_at", "events")
    tester, label = state.get("tester", ""), state.get("label", "")
    if any(e["type"] == "plan_built" for e in events):
        state["plan"]["run_id"] = store.save_run(
            flow.going_pod(state), state["request"], state["config"], state["plan"], tester, label,
            session_id=session_id, round_no=state.get("round"))
        state["plan"]["config"] = state["config"]
    store.append_events(session_id, events)
    store.save_session(session_id, {k: v for k, v in state.items() if k not in meta_keys})
    return _session_out(session_id)


def _session_out(session_id):
    state = store.get_session(session_id)
    if not state or "phase" not in state:
        raise HTTPException(404, "Plan not found.")
    state["events"] = store.list_events(session_id)
    return state


@app.post("/api/session")
def api_session_start(body: dict = Body(...)):
    _validate(body.get("pod"), body.get("request"))
    tester, label = body.get("tester", ""), body.get("label", "")
    try:
        state, events = flow.start(ds, body["pod"], body["request"], body.get("config"), body.get("pitcher") or None)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, f"Could not read the request: {exc}")
    session_id = store.create_session(tester, label)
    state.update(tester=tester, label=label)
    return _commit(session_id, state, events)


@app.get("/api/session/{session_id}")
def api_session(session_id: int):
    return _session_out(session_id)


@app.post("/api/session/{session_id}/votes")
def api_votes(session_id: int, body: dict = Body(...)):
    state = _session_out(session_id)
    try:
        events = flow.submit_votes(ds, state, body.get("votes") or {})
    except flow.FlowError as exc:
        raise HTTPException(409, str(exc))
    return _commit(session_id, state, events)


@app.post("/api/session/{session_id}/act")
def api_act(session_id: int, body: dict = Body(...)):
    state = _session_out(session_id)
    try:
        events = flow.act(ds, state, body)
    except flow.FlowError as exc:
        raise HTTPException(409, str(exc))
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise HTTPException(422, f"Could not do that: {exc}")
    return _commit(session_id, state, events)


@app.get("/api/session/{session_id}/options")
def api_options(session_id: int, stop: int | None = None):
    state = _session_out(session_id)
    if state["phase"] != "planning":
        raise HTTPException(409, "Stops can only be changed once it's a plan (Planning).")
    try:
        return {"options": flow.options(ds, state, stop)}
    except (IndexError, ValueError) as exc:
        raise HTTPException(422, f"Could not find options: {exc}")


@app.get("/api/sessions")
def api_sessions():
    return {"sessions": store.list_sessions()}


@app.get("/api/events")
def api_events(session_id: int | None = None, limit: int = 500):
    return {"events": store.list_events(session_id, min(max(limit, 1), 5000))}


@app.post("/api/runs/{run_id}/feedback")
def api_feedback(run_id: int, body: dict = Body(...)):
    score = body.get("plan_score")
    if score is not None and score not in (1, 2, 3, 4, 5):
        raise HTTPException(422, "Plan score is 1 to 5.")
    stops = [{"index": int(s["index"]), "verdict": s.get("verdict") or "", "reason": s.get("reason") or "",
              "note": (s.get("note") or "")[:500]} for s in body.get("stops") or []]
    if not store.save_feedback(run_id, score, (body.get("plan_note") or "")[:1000], stops):
        raise HTTPException(404, "Run not found.")
    return {"ok": True}


@app.get("/api/runs")
def api_runs(limit: int = 200):
    return store.list_runs(min(max(limit, 1), 1000))


@app.get("/api/runs/{run_id}")
def api_run(run_id: int):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found.")
    return run


@app.get("/api/export.csv")
def api_export(level: str = "stops"):
    level = level if level in ("runs", "events") else "stops"
    name = f"peapod-bench-{level}-{now_sgt():%Y%m%d-%H%M}.csv"
    body = store.export_events_csv() if level == "events" else store.export_csv(level)
    return Response("﻿" + body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


app.mount("/static", StaticFiles(directory=STATIC), name="static")
