#!/usr/bin/env python3
"""Blind export for a second human labeller, and agreement (Cohen's kappa) once they are done.

    python3 evals/labels/agreement.py export --out blind-pack/
    python3 evals/labels/agreement.py score evals/labels/second-labeller.csv --key blind-pack/key.json

Stdlib only. See evals/labels/second-labeller-template.md for the procedure.
This compares two people. It must never be fed a model's output as a "labeller".
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from check_post import HARD_RULES  # noqa: E402
from reviewer_prompt import cited_story, load_stories  # noqa: E402
from run_reviewer_eval import load_cases  # noqa: E402

VERDICTS = ("PASS", "FLAG", "FAIL")


def cohen_kappa(a: list[str], b: list[str]) -> float:
    if len(a) != len(b) or not a:
        raise ValueError("need two equal-length, non-empty label lists")
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b)) / n
    count_a, count_b = Counter(a), Counter(b)
    expected = sum(count_a[k] * count_b[k] for k in set(a) | set(b)) / (n * n)
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1 - expected)


def bootstrap_kappa(a: list[str], b: list[str], draws: int = 2000, seed: int = 7) -> tuple[float, float]:
    rng = random.Random(seed)
    n = len(a)
    values = []
    for _ in range(draws):
        idx = [rng.randrange(n) for _ in range(n)]
        values.append(cohen_kappa([a[i] for i in idx], [b[i] for i in idx]))
    values.sort()
    return values[int(0.025 * draws)], values[int(0.975 * draws) - 1]


def export(out: Path, seed: int = 2026) -> dict:
    cases = load_cases()
    stories = load_stories()
    order = [c["id"] for c in cases]
    random.Random(seed).shuffle(order)
    by_id = {c["id"]: c for c in cases}
    out.mkdir(parents=True, exist_ok=True)
    key = {}
    for n, case_id in enumerate(order, start=1):
        neutral = f"P{n:02d}"
        key[neutral] = case_id
        post = by_id[case_id]["post"]
        (out / f"{neutral}.md").write_text(
            f"# {neutral}\n\n## The post\n\n{post}\n\n## The story it cites\n\n"
            f"{cited_story(post, stories)}\n", encoding="utf-8")
    (out / "key.json").write_text(json.dumps(key, indent=2) + "\n", encoding="utf-8")
    return key


def read_sheet(path: Path, key: dict[str, str]) -> dict[str, dict]:
    labels = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            verdict = row["verdict"].strip().upper()
            if verdict not in VERDICTS:
                raise ValueError(f"{row['post']}: verdict must be PASS, FLAG or FAIL")
            case_id = key.get(row["post"].strip(), row["post"].strip())
            labels[case_id] = {"verdict": verdict, "rules": sorted(set(row.get("rules", "").split())),
                               "quote": row.get("quote", "")}
    return labels


def score(second: dict[str, dict]) -> dict:
    cases = {c["id"]: c for c in load_cases()}
    missing = sorted(set(cases) - set(second))
    if missing:
        raise ValueError(f"the sheet has no label for {', '.join(missing)}")
    ids = sorted(cases)
    first_v = [cases[i]["expected_verdict"] for i in ids]
    second_v = [second[i]["verdict"] for i in ids]
    per_rule = {}
    for rule in HARD_RULES:
        a = ["yes" if rule in cases[i]["expected_rules"] else "no" for i in ids]
        b = ["yes" if rule in second[i]["rules"] else "no" for i in ids]
        per_rule[rule] = round(cohen_kappa(a, b), 3)
    jaccard = []
    for i in ids:
        x, y = set(cases[i]["expected_rules"]), set(second[i]["rules"])
        jaccard.append(1.0 if not x and not y else len(x & y) / len(x | y))
    low, high = bootstrap_kappa(first_v, second_v)
    return {
        "n": len(ids),
        "verdict_agreement": sum(x == y for x, y in zip(first_v, second_v)),
        "verdict_kappa": round(cohen_kappa(first_v, second_v), 3),
        "verdict_kappa_95": [round(low, 3), round(high, 3)],
        "rule_kappa": per_rule,
        "mean_rule_jaccard": round(sum(jaccard) / len(jaccard), 3),
        "disagreements": [
            {"id": i, "first": cases[i]["expected_verdict"], "first_rules": cases[i]["expected_rules"],
             "second": second[i]["verdict"], "second_rules": second[i]["rules"],
             "second_quote": second[i]["quote"]}
            for i in ids if cases[i]["expected_verdict"] != second[i]["verdict"]
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    ex = sub.add_parser("export")
    ex.add_argument("--out", type=Path, required=True)
    sc = sub.add_parser("score")
    sc.add_argument("sheet", type=Path)
    sc.add_argument("--key", type=Path, help="key.json from the export")
    args = parser.parse_args(argv)
    if args.command == "export":
        key = export(args.out)
        print(f"wrote {len(key)} blind posts and key.json to {args.out}; keep key.json from the labeller")
        return 0
    key = json.loads(args.key.read_text(encoding="utf-8")) if args.key else {}
    print(json.dumps(score(read_sheet(args.sheet, key)), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
