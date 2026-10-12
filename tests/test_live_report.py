"""The comparison report: percentiles, the McNemar test, flips and the variance table."""
from __future__ import annotations

import copy
import sys
import tempfile
import unittest
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))
sys.path.insert(0, str(ROOT / "evals" / "variance"))

import live_report  # noqa: E402
from run_reviewer_eval import load_cases, run_standin  # noqa: E402
from verdict_variance import variance  # noqa: E402


class Stats(unittest.TestCase):
    def test_percentiles(self):
        values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        self.assertAlmostEqual(live_report.percentile(values, 50), 5.5)
        self.assertAlmostEqual(live_report.percentile(values, 95), 9.55)
        self.assertEqual(live_report.percentile([3], 95), 3)

    def test_mcnemar_exact(self):
        self.assertEqual(live_report.mcnemar_exact(0, 0), 1.0)
        self.assertAlmostEqual(live_report.mcnemar_exact(0, 6), 2 / 64)  # 0.03125
        self.assertAlmostEqual(live_report.mcnemar_exact(1, 3), 0.625)
        self.assertGreater(live_report.mcnemar_exact(2, 5), 0.05)


class Report(unittest.TestCase):
    def setUp(self):
        self.cases = load_cases()
        self.standin = run_standin(self.cases, frozenset())

    def fake_live(self, model: str) -> dict:
        run = copy.deepcopy(self.standin)
        run.update({"reviewer": model, "model": model, "effort": "medium"})
        for i, (case_id, result) in enumerate(run["results"].items()):
            result.update({"cost_usd": 0.001 * (i + 1), "latency_s": 1.0 + i / 10})
        # Make the "model" catch H4c, which the stand-in misses.
        run["results"]["H4c"].update({"verdict": "FAIL", "rules": ["H4"], "findings": [
            {"rule": "H4", "severity": "fail", "quote": "If we were in your shoes", "why": "advice"}]})
        return run

    def test_flip_listed_and_called_noise(self):
        live = self.fake_live("claude-haiku-5-5")
        comps = live_report.compare(self.cases, {"stand-in": self.standin, "claude-haiku-5-5": live})
        self.assertEqual([f["id"] for f in comps[0]["flips"]], ["H4c"])
        self.assertEqual((comps[0]["only_a_right"], comps[0]["only_b_right"]), (0, 1))
        self.assertTrue(comps[0]["within_noise"])

    def test_markdown_has_every_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.json"
            path.write_text(json.dumps(self.fake_live("claude-haiku-5-5")))
            vdir = Path(tmp) / "variance"
            vdir.mkdir()
            for n in range(3):
                run = self.fake_live("claude-haiku-5-5")
                if n == 2:
                    run["results"]["B01"]["verdict"] = "PASS"
                    run["results"]["B01"]["rules"] = []
                (vdir / f"run-{n}.json").write_text(json.dumps(run))
            text, data = live_report.build([path], vdir)
        self.assertIn("### claude-haiku-5-5", text)
        self.assertIn("Cost per case (USD) | median", text)
        self.assertIn("Latency per case (s) | p50", text)
        self.assertIn("Quoted evidence found in the post", text)
        self.assertIn("within noise", text)
        self.assertIn("| H4c | FAIL | PASS | FAIL |", text)
        self.assertIn("Cases where every repeat agreed on verdict and rules | 23 of 24", text)
        self.assertEqual(data["scores"]["claude-haiku-5-5"]["per_rule"]["H4"]["caught"], 3)


class RuleSetVariance(unittest.TestCase):
    def test_rule_change_without_verdict_change(self):
        runs = [{"reviewer": "t", "results": {"a": {"verdict": "FAIL", "rules": ["H4"]}}},
                {"reviewer": "t", "results": {"a": {"verdict": "FAIL", "rules": ["H3", "H4"]}}}]
        report = variance(runs)
        self.assertEqual(report["inputs_with_any_change"], 0)
        self.assertEqual(report["rule_changed_ids"], ["a"])
        self.assertEqual(report["inputs_all_agree"], 0)


if __name__ == "__main__":
    unittest.main()
