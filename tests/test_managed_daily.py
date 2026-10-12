"""The Managed Agents definitions and the orchestrator, against a fake API client and a stub MCP server.

No network. YAML parsing needs pyyaml (requirements-live.txt); those tests skip without it.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
import io
from contextlib import contextmanager, redirect_stderr
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import managed_daily as md  # noqa: E402
from policy_bridge import POLICY_TOOLS, SERVER, PolicyBridge  # noqa: E402

HAVE_YAML = importlib.util.find_spec("yaml") is not None
STUB = [sys.executable, str(ROOT / "tests" / "fixtures" / "stub_mcp_server.py")]
POST = "# Rates hold\n\nBody text.\n\nSources:\n- https://news.example.invalid/forth-ledger/2026-09-02-base-rate-held\n"


@unittest.skipUnless(HAVE_YAML, "pyyaml not installed (pip install -r requirements-live.txt)")
class Definitions(unittest.TestCase):
    def setUp(self):
        self.d = md.load_definitions()

    def test_every_built_in_tool_is_disabled(self):
        toolset = [t for t in self.d["agent"]["tools"] if t["type"] == "agent_toolset_20260401"]
        self.assertEqual(len(toolset), 1)
        self.assertIs(toolset[0]["default_config"]["enabled"], False)
        names = {c["name"]: c["enabled"] for c in toolset[0]["configs"]}
        self.assertEqual(set(names), {"bash", "read", "write", "edit", "glob", "grep", "web_fetch", "web_search"})
        self.assertFalse(any(names.values()))
        self.assertNotIn("mcp_servers", self.d["agent"])

    def test_custom_tools_mirror_the_policy_server_plus_one_read_and_one_write(self):
        custom = {t["name"]: t for t in self.d["agent"]["tools"] if t["type"] == "custom"}
        self.assertEqual(set(custom), set(POLICY_TOOLS) | {"get_new_stories", "queue_for_approval"})
        for tool in custom.values():
            self.assertIs(tool["input_schema"]["additionalProperties"], False, tool["name"])
        self.assertEqual(set(md.WRITE_TOOLS), {"queue_for_approval"})

    def test_model_and_prompt(self):
        self.assertEqual(self.d["agent"]["model"]["id"], "claude-sonnet-5-5")
        self.assertIn("You never publish", self.d["agent"]["system"])
        self.assertIn("morning-after report", self.d["agent"]["system"])

    def test_networking_is_limited_to_an_explicit_list(self):
        net = self.d["environment"]["config"]["networking"]
        self.assertEqual(net["type"], "limited")
        self.assertEqual(net["allowed_hosts"], [])
        self.assertFalse(net["allow_package_managers"])
        self.assertFalse(net["allow_mcp_servers"])

    def test_schedule_and_budget(self):
        dep = self.d["deployment"]
        self.assertEqual(dep["schedule"], {"type": "cron", "expression": "0 7 * * 1-5",
                                           "timezone": "Europe/London"})
        self.assertEqual(dep["budget"], md.SESSION_BUDGET)
        self.assertEqual(md.SESSION_BUDGET["max_list_cost"], {"amount": "100", "currency": "USD"})
        self.assertEqual((dep["agent"], dep["environment_id"]), ("./agent.md", "./environment.yaml"))
        self.assertEqual(dep["initial_events"][0]["type"], "user.message")


class Bridge(unittest.TestCase):
    def test_round_trip_against_a_stub_server(self):
        with PolicyBridge(STUB) as policy:
            self.assertEqual(policy.list_tools(), ["check_post", "get_checklist"])
            self.assertEqual(policy.call("check_post", {"text": "guaranteed"}), {"ok": True, "data": {"verdict": "FAIL"}})
            self.assertFalse(policy.call("get_checklist", {})["ok"])
            self.assertEqual(policy.call("write_rules", {})["ok"], False)

    @unittest.skipUnless(SERVER.exists() and shutil.which("node"), "policy server not built")
    def test_round_trip_against_the_real_server(self):
        with PolicyBridge() as policy:
            self.assertEqual(sorted(policy.list_tools()), sorted(POLICY_TOOLS))
            out = policy.call("check_post", {"text": POST})
            self.assertTrue(out["ok"])
            self.assertIn(out["data"]["verdict"], {"PASS", "FLAG", "FAIL"})


class FakeEvents:
    """Plays a scripted session: the agent calls tools, waits for results, then reports."""

    def __init__(self, script):
        self.script, self.sent, self.stream_opened_before_send = script, [], None

    @contextmanager
    def stream(self, session_id):
        if self.stream_opened_before_send is None:
            self.stream_opened_before_send = not self.sent
        yield iter(self.script)

    def send(self, session_id, events):
        self.sent.extend(events)

    def list(self, session_id):
        return [SimpleNamespace(type=e.type, id=getattr(e, "id", None)) for e in self.script]


def tool_use(event_id, name, arguments):
    return SimpleNamespace(type="agent.custom_tool_use", id=event_id, name=name, input=arguments)


class Orchestrator(unittest.TestCase):
    def script(self):
        return [
            tool_use("sevt_1", "get_new_stories", {"story_id": "S02"}),
            tool_use("sevt_2", "check_post", {"text": POST}),
            tool_use("sevt_3", "queue_for_approval", {"story_id": "S02", "headline": "Rates hold",
                                                      "post": POST, "checker_verdict": "PASS"}),
            tool_use("sevt_4", "delete_everything", {}),
            SimpleNamespace(type="agent.tool_use", id="sevt_5", evaluated_permission="ask"),
            SimpleNamespace(type="session.status_idle", stop_reason=SimpleNamespace(type="requires_action")),
            SimpleNamespace(type="agent.message", content=[SimpleNamespace(type="text", text="Report.")]),
            SimpleNamespace(type="session.status_idle", stop_reason=SimpleNamespace(type="end_turn")),
        ]

    def run_with(self, decision, approver, sha=md.post_hash(POST)[:12], script=None):
        events = FakeEvents(script or self.script())
        client = SimpleNamespace(beta=SimpleNamespace(sessions=SimpleNamespace(events=events)))
        approvals = []
        with PolicyBridge(STUB) as policy, redirect_stderr(io.StringIO()):
            dispatch = md.make_dispatch(policy, md.cli_approver(decision, approver, sha), approvals)
            kickoff = [{"type": "user.message", "content": [{"type": "text", "text": "go"}]}]
            outcome = md.drive(client, "sesn_1", dispatch, kickoff)
        return events, approvals, outcome

    def test_tools_answered_write_confirmed_unknown_denied(self):
        events, approvals, outcome = self.run_with("approve", "Euan Lennie")
        self.assertTrue(events.stream_opened_before_send)
        self.assertEqual((outcome["stop"], outcome["tool_calls"]), ("end_turn", 4))
        results = {e["custom_tool_use_id"]: e for e in events.sent if e["type"] == "user.custom_tool_result"}
        self.assertIn("S02", results["sevt_1"]["content"][0]["text"])
        self.assertEqual(json.loads(results["sevt_2"]["content"][0]["text"]), {"verdict": "PASS"})
        self.assertIn("Euan Lennie", results["sevt_3"]["content"][0]["text"])
        self.assertNotIn("is_error", results["sevt_3"])
        self.assertTrue(results["sevt_4"]["is_error"])
        confirmations = [e for e in events.sent if e["type"] == "user.tool_confirmation"]
        self.assertEqual([c["result"] for c in confirmations], ["deny"])
        self.assertEqual(approvals[0]["decision"], "approve")
        self.assertLessEqual(approvals[0]["paused_at"], approvals[0]["answered_at"])

    def test_decline_unnamed_and_unhashed_approval_do_not_queue(self):
        cases = (("decline", "Euan Lennie", md.post_hash(POST)[:12]), ("approve", "", md.post_hash(POST)[:12]),
                 ("approve", "Euan Lennie", None), ("approve", "Euan Lennie", "0" * 12),
                 ("approve", "Euan Lennie", md.post_hash(POST)[:6]))
        for decision, approver, sha in cases:
            events, approvals, _ = self.run_with(decision, approver, sha)
            result = next(e for e in events.sent if e.get("custom_tool_use_id") == "sevt_3")
            self.assertTrue(result["is_error"])
            self.assertEqual(approvals[0]["decision"], "decline")

    def test_get_new_stories_only_returns_new_ones(self):
        out = md.new_stories()
        self.assertTrue(out["count"] > 0)
        self.assertNotIn("S01", [s["id"] for s in out["stories"]])  # S01 is used
        self.assertEqual([s["id"] for s in md.new_stories("S01")["stories"]], ["S01"])

    def test_session_carries_the_budget_and_pins_the_agent_version(self):
        captured = {}
        client = SimpleNamespace(beta=SimpleNamespace(sessions=SimpleNamespace(
            create=lambda **kw: captured.update(kw) or SimpleNamespace(id="sesn_1"))))
        md.start_session(client, {"agent_id": "agent_1", "agent_version": 3, "environment_id": "env_1"}, "S02")
        self.assertEqual(captured["budget"], {"type": "limit", "max_list_cost": {"amount": "100", "currency": "USD"}})
        self.assertEqual(captured["agent"], {"type": "agent", "id": "agent_1", "version": 3})


def queue_call(event_id, post=POST, claimed="PASS", headline="Rates hold"):
    return tool_use(event_id, "queue_for_approval", {"story_id": "S02", "headline": headline,
                                                      "post": post, "checker_verdict": claimed})


END = SimpleNamespace(type="session.status_idle", stop_reason=SimpleNamespace(type="end_turn"))
BAD_POST = "# Fix now\n\nThis is guaranteed to save you money.\n"


class QueueGuards(unittest.TestCase):
    """Review finding 1: the orchestrator's own checker decides, and an approval is bound to one post."""

    def drive(self, script, approver):
        events = FakeEvents(script)
        client = SimpleNamespace(beta=SimpleNamespace(sessions=SimpleNamespace(events=events)))
        approvals = []
        with PolicyBridge(STUB) as policy, redirect_stderr(io.StringIO()):
            md.drive(client, "sesn_1", md.make_dispatch(policy, approver, approvals))
        results = {e["custom_tool_use_id"]: e for e in events.sent if e["type"] == "user.custom_tool_result"}
        return results, approvals

    def test_a_fail_is_refused_whatever_the_agent_claims_and_nobody_is_asked(self):
        asked = []
        results, approvals = self.drive([queue_call("q1", post=BAD_POST, claimed="PASS"), END],
                                        lambda *a: asked.append(a) or ("approve", "Euan Lennie", "x"))
        self.assertEqual(asked, [])
        self.assertTrue(results["q1"]["is_error"])
        self.assertIn("A FAIL cannot be queued", results["q1"]["content"][0]["text"])
        self.assertEqual((approvals[0]["decision"], approvals[0]["checker_verdict"],
                          approvals[0]["agent_claimed_verdict"]), ("refused", "FAIL", "PASS"))

    def test_the_recorded_verdict_is_the_orchestrators_not_the_agents(self):
        sha = md.post_hash(POST)[:12]
        results, approvals = self.drive([queue_call("q1", claimed="FAIL"), END],
                                        md.cli_approver("approve", "Euan Lennie", sha))
        self.assertEqual(approvals[0]["checker_verdict"], "PASS")
        self.assertEqual(approvals[0]["agent_claimed_verdict"], "FAIL")
        self.assertEqual(approvals[0]["post_sha256"], md.post_hash(POST))
        self.assertNotIn("is_error", results["q1"])

    def test_a_preset_approval_covers_one_queue_call_only(self):
        sha = md.post_hash(POST)[:12]
        results, approvals = self.drive([queue_call("q1"), queue_call("q2"), END],
                                        md.cli_approver("approve", "Euan Lennie", sha))
        self.assertEqual([a["decision"] for a in approvals], ["approve", "decline"])
        self.assertTrue(results["q2"]["is_error"])

    def test_the_approver_sees_the_orchestrators_check_and_the_hash(self):
        out = io.StringIO()
        approve = md.cli_approver("approve", "Euan Lennie", md.post_hash(POST)[:12], out=out)
        approve({"story_id": "S02", "headline": "Rates hold", "post": POST, "checker_verdict": "FAIL"},
                {"verdict": "PASS", "findings": []}, md.post_hash(POST))
        shown = out.getvalue()
        self.assertIn("Checker verdict (run by the orchestrator, not the agent's claim): PASS", shown)
        self.assertIn("(the agent claimed FAIL)", shown)
        self.assertIn(md.post_hash(POST), shown)

    def test_answer_file_pauses_until_a_matching_answer_arrives(self):
        import threading
        for given, expected in ((md.post_hash(POST)[:12], "approve"), ("f" * 12, "decline")):
            with self.subTest(given=given), tempfile.TemporaryDirectory() as tmp:
                answer = Path(tmp) / "answer.json"
                pending = Path(tmp) / "answer.json.pending.json"

                def respond():
                    for _ in range(100):
                        if pending.exists():
                            shown = json.loads(pending.read_text())
                            self.assertEqual(shown["post_sha256"], md.post_hash(POST))
                            answer.write_text(json.dumps({"decision": "approve", "approver": "Euan Lennie",
                                                          "post_sha256": given}))
                            return
                        __import__("time").sleep(0.05)

                thread = threading.Thread(target=respond)
                thread.start()
                approve = md.cli_approver(None, None, answer_file=answer, wait_seconds=10, out=io.StringIO())
                decision, name, _ = approve({"story_id": "S02", "post": POST}, {"verdict": "PASS"},
                                            md.post_hash(POST))
                thread.join()
                self.assertEqual((decision, name), (expected, "Euan Lennie"))
                self.assertFalse(pending.exists())

    def test_reconnect_answers_an_unanswered_call_once(self):
        call = queue_call("q1")

        class Dropping(FakeEvents):
            def __init__(self):
                super().__init__([])
                self.opens = 0

            @contextmanager
            def stream(self, session_id):
                self.opens += 1
                if self.opens == 1:
                    raise ConnectionError("dropped")
                yield iter([END])

            def list(self, session_id):
                return [call, SimpleNamespace(type="session.status_idle",
                                              stop_reason=SimpleNamespace(type="requires_action"))]

        events = Dropping()
        client = SimpleNamespace(beta=SimpleNamespace(sessions=SimpleNamespace(events=events)))
        approvals = []
        with PolicyBridge(STUB) as policy, redirect_stderr(io.StringIO()):
            outcome = md.drive(client, "sesn_1", md.make_dispatch(
                policy, md.cli_approver("approve", "Euan Lennie", md.post_hash(POST)[:12]), approvals))
        self.assertEqual(outcome["stop"], "end_turn")
        self.assertEqual(outcome["reconnects"], 1)
        self.assertEqual(len([e for e in events.sent if e["type"] == "user.custom_tool_result"]), 1)


class SafeDisplay(unittest.TestCase):
    """Review finding 2: agent-supplied text cannot drive the terminal or break the report table."""

    def test_control_characters_and_escape_sequences_become_visible_text(self):
        nasty = "ok\x1b[2J\x1b]0;owned\x07\x9b31m\x00\x08\x7fline\n\tend"
        safe = md.safe_text(nasty)
        for raw in ("\x1b", "\x07", "\x9b", "\x00", "\x08", "\x7f"):
            self.assertNotIn(raw, safe)
        self.assertIn("\\x1b[2J", safe)
        self.assertIn("\\x9b", safe)
        self.assertIn("line\n\tend", safe, "newline and tab are kept")

    def test_markdown_cells_escape_pipes_and_newlines(self):
        self.assertEqual(md.md_cell("a | b\nc\r\nd"), "a \\| b c d")
        self.assertEqual(md.md_cell(None), "")
        self.assertEqual(md.md_cell("x\\|y"), "x\\\\\\|y")  # a backslash cannot un-escape the pipe

    def test_report_table_survives_a_hostile_headline(self):
        run = {"session_id": "s", "exported": "t", "outcome": {"stop": "end_turn"}, "session": {},
               "approvals": [{"story_id": "S02", "headline": "Evil | col\n| injected | row \x1b[31m",
                              "checker_verdict": "PASS", "decision": "approve", "approver": "Euan Lennie",
                              "post_sha256": "ab" * 32}],
               "events": [{"type": "agent.message", "content": [{"type": "text", "text": "bye\x1b[2J"}]}]}
        text = md.morning_report(run)
        row = next(l for l in text.splitlines() if l.startswith("| S02"))
        import re
        cells = re.split(r"(?<!\\)(?:\\\\)*\|", row.replace("\\\\", ""))
        self.assertEqual(len(cells), 8, row)  # six cells between seven unescaped pipes
        self.assertNotIn("\x1b", text)
        self.assertIn("abababababab", row)

    def test_approval_screen_is_sanitised(self):
        out = io.StringIO()
        approve = md.cli_approver(None, None, out=out)
        approve({"story_id": "S02\x1b[2J", "headline": "\x9bhi", "post": "body\x07"}, {"verdict": "PASS"}, "0" * 64)
        self.assertNotIn("\x1b", out.getvalue())
        self.assertNotIn("\x9b", out.getvalue())
        self.assertNotIn("\x07", out.getvalue())

    def test_setup_creates_once(self):
        calls = []
        client = SimpleNamespace(beta=SimpleNamespace(
            environments=SimpleNamespace(create=lambda **kw: calls.append("env") or SimpleNamespace(id="env_1")),
            agents=SimpleNamespace(create=lambda **kw: calls.append("agent") or SimpleNamespace(id="agent_1", version=1))))
        with tempfile.TemporaryDirectory() as tmp:
            ids_path = Path(tmp) / "ids.json"
            defs = {"environment": {"name": "e"}, "agent": {"name": "a"}}
            md.setup(client, defs, ids_path)
            md.setup(client, defs, ids_path)
        self.assertEqual(calls, ["env", "agent"])

    def test_morning_report_lists_drafted_and_queued(self):
        run = {"session_id": "sesn_1", "exported": "2026-10-12T07:05:00Z", "outcome": {"stop": "end_turn"},
               "session": {"usage": {"list_cost": {"amount": "23", "currency": "USD"}}},
               "approvals": [{"story_id": "S02", "headline": "Rates hold", "checker_verdict": "PASS",
                              "decision": "approve", "approver": "Euan Lennie"}],
               "events": [{"type": "agent.custom_tool_use", "id": "sevt_2", "name": "check_post"},
                          {"type": "user.custom_tool_result", "custom_tool_use_id": "sevt_2",
                           "content": [{"type": "text", "text": "{\"verdict\": \"PASS\"}"}]},
                          {"type": "agent.message", "content": [{"type": "text", "text": "All done."}]}]}
        text = md.morning_report(run)
        self.assertIn("Drafts checked by the deterministic checker: 1 (PASS)", text)
        self.assertIn("| S02 | Rates hold | PASS | approve | Euan Lennie |  |", text)
        self.assertIn("0.23 USD against a 1.00 USD session budget", text)
        self.assertIn("Nothing was published", text)
        self.assertIn("All done.", text)

    def test_session_list_cost_goes_into_the_ledger(self):
        sys.path.insert(0, str(ROOT / "evals"))
        from ledger import Ledger
        data = {"session": {"agent": {"model": {"id": "claude-sonnet-5-5"}},
                            "usage": {"list_cost": {"amount": "5", "currency": "USD"}, "input_tokens": 10,
                                      "output_tokens": 2328, "cache_read_input_tokens": 15579,
                                      "cache_creation": {"ephemeral_5m_input_tokens": 7993,
                                                         "ephemeral_1h_input_tokens": 0}}}}
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Ledger(Path(tmp) / "spend.jsonl")
            self.assertEqual(md.record_session_cost(data, "sesn_1", ledger), 0.05)
            row = json.loads(ledger.path.read_text())
        self.assertEqual((row["model"], row["cache_creation_input_tokens"], row["label"]),
                         ("claude-sonnet-5-5", 7993, "managed-session"))

    def test_no_key_means_no_request(self):
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            with redirect_stderr(io.StringIO()):
                self.assertEqual(md.main(["run", "--story", "S02"]), 2)


if __name__ == "__main__":
    unittest.main()
