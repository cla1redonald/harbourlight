"""The approval gate is a shell script. These tests run it exactly as Claude Code would."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "require-approver.sh"


class ApprovalHook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name)
        self.env = {k: v for k, v in os.environ.items()
                    if k not in {"HARBOURLIGHT_APPROVER", "CLAUDE_PLUGIN_ROOT"}}
        self.env["CLAUDE_PROJECT_DIR"] = str(self.project)

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, tool: str, tool_input: dict, **env) -> subprocess.CompletedProcess:
        payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": tool,
                              "tool_input": tool_input})
        return subprocess.run(["bash", str(HOOK)], input=payload, capture_output=True, text=True,
                              env={**self.env, **env}, cwd=self.project)

    def write(self, rel: str, **env) -> subprocess.CompletedProcess:
        return self.run_hook("Write", {"file_path": str(self.project / rel), "content": "x"}, **env)

    def marker(self, text: str, age_seconds: int = 0) -> None:
        path = self.project / ".approver"
        path.write_text(text)
        if age_seconds:
            then = time.time() - age_seconds
            os.utime(path, (then, then))

    def assertBlocked(self, result):
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("approval hook", result.stderr)

    def assertAllowed(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)

    # Protected paths without an approver
    def test_blocks_references_write(self):
        self.assertBlocked(self.write("references/rules.json"))

    def test_blocks_skills_edit(self):
        result = self.run_hook("Edit", {"file_path": str(self.project / "skills/post-writer/SKILL.md"),
                                        "old_string": "a", "new_string": "b"})
        self.assertBlocked(result)

    def test_blocks_relative_path(self):
        self.assertBlocked(self.run_hook("Write", {"file_path": "references/watchlist.md"}))

    def test_blocks_plugin_root_path(self):
        plugin = self.project / "plugin"
        result = self.run_hook("Write", {"file_path": str(plugin / "skills/x/SKILL.md")},
                               CLAUDE_PLUGIN_ROOT=str(plugin))
        self.assertBlocked(result)

    # Unprotected paths
    def test_allows_data_write(self):
        self.assertAllowed(self.write("data/posts/2026-10-01-x.draft.md"))

    def test_allows_paths_outside_project(self):
        self.assertAllowed(self.run_hook("Write", {"file_path": "/elsewhere/references/notes.md"}))

    def test_allows_read_only_bash(self):
        self.assertAllowed(self.run_hook("Bash", {"command": "ls skills/ references/"}))

    # Approver by environment
    def test_env_approver_allows(self):
        self.assertAllowed(self.write("references/rules.json", HARBOURLIGHT_APPROVER="Morag Baird"))

    def test_blank_env_approver_blocks(self):
        self.assertBlocked(self.write("references/rules.json", HARBOURLIGHT_APPROVER="   "))

    # Approver by marker file
    def test_fresh_marker_allows(self):
        self.marker("approver: Morag Baird\ndate: 2026-10-01T09:00Z\n")
        self.assertAllowed(self.write("references/rules.json"))

    def test_marker_without_name_blocks(self):
        self.marker("approver:   \n")
        self.assertBlocked(self.write("references/rules.json"))

    def test_stale_marker_blocks(self):
        self.marker("approver: Morag Baird\n", age_seconds=2 * 60 * 60)
        self.assertBlocked(self.write("references/rules.json"))

    # The marker cannot be forged by Claude
    def test_writing_marker_always_blocked(self):
        self.assertBlocked(self.write(".approver", HARBOURLIGHT_APPROVER="Morag Baird"))

    def test_bash_touching_marker_blocked(self):
        result = self.run_hook("Bash", {"command": "echo \"approver: Claude\" > .approver"},
                               HARBOURLIGHT_APPROVER="Morag Baird")
        self.assertBlocked(result)

    def test_bash_make_approve_blocked(self):
        self.assertBlocked(self.run_hook("Bash", {"command": "make approve APPROVER=\"Claude\""}))

    # Shell writes to rule files
    def test_bash_sed_on_rules_blocked_without_approver(self):
        result = self.run_hook("Bash", {"command": "sed -i '' 's/1/2/' references/rules.json"})
        self.assertBlocked(result)

    def test_bash_sed_on_rules_allowed_with_approver(self):
        result = self.run_hook("Bash", {"command": "sed -i '' 's/1/2/' references/rules.json"},
                               HARBOURLIGHT_APPROVER="Morag Baird")
        self.assertAllowed(result)


if __name__ == "__main__":
    unittest.main()
