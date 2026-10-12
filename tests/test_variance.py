"""The variance script reports zero for identical runs and counts real changes."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals" / "variance"))

from verdict_variance import load_runs, variance  # noqa: E402

FIXTURES = ROOT / "evals" / "variance" / "fixtures"


def fake_run(**verdicts: str) -> dict:
    return {"reviewer": "test", "results": {k: {"verdict": v} for k, v in verdicts.items()}}


class Variance(unittest.TestCase):
    def test_recorded_standin_fixtures_are_stable(self):
        runs = load_runs([FIXTURES])
        self.assertEqual(len(runs), 5)
        report = variance(runs)
        self.assertEqual(report["inputs"], 24)
        self.assertEqual(report["inputs_with_any_change"], 0)
        self.assertEqual(report["verdicts_matching_modal"], 120)

    def test_detects_a_flip(self):
        report = variance([fake_run(a="PASS", b="FAIL"), fake_run(a="PASS", b="FLAG"),
                           fake_run(a="PASS", b="FAIL")])
        self.assertEqual(report["changed_ids"], ["b"])
        self.assertEqual(report["per_case"]["b"]["modal"], "FAIL")
        self.assertEqual(report["per_case"]["b"]["agree_with_modal"], 2)
        self.assertAlmostEqual(report["verdict_change_rate"], 0.5)

    def test_needs_two_runs(self):
        with self.assertRaises(ValueError):
            variance([fake_run(a="PASS")])


if __name__ == "__main__":
    unittest.main()
