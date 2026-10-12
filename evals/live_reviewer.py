"""The compliance reviewer, run live against the Claude API.

The prompt (evals/reviewer_prompt.py) is the reviewer skill, the checklist and the
brand voice, in that order, as a cached system prefix. The per-case content goes
last: the one story the draft cites (the skill lets the reviewer read it, see
docs/design/0004 item 3) and then the post itself. The reply is constrained to a
schema with `messages.parse`, so every finding arrives as a rule id, a quote and
a reason.

Every response, including refusals and truncated ones, is priced and written to
the cost ledger before anything else happens to it; a reply the SDK cannot
parse is charged at a worst-case estimate, since its usage is not returned. The SDK is never imported
here; the caller passes a client in.
"""
from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field

from ledger import Ledger, cost_usd, usage_dict
from reviewer_prompt import DEFAULT_EFFORT, MAX_TOKENS, system_blocks, user_content

RuleId = Literal["H1", "H2", "H3", "H4", "H5", "H6", "H7", "S1", "S2", "S3", "S4", "S5"]


class Finding(BaseModel):
    rule: RuleId = Field(description="The checklist rule id.")
    severity: Literal["fail", "flag"] = Field(description="fail for a hard-rule failure, flag otherwise.")
    quote: str = Field(description="Exact words copied from the draft, or (no sources block).")
    reason: str = Field(description="One line saying why this breaks the rule.")


class ReviewerVerdict(BaseModel):
    verdict: Literal["PASS", "FLAG", "FAIL"]
    needs_human: bool = Field(description="True if the post touches a sensitive topic.")
    findings: list[Finding]
    what_would_change: list[str] = Field(
        description="For a FAIL, one entry per failing rule saying what would have to change.")
    summary_for_approver: str = Field(description="At most five short lines for the approver.")


def _to_record(parsed: ReviewerVerdict) -> dict:
    findings = [{"rule": f.rule, "severity": f.severity, "quote": f.quote, "why": f.reason}
                for f in parsed.findings]
    return {
        "verdict": parsed.verdict,
        "needs_human": parsed.needs_human,
        "rules": sorted({f["rule"] for f in findings}),
        "findings": findings,
        "what_would_change": parsed.what_would_change,
        "summary": parsed.summary_for_approver,
    }


def _no_verdict(kind: str, detail: str) -> dict:
    # Scored as a disagreement with any label and as a miss for every rule.
    return {"verdict": kind, "needs_human": True, "rules": [], "findings": [],
            "what_would_change": [], "summary": detail}


def worst_case_usage(post: str, stories: dict[str, str]) -> dict:
    """What a reply we could not read might have cost: the whole prompt uncached, full max_tokens."""
    chars = sum(len(b["text"]) for b in system_blocks()) + len(str(user_content(post, stories)))
    return {"input_tokens": chars // 3, "output_tokens": MAX_TOKENS,
            "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}


def _stop_category(message: Any) -> str | None:
    details = getattr(message, "stop_details", None)
    if details is None:
        return None
    return details.get("category") if isinstance(details, dict) else getattr(details, "category", None)


def review(client: Any, model: str, post: str, stories: dict[str, str], ledger: Ledger,
           label: str = "", run: str = "", effort: str | None = None) -> dict:
    """Review one post. Returns a record in the shape run_reviewer_eval.score() reads."""
    effort = effort or DEFAULT_EFFORT[model]
    ledger.check()
    started = time.monotonic()
    try:
        message = client.messages.parse(
            model=model,
            max_tokens=MAX_TOKENS,
            system=system_blocks(),
            messages=[{"role": "user", "content": user_content(post, stories)}],
            output_format=ReviewerVerdict,
            output_config={"effort": effort},
        )
    except ValueError as error:
        # The SDK validates the JSON inside parse(), so a reply that fails the schema (pydantic's
        # ValidationError is a ValueError) arrives as an exception and its usage is lost. Charge
        # the ledger a worst case instead, so the ceiling still holds, and mark the row estimated.
        latency = time.monotonic() - started
        usage = worst_case_usage(post, stories)
        ledger.record(model, usage, label=label, run=run, estimated=True)
        record = _no_verdict("UNPARSED", f"{type(error).__name__}: {error}"[:300])
        stop_reason, request_id = None, None
    else:
        latency = time.monotonic() - started
        usage = message.usage
        request_id = getattr(message, "_request_id", None)
        # Price it before reading anything else, so a bad reply is still paid for.
        ledger.record(model, usage, label=label, run=run, request_id=request_id)
        stop_reason = message.stop_reason
        if stop_reason == "refusal":
            record = _no_verdict("REFUSED", f"refusal: {_stop_category(message)}")
        elif stop_reason == "max_tokens":
            record = _no_verdict("INCOMPLETE", "hit max_tokens before the JSON was complete")
        else:
            parsed = getattr(message, "parsed_output", None)
            record = _to_record(parsed) if parsed else _no_verdict("UNPARSED", "no parsed output")

    record.update({
        "reviewer": model,
        "model": model,
        "effort": effort,
        "stop_reason": stop_reason,
        "request_id": request_id,
        "usage": usage_dict(usage),
        "cost_usd": round(cost_usd(model, usage), 8),
        "cost_estimated": stop_reason is None,
        "latency_s": round(latency, 3),
    })
    return record
