#!/usr/bin/env python3
"""Set the Status line of one story in data/incoming-stories.md.

Only the Status line of the named story changes. Used by /content-run after
the human decision: `used (date)` on approval, `rejected (date, rule)` on rejection.

    python3 scripts/mark_story.py S02 used
    python3 scripts/mark_story.py S07 rejected --rule H5
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = ROOT / "data" / "incoming-stories.md"


def mark(story_id: str, status: str, date: str, rule: str | None = None,
         corpus: Path = DEFAULT_CORPUS) -> str:
    text = corpus.read_text(encoding="utf-8")
    section = re.search(rf"^## {re.escape(story_id)}\n(?:.*\n)*?- Status: (?P<status>.*)$",
                        text, re.MULTILINE)
    if not section:
        raise ValueError(f"story {story_id} not found")
    if section.group("status") != "new":
        raise ValueError(f"story {story_id} is already '{section.group('status')}'")
    if status == "used":
        new_status = f"used ({date})"
    elif status == "rejected":
        new_status = f"rejected ({date}, {rule})" if rule else f"rejected ({date})"
    else:
        raise ValueError("status must be used or rejected")
    start, end = section.span("status")
    corpus.write_text(text[:start] + new_status + text[end:], encoding="utf-8")
    return new_status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mark a story used or rejected.")
    parser.add_argument("story_id")
    parser.add_argument("status", choices=["used", "rejected"])
    parser.add_argument("--rule", help="rule id behind a rejection, for example H5")
    parser.add_argument("--date", default=dt.date.today().isoformat())
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    args = parser.parse_args(argv)
    try:
        new_status = mark(args.story_id, args.status, args.date, args.rule, args.corpus)
    except ValueError as error:
        print(f"Not changed: {error}", file=sys.stderr)
        return 1
    print(f"{args.story_id}: {new_status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
