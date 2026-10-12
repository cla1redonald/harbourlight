"""The blind export hides the labels, and kappa is computed correctly."""
from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))
sys.path.insert(0, str(ROOT / "evals" / "labels"))

import agreement  # noqa: E402
from run_reviewer_eval import load_cases  # noqa: E402


class Kappa(unittest.TestCase):
    def test_textbook_value(self):
        # 2x2: 20 yes-yes, 5 yes-no, 10 no-yes, 15 no-no -> po 0.7, pe 0.5, kappa 0.4
        a = ["y"] * 25 + ["n"] * 25
        b = ["y"] * 20 + ["n"] * 5 + ["y"] * 10 + ["n"] * 15
        self.assertAlmostEqual(agreement.cohen_kappa(a, b), 0.4)

    def test_perfect_and_degenerate(self):
        self.assertEqual(agreement.cohen_kappa(["PASS", "FAIL"], ["PASS", "FAIL"]), 1.0)
        self.assertEqual(agreement.cohen_kappa(["FAIL", "FAIL"], ["FAIL", "FAIL"]), 1.0)
        with self.assertRaises(ValueError):
            agreement.cohen_kappa([], [])


class BlindExport(unittest.TestCase):
    def test_export_hides_case_ids_and_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            key = agreement.export(out)
            self.assertEqual(len(key), 24)
            self.assertEqual(sorted(key.values()), sorted(c["id"] for c in load_cases()))
            for neutral in key:
                text = (out / f"{neutral}.md").read_text()
                for leak in ["expected_verdict", "evidence_phrase", "notes", key[neutral]]:
                    self.assertNotIn(leak, text, f"{neutral} leaks {leak}")

    def test_scoring_a_sheet_that_copies_the_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            sheet = Path(tmp) / "sheet.csv"
            with sheet.open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["post", "verdict", "rules", "quote", "notes"])
                for case in load_cases():
                    verdict = "FLAG" if case["id"] == "C01" else case["expected_verdict"]
                    writer.writerow([case["id"], verdict, " ".join(case["expected_rules"]), "", ""])
            result = agreement.score(agreement.read_sheet(sheet, {}))
        self.assertEqual(result["verdict_agreement"], 23)
        self.assertEqual([d["id"] for d in result["disagreements"]], ["C01"])
        self.assertLess(result["verdict_kappa"], 1.0)
        self.assertEqual(result["rule_kappa"]["H4"], 1.0)

    def test_template_says_pending_and_forbids_a_model_labeller(self):
        text = (ROOT / "evals" / "labels" / "second-labeller-template.md").read_text()
        self.assertIn("**pending**", text)
        self.assertIn("A model is not used as a second labeller", text)


if __name__ == "__main__":
    unittest.main()
