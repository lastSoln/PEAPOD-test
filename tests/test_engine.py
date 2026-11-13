"""Engine checks against the bundled dataset.  python -m unittest discover tests"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import ADULT_HUB, flow, load_dataset, plan  # noqa: E402
from engine.dataset import parse_hours, Place, is_open  # noqa: E402

DS = load_dataset(ROOT / "data" / "places.sqlite")


def member(name, interests, favourites=(), tier="mid", travel="far", style="flow", zone="Central", over18=True):
    return {"name": name, "interests": list(interests), "favourites": list(favourites), "budget_tier": tier,
            "travel": travel, "style": style, "over18": over18, "home": {"zone": zone}}


POD = {"members": [
    member("Ana", ["cafe", "sights", "eat"], ["Specialty coffee", "Art galleries"], style="explorer"),
    member("Ben", ["active", "eat", "play"], ["Hiking", "Local & street food"], tier="low", zone="East", style="foodie"),
    member("Cy", ["bars", "sights", "cafe"], ["Cocktail bars", "Museums"], tier="high", zone="West", style="planner"),
    member("Di", ["nature", "shop", "cafe"], zone="Central"),
]}
DAY = {"kind": "dayout", "date": "2026-11-14", "start": "11:00"}


def fresh():
    return json.loads(json.dumps(POD))


class EngineTests(unittest.TestCase):
    def test_hours_overnight(self):
        p = Place("x", "x", "", 1.3, 103.8, "Central", "Food", (), frozenset(), 0, 0, 0,
                  parse_hours({"Fri": ["18:00-01:00"]}), {}, 60, "", "", "", {})
        self.assertTrue(is_open(p, 4, 23 * 60, 60))          # Fri 23:00-24:00
        self.assertTrue(is_open(p, 5, 0, 60))                # Sat 00:00-01:00, Friday's session
        self.assertFalse(is_open(p, 5, 30, 60))              # runs past closing
        self.assertFalse(is_open(p, 5, 19 * 60, 60))         # closed Saturday

    def test_day_out_passes_checks_and_repeats(self):
        a = plan(DS, POD, DAY, {"seed": 7})
        b = plan(DS, POD, DAY, {"seed": 7})
        self.assertEqual(a["status"], "ok")
        self.assertEqual(json.dumps(a), json.dumps(b))
        self.assertEqual(len(a["stops"]), 4)
        self.assertEqual(a["checks"]["passed"], a["checks"]["total"], a["checks"])
        self.assertLessEqual(a["total_cost"], 40)            # Ben's "low" tier is the lowest
        for s in a["stops"]:
            self.assertGreaterEqual(len(s["alternatives"]), 2)

    def test_legacy_chips_still_work(self):
        pod = {"members": [{"name": n, "chips": c, "budget_tier": "mid", "over18": True, "home": {"zone": "Central"}}
                           for n, c in [("A", ["Asian", "Museums", "Hiking"]), ("B", ["Specialty coffee", "Karaoke", "Bookshops"]),
                                        ("C", ["Gardens & parks", "Cinema", "Tea & boba"])]]}
        self.assertEqual(plan(DS, pod, DAY)["status"], "ok")

    def test_moment_is_one_stop(self):
        r = plan(DS, POD, {"kind": "moment", "date": "2026-11-14", "start": "19:00"})
        self.assertEqual((r["status"], len(r["stops"])), ("ok", 1))

    def test_bars_need_everyone_over_18(self):
        pod = fresh()
        pod["members"][1]["over18"] = False
        r = plan(DS, pod, DAY)
        self.assertTrue(all(s["place"]["hub"] != ADULT_HUB for s in r["stops"]))
        r = plan(DS, pod, {"kind": "moment", "date": "2026-11-14", "start": "19:00", "hub": ADULT_HUB})
        self.assertEqual(r["status"], "no_plan")
        self.assertIn("Kind row", r["message"])              # names the row, never the person
        for m in pod["members"]:
            self.assertNotIn(m["name"], r["message"])

    def test_fixed_area(self):
        r = plan(DS, POD, dict(DAY, area="East"))
        self.assertTrue(r["stops"] and all(s["place"]["zone"] == "East" for s in r["stops"]))

    def test_travel_limit_is_hard(self):
        pod = fresh()
        pod["members"][0]["travel"] = "close"                # Ana, Central, 15 minutes
        r = plan(DS, pod, DAY)
        self.assertEqual(r["status"], "ok")
        ana = next(x for x in r["leave_home"] if x["name"] == "Ana")
        self.assertLessEqual(ana["furthest_min"], 15)
        for m in pod["members"]:                             # everyone close by, homes far apart
            m["travel"] = "close"
        r = plan(DS, pod, DAY)
        self.assertEqual(r["status"], "no_plan")
        self.assertNotIn("travel", r["message"].lower())     # never says which limit

    def test_style_majority_changes_the_day(self):
        pod = fresh()
        for m in pod["members"]:
            m["style"] = "flow"
        self.assertEqual(len(plan(DS, pod, DAY)["stops"]), 3)
        for m in pod["members"]:
            m["style"] = "planner"
        self.assertEqual(len(plan(DS, pod, DAY)["stops"]), 5)


class FlowTests(unittest.TestCase):
    def test_rounds_rework_planning_approved(self):
        s, ev = flow.start(DS, fresh(), DAY, {"seed": 5}, pitcher="Ana")
        self.assertEqual((s["phase"], s["round"]), ("swiping", 1))
        self.assertEqual(s["members"]["Ana"]["status"], "in")            # the pitcher never swipes
        self.assertEqual([e["type"] for e in ev], ["plan_requested", "plan_built"])
        before = s["plan"]["total_cost"]
        ev = flow.submit_votes(DS, s, {"Ben": {"answer": "in"}, "Cy": {"answer": "maybe", "reason": "too_pricey"}})
        self.assertEqual((s["phase"], s["round"]), ("swiping", 2))
        self.assertLess(s["plan"]["total_cost"], before)                 # reworked cheaper
        self.assertEqual(s["members"]["Di"]["missed"], 1)                # silence counts as a missed round
        self.assertIn("rework", [e["type"] for e in ev])
        for c in s["rounds"][-1]["changes"]:                             # the pod never sees who asked
            self.assertNotIn("Cy", json.dumps(c))
        flow.submit_votes(DS, s, {"Cy": {"answer": "in"}, "Di": {"answer": "cant", "reason": "not_my_thing"}})
        self.assertEqual(s["phase"], "planning")
        self.assertEqual(s["members"]["Di"]["status"], "out")
        di = next(m for m in s["pod"]["members"] if m["name"] == "Di")
        self.assertTrue(di["taste"]["down"])                             # "not for me" nudges taste
        with self.assertRaises(flow.FlowError):
            flow.act(DS, s, {"type": "approve", "name": "Di"})           # out cannot approve
        opts = flow.options(DS, s, 0)
        self.assertTrue(1 <= len(opts) <= 4)
        flow.act(DS, s, {"type": "change", "name": "Ben", "stop": 0, "place_id": opts[0]["place"]["id"]})
        self.assertEqual(s["plan"]["stops"][0]["place"]["id"], opts[0]["place"]["id"])
        flow.act(DS, s, {"type": "rejoin", "name": "Di"})
        for n in ("Ana", "Ben", "Cy", "Di"):
            flow.act(DS, s, {"type": "approve", "name": n})
        self.assertEqual(s["phase"], "approved")
        with self.assertRaises(flow.FlowError):
            flow.act(DS, s, {"type": "remove", "name": "Ben", "stop": 0})  # locked

    def test_final_round_and_ending(self):
        s, _ = flow.start(DS, fresh(), DAY, {"seed": 5}, pitcher=None)
        for _ in range(2):
            flow.submit_votes(DS, s, {"Ana": {"answer": "in"}, "Ben": {"answer": "maybe", "reason": "wrong_time"}})
        self.assertEqual(s["round"], 3)
        with self.assertRaises(flow.FlowError):
            flow.submit_votes(DS, s, {"Ben": {"answer": "maybe", "reason": "too_far"}})   # no Maybe in round 3
        flow.submit_votes(DS, s, {"Ben": {"answer": "in"}})
        self.assertEqual(s["phase"], "planning")
        self.assertEqual(s["members"]["Cy"]["out_how"], "missed")        # three silent rounds
        s2, _ = flow.start(DS, fresh(), DAY, {"seed": 5}, pitcher="Ana")
        flow.submit_votes(DS, s2, {n: {"answer": "cant", "reason": "not_with_group"} for n in ("Ben", "Cy", "Di")})
        self.assertEqual(s2["phase"], "ended")                           # fewer than 2 in


if __name__ == "__main__":
    unittest.main()
