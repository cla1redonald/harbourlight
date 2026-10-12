#!/usr/bin/env python3
"""Run-to-run consistency: how often do the reviewer's verdict and cited rules change?

Give it N recorded run files for the same set of inputs (the format written by
`run_reviewer_eval.py --record` or `--live --repeats N`). For each input it finds
the most common verdict, counts how many runs disagreed with it, and checks
whether the set of rule ids cited changed between runs.

    python3 evals/variance/verdict_variance.py evals/variance/fixtures/
    python3 evals/variance/verdict_variance.py run1.json run2.json run3.json

A deterministic reviewer should score 0 changes. A model reviewer will not,
and this is the number that says whether one live run can be trusted on its own.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def load_runs(paths: list[Path]) -> list[dict]:
    files: list[Path] = []
    for path in paths:
        files += sorted(path.glob("*.json")) if path.is_dir() else [path]
    return [json.loads(f.read_text(encoding="utf-8")) for f in files]


def variance(runs: list[dict]) -> dict:
    if len(runs) < 2:
        raise ValueError("need at least two runs to measure variance")
    ids = sorted(set.intersection(*(set(r["results"]) for r in runs)))
    per_case = {}
    for case_id in ids:
        verdicts = [r["results"][case_id]["verdict"] for r in runs]
        rule_sets = [sorted(set(r["results"][case_id].get("rules", []))) for r in runs]
        modal, count = Counter(verdicts).most_common(1)[0]
        rules_changed = len({tuple(rs) for rs in rule_sets}) > 1
        per_case[case_id] = {
            "verdicts": verdicts,
            "rule_sets": rule_sets,
            "modal": modal,
            "agree_with_modal": count,
            "changed": len(set(verdicts)) > 1,
            "rules_changed": rules_changed,
        }
    changed = [c for c, v in per_case.items() if v["changed"]]
    rule_changed = [c for c, v in per_case.items() if v["rules_changed"]]
    all_agree = [c for c, v in per_case.items() if not v["changed"] and not v["rules_changed"]]
    total = len(ids) * len(runs)
    stable = sum(v["agree_with_modal"] for v in per_case.values())
    return {
        "runs": len(runs),
        "reviewers": sorted({r.get("reviewer", "unknown") for r in runs}),
        "inputs": len(ids),
        "inputs_with_any_change": len(changed),
        "changed_ids": changed,
        "verdict_change_rate": len(changed) / len(ids) if ids else 0.0,
        "inputs_with_rule_change": len(rule_changed),
        "rule_changed_ids": rule_changed,
        "inputs_all_agree": len(all_agree),
        "verdicts_matching_modal": stable,
        "verdicts_total": total,
        "per_case": per_case,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure run-to-run verdict changes.")
    parser.add_argument("paths", nargs="+", type=Path, help="run files or a directory of them")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = variance(load_runs(args.paths))
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    print(f"Variance: {report['runs']} recorded runs of {', '.join(report['reviewers'])}"
          f" over {report['inputs']} inputs")
    print(f"Inputs whose verdict changed between runs: {report['inputs_with_any_change']}"
          f"/{report['inputs']} ({100 * report['verdict_change_rate']:.0f}%)")
    print(f"Inputs whose cited rule set changed between runs: {report['inputs_with_rule_change']}"
          f"/{report['inputs']}")
    print(f"Inputs where every run agreed on verdict and rules: {report['inputs_all_agree']}"
          f"/{report['inputs']}")
    print(f"Individual verdicts matching that input's most common verdict: "
          f"{report['verdicts_matching_modal']}/{report['verdicts_total']}")
    for case_id in sorted(set(report["changed_ids"]) | set(report["rule_changed_ids"])):
        case = report["per_case"][case_id]
        rules = " / ".join(",".join(r) or "none" for r in case["rule_sets"])
        print(f"  {case_id}: {' '.join(case['verdicts'])}   rules: {rules}")
    if not report["changed_ids"] and not report["rule_changed_ids"]:
        print("  No changes. Expected for the deterministic stand-in; a live reviewer will differ.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
