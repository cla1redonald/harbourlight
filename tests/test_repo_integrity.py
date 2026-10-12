"""The seed data, the labelled cases and the plugin layout hold together."""
from __future__ import annotations

import csv
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))
sys.path.insert(0, str(ROOT / "scripts"))

from append_audit import HEADER, validate  # noqa: E402
from check_post import ALL_RULES, HARD_RULES, check_text, count_words, split_post  # noqa: E402

DATA = ROOT / "data"
PRISTINE = ROOT / "data-pristine"
RULES = json.loads((ROOT / "references" / "rules.json").read_text())
STORY = re.compile(r"^## (S\d\d)\n((?:- .*\n)+)", re.MULTILINE)


def stories(path: Path = DATA / "incoming-stories.md") -> dict[str, dict]:
    found = {}
    for story_id, block in STORY.findall(path.read_text()):
        fields = dict(line[2:].split(": ", 1) for line in block.strip().splitlines())
        found[story_id] = fields
    return found


def frontmatter(text: str) -> dict:
    lines = text.split("---\n")[1].strip().splitlines()
    return dict(line.split(": ", 1) for line in lines)


class Corpus(unittest.TestCase):
    def test_size_dates_and_urls(self):
        found = stories()
        self.assertTrue(25 <= len(found) <= 30, len(found))
        for story_id, fields in found.items():
            self.assertTrue(fields["Date"].startswith("2026-09-"), story_id)
            self.assertTrue(fields["URL"].startswith("https://news.example.invalid/"), story_id)
            self.assertRegex(fields["Status"], r"^(new|used \(.+\)|rejected \(.+\))$")
        urls = [f["URL"] for f in found.values()]
        self.assertEqual(len(urls), len(set(urls)))

    def test_traps_are_complete_and_private(self):
        traps = json.loads((ROOT / "evals" / "traps.json").read_text())["traps"]
        kinds = {t["trap"] for t in traps}
        self.assertEqual(kinds, {"named_customer", "competitor_breach", "stat_bait", "bereavement",
                                 "arrears", "scam_warning", "thin_story", "injected_instruction",
                                 "duplicate", "out_of_scope"})
        found = stories()
        for trap in traps:
            self.assertIn(trap["story_id"], found)
            if "duplicate_of" in trap:
                self.assertIn(trap["duplicate_of"], found)
        text = (DATA / "incoming-stories.md").read_text().lower()
        for word in ["trap", "planted", "stat bait", "duplicate"]:
            self.assertNotIn(word, text)


class Logs(unittest.TestCase):
    def rows(self, path: Path = DATA / "audit-log.csv") -> list[dict]:
        with path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            self.assertEqual(reader.fieldnames, HEADER)
            return list(reader)

    def test_audit_rows_are_valid(self):
        rows = self.rows()
        self.assertGreaterEqual(len(rows), 3)
        verdicts = {r["verdict"] for r in rows[:3]}
        self.assertEqual(verdicts, {"PASS", "FLAG", "FAIL"})
        for row in rows:
            validate(row)
            self.assertTrue((ROOT / row["post_file"]).exists(), row["post_file"])
            self.assertLessEqual(int(row["voice_version"]), RULES["voice_version"])

    def test_logs_are_append_only_against_pristine(self):
        for name in ["audit-log.csv", "research-log.md", "voice-changelog.md"]:
            with self.subTest(name=name):
                current = (DATA / name).read_text()
                self.assertTrue(current.startswith((PRISTINE / name).read_text()),
                                f"{name} has had earlier content changed")

    def test_seeded_drafts_match_their_logged_verdicts(self):
        for row in self.rows(PRISTINE / "audit-log.csv"):
            draft = PRISTINE / Path(row["post_file"].replace(".final.md", ".draft.md")).relative_to("data")
            with self.subTest(draft=draft.name):
                self.assertEqual(check_text(draft.read_text()).verdict, row["verdict"])

    def test_voice_version_matches_changelog(self):
        changelog = (DATA / "voice-changelog.md").read_text()
        versions = [int(v) for v in re.findall(r"^## v(\d+) ", changelog, re.MULTILINE)]
        self.assertEqual(max(versions), RULES["voice_version"])


class ProductLines(unittest.TestCase):
    def test_claims_in_sync_across_three_files(self):
        claims_md = (ROOT / "references" / "approved-claims.md").read_text()
        checklist = (ROOT / "references" / "compliance-checklist.md").read_text()
        appendix = checklist.split("## Appendix: approved product lines", 1)[1]
        for product in RULES["products"]:
            with self.subTest(product=product["name"]):
                self.assertIn(product["claim"], claims_md)
                self.assertIn(product["claim"], appendix)
        self.assertEqual(appendix.count("\n- "), len(RULES["products"]))


class ReviewerCases(unittest.TestCase):
    def setUp(self):
        self.cases = [json.loads(p.read_text())
                      for p in sorted((ROOT / "evals" / "reviewer-cases").glob("*.json"))]

    def test_composition(self):
        self.assertEqual(len(self.cases), 24)
        categories = [c["category"] for c in self.cases]
        self.assertEqual(categories.count("clean"), 2)
        self.assertEqual(categories.count("borderline"), 2)
        for rule in HARD_RULES:
            n = sum(1 for c in self.cases if c["category"] == "hard" and c["target_rule"] == rule)
            self.assertGreaterEqual(n, 2, rule)

    def test_labels_are_well_formed(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                self.assertIn(case["expected_verdict"], {"PASS", "FLAG", "FAIL"})
                self.assertTrue(set(case["expected_rules"]) <= set(ALL_RULES))
                if case["expected_verdict"] == "PASS":
                    self.assertEqual(case["expected_rules"], [])
                phrase = case["evidence_phrase"]
                if phrase and phrase != "(no sources block)":
                    self.assertIn(phrase.lower(), case["post"].lower())

    def test_lengths_in_range_so_s4_never_muddies_a_label(self):
        for case in self.cases:
            body, _ = split_post(case["post"])
            self.assertTrue(120 <= count_words(body) <= 220, case["id"])


class PluginLayout(unittest.TestCase):
    def test_manifest(self):
        manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
        self.assertEqual(manifest["name"], "harbourlight-content")
        self.assertEqual(manifest["author"]["name"], "Claire Donald")
        self.assertEqual(manifest["license"], "MIT")

    def test_skills_have_matching_names(self):
        skills = sorted((ROOT / "skills").glob("*/SKILL.md"))
        self.assertEqual({p.parent.name for p in skills},
                         {"market-research", "post-writer", "compliance-reviewer",
                          "monthly-audit-report"})
        for path in skills:
            self.assertIn(f"name: {path.parent.name}\n", path.read_text())

    def test_agents_are_read_only(self):
        for path in (ROOT / "agents").glob("*.md"):
            with self.subTest(agent=path.name):
                tools = re.search(r"^tools: (.*)$", path.read_text(), re.MULTILINE).group(1)
                self.assertEqual({t.strip() for t in tools.split(",")}, {"Read", "Grep", "Glob"})

    def test_hook_wiring(self):
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())
        command = hooks["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        self.assertIn("require-approver.sh", command)
        self.assertTrue((ROOT / "hooks" / "require-approver.sh").exists())

    def test_no_em_dashes_anywhere(self):
        dash = "\u2014"
        for path in ROOT.rglob("*"):
            skip = {".git", "node_modules", "dist"}
            if skip & set(path.parts) or not path.is_file() or path.suffix not in {
                    ".md", ".py", ".json", ".csv", ".sh", ".yml", ".yaml", ".ts", ""}:
                continue
            with self.subTest(path=str(path.relative_to(ROOT))):
                self.assertNotIn(dash, path.read_text(errors="ignore"))


if __name__ == "__main__":
    unittest.main()
