#!/usr/bin/env python3
"""Count a month of decisions from data/audit-log.csv into a short Markdown report.

The numbers come from this script so they can be checked; the
monthly-audit-report skill adds the commentary on top.

    python3 scripts/monthly_report.py --month 2026-09
    python3 scripts/monthly_report.py --month 2026-09 --write   # data/reports/2026-09.md
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG = ROOT / "data" / "audit-log.csv"
REPORTS = ROOT / "data" / "reports"
RULE_ID = re.compile(r"\b([HS][1-7])\b")


def load_rows(log: Path, month: str) -> list[dict]:
    with log.open(encoding="utf-8", newline="") as handle:
        return [row for row in csv.DictReader(handle) if row["date"].startswith(month)]


def decision_kind(decision: str) -> str:
    return decision.split(" (", 1)[0]


def report(rows: list[dict], month: str) -> str:
    verdicts = Counter(r["verdict"] for r in rows)
    decisions = Counter(decision_kind(r["human_decision"]) for r in rows)
    rules = Counter(rule for r in rows for rule in sorted(set(RULE_ID.findall(r["verdict_reasons"]))))
    posted = sum(1 for r in rows if r["posted"] == "yes")
    versions = sorted({r["voice_version"] for r in rows})
    overrides = [r for r in rows if r["verdict"] == "FAIL" and r["posted"] == "yes"]
    lines = [
        f"# Content audit report: {month}",
        "",
        f"Source: `data/audit-log.csv`, {len(rows)} decisions dated {month}.",
        "",
        "## Numbers",
        "",
        "| Measure | Count |",
        "|---|---|",
        f"| Drafts reviewed | {len(rows)} |",
        f"| Reviewer PASS | {verdicts['PASS']} |",
        f"| Reviewer FLAG | {verdicts['FLAG']} |",
        f"| Reviewer FAIL | {verdicts['FAIL']} |",
        f"| Approved as drafted | {decisions['approved']} |",
        f"| Approved with edits | {decisions['approved with edit']} |",
        f"| Rejected | {decisions['rejected']} |",
        f"| Posted | {posted} |",
        f"| FAIL verdicts that were posted anyway | {len(overrides)} |",
        "",
        f"Voice versions in use: {', '.join('v' + v for v in versions) or 'none'}.",
        "",
        "## Rules cited by the reviewer",
        "",
    ]
    if rules:
        lines += [f"- {rule}: {count} decision{'s' if count != 1 else ''}"
                  for rule, count in sorted(rules.items())]
    else:
        lines.append("- none")
    lines += ["", "## Decisions", "", "| Date | Story | Verdict | Decision | Posted |",
              "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['date']} | {r['story_headline']} | {r['verdict']} | "
                     f"{r['human_decision']} | {r['posted']} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Monthly audit report from the audit log.")
    parser.add_argument("--month", required=True, help="YYYY-MM")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--write", action="store_true", help="also write data/reports/YYYY-MM.md")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"\d{4}-\d{2}", args.month):
        parser.error("--month must look like 2026-09")
    text = report(load_rows(args.log, args.month), args.month)
    print(text, end="")
    if args.write:
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / f"{args.month}.md").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
