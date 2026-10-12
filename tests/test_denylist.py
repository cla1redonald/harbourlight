"""The deny-list script reads its terms from outside the repo and refuses to run without them.

Every term used here is made up.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "denylist.sh"


class DenyList(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "notes.md").write_text("A plain note about Harbourlight.\n")
        self.env = {k: v for k, v in os.environ.items() if k != "DENY_LIST"}

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, deny_list: str | None = None) -> subprocess.CompletedProcess:
        env = dict(self.env)
        if deny_list is not None:
            env["DENY_LIST"] = deny_list
        return subprocess.run(["bash", str(SCRIPT), str(self.root)], capture_output=True,
                              text=True, env=env)

    def test_passes_when_no_term_appears(self):
        result = self.run_script("zorbleflux\nquimbly trust")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("2 terms", result.stdout)

    def test_fails_on_a_term_case_insensitively(self):
        (self.root / "bad.md").write_text("We once worked with ZorbleFlux.\n")
        result = self.run_script("zorbleflux\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("bad.md", result.stdout)

    def test_fails_on_a_multi_word_term(self):
        (self.root / "bad.md").write_text("The Quimbly Trust scheme.\n")
        self.assertEqual(self.run_script("quimbly trust").returncode, 1)

    def test_always_screens_for_em_dashes(self):
        (self.root / "bad.md").write_text("one \u2014 two\n")
        self.assertEqual(self.run_script("zorbleflux").returncode, 1)

    def test_skips_installed_dependencies_and_build_output(self):
        for folder in ("node_modules/pkg", "dist"):
            (self.root / folder).mkdir(parents=True)
            (self.root / folder / "vendor.js").write_text("zorbleflux \u2014 vendored\n")
        self.assertEqual(self.run_script("zorbleflux").returncode, 0)

    def test_a_term_inside_an_opaque_api_id_is_not_a_match_but_prose_is(self):
        (self.root / "log.json").write_text('{"id": "sevt_01QzorbXyz9AbCdEfGh"}\n')
        self.assertEqual(self.run_script("zorb").returncode, 0)
        (self.root / "notes2.md").write_text("We met zorb last week, id sevt_01QzorbXyz9AbCdEfGh.\n")
        self.assertEqual(self.run_script("zorb").returncode, 1)

    def test_falls_back_to_local_file_and_does_not_flag_it(self):
        (self.root / ".denylist").write_text("zorbleflux\n")
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(".denylist file", result.stdout)
        (self.root / "bad.md").write_text("zorbleflux\n")
        self.assertEqual(self.run_script().returncode, 1)

    def test_environment_wins_over_file(self):
        (self.root / ".denylist").write_text("plain\n")
        self.assertEqual(self.run_script("zorbleflux").returncode, 0)

    def test_missing_list_is_an_error(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 2)
        self.assertIn("no list", result.stderr)

    def test_blank_list_is_an_error(self):
        (self.root / ".denylist").write_text("\n  \n\r\n")
        result = self.run_script()
        self.assertEqual(result.returncode, 2)
        self.assertIn("empty", result.stderr)

    def test_script_holds_no_terms(self):
        text = SCRIPT.read_text()
        self.assertNotIn("<<'TERMS'", text)
        self.assertLess(len(text.splitlines()), 60)


if __name__ == "__main__":
    unittest.main()
