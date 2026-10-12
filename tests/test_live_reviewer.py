"""The live reviewer builds the request the brief describes and records every response, using a fake client.

No network. Skipped when pydantic (requirements-live.txt) is not installed.
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))

import reviewer_prompt  # noqa: E402
import run_reviewer_eval as harness  # noqa: E402
from ledger import Ledger  # noqa: E402

HAVE_PYDANTIC = importlib.util.find_spec("pydantic") is not None


class FakeClient:
    """Records every request; answers from a script of (stop_reason, verdict-or-None)."""

    def __init__(self, script):
        self.calls, self.script = [], list(script)
        self.messages = SimpleNamespace(parse=self._parse)

    def _parse(self, **kwargs):
        self.calls.append(kwargs)
        stop_reason, parsed = self.script.pop(0) if self.script else ("end_turn", None)
        if stop_reason == "end_turn" and parsed is None:
            raise ValueError("1 validation error for ReviewerVerdict")
        usage = {"input_tokens": 400, "output_tokens": 1500,
                 "cache_read_input_tokens": 2200 if len(self.calls) > 1 else 0,
                 "cache_creation_input_tokens": 0 if len(self.calls) > 1 else 2200}
        return SimpleNamespace(stop_reason=stop_reason, usage=usage, _request_id="req_fake",
                               stop_details={"category": "general_harms"} if stop_reason == "refusal" else None,
                               parsed_output=parsed, content=[])


class Prompt(unittest.TestCase):
    def test_cached_prefix_holds_skill_checklist_and_voice(self):
        blocks = reviewer_prompt.system_blocks()
        text = "\n".join(b["text"] for b in blocks)
        self.assertIn("# Compliance reviewer", text)
        self.assertIn("## Hard rules (fail)", text)
        self.assertIn("# Harbourlight brand voice", text)
        self.assertEqual([b for b in blocks if "cache_control" in b], [blocks[-1]])
        self.assertEqual(blocks[-1]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(blocks, reviewer_prompt.system_blocks(), "prefix must be byte-stable")

    def test_post_goes_last_after_the_cited_story(self):
        case = json.loads((ROOT / "evals" / "reviewer-cases" / "C01.json").read_text())
        content = reviewer_prompt.user_content(case["post"], reviewer_prompt.load_stories())
        self.assertIn("<cited_story>", content[0]["text"])
        self.assertIn("Lenders trim five-year fixed rates", content[0]["text"])
        self.assertNotIn("Status:", content[0]["text"])
        self.assertTrue(content[-1]["text"].startswith("<draft>"))
        self.assertIn(case["post"], content[-1]["text"])

    def test_missing_and_unknown_sources_are_said_plainly(self):
        stories = reviewer_prompt.load_stories()
        self.assertIn("no Sources block", reviewer_prompt.cited_story("# T\n\nBody.\n", stories))
        post = "# T\n\nBody.\n\nSources:\n- https://news.example.invalid/nowhere/x\n"
        self.assertIn("No story in the corpus", reviewer_prompt.cited_story(post, stories))

    def test_dry_run_makes_no_calls_and_needs_no_key(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = harness.main(["--live", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("no calls made", out.getvalue())
        self.assertIn("claude-sonnet-5-5", out.getvalue())


@unittest.skipUnless(HAVE_PYDANTIC, "pydantic not installed (pip install -r requirements-live.txt)")
class LiveReview(unittest.TestCase):
    def setUp(self):
        import live_reviewer
        self.lr = live_reviewer
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name) / "spend.jsonl")
        self.stories = reviewer_prompt.load_stories()

    def tearDown(self):
        self.tmp.cleanup()

    def verdict(self, **kw):
        base = {"verdict": "FAIL", "needs_human": False, "what_would_change": ["H4: x"],
                "summary_for_approver": "s",
                "findings": [{"rule": "H4", "severity": "fail", "quote": "We recommend", "reason": "advice"}]}
        base.update(kw)
        return self.lr.ReviewerVerdict.model_validate(base)

    def test_request_shape(self):
        client = FakeClient([("end_turn", self.verdict())])
        self.lr.review(client, "claude-haiku-5-5", "post", self.stories, self.ledger, label="X")
        call = client.calls[0]
        self.assertEqual(call["model"], "claude-haiku-5-5")
        self.assertIs(call["output_format"], self.lr.ReviewerVerdict)
        self.assertEqual(call["output_config"], {"effort": "medium"})
        self.assertEqual(call["system"][-1]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(call["messages"][0]["role"], "user")

    def test_records_verdict_cost_and_ledger_row(self):
        client = FakeClient([("end_turn", self.verdict())])
        record = self.lr.review(client, "claude-sonnet-5-5", "post", self.stories, self.ledger,
                                label="H4b", run="r")
        self.assertEqual(record["verdict"], "FAIL")
        self.assertEqual(record["rules"], ["H4"])
        self.assertEqual(record["findings"][0]["why"], "advice")
        self.assertEqual(record["effort"], "high")
        self.assertGreater(record["cost_usd"], 0)
        self.assertAlmostEqual(self.ledger.total, record["cost_usd"], places=6)
        row = json.loads(self.ledger.path.read_text().splitlines()[0])
        self.assertEqual((row["label"], row["request_id"]), ("H4b", "req_fake"))

    def test_refusal_truncation_and_bad_json_are_recorded_and_paid_for(self):
        client = FakeClient([("refusal", None), ("max_tokens", None), ("end_turn", None)])
        records = [self.lr.review(client, "claude-haiku-5-5", "p", self.stories, self.ledger)
                   for _ in range(3)]
        self.assertEqual([r["verdict"] for r in records], ["REFUSED", "INCOMPLETE", "UNPARSED"])
        self.assertIn("general_harms", records[0]["summary"])
        rows = [json.loads(l) for l in self.ledger.path.read_text().splitlines()]
        self.assertEqual([r["estimated"] for r in rows], [False, False, True])
        # The unreadable reply is charged a worst case: full max_tokens of output.
        self.assertEqual(rows[2]["output_tokens"], reviewer_prompt.MAX_TOKENS)
        self.assertTrue(records[2]["cost_estimated"])

    def test_schema_rejects_an_unknown_rule(self):
        with self.assertRaises(Exception):
            self.verdict(findings=[{"rule": "H9", "severity": "fail", "quote": "q", "reason": "r"}])

    def test_run_live_writes_named_runs_that_the_harness_can_score(self):
        cases = harness.load_cases()
        script = [("end_turn", self.verdict(verdict="PASS", findings=[], what_would_change=[]))] * (2 * len(cases))
        client = FakeClient(script)
        out_dir = Path(self.tmp.name) / "out"
        err = io.StringIO()
        from contextlib import redirect_stderr
        with redirect_stderr(err):
            paths = harness.run_live(cases, "claude-haiku-5-5", None, 2, out_dir, client=client,
                                     ledger=self.ledger)
        self.assertEqual(len(paths), 2)
        self.assertRegex(paths[0].name, r"^reviewer-\d{4}-\d{2}-\d{2}-claude-haiku-5-5-run-1\.json$")
        run = json.loads(paths[0].read_text())
        self.assertEqual((run["model"], run["effort"]), ("claude-haiku-5-5", "medium"))
        scores = harness.score(cases, run)
        self.assertEqual(scores["clean_false_positives"], 0)
        self.assertEqual(len(client.calls), 2 * len(cases))
        self.assertEqual(len(self.ledger.path.read_text().splitlines()), 2 * len(cases))


class EvidenceAccuracy(unittest.TestCase):
    def test_quote_must_really_be_in_the_post(self):
        post = "# T\n\nWe’d   recommend fixing.\n\nSources:\n- https://x.example.invalid/a\n"
        self.assertTrue(harness.quote_in_post("We'd recommend fixing.", post))
        self.assertFalse(harness.quote_in_post("We recommend fixing", post))
        self.assertFalse(harness.quote_in_post("(no sources block)", post))
        self.assertTrue(harness.quote_in_post("(no sources block)", "# T\n\nNo sources here.\n"))
        self.assertFalse(harness.quote_in_post("", post))


if __name__ == "__main__":
    unittest.main()
