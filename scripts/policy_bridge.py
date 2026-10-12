"""A minimal MCP stdio client, stdlib only, for forwarding tool calls to the policy server.

Managed Agents cannot reach a stdio server on this machine, so the orchestrator
answers the agent's custom tool calls by forwarding them here. That keeps one
implementation of the policy (mcp/policy-server) behind every surface.

    with PolicyBridge() as policy:
        result = policy.call("check_post", {"text": post})

MCP over stdio is newline-delimited JSON-RPC 2.0: initialise, confirm, then call.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "mcp" / "policy-server" / "dist" / "src" / "index.js"
PROTOCOL_VERSION = "2025-06-18"
POLICY_TOOLS = ("list_approved_claims", "check_claim", "check_post", "get_checklist", "get_voice_rules")


class BridgeError(RuntimeError):
    pass


class PolicyBridge:
    def __init__(self, command: list[str] | None = None) -> None:
        if command is None:
            if not SERVER.exists():
                raise BridgeError(f"{SERVER.relative_to(ROOT)} is missing; run `make policy-server` first")
            command = ["node", str(SERVER)]
        self.command = command
        self.process: subprocess.Popen[str] | None = None
        self._next_id = 0

    def __enter__(self) -> "PolicyBridge":
        self.process = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
        self._request("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                     "clientInfo": {"name": "harbourlight-orchestrator", "version": "0.1.0"}})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return self

    def __exit__(self, *exc: object) -> None:
        if self.process:
            self.process.stdin.close()  # type: ignore[union-attr]
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process.stdout.close()  # type: ignore[union-attr]

    def _send(self, message: dict) -> None:
        assert self.process and self.process.stdin
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def _request(self, method: str, params: dict) -> dict:
        self._next_id += 1
        request_id = self._next_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        assert self.process and self.process.stdout
        while True:
            line = self.process.stdout.readline()
            if not line:
                raise BridgeError(f"policy server closed the stream during {method}")
            message = json.loads(line)
            if message.get("id") != request_id:
                continue  # a notification or log line; not ours
            if "error" in message:
                raise BridgeError(f"{method}: {message['error'].get('message')}")
            return message["result"]

    def list_tools(self) -> list[str]:
        return [t["name"] for t in self._request("tools/list", {})["tools"]]

    def call(self, name: str, arguments: dict[str, Any]) -> dict:
        """Call one policy tool. Returns {'ok': bool, 'data': structured result or error text}."""
        if name not in POLICY_TOOLS:
            return {"ok": False, "data": f"{name} is not a policy tool"}
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            text = " ".join(c.get("text", "") for c in result.get("content", []))
            return {"ok": False, "data": text}
        return {"ok": True, "data": result.get("structuredContent")
                or json.loads(result["content"][0]["text"])}
