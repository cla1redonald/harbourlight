"""Rule-based stand-in for the compliance reviewer.

It produces output in the same shape the model reviewer is asked for in
skills/compliance-reviewer/SKILL.md, so the eval harness can score either one.
It is deliberately simple: the deterministic checker plus the sensitive-topic
gate. Its job is to prove the harness works, not to be a good reviewer.
"""
from __future__ import annotations

from check_post import check_text, load_corpus_urls, load_rules

REVIEWER_NAME = "standin-rules-v1"


def sensitive_gate(result: dict) -> dict:
    """A sensitive topic can never come back as PASS, whatever else is true."""
    if result["needs_human"] and result["verdict"] == "PASS":
        result["verdict"] = "FLAG"
    return result


def review(post: str, disabled: frozenset[str] = frozenset(), rules: dict | None = None,
           corpus_urls: set[str] | None = None) -> dict:
    rules = rules or load_rules()
    corpus_urls = load_corpus_urls() if corpus_urls is None else corpus_urls
    checked = check_text(post, rules, corpus_urls, set(disabled))
    result = {
        "reviewer": REVIEWER_NAME,
        "verdict": checked.verdict,
        "needs_human": checked.needs_human,
        "rules": checked.rules(),
        "findings": [
            {"rule": f.rule, "severity": f.severity, "quote": f.quote, "why": f.why}
            for f in checked.findings
        ],
        "what_would_change": checked.what_would_change,
    }
    return sensitive_gate(result)
