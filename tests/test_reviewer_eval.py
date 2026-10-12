"""The eval harness measures what it says, and goes red when a rule is broken."""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))

import run_reviewer_eval as harness  # noqa: E402
from check_post import HARD_RULES  # noqa: E402


def run(*args: str) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out):
        code = harness.main(list(args))
    return code, out.getvalue()


class Wilson(unittest.TestCase):
    def test_known_value(self):
        low, high = harness.wilson_interval(15, 24)
        self.assertAlmostEqual(low, 0.4271, places=3)
        self.assertAlmostEqual(high, 0.7884, places=3)

    def test_edges(self):
        self.assertEqual(harness.wilson_interval(0, 10)[0], 0.0)
        self.assertEqual(harness.wilson_interval(10, 10)[1], 1.0)
        self.assertEqual(harness.wilson_interval(0, 0), (0.0, 1.0))


class Harness(unittest.TestCase):
    def test_default_run_is_green_and_matches_baseline(self):
        code, out = run()
        self.assertEqual(code, 0, out)
        self.assertIn("GATE: GREEN", out)
        cases = harness.load_cases()
        scores = harness.score(cases, harness.run_standin(cases, frozenset()))
        baseline = json.loads(harness.BASELINE.read_text())
        self.assertEqual({r: v["caught"] for r, v in scores["per_rule"].items()}, baseline["caught"])
        self.assertEqual(scores["agreement"], baseline["agreement"])
        self.assertEqual(scores["clean_false_positives"], 0)

    def test_every_hard_rule_fault_turns_the_gate_red(self):
        for rule in HARD_RULES:
            with self.subTest(rule=rule):
                code, out = run("--seed-fault", rule, "--summary")
                self.assertEqual(code, 1, out)
                self.assertIn(f"{rule} catch fell", out)

    def test_live_mode_without_a_key_makes_no_calls(self):
        # Never let the unit tests spend money, even on a machine that has a key.
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            code, out = run("--live")
        self.assertEqual(code, 2)
        self.assertIn("needs ANTHROPIC_API_KEY", out)
        self.assertIn("no calls were made", out)

    def test_live_dry_run_prints_a_plan(self):
        code, out = run("--live", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("tokens", out)
        self.assertIn("per pass at list prices", out)

    def test_recorded_round_trip_scores_the_same(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = Path(tmp) / "run.json"
            code, first = run("--record", str(record), "--json")
            code2, second = run("--from-recorded", str(record), "--json")
        self.assertEqual((code, code2), (0, 0))
        a, b = json.loads(first), json.loads(second)
        self.assertEqual(a["per_rule"], b["per_rule"])
        self.assertEqual(a["agreement"], b["agreement"])

    def test_report_lists_disagreements_and_interval(self):
        code, out = run()
        self.assertIn("Wilson interval", out)
        self.assertIn("Cases where the reviewer disagreed", out)
        self.assertIn("False positives on clean cases: 0/2", out)

    def test_catch_needs_rule_and_non_pass_verdict(self):
        cases = [{"id": "X", "category": "hard", "post": "", "expected_verdict": "FAIL",
                  "expected_rules": ["H4"], "evidence_phrase": "we recommend"}]
        miss = {"results": {"X": {"verdict": "PASS", "rules": ["H4"], "findings": []}}}
        hit = {"results": {"X": {"verdict": "FAIL", "rules": ["H4"], "findings": [
            {"rule": "H4", "quote": "We recommend you fix"}]}}}
        self.assertEqual(harness.score(cases, miss)["per_rule"]["H4"]["caught"], 0)
        scored = harness.score(cases, hit)["per_rule"]["H4"]
        self.assertEqual((scored["caught"], scored["quoted_expected_evidence"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
