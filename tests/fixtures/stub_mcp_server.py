"""A stand-in MCP stdio server for the bridge tests: canned answers, same protocol."""
import json
import sys

for line in sys.stdin:
    message = json.loads(line)
    if "id" not in message:
        continue
    method = message["method"]
    if method == "initialize":
        result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                  "serverInfo": {"name": "stub", "version": "0"}}
    elif method == "tools/list":
        result = {"tools": [{"name": "check_post"}, {"name": "get_checklist"}]}
    elif method == "tools/call" and message["params"]["name"] == "check_post":
        text = message["params"]["arguments"].get("text", "")
        verdict = "FAIL" if "guaranteed" in text else "PASS"
        result = {"content": [{"type": "text", "text": json.dumps({"verdict": verdict})}],
                  "structuredContent": {"verdict": verdict}}
    else:
        result = {"content": [{"type": "text", "text": "unknown tool"}], "isError": True}
    print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}), flush=True)
