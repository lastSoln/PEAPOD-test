"""Writable bench store (bench.sqlite): saved runs and tester feedback.

Completely separate from the places dataset, which is never written to.
"""

import csv
import io
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

SGT = timezone(timedelta(hours=8))

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,          -- Singapore time, ISO 8601
    tester TEXT, label TEXT, compare_group TEXT,
    kind TEXT, status TEXT, seed INTEGER,
    checks_passed INTEGER, checks_total INTEGER, total_cost REAL,
    pod_json TEXT NOT NULL, request_json TEXT NOT NULL, config_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    plan_score INTEGER, plan_note TEXT, feedback_json TEXT, feedback_at TEXT
);
"""


def now_sgt():
    return datetime.now(SGT)


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._con() as con:
            con.executescript(SCHEMA)

    @contextmanager
    def _con(self):
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def save_run(self, pod, request, config, result, tester="", label="", compare_group=None):
        with self._con() as con:
            cur = con.execute(
                "INSERT INTO runs (created_at, tester, label, compare_group, kind, status, seed, checks_passed, "
                "checks_total, total_cost, pod_json, request_json, config_json, result_json) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (now_sgt().isoformat(timespec="seconds"), tester, label, compare_group, result["kind"],
                 result["status"], result["seed"], result["checks"]["passed"], result["checks"]["total"],
                 result.get("total_cost"), json.dumps(pod), json.dumps(request), json.dumps(config),
                 json.dumps(result)))
            return cur.lastrowid

    def save_feedback(self, run_id, plan_score, plan_note, stops):
        with self._con() as con:
            cur = con.execute(
                "UPDATE runs SET plan_score=?, plan_note=?, feedback_json=?, feedback_at=? WHERE id=?",
                (plan_score, plan_note, json.dumps(stops), now_sgt().isoformat(timespec="seconds"), run_id))
            return cur.rowcount > 0

    def get_run(self, run_id):
        with self._con() as con:
            r = con.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        for k in ("pod", "request", "config", "result", "feedback"):
            raw = d.pop(k + "_json")
            d[k] = json.loads(raw) if raw else None
        return d

    def list_runs(self, limit=200):
        with self._con() as con:
            rows = con.execute(
                "SELECT id, created_at, tester, label, compare_group, kind, status, seed, checks_passed, "
                "checks_total, total_cost, plan_score, feedback_json, request_json FROM runs ORDER BY id DESC LIMIT ?",
                (limit,)).fetchall()
            agg = con.execute(
                "SELECT COUNT(*) n, SUM(status='ok') ok, SUM(checks_passed) cp, SUM(checks_total) ct, "
                "SUM(checks_total>0 AND checks_passed=checks_total) clean, AVG(plan_score) avg_score, "
                "COUNT(plan_score) scored FROM runs").fetchone()
            fb = con.execute("SELECT feedback_json FROM runs WHERE feedback_json IS NOT NULL").fetchall()
        verdicts, reasons = {}, {}
        for (raw,) in fb:
            for s in json.loads(raw) or []:
                if s.get("verdict"):
                    verdicts[s["verdict"]] = verdicts.get(s["verdict"], 0) + 1
                if s.get("reason"):
                    reasons[s["reason"]] = reasons.get(s["reason"], 0) + 1
        out = []
        for r in rows:
            d = dict(r)
            d["request"] = json.loads(d.pop("request_json"))
            d["has_feedback"] = bool(d.pop("feedback_json")) or d["plan_score"] is not None
            out.append(d)
        return {"runs": out, "stats": {
            "runs": agg["n"] or 0, "planned": agg["ok"] or 0, "checks_passed": agg["cp"] or 0,
            "checks_total": agg["ct"] or 0, "clean_runs": agg["clean"] or 0,
            "avg_plan_score": round(agg["avg_score"], 2) if agg["avg_score"] is not None else None,
            "scored_runs": agg["scored"] or 0, "verdicts": verdicts, "reasons": reasons}}

    def export_csv(self, level="stops"):
        """level='stops': one row per stop (plus one row for a run with no stops). level='runs': one row per run."""
        run_cols = ["run_id", "created_at_sgt", "tester", "label", "compare_group", "kind", "date", "start",
                    "fixed_area", "fixed_budget", "fixed_kind", "seed", "status", "message", "pod_size",
                    "lowest_budget", "total_cost", "checks_passed", "checks_total", "checks_failed",
                    "plan_score", "plan_note", "feedback_at", "weights_json", "budget_tiers_json", "pod_json"]
        stop_cols = ["stop_index", "place_id", "place_name", "hub", "zone", "chips", "arrival", "duration_min",
                     "price_est", "leg_minutes", "leg_mode", "score", "score_parts_json", "matched_members",
                     "is_new_slot", "why", "alternatives", "verdict", "reason", "note"]
        buf = io.StringIO()
        wr = csv.writer(buf, lineterminator="\n")
        wr.writerow(run_cols + (stop_cols if level == "stops" else ["stops", "stop_verdicts"]))
        with self._con() as con:
            rows = con.execute("SELECT * FROM runs ORDER BY id").fetchall()
        for r in rows:
            pod, req = json.loads(r["pod_json"]), json.loads(r["request_json"])
            cfg, res = json.loads(r["config_json"]), json.loads(r["result_json"])
            fb = {s.get("index"): s for s in (json.loads(r["feedback_json"]) if r["feedback_json"] else [])}
            base = [r["id"], r["created_at"], r["tester"], r["label"], r["compare_group"], r["kind"],
                    req.get("date"), req.get("start"), req.get("area") or "", req.get("budget") or "",
                    req.get("hub") or "", r["seed"], r["status"], res.get("message"),
                    len(pod.get("members") or []), res.get("budget_label"), r["total_cost"],
                    r["checks_passed"], r["checks_total"],
                    "; ".join(c["key"] for c in res["checks"]["items"] if not c["pass"]),
                    r["plan_score"], r["plan_note"], r["feedback_at"],
                    json.dumps(cfg.get("weights")), json.dumps(cfg.get("budget_tiers")), json.dumps(pod)]
            stops = res.get("stops") or []
            if level != "stops":
                wr.writerow(base + [" > ".join(s["place"]["name"] for s in stops),
                                    " > ".join((fb.get(s["index"], {}).get("verdict") or "-") for s in stops)])
                continue
            if not stops:
                wr.writerow(base + [""] * len(stop_cols))
            for s in stops:
                f = fb.get(s["index"], {})
                leg = s.get("leg") or {}
                wr.writerow(base + [
                    s["index"] + 1, s["place"]["id"], s["place"]["name"], s["place"]["hub"], s["place"]["zone"],
                    "; ".join(s["place"]["chips"]), s["arrival"], s["duration"], s["price_est"],
                    leg.get("minutes", ""), leg.get("mode", ""), s["score"], json.dumps(s["parts"]),
                    "; ".join(f"{m['name']} ({m['level']})" for m in s["matched"]), int(s["is_new_slot"]),
                    s["why"], "; ".join(a["place"]["name"] for a in s["alternatives"]),
                    f.get("verdict", ""), f.get("reason", ""), f.get("note", "")])
        return buf.getvalue()
