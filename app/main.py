"""Web layer for the Peapod plan test bench. All planning logic lives in engine/."""

import hashlib
import hmac
import os
import uuid
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from engine import (DEFAULT_BUDGET_TIERS, DEFAULT_CONFIG, HUBS, TILES, WEIGHT_SPECS, ZONES, load_dataset,
                    merged_config, plan)

from .pods import EXAMPLE_PODS, random_pod
from .store import Store, now_sgt

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
PLACES_DB = Path(os.environ.get("PEAPOD_PLACES_DB", ROOT / "data" / "places.sqlite"))
BENCH_DB = Path(os.environ.get("BENCH_DB", ROOT / "bench.sqlite"))
PASSWORD = os.environ.get("BENCH_PASSWORD", "")
NO_AUTH = os.environ.get("BENCH_NO_AUTH") == "1"
COOKIE = "peapod_bench"

if not PASSWORD and not NO_AUTH:
    raise RuntimeError("Set BENCH_PASSWORD (the shared password), or BENCH_NO_AUTH=1 for local use only.")

app = FastAPI(title="Peapod plan test bench", docs_url=None, redoc_url=None, openapi_url=None)
ds = load_dataset(PLACES_DB)          # read-only, loaded once into memory
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
    return {"ok": True, "places": len(ds.places)}


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


def _chip_list():
    return sorted(ds.chip_counts.items(), key=lambda kv: -kv[1])


@app.get("/api/meta")
def meta():
    known = set(ds.chip_counts)
    tiles = [{"key": t["key"], "label": t["label"],
              "chips": [{"name": c, "count": ds.chip_counts[c], "hub": ds.chip_hub[c]} for c in t["chips"] if c in known]}
             for t in TILES]
    today = now_sgt().date()
    saturday = today + timedelta(days=(5 - today.weekday()) % 7 or 7)
    return {
        "zones": ZONES, "hubs": HUBS, "tiles": tiles,
        "zone_centroids": {z: [round(v[0], 5), round(v[1], 5)] for z, v in ds.zone_centroids.items()},
        "weights": [{"key": k, "label": l, "default": d, "min": lo, "max": hi, "step": st, "help": h}
                    for k, l, d, lo, hi, st, h in WEIGHT_SPECS],
        "budget_tiers": DEFAULT_BUDGET_TIERS, "seed": DEFAULT_CONFIG["seed"],
        "examples": EXAMPLE_PODS,
        "defaults": {"date": saturday.isoformat(), "start": "11:00", "today": today.isoformat()},
        "dataset": {"places": len(ds.places), "chips": len(known),
                    "no_chip": sum(1 for p in ds.places if not p.chips)},
        "reasons": ["wrong vibe", "closed", "too far", "too pricey", "repeat", "other"],
    }


@app.get("/api/random-pod")
def api_random_pod(seed: int | None = None):
    seed = seed if seed is not None else int(uuid.uuid4().int % 100000)
    return random_pod(_chip_list(), ZONES, DEFAULT_BUDGET_TIERS, seed)


def _validate(pod, request):
    members = (pod or {}).get("members") or []
    if not 3 <= len(members) <= 10:
        raise HTTPException(422, "A pod needs 3 to 10 members.")
    for m in members:
        n = len(m.get("chips") or [])
        if not 3 <= n <= 5:
            raise HTTPException(422, f"{m.get('name') or 'A member'} needs 3 to 5 interest chips (has {n}).")
    if not (request or {}).get("date"):
        raise HTTPException(422, "Pick a date.")


def _run(pod, request, config, tester, label, group=None):
    cfg = merged_config(config)
    try:
        result = plan(ds, pod, request, cfg)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, f"Could not read the request: {exc}")
    saved_cfg = {"weights": cfg["weights"], "budget_tiers": cfg["budget_tiers"], "seed": cfg["seed"]}
    result["run_id"] = store.save_run(pod, request, saved_cfg, result, tester, label, group)
    result["config"] = saved_cfg
    return result


@app.post("/api/plan")
def api_plan(body: dict = Body(...)):
    _validate(body.get("pod"), body.get("request"))
    return _run(body["pod"], body["request"], body.get("config"), body.get("tester", ""), body.get("label", ""))


@app.post("/api/compare")
def api_compare(body: dict = Body(...)):
    """Same pod and request, two configs (weight sets). Both runs are saved and linked."""
    _validate(body.get("pod"), body.get("request"))
    group = uuid.uuid4().hex[:8]
    tester, label = body.get("tester", ""), body.get("label", "")
    return {"group": group,
            "a": _run(body["pod"], body["request"], body.get("config_a"), tester, (label + " [A]").strip(), group),
            "b": _run(body["pod"], body["request"], body.get("config_b"), tester, (label + " [B]").strip(), group)}


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
    level = "runs" if level == "runs" else "stops"
    name = f"peapod-bench-{level}-{now_sgt():%Y%m%d-%H%M}.csv"
    return Response("﻿" + store.export_csv(level), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


app.mount("/static", StaticFiles(directory=STATIC), name="static")
