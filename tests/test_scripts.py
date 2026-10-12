"""Audit appends, story marking, the monthly report and the demo reset."""
from __future__ import annotations

import io
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import append_audit  # noqa: E402
import mark_story  # noqa: E402
import monthly_report  # noqa: E402
import reset_data  # noqa: E402

PRISTINE = ROOT / "data-pristine"


def good_row(**overrides: str) -> dict:
    row = {
        "date": "2026-10-01", "run_trigger": "manual",
        "story_headline": "Thousands of fixed-rate deals end this autumn",
        "source_url": "https://news.example.invalid/lothian-property-weekly/2026-09-04-fixed-deals-ending",
        "verdict": "PASS", "verdict_reasons": "none", "voice_version": "1",
        "human_decision": "approved (Euan Lennie)", "edit_summary": "none", "posted": "yes",
        "post_file": "data/posts/2026-10-01-fixed-deals.final.md",
    }
    row.update(overrides)
    return row


class Workspace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shutil.copytree(PRISTINE, self.root / "data")
        self.log = self.root / "data" / "audit-log.csv"
        self.corpus = self.root / "data" / "incoming-stories.md"

    def tearDown(self):
        self.tmp.cleanup()


class AppendAudit(Workspace):
    def test_appends_without_touching_earlier_rows(self):
        before = self.log.read_text()
        append_audit.append(good_row(), self.log)
        after = self.log.read_text()
        self.assertTrue(after.startswith(before))
        self.assertEqual(len(after.splitlines()), len(before.splitlines()) + 1)

    def test_refuses_approving_a_fail(self):
        with self.assertRaises(append_audit.AuditError):
            append_audit.append(good_row(verdict="FAIL"), self.log)

    def test_refuses_posting_a_rejection(self):
        with self.assertRaises(append_audit.AuditError):
            append_audit.append(good_row(human_decision="rejected (Isla Drummond)"), self.log)

    def test_refuses_decision_without_a_name(self):
        for decision in ["approved", "approved ()", "yes"]:
            with self.subTest(decision=decision), self.assertRaises(append_audit.AuditError):
                append_audit.append(good_row(human_decision=decision), self.log)

    def test_refuses_edit_without_summary(self):
        with self.assertRaises(append_audit.AuditError):
            append_audit.append(good_row(human_decision="approved with edit (Euan Lennie)"), self.log)

    def test_refuses_a_log_with_the_wrong_header(self):
        self.log.write_text("date,verdict\n")
        with self.assertRaises(append_audit.AuditError):
            append_audit.append(good_row(), self.log)

    def test_cli_reports_refusal(self):
        with redirect_stderr(io.StringIO()):
            code = append_audit.main([
                "--log", str(self.log), "--run-trigger", "manual", "--story-headline", "x",
                "--source-url", "https://news.example.invalid/x", "--verdict", "FAIL",
                "--verdict-reasons", "H5", "--human-decision", "approved (Euan Lennie)",
                "--edit-summary", "none", "--posted", "yes", "--post-file", "x.md"])
        self.assertEqual(code, 1)


class MarkStory(Workspace):
    def test_marks_only_that_story(self):
        before = self.corpus.read_text()
        mark_story.mark("S02", "used", "2026-10-01", corpus=self.corpus)
        after = self.corpus.read_text()
        self.assertIn("- Status: used (2026-10-01)", after)
        changed = [(a, b) for a, b in zip(before.splitlines(), after.splitlines()) if a != b]
        self.assertEqual(changed, [("- Status: new", "- Status: used (2026-10-01)")])

    def test_rejection_records_rule(self):
        status = mark_story.mark("S04", "rejected", "2026-10-01", "H3", corpus=self.corpus)
        self.assertEqual(status, "rejected (2026-10-01, H3)")

    def test_cannot_reuse_a_used_story(self):
        with self.assertRaises(ValueError):
            mark_story.mark("S01", "used", "2026-10-01", corpus=self.corpus)

    def test_unknown_story(self):
        with self.assertRaises(ValueError):
            mark_story.mark("S99", "used", "2026-10-01", corpus=self.corpus)


class MonthlyReport(Workspace):
    def test_september_numbers(self):
        text = monthly_report.report(monthly_report.load_rows(self.log, "2026-09"), "2026-09")
        for expected in ["| Drafts reviewed | 3 |", "| Reviewer PASS | 1 |", "| Reviewer FLAG | 1 |",
                         "| Reviewer FAIL | 1 |", "| Rejected | 1 |", "| Posted | 2 |",
                         "| FAIL verdicts that were posted anyway | 0 |", "- H5: 1 decision",
                         "- H7: 1 decision", "- S1: 1 decision"]:
            self.assertIn(expected, text)

    def test_empty_month(self):
        text = monthly_report.report(monthly_report.load_rows(self.log, "2027-01"), "2027-01")
        self.assertIn("| Drafts reviewed | 0 |", text)


class Reset(Workspace):
    def test_reset_restores_pristine(self):
        shutil.copytree(PRISTINE, self.root / "data-pristine")
        (self.root / "data" / "posts" / "extra.md").write_text("x")
        self.log.write_text("broken")
        reset_data.reset(self.root)
        self.assertFalse((self.root / "data" / "posts" / "extra.md").exists())
        self.assertEqual(self.log.read_text(), (PRISTINE / "audit-log.csv").read_text())

    def test_reset_without_pristine_fails(self):
        with self.assertRaises(FileNotFoundError):
            reset_data.reset(self.root)


if __name__ == "__main__":
    unittest.main()
