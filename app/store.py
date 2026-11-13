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
    plan_score INTEGER, plan_note TEXT, feedback_json TEXT, feedback_at TEXT,
    session_id INTEGER, round INTEGER
);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    tester TEXT, label TEXT, phase TEXT, round INTEGER, state_json TEXT NOT NULL
);
-- The engine's log. Rows are only ever inserted, never updated or deleted.
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,                  -- Singapore time, ISO 8601
    session_id INTEGER NOT NULL, round INTEGER, phase TEXT,
    actor TEXT, type TEXT NOT NULL, data_json TEXT NOT NULL
);
"""


def now_sgt():
    return datetime.now(SGT)


def event_summary(kind, d):
    """One readable line per log event."""
    if kind == "plan_requested":
        r = d.get("request", {})
        return f"{r.get('kind')} on {r.get('date')} at {r.get('start')}, pitched by {d.get('pitcher') or 'Peapod'}"
    if kind == "plan_built":
        if d.get("status") != "ok":
            return f"{d.get('why')}: {d.get('message')}"
        return (f"{d.get('why')}: " + " > ".join(s["name"] for s in d.get("stops", []))
                + f" (${d.get('total_cost'):g}, checks {d.get('checks_passed')}/{d.get('checks_total')})")
    if kind == "vote":
        return d.get("answer", "") + (f" ({d['reason']})" if d.get("reason") else "")
    if kind == "no_answer":
        return f"no answer, {d.get('missed_in_a_row')} in a row" + (" -> out" if d.get("out") else "")
    if kind == "member_out":
        return f"out ({d.get('how')})"
    if kind == "rework":
        ch = "; ".join(f"{c.get('kind')}: {c.get('from')} -> {c.get('to')}" for c in d.get("changes", []) if c.get("from") is not None)
        return (f"{d.get('outcome')}. Reasons: " + ", ".join(f"{r['member']} {r['reason']}" for r in d.get("reasons", []))
                + (f". {ch}" if ch else ""))
    if kind == "edit":
        return f"{d.get('kind')}: {d.get('from')} -> {d.get('to')} (checks {d.get('checks_passed')}/{d.get('checks_total')})"
    if kind == "taste_nudge":
        return f"{d.get('reason')}: {d.get('effect')}"
    if kind == "heart":
        return ("hearted " if d.get("on") else "un-hearted ") + str(d.get("place"))
    if kind == "phase_changed":
        return f"-> {d.get('to')}" + (f" ({d['why']})" if d.get("why") else "")
    if kind == "round_started":
        return f"round {d.get('round')} goes to " + ", ".join(d.get("asked", []))
    if kind == "leave":
        return "left" + (f" ({d['reason']})" if d.get("reason") else "")
    if kind == "feedback":
        return f"plan score {d.get('plan_score')}; " + ", ".join(
            f"stop {s['index'] + 1} {s.get('verdict')}" for s in d.get("stops", []) if s.get("verdict"))
    return kind.replace("_", " ")


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._con() as con:
            con.executescript(SCHEMA)
            cols = {r[1] for r in con.execute("PRAGMA table_info(runs)")}
            for col in ("session_id", "round"):           # benches created before sessions existed
                if col not in cols:
                    con.execute(f"ALTER TABLE runs ADD COLUMN {col} INTEGER")

    @contextmanager
    def _con(self):
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def save_run(self, pod, request, config, result, tester="", label="", compare_group=None,
                 session_id=None, round_no=None):
        with self._con() as con:
            cur = con.execute(
                "INSERT INTO runs (created_at, tester, label, compare_group, kind, status, seed, checks_passed, "
                "checks_total, total_cost, pod_json, request_json, config_json, result_json, session_id, round) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (now_sgt().isoformat(timespec="seconds"), tester, label, compare_group, result["kind"],
                 result["status"], result["seed"], result["checks"]["passed"], result["checks"]["total"],
                 result.get("total_cost"), json.dumps(pod), json.dumps(request), json.dumps(config),
                 json.dumps(result), session_id, round_no))
            return cur.lastrowid

    # ---- sessions: one plan from request to approved ----

    def create_session(self, tester, label):
        now = now_sgt().isoformat(timespec="seconds")
        with self._con() as con:
            return con.execute("INSERT INTO sessions (created_at, updated_at, tester, label, phase, round, state_json) "
                               "VALUES (?,?,?,?,?,?,?)", (now, now, tester, label, "new", 0, "{}")).lastrowid

    def save_session(self, session_id, state):
        with self._con() as con:
            con.execute("UPDATE sessions SET updated_at=?, phase=?, round=?, state_json=? WHERE id=?",
                        (now_sgt().isoformat(timespec="seconds"), state.get("phase"), state.get("round"),
                         json.dumps(state), session_id))

    def get_session(self, session_id):
        with self._con() as con:
            r = con.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not r:
            return None
        state = json.loads(r["state_json"])
        state.update(id=r["id"], tester=r["tester"], label=r["label"], created_at=r["created_at"])
        return state

    def list_sessions(self, limit=100):
        with self._con() as con:
            rows = con.execute("SELECT id, created_at, updated_at, tester, label, phase, round FROM sessions "
                               "WHERE phase != 'new' ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ---- the append-only log ----

    def append_events(self, session_id, events):
        at = now_sgt().isoformat(timespec="seconds")
        with self._con() as con:
            con.executemany(
                "INSERT INTO events (at, session_id, round, phase, actor, type, data_json) VALUES (?,?,?,?,?,?,?)",
                [(at, session_id, e.get("round"), e.get("phase"), e.get("actor"), e["type"], json.dumps(e.get("data") or {}))
                 for e in events])

    def list_events(self, session_id=None, limit=500):
        q = "SELECT id, at, session_id, round, phase, actor, type, data_json FROM events"
        args = []
        if session_id:
            q += " WHERE session_id=?"
            args.append(session_id)
        q += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        with self._con() as con:
            rows = con.execute(q, args).fetchall()
        out = []
        for r in reversed(rows):
            d = dict(r)
            d["data"] = json.loads(d.pop("data_json"))
            d["summary"] = event_summary(d["type"], d["data"])
            out.append(d)
        return out

    def export_events_csv(self):
        buf = io.StringIO()
        wr = csv.writer(buf, lineterminator="\n")
        wr.writerow(["event_id", "at_sgt", "session_id", "round", "phase", "actor", "type", "answer", "reason",
                     "summary", "data_json"])
        with self._con() as con:
            rows = con.execute("SELECT * FROM events ORDER BY id").fetchall()
        for r in rows:
            d = json.loads(r["data_json"])
            wr.writerow([r["id"], r["at"], r["session_id"], r["round"], r["phase"], r["actor"], r["type"],
                         d.get("answer", ""), d.get("reason", "") or "", event_summary(r["type"], d), r["data_json"]])
        return buf.getvalue()

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
        run_cols = ["run_id", "session_id", "round", "created_at_sgt", "tester", "label", "compare_group", "kind", "date", "start",
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
            base = [r["id"], r["session_id"], r["round"], r["created_at"], r["tester"], r["label"], r["compare_group"], r["kind"],
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
