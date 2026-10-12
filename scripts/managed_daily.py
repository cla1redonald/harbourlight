#!/usr/bin/env python3
"""Orchestrator for the harbourlight-daily Managed Agents deployment.

The agent, environment and schedule are defined as files in agents/harbourlight-daily/.
This script is the data plane: it creates them once, starts or attaches to a
session, answers the agent's custom tool calls (policy tools are forwarded to the
policy MCP server; the one write is confirm-first), exports the event log and
writes the morning-after report.

    python3 scripts/managed_daily.py setup                     # create environment and agent once
    python3 scripts/managed_daily.py run --story S02 --approver "Name" --decision approve
    python3 scripts/managed_daily.py attach --session-id sesn_... --approver "Name"
    python3 scripts/managed_daily.py report evals/results/managed-run-2026-10-12.json

Needs ANTHROPIC_API_KEY, the packages in requirements-live.txt, and a built policy
server (`make policy-server`). Exit codes: 0 done, 2 not possible (key, build), 4 the
API refused (the response is recorded).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from policy_bridge import POLICY_TOOLS  # noqa: E402

AGENT_DIR = ROOT / "agents" / "harbourlight-daily"
IDS = AGENT_DIR / "ids.json"
RESULTS = ROOT / "evals" / "results"
CORPUS = ROOT / "data" / "incoming-stories.md"
SESSION_BUDGET = {"type": "limit", "max_list_cost": {"amount": "100", "currency": "USD"}}  # $1.00
WRITE_TOOLS = ("queue_for_approval",)
READ_TOOLS = POLICY_TOOLS + ("get_new_stories",)


# ---------- definitions ----------

def load_yaml(path: Path) -> dict:
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_agent(path: Path = AGENT_DIR / "agent.md") -> dict:
    """agent.md: YAML front matter is the agent config, the Markdown body is the system prompt."""
    import yaml
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not match:
        raise ValueError(f"{path} has no front matter")
    config = yaml.safe_load(match.group(1))
    config["system"] = match.group(2).strip()
    return config


def load_definitions() -> dict:
    return {
        "agent": load_agent(),
        "environment": load_yaml(AGENT_DIR / "environment.yaml"),
        "deployment": load_yaml(AGENT_DIR / "deployment-daily.yaml"),
    }


# ---------- tools the orchestrator answers ----------

def new_stories(story_id: str | None = None, corpus: Path = CORPUS) -> dict:
    text = corpus.read_text(encoding="utf-8")
    stories = []
    for block in re.split(r"\n---\n", text):
        block = block.strip()
        head = re.match(r"^## (S\d\d)\n", block)
        if not head:
            continue
        sid = head.group(1)
        status = re.search(r"^- Status: (.*)$", block, re.MULTILINE)
        if story_id and sid != story_id:
            continue
        if not story_id and (not status or status.group(1) != "new"):
            continue
        stories.append({"id": sid, "text": block})
    return {"stories": stories, "count": len(stories)}


# ---------- safe display ----------

# ESC-introduced sequences (CSI, OSC, and two-character escapes) first, so a whole
# sequence shows as text; then any other C0 or C1 control character, and DEL.
_ESCAPE_SEQUENCE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)?|[@-Z\\-_])")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def _repr_inner(text: str) -> str:
    return repr(text)[1:-1]


def safe_text(value: Any) -> str:
    """Make agent-supplied text safe to print: control characters and escape sequences become
    their repr (for example \x1b[2J), so they are visible and inert. Newline and tab are kept."""
    text = "" if value is None else str(value)
    text = _ESCAPE_SEQUENCE.sub(lambda m: _repr_inner(m.group(0)), text)
    return _CONTROL.sub(lambda m: _repr_inner(m.group(0)), text)


def md_cell(value: Any) -> str:
    """One Markdown table cell: safe text, no newlines, pipes escaped."""
    raw = "" if value is None else str(value)
    text = safe_text(raw.replace("\r\n", " ").replace("\n", " ").replace("\r", " "))
    # Escape backslashes first, so text ending in a backslash cannot un-escape the pipe after it.
    return text.replace("\\", "\\\\").replace("|", "\\|").strip()


def post_hash(post: str) -> str:
    return hashlib.sha256(post.encode("utf-8")).hexdigest()


HASH_PREFIX = 12  # characters of the SHA-256 an approver must give back


# ---------- confirm-first approval ----------

Approver = Callable[[dict, dict, str], tuple[str, str, str]]


def make_dispatch(policy: Any, approve: Approver, log: list[dict]) -> Callable[[str, dict], dict]:
    """Return a function that answers one custom tool call. Deny by default."""

    def dispatch(name: str, arguments: dict) -> dict:
        if name in POLICY_TOOLS:
            return policy.call(name, arguments)
        if name == "get_new_stories":
            return {"ok": True, "data": new_stories(arguments.get("story_id"))}
        if name == "queue_for_approval":
            return queue(arguments)
        return {"ok": False, "data": f"{name} is not an available tool"}

    def queue(arguments: dict) -> dict:
        post = str(arguments.get("post") or "")
        digest = post_hash(post)
        # Never trust the agent's own account of the checker: run it here.
        check = policy.call("check_post", {"text": post}) if post else {"ok": False, "data": "empty post"}
        verdict = check["data"].get("verdict") if check.get("ok") and isinstance(check.get("data"), dict) else None
        entry = {"tool": "queue_for_approval", "paused_at": _now(), "story_id": arguments.get("story_id"),
                 "headline": arguments.get("headline"), "post": post, "post_sha256": digest,
                 "checker_verdict": verdict, "checker_findings": (check.get("data") or {}).get("findings")
                 if isinstance(check.get("data"), dict) else None,
                 "agent_claimed_verdict": arguments.get("checker_verdict")}
        if verdict not in ("PASS", "FLAG"):
            entry.update({"answered_at": _now(), "decision": "refused", "approver": "",
                          "reason": f"orchestrator's check_post returned {verdict or 'no verdict'}; "
                                    "a FAIL is never queued"})
            log.append(entry)
            return {"ok": False, "data": f"Not queued: the orchestrator's own check_post returned "
                                         f"{verdict or 'no verdict'}. A FAIL cannot be queued."}
        decision, approver, reason = approve(arguments, check["data"], digest)
        entry.update({"answered_at": _now(), "decision": decision, "approver": approver, "reason": reason})
        log.append(entry)
        if decision == "approve":
            return {"ok": True, "data": {"queued": True, "confirmed_by": approver, "post_sha256": digest,
                                         "checker_verdict": verdict,
                                         "note": "Queued for the independent review and a named "
                                                 "approver's decision. Nothing is published."}}
        return {"ok": False, "data": f"Not queued: {approver or 'nobody'} declined. {reason}".strip()}

    return dispatch


def show_for_approval(arguments: dict, check: dict, digest: str) -> str:
    findings = check.get("findings") or []
    lines = ["", "=== CONFIRM BEFORE QUEUEING ===",
             f"Story {safe_text(arguments.get('story_id'))}: {safe_text(arguments.get('headline'))}",
             f"Checker verdict (run by the orchestrator, not the agent's claim): {check.get('verdict')}"]
    for f in findings:
        lines.append(f"  {safe_text(f.get('rule'))} {safe_text(f.get('severity'))}: "
                     f"\"{safe_text(f.get('quote'))}\" {safe_text(f.get('why'))}")
    if arguments.get("checker_verdict") != check.get("verdict"):
        lines.append(f"  (the agent claimed {safe_text(arguments.get('checker_verdict'))})")
    lines += [f"Post SHA-256: {digest}", "----- post -----", safe_text(arguments.get("post")), "----- end -----"]
    return "\n".join(lines)


def cli_approver(decision: str | None, approver: str | None, expected_sha: str | None = None,
                 answer_file: Path | None = None, wait_seconds: float = 900.0,
                 out: Any = None) -> Approver:
    """Confirm-first, bound to the exact text shown.

    - A preset --decision approve needs --post-sha256 (at least 12 characters of the hash of the
      post being approved) and covers one queue call only. Any later call falls through.
    - --answer-file: the run pauses, writes the pending draft beside the file, and waits for a JSON
      answer {"decision", "approver", "post_sha256"} whose hash matches the post shown.
    - At a terminal: the approver types the first 12 characters of the hash, a decision and a name.
    - Otherwise the answer is decline.
    """
    preset = {"left": 1 if decision else 0}

    def approve(arguments: dict, check: dict, digest: str) -> tuple[str, str, str]:
        out_stream = out or sys.stderr
        print(show_for_approval(arguments, check, digest), file=out_stream, flush=True)
        if preset["left"]:
            preset["left"] -= 1
            name = (approver or "").strip()
            if decision == "decline":
                return "decline", name, "declined on the command line"
            if not name:
                return "decline", "", "no approver named"
            if not expected_sha or len(expected_sha) < HASH_PREFIX or not digest.startswith(expected_sha.lower()):
                return "decline", name, "preset approval did not carry this post's hash"
            print(f"Preset approval accepted for hash {digest[:HASH_PREFIX]} ({name})", file=out_stream)
            return "approve", name, "preset approval matching the post hash"
        if answer_file is not None:
            return wait_for_answer(answer_file, arguments, check, digest, wait_seconds, out_stream)
        if sys.stdin.isatty():
            typed = input(f"Type the first {HASH_PREFIX} characters of the hash to confirm you read this post: ")
            answer = input("Queue this draft for approval? [approve/decline] ").strip().lower()
            name = input("Your name: ").strip()
            if answer.startswith("a") and name and typed.strip().lower() == digest[:HASH_PREFIX]:
                return "approve", name, "answered at the terminal"
            return "decline", name, "declined, or the hash did not match, at the terminal"
        return "decline", "", "unattended: nobody confirmed"

    return approve


def wait_for_answer(answer_file: Path, arguments: dict, check: dict, digest: str,
                    wait_seconds: float, out: Any) -> tuple[str, str, str]:
    pending = answer_file.with_name(answer_file.name + ".pending.json")
    pending.write_text(json.dumps({"story_id": arguments.get("story_id"), "headline": arguments.get("headline"),
                                   "post": arguments.get("post"), "post_sha256": digest, "check": check},
                                  indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Paused. Pending draft written to {pending}. Waiting up to {int(wait_seconds)}s for {answer_file}.",
          file=out, flush=True)
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if answer_file.exists():
            try:
                answer = json.loads(answer_file.read_text(encoding="utf-8"))
            except ValueError:
                time.sleep(1)
                continue
            answer_file.unlink()
            pending.unlink(missing_ok=True)
            name = str(answer.get("approver") or "").strip()
            given = str(answer.get("post_sha256") or "").strip().lower()
            if answer.get("decision") != "approve":
                return "decline", name, "declined in the answer file"
            if not name:
                return "decline", "", "no approver named in the answer file"
            if len(given) < HASH_PREFIX or not digest.startswith(given):
                return "decline", name, "the answer's hash does not match the post shown"
            return "approve", name, "answered at the pause, hash matched"
        time.sleep(1)
    pending.unlink(missing_ok=True)
    return "decline", "", "nobody answered in time"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get(obj: Any, name: str, default: Any = None) -> Any:
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


def _as_dict(obj: Any) -> Any:
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "__dict__"):
        return {k: _as_dict(v) for k, v in vars(obj).items()}
    if isinstance(obj, list):
        return [_as_dict(v) for v in obj]
    return obj


# ---------- the session loop ----------

def drive(client: Any, session_id: str, dispatch: Callable[[str, dict], dict],
          first_events: list[dict] | None = None, max_reconnects: int = 5) -> dict:
    """Stream the session, answer custom tool calls, stop when the agent is done or paused.

    The stream has no replay, so after a drop it reconciles against the event list: any tool
    call still unanswered is answered (once; ids are tracked), then the stream is reopened."""
    outcome: dict = {"stop": None, "tool_calls": 0, "reconnects": 0}
    answered: set[str] = set()

    def handle(event: Any) -> bool:
        """Process one event. True means the session is finished or paused for good."""
        kind = _get(event, "type")
        if kind == "agent.custom_tool_use":
            event_id = _get(event, "id")
            if event_id in answered:
                return False
            answered.add(event_id)
            outcome["tool_calls"] += 1
            result = dispatch(_get(event, "name"), dict(_get(event, "input") or {}))
            payload = {"type": "user.custom_tool_result", "custom_tool_use_id": event_id,
                       "content": [{"type": "text", "text": json.dumps(result["data"], ensure_ascii=False)}]}
            if not result["ok"]:
                payload["is_error"] = True
            client.beta.sessions.events.send(session_id=session_id, events=[payload])
        elif kind in ("agent.tool_use", "agent.mcp_tool_use") and _get(event, "evaluated_permission") == "ask":
            # No built-in or MCP tool is enabled, so this should never happen. Deny if it does.
            client.beta.sessions.events.send(session_id=session_id, events=[{
                "type": "user.tool_confirmation", "tool_use_id": _get(event, "id"), "result": "deny",
                "deny_message": "Only the custom tools are available to this agent."}])
        elif kind == "user.custom_tool_result":
            answered.add(_get(event, "custom_tool_use_id"))
        elif kind == "session.status_idle":
            stop = _get(_get(event, "stop_reason"), "type")
            if stop != "requires_action":
                outcome["stop"] = stop
                return True
        elif kind == "session.status_terminated":
            outcome["stop"] = "terminated"
            return True
        elif kind == "session.error":
            outcome.setdefault("errors", []).append(_as_dict(_get(event, "error")))
        return False

    pending_first = first_events
    while True:
        try:
            with client.beta.sessions.events.stream(session_id=session_id) as stream:
                if pending_first:
                    client.beta.sessions.events.send(session_id=session_id, events=pending_first)
                    pending_first = None
                for event in stream:
                    if handle(event):
                        return outcome
        except Exception as error:  # a dropped stream; reconcile below
            if pending_first is not None:
                raise
            outcome.setdefault("stream_errors", []).append(f"{type(error).__name__}: {error}"[:200])
        if outcome["reconnects"] >= max_reconnects:
            outcome["stop"] = outcome["stop"] or "gave_up_reconnecting"
            return outcome
        outcome["reconnects"] += 1
        history = list(client.beta.sessions.events.list(session_id=session_id))
        for event in history:
            if _get(event, "type") == "user.custom_tool_result":
                answered.add(_get(event, "custom_tool_use_id"))
        last_status = None
        for event in history:
            if _get(event, "type") == "agent.custom_tool_use" and _get(event, "id") not in answered:
                handle(event)
            if _get(event, "type") in ("session.status_idle", "session.status_terminated"):
                last_status = event
        if last_status is not None and _get(last_status, "type") == "session.status_terminated":
            outcome["stop"] = "terminated"
            return outcome
        if last_status is not None and _get(_get(last_status, "stop_reason"), "type") not in (None, "requires_action"):
            if not any(_get(e, "type") == "agent.custom_tool_use" and _get(e, "id") not in answered for e in history):
                outcome["stop"] = _get(_get(last_status, "stop_reason"), "type")
                return outcome


def export(client: Any, session_id: str, ids: dict, outcome: dict, approvals: list[dict],
           path: Path) -> dict:
    events = [_as_dict(e) for e in client.beta.sessions.events.list(session_id=session_id)]
    session = _as_dict(client.beta.sessions.retrieve(session_id=session_id))
    data = {"exported": _now(), "session_id": session_id, "ids": ids, "session": session,
            "outcome": outcome, "approvals": approvals, "events": events}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    return data


# ---------- the morning-after report ----------

def morning_report(run: dict) -> str:
    events = run.get("events", [])
    checks = []
    for event in events:
        if event.get("type") == "agent.custom_tool_use" and event.get("name") == "check_post":
            checks.append(event.get("id"))
    results = {e.get("custom_tool_use_id"): e for e in events if e.get("type") == "user.custom_tool_result"}
    verdicts = []
    for check_id in checks:
        result = results.get(check_id, {})
        text = "".join(c.get("text", "") for c in result.get("content", []))
        try:
            verdicts.append(json.loads(text).get("verdict", "?"))
        except (ValueError, AttributeError):
            verdicts.append("?")
    final = ""
    for event in events:
        if event.get("type") == "agent.message":
            final = "".join(b.get("text", "") for b in event.get("content", []) if b.get("type") == "text") or final
    usage = (run.get("session") or {}).get("usage") or {}
    cost = (usage.get("list_cost") or {}).get("amount")
    lines = [f"# Harbourlight daily run: morning-after report", "",
             f"Session `{run.get('session_id')}`, exported {run.get('exported')}, "
             f"stopped with `{(run.get('outcome') or {}).get('stop')}`.", ""]
    lines.append(f"Drafts checked by the deterministic checker: {len(checks)} "
                 f"({', '.join(verdicts) or 'none'}).")
    if run.get("approvals"):
        lines += ["", "| Story | Headline | Checker (orchestrator's run) | Queue decision | Confirmed by | Post hash |",
                  "|---|---|---|---|---|---|"]
        for a in run["approvals"]:
            lines.append(f"| {md_cell(a.get('story_id'))} | {md_cell(a.get('headline'))} "
                         f"| {md_cell(a.get('checker_verdict'))} | {md_cell(a.get('decision'))} "
                         f"| {md_cell(a.get('approver') or 'nobody')} | {md_cell((a.get('post_sha256') or '')[:12])} |")
    else:
        lines.append("Nothing was offered for the approval queue.")
    lines += ["", f"List cost: {int(cost) / 100:.2f} USD against a 1.00 USD session budget." if cost
              else "List cost: not reported.", "",
              "Still to happen for anything queued: the independent compliance review and a named "
              "approver's decision. Nothing was published.", ""]
    if final:
        lines += ["## The agent's own report", "", safe_text(final).strip(), ""]
    return "\n".join(lines)


# ---------- commands ----------

def setup(client: Any, definitions: dict, ids_path: Path = IDS) -> dict:
    """Create the environment and agent once. Re-running reuses the stored ids."""
    if ids_path.exists():
        return json.loads(ids_path.read_text(encoding="utf-8"))
    env = client.beta.environments.create(**definitions["environment"])
    agent = client.beta.agents.create(**definitions["agent"])
    ids = {"environment_id": _get(env, "id"), "agent_id": _get(agent, "id"),
           "agent_version": _get(agent, "version"), "created": _now()}
    ids_path.write_text(json.dumps(ids, indent=2) + "\n", encoding="utf-8")
    return ids


def start_session(client: Any, ids: dict, story: str) -> Any:
    kickoff = (f"Run today's content draft from story {story}. Call get_new_stories with "
               f"story_id {story}, draft one post, check it, queue it for approval if it does not "
               "fail, and finish with the morning-after report.")
    return client.beta.sessions.create(
        agent={"type": "agent", "id": ids["agent_id"], "version": ids["agent_version"]},
        environment_id=ids["environment_id"],
        title=f"harbourlight-daily {story}",
        budget=SESSION_BUDGET,
        metadata={"story": story, "repo": "harbourlight"},
    ), [{"type": "user.message", "content": [{"type": "text", "text": kickoff}]}]


def record_session_cost(data: dict, session_id: str, ledger: Any = None) -> float | None:
    """Put the session's platform-priced list cost into the eval cost ledger."""
    sys.path.insert(0, str(ROOT / "evals"))
    from ledger import Ledger
    ledger = ledger or Ledger()
    usage = (data.get("session") or {}).get("usage") or {}
    amount = (usage.get("list_cost") or {}).get("amount")
    if amount is None:
        return None
    model = ((data.get("session") or {}).get("agent") or {}).get("model")
    model_id = model.get("id") if isinstance(model, dict) else model
    tokens = {k: v for k, v in usage.items() if k.endswith("tokens")}
    # Sessions report cache writes as a breakdown by TTL under "cache_creation".
    tokens["cache_creation_input_tokens"] = usage.get("cache_creation") or tokens.get("cache_creation_input_tokens", 0)
    return ledger.record_cost(model_id or "managed-agents", int(amount) / 100, label="managed-session",
                                run=session_id, usage=tokens)


def record_refusal(error: Exception, step: str, path: Path) -> None:
    body = getattr(error, "body", None)
    status = getattr(error, "status_code", None)
    data = {"exported": _now(), "ran": False, "step": step, "status_code": status,
            "error_type": type(error).__name__, "response_body": body, "message": str(error)[:1000]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"The API refused at {step}: {status} {type(error).__name__}. Recorded in {path}.", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("setup")
    run_p = sub.add_parser("run")
    run_p.add_argument("--story", required=True)
    attach_p = sub.add_parser("attach")
    attach_p.add_argument("--session-id", required=True)
    for p in (run_p, attach_p):
        p.add_argument("--approver", help="the person confirming the queue write")
        p.add_argument("--decision", choices=("approve", "decline"),
                       help="a preset answer for one queue call; approve also needs --post-sha256")
        p.add_argument("--post-sha256", help="first 12 or more characters of the approved post's SHA-256")
        p.add_argument("--answer-file", type=Path,
                       help="pause at the approval and wait for a JSON answer in this file")
        p.add_argument("--wait", type=float, default=900.0, help="seconds to wait for --answer-file")
    report_p = sub.add_parser("report")
    report_p.add_argument("export", type=Path)
    args = parser.parse_args(argv)

    if args.command == "report":
        print(safe_text(morning_report(json.loads(args.export.read_text(encoding="utf-8")))))
        return 0
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("needs ANTHROPIC_API_KEY; no request was sent", file=sys.stderr)
        return 2

    import anthropic

    from policy_bridge import BridgeError, PolicyBridge
    client = anthropic.Anthropic()
    day = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    out = RESULTS / f"managed-run-{day}.json"
    try:
        ids = setup(client, load_definitions())
    except anthropic.APIStatusError as error:
        record_refusal(error, "setup", out)
        return 4
    if args.command == "setup":
        print(json.dumps(ids, indent=2))
        return 0

    approvals: list[dict] = []
    try:
        policy = PolicyBridge()
    except BridgeError as error:
        print(error, file=sys.stderr)
        return 2
    with policy:
        dispatch = make_dispatch(policy, cli_approver(args.decision, args.approver, args.post_sha256,
                                                         args.answer_file, args.wait), approvals)
        try:
            if args.command == "run":
                session, first = start_session(client, ids, args.story)
                session_id = _get(session, "id")
                print(f"session {session_id}", file=sys.stderr)
            else:
                session_id, first = args.session_id, None
            outcome = drive(client, session_id, dispatch, first)
        except anthropic.APIStatusError as error:
            record_refusal(error, args.command, out)
            return 4
    data = export(client, session_id, ids, outcome, approvals, out)
    record_session_cost(data, session_id)
    report = morning_report(data)
    out.with_name(out.stem + "-report.md").write_text(report, encoding="utf-8")
    print(safe_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
