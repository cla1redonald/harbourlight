#!/usr/bin/env python3
"""Append one decision to data/audit-log.csv. The only way the pipeline writes to the log.

It never rewrites or reorders existing rows. It refuses rows that break the
standing rules: a FAIL can never be posted, nothing is posted without a named
approver, and every row carries the voice_version it was judged under.

    python3 scripts/append_audit.py --run-trigger manual \\
        --story-headline "Central bank holds base rate at 3.75%" \\
        --source-url https://news.example.invalid/... --verdict PASS --verdict-reasons none \\
        --human-decision "approved (Euan Lennie)" --edit-summary none --posted yes \\
        --post-file data/posts/2026-10-01-example.final.md
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG = ROOT / "data" / "audit-log.csv"
RULES = ROOT / "references" / "rules.json"
HEADER = [
    "date", "run_trigger", "story_headline", "source_url", "verdict", "verdict_reasons",
    "voice_version", "human_decision", "edit_summary", "posted", "post_file",
]
DECISION = re.compile(r"^(approved|approved with edit|rejected) \((?P<name>[^)]*\S[^)]*)\)$")


class AuditError(ValueError):
    pass


def validate(row: dict) -> None:
    if row["verdict"] not in {"PASS", "FLAG", "FAIL"}:
        raise AuditError("verdict must be PASS, FLAG or FAIL")
    match = DECISION.match(row["human_decision"])
    if not match:
        raise AuditError('human_decision must be "approved (Name)", '
                         '"approved with edit (Name)" or "rejected (Name)"')
    if row["posted"] not in {"yes", "no"}:
        raise AuditError("posted must be yes or no")
    if row["posted"] == "yes" and match.group(1) == "rejected":
        raise AuditError("a rejected post cannot be posted")
    if row["verdict"] == "FAIL" and match.group(1) != "rejected":
        raise AuditError("a FAIL cannot be approved: rewrite the draft and review it again")
    if match.group(1) == "approved with edit" and row["edit_summary"] in {"", "none"}:
        raise AuditError("an approval with edits needs an edit_summary")
    if not str(row["voice_version"]).isdigit():
        raise AuditError("voice_version must be a whole number")
    if not row["source_url"].startswith("https://"):
        raise AuditError("source_url must be the story's URL")


def append(row: dict, log: Path = DEFAULT_LOG) -> None:
    validate(row)
    with log.open(encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle), None)
    if header != HEADER:
        raise AuditError(f"{log} does not start with the expected header")
    needs_newline = False
    with log.open("rb") as handle:
        if handle.seek(0, 2) > 0:
            handle.seek(-1, 2)
            needs_newline = handle.read(1) != b"\n"
    with log.open("a", encoding="utf-8", newline="") as handle:
        if needs_newline:
            handle.write("\n")
        csv.writer(handle, lineterminator="\n").writerow([row[k] for k in HEADER])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Append one row to the audit log.")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--date", default=dt.date.today().isoformat())
    for field in HEADER[1:]:
        if field in {"voice_version"}:
            continue
        parser.add_argument("--" + field.replace("_", "-"), required=True)
    parser.add_argument("--voice-version", default=None,
                        help="defaults to the current voice_version in references/rules.json")
    args = parser.parse_args(argv)
    row = {k: getattr(args, k) for k in HEADER if k != "voice_version"}
    row["voice_version"] = args.voice_version or str(
        json.loads(RULES.read_text(encoding="utf-8"))["voice_version"])
    try:
        append(row, args.log)
    except AuditError as error:
        print(f"Not logged: {error}", file=sys.stderr)
        return 1
    print(f"Logged: {row['date']} {row['verdict']} {row['human_decision']} -> {args.log.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
