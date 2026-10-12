"""The reviewer prompt, built from the skill and reference files. Stdlib only.

Shared by evals/live_reviewer.py (which sends it) and the dry run (which only
measures it), so the estimate and the real request can never drift apart.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from check_post import ROOT, URL_PATTERN, _clean_url, split_post

SKILL = ROOT / "skills" / "compliance-reviewer" / "SKILL.md"
CHECKLIST = ROOT / "references" / "compliance-checklist.md"
VOICE = ROOT / "references" / "brand-voice.md"
CORPUS = ROOT / "data-pristine" / "incoming-stories.md"

MODELS = ("claude-haiku-5-5", "claude-sonnet-5-5")
# Each model's documented default effort, sent explicitly so the recorded run says
# what it ran at.
DEFAULT_EFFORT = {"claude-haiku-5-5": "medium", "claude-sonnet-5-5": "high"}
MAX_TOKENS = 16000

HARNESS_NOTE = """## How this review is delivered

You are running as an API call, not in a file system, so there is nothing to open.
The user turn gives you, in this order: the one story the draft cites (looked up by
its URL in the story corpus, or a note that no story matches the URL), then the
draft. That is everything the skill lets you read. Reply only with the JSON object
the schema asks for. In `findings`, put `reason` where the skill says `why`."""


def system_blocks() -> list[dict]:
    """The cached prefix. Byte-identical across every case, so every call after the first reads it."""
    skill = SKILL.read_text(encoding="utf-8")
    checklist = CHECKLIST.read_text(encoding="utf-8")
    voice = VOICE.read_text(encoding="utf-8")
    return [
        {"type": "text", "text": skill},
        {"type": "text", "text": HARNESS_NOTE},
        {"type": "text", "text": "# The checklist\n\n" + checklist},
        {"type": "text", "text": "# The brand voice\n\n" + voice,
         "cache_control": {"type": "ephemeral"}},
    ]


def load_stories(path: Path = CORPUS) -> dict[str, str]:
    """Map each story URL to its full block of text in the corpus."""
    text = path.read_text(encoding="utf-8")
    stories = {}
    for block in re.split(r"\n---\n", text):
        match = re.search(r"^- URL: (\S+)", block, re.MULTILINE)
        if match and block.lstrip().startswith("## S"):
            # The Status line is pipeline bookkeeping, not part of the story.
            lines = [l for l in block.strip().splitlines() if not l.startswith("- Status:")]
            stories[_clean_url(match.group(1))] = "\n".join(lines)
    return stories


def cited_story(post: str, stories: dict[str, str]) -> str:
    _, sources = split_post(post)
    urls = [_clean_url(u) for line in (sources or []) for u in URL_PATTERN.findall(line)]
    if not urls:
        return "The draft has no Sources block, so no story could be looked up."
    for url in urls:
        if url in stories:
            return stories[url]
    return f"No story in the corpus has the URL the draft cites ({urls[0]})."


def user_content(post: str, stories: dict[str, str]) -> list[dict]:
    return [
        {"type": "text", "text": "<cited_story>\n" + cited_story(post, stories) + "\n</cited_story>"},
        {"type": "text", "text": "<draft>\n" + post + "\n</draft>"},
    ]


def estimate(cases: list[dict]) -> dict:
    """Rough token and cost estimate for one pass, with no network. Four characters per token."""
    prefix = sum(len(b["text"]) for b in system_blocks()) // 4
    stories = load_stories()
    per_case = [len(json.dumps(user_content(c["post"], stories))) // 4 for c in cases]
    output = 2500  # schema JSON plus adaptive thinking; a deliberately high guess
    n = len(cases)
    from ledger import PRICES
    out = {"cases": n, "prefix_tokens": prefix, "per_case_tokens_mean": sum(per_case) // max(n, 1),
           "output_tokens_assumed": output, "models": {}}
    for model in MODELS:
        price = PRICES[model]
        dollars = (prefix * price.cache_write_5m + (n - 1) * prefix * price.cache_read
                   + sum(per_case) * price.input + n * output * price.output) / 1_000_000
        out["models"][model] = round(dollars, 4)
    return out
