"""The cost ledger prices usage at list rates, persists the total, and stops the process at the ceiling."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))

import ledger as ledger_module  # noqa: E402
from ledger import HARD_STOP_USD, Ledger, SpendCeilingReached, cost_usd, summary  # noqa: E402


def usage(i=0, o=0, read=0, write=0) -> dict:
    return {"input_tokens": i, "output_tokens": o, "cache_read_input_tokens": read,
            "cache_creation_input_tokens": write}


class Prices(unittest.TestCase):
    def test_sonnet_list_prices(self):
        self.assertAlmostEqual(cost_usd("claude-sonnet-5-5", usage(i=1_000_000)), 2.00)
        self.assertAlmostEqual(cost_usd("claude-sonnet-5-5", usage(o=1_000_000)), 10.00)
        self.assertAlmostEqual(cost_usd("claude-sonnet-5-5", usage(read=1_000_000)), 0.20)
        self.assertAlmostEqual(cost_usd("claude-sonnet-5-5", usage(write=1_000_000)), 2.50)

    def test_haiku_list_prices(self):
        # Prompts of 100K tokens or fewer, so the standard card applies.
        self.assertAlmostEqual(cost_usd("claude-haiku-5-5", usage(i=100_000)), 0.010)
        self.assertAlmostEqual(cost_usd("claude-haiku-5-5", usage(o=1_000_000)), 0.50)
        self.assertAlmostEqual(cost_usd("claude-haiku-5-5", usage(read=100_000)), 0.001)

    def test_haiku_long_prompt_card(self):
        # Over 100K prompt tokens, Haiku 5.5 bills $0.50 / $2.50.
        self.assertAlmostEqual(cost_usd("claude-haiku-5-5", usage(i=200_000, o=1_000_000)), 0.10 + 2.50)

    def test_a_typical_cached_call(self):
        cost = cost_usd("claude-sonnet-5-5", usage(i=400, o=2000, read=2200))
        self.assertAlmostEqual(cost, (400 * 2 + 2000 * 10 + 2200 * 0.2) / 1e6)

    def test_unknown_model_is_refused_not_guessed(self):
        with self.assertRaises(KeyError):
            cost_usd("claude-opus-5-5", usage(i=1))

    def test_accepts_sdk_style_objects(self):
        class Usage:
            input_tokens, output_tokens = 10, 20
            cache_read_input_tokens = None
            cache_creation_input_tokens = None
        self.assertAlmostEqual(cost_usd("claude-haiku-5-5", Usage()), (10 * 0.1 + 20 * 0.5) / 1e6)


class Ledgering(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "spend.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_appends_rows_and_survives_a_restart(self):
        first = Ledger(self.path)
        first.record("claude-haiku-5-5", usage(i=1000, o=1000), label="H1a", run="r1", request_id="req_1")
        second = Ledger(self.path)
        self.assertAlmostEqual(second.total, first.total)
        second.record("claude-sonnet-5-5", usage(o=1000), label="H1b", run="r1")
        rows = [json.loads(l) for l in self.path.read_text().splitlines()]
        self.assertEqual([r["label"] for r in rows], ["H1a", "H1b"])
        self.assertEqual(rows[0]["model"], "claude-haiku-5-5")
        self.assertEqual(rows[0]["request_id"], "req_1")
        self.assertAlmostEqual(rows[1]["running_total_usd"], first.total + 0.01, places=6)
        self.assertAlmostEqual(summary(self.path)["by_model"]["claude-sonnet-5-5"], 0.01)

    def test_aborts_on_the_row_that_crosses_the_ceiling(self):
        ledger = Ledger(self.path, hard_stop=0.01)
        ledger.record("claude-sonnet-5-5", usage(o=500))  # $0.005
        with self.assertRaises(SpendCeilingReached) as raised:
            ledger.record("claude-sonnet-5-5", usage(o=600))  # passes $0.01
        self.assertEqual(raised.exception.code, 3)
        self.assertEqual(len(self.path.read_text().splitlines()), 2, "the crossing row is still written")

    def test_platform_priced_cost_counts_against_the_stop(self):
        ledger = Ledger(self.path, hard_stop=0.5)
        ledger.record_cost("claude-sonnet-5-5", 0.23, label="managed-session", run="sesn_1",
                           usage={"input_tokens": 10, "cache_creation_input_tokens": {"ephemeral_5m": 7}})
        row = json.loads(self.path.read_text())
        self.assertEqual((row["cost_usd"], row["platform_priced"], row["cache_creation_input_tokens"]),
                         (0.23, True, 7))
        with self.assertRaises(SpendCeilingReached):
            ledger.record_cost("claude-sonnet-5-5", 0.30)

    def test_check_refuses_to_start_once_over(self):
        Ledger(self.path, hard_stop=1.0)  # nothing yet
        self.path.write_text(json.dumps({"cost_usd": 51.0, "model": "x", "run": ""}) + "\n")
        with self.assertRaises(SpendCeilingReached):
            Ledger(self.path).check()

    def test_the_ceiling_cannot_be_raised_from_outside(self):
        self.assertEqual(HARD_STOP_USD, 50.00)
        self.assertEqual(Ledger(self.path, hard_stop=500).hard_stop, 50.00)
        source = (ROOT / "evals" / "ledger.py").read_text()
        self.assertNotIn("os.environ", source)
        self.assertNotIn("argparse", source)

    def test_abort_really_exits_the_process(self):
        script = textwrap.dedent(f"""
            import sys; sys.path.insert(0, {str(ROOT / 'evals')!r})
            from ledger import Ledger
            l = Ledger(__import__('pathlib').Path({str(self.path)!r}), hard_stop=0.001)
            try:
                l.record('claude-sonnet-5-5', {{'output_tokens': 1000}})
            except Exception:
                print('caught by a broad except, which must not happen')
            print('still running')
        """)
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertNotIn("still running", result.stdout)
        self.assertIn("SPEND CEILING", result.stderr)


if __name__ == "__main__":
    unittest.main()
