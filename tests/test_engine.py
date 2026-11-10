"""Engine checks against the bundled dataset.  python -m unittest discover tests"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import ADULT_HUB, load_dataset, plan  # noqa: E402
from engine.dataset import parse_hours, Place, is_open  # noqa: E402

DS = load_dataset(ROOT / "data" / "places.sqlite")


def member(name, chips, tier="mid", over18=True, zone="Central"):
    return {"name": name, "chips": chips, "budget_tier": tier, "over18": over18, "home": {"zone": zone}}


POD = {"members": [
    member("Ana", ["Specialty coffee", "Art galleries", "Asian"]),
    member("Ben", ["Hiking", "Local & street food", "Arcades & VR"], "low", zone="East"),
    member("Cy", ["Cocktail bars", "Museums", "Desserts & ice cream"], "high", zone="West"),
]}
DAY = {"kind": "dayout", "date": "2026-11-14", "start": "11:00"}


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

    def test_moment_is_one_stop(self):
        r = plan(DS, POD, {"kind": "moment", "date": "2026-11-14", "start": "19:00"})
        self.assertEqual((r["status"], len(r["stops"])), ("ok", 1))

    def test_bars_need_everyone_over_18(self):
        pod = json.loads(json.dumps(POD))
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


if __name__ == "__main__":
    unittest.main()
