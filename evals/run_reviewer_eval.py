#!/usr/bin/env python3
"""Score a compliance reviewer against the labelled cases in evals/reviewer-cases/.

By default it runs the rule-based stand-in reviewer (evals/standin_reviewer.py).
It can also score a recorded run (--from-recorded), which is how live model
outputs are scored without paying for them twice, and it can call Claude (--live).

    python3 evals/run_reviewer_eval.py                  # stand-in, full report
    python3 evals/run_reviewer_eval.py --seed-fault H3  # switch H3 off; gate must go red
    python3 evals/run_reviewer_eval.py --record out.json
    python3 evals/run_reviewer_eval.py --from-recorded out.json
    python3 evals/run_reviewer_eval.py --live --dry-run # the plan and a cost estimate, no calls
    python3 evals/run_reviewer_eval.py --live --model claude-haiku-5-5
    python3 evals/run_reviewer_eval.py --live --model claude-haiku-5-5 --repeats 5 \
        --out-dir evals/results/variance

Live runs need ANTHROPIC_API_KEY and the packages in requirements-live.txt. Every
response is priced into evals/results/spend.jsonl, and evals/ledger.py stops the
process when the running total passes its hard stop.

Exit codes: 0 gate green (or dry run), 1 gate red, 2 live run not possible,
3 spend ceiling reached.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from check_post import ALL_RULES, HARD_RULES, ROOT, load_rules, split_post  # noqa: E402
from standin_reviewer import REVIEWER_NAME, review  # noqa: E402

CASES_DIR = HERE / "reviewer-cases"
RESULTS = HERE / "results"
BASELINE = HERE / "baseline.json"
CHECKLIST = ROOT / "references" / "compliance-checklist.md"


def load_cases(directory: Path = CASES_DIR) -> list[dict]:
    cases = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("*.json"))]
    required = {"id", "category", "post", "expected_verdict", "expected_rules", "evidence_phrase"}
    for case in cases:
        missing = required - case.keys()
        if missing:
            raise ValueError(f"case {case.get('id', '?')} is missing {sorted(missing)}")
    return cases


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion. Behaves sensibly at small n and at 0 or 1."""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def run_standin(cases: list[dict], disabled: frozenset[str]) -> dict:
    rules = load_rules()
    results = {}
    for case in cases:
        results[case["id"]] = review(case["post"], disabled, rules)
    return {
        "reviewer": REVIEWER_NAME,
        "voice_version": rules["voice_version"],
        "seeded_faults": sorted(disabled),
        "created": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "results": results,
    }


def _quoted(output: dict, rule: str, phrase: str) -> bool:
    if not phrase:
        return False
    phrase = phrase.lower()
    for finding in output.get("findings", []):
        quote = finding.get("quote", "").lower()
        if finding.get("rule") == rule and quote and (phrase in quote or quote in phrase):
            return True
    return False


def _norm_quote(text: str) -> str:
    text = text.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"')
    text = text.replace("\u201d", '"')
    return re.sub(r"\s+", " ", text).strip()


def quote_in_post(quote: str, post: str) -> bool:
    """Did the reviewer quote words that are really in the post? Whitespace and curly
    quotes are normalised; case is not. '(no sources block)' is accurate only when the
    post really has no Sources block."""
    if quote.strip().lower() == "(no sources block)":
        return split_post(post)[1] is None
    quote = _norm_quote(quote).strip(" .\"'")
    return bool(quote) and quote in _norm_quote(post)


def evidence_accuracy(cases: list[dict], results: dict) -> dict:
    total, accurate, wrong = 0, 0, []
    posts = {c["id"]: c["post"] for c in cases}
    for case_id, output in results.items():
        if case_id not in posts:
            continue
        for finding in output.get("findings", []):
            total += 1
            if quote_in_post(finding.get("quote", ""), posts[case_id]):
                accurate += 1
            else:
                wrong.append({"id": case_id, "rule": finding.get("rule"),
                              "quote": finding.get("quote", "")})
    return {"findings": total, "quote_in_post": accurate, "not_in_post": wrong}


def score(cases: list[dict], run: dict) -> dict:
    results = run["results"]
    per_rule = {}
    for rule in HARD_RULES:
        targets = [c for c in cases if c["expected_verdict"] == "FAIL" and rule in c["expected_rules"]]
        caught = [
            c for c in targets
            if rule in results[c["id"]]["rules"] and results[c["id"]]["verdict"] != "PASS"
        ]
        quoted = [c for c in caught if _quoted(results[c["id"]], rule, c["evidence_phrase"])]
        per_rule[rule] = {
            "cases": len(targets),
            "caught": len(caught),
            "quoted_expected_evidence": len(quoted),
            "missed": [c["id"] for c in targets if c not in caught],
        }
    clean = [c for c in cases if c["category"] == "clean"]
    expected_pass = [c for c in cases if c["expected_verdict"] == "PASS"]
    agreed = [c for c in cases if results[c["id"]]["verdict"] == c["expected_verdict"]]
    disagreements = [
        {
            "id": c["id"],
            "expected": c["expected_verdict"],
            "expected_rules": c["expected_rules"],
            "got": results[c["id"]]["verdict"],
            "got_rules": results[c["id"]]["rules"],
            "note": c.get("notes", ""),
        }
        for c in cases if c not in agreed
    ]
    low, high = wilson_interval(len(agreed), len(cases))
    return {
        "reviewer": run.get("reviewer", "unknown"),
        "seeded_faults": run.get("seeded_faults", []),
        "n": len(cases),
        "per_rule": per_rule,
        "clean_cases": len(clean),
        "clean_false_positives": sum(1 for c in clean if results[c["id"]]["verdict"] != "PASS"),
        "expected_pass_cases": len(expected_pass),
        "expected_pass_false_positives": sum(
            1 for c in expected_pass if results[c["id"]]["verdict"] != "PASS"
        ),
        "agreement": len(agreed),
        "agreement_rate": len(agreed) / len(cases) if cases else 0.0,
        "wilson_95": [low, high],
        "disagreements": disagreements,
        "evidence": evidence_accuracy(cases, results),
    }


def gate(scores: dict, baseline: dict) -> list[str]:
    """Return reasons the run is worse than the committed baseline. Empty means green."""
    reasons = []
    for rule, base in baseline["caught"].items():
        got = scores["per_rule"][rule]["caught"]
        if got < base:
            reasons.append(f"{rule} catch fell from {base} to {got}")
    if scores["clean_false_positives"] > baseline["clean_false_positives"]:
        reasons.append(
            f"false positives on clean cases rose from {baseline['clean_false_positives']} "
            f"to {scores['clean_false_positives']}"
        )
    if scores["agreement"] < baseline["agreement"]:
        reasons.append(f"agreement fell from {baseline['agreement']} to {scores['agreement']}")
    return reasons


def baseline_from(scores: dict) -> dict:
    return {
        "_note": "Committed scores the eval must not fall below. Regenerate with --write-baseline "
                 "only when a reviewer change is a deliberate improvement.",
        "reviewer": scores["reviewer"],
        "caught": {rule: v["caught"] for rule, v in scores["per_rule"].items()},
        "clean_false_positives": scores["clean_false_positives"],
        "agreement": scores["agreement"],
    }


def pct(numerator: int, denominator: int) -> str:
    return "n/a" if denominator == 0 else f"{100 * numerator / denominator:.0f}%"


def print_report(scores: dict, reasons: list[str], summary_only: bool = False) -> None:
    faults = ", ".join(scores["seeded_faults"]) or "none"
    print(f"Reviewer eval: {scores['reviewer']}  (seeded faults: {faults})")
    print(f"n = {scores['n']} labelled posts")
    if not summary_only:
        print("\nCatch rate per hard rule (cases labelled FAIL for that rule):")
        for rule, v in scores["per_rule"].items():
            missed = f"  missed: {', '.join(v['missed'])}" if v["missed"] else ""
            print(f"  {rule}  {v['caught']}/{v['cases']}  {pct(v['caught'], v['cases']):>4}"
                  f"  quoted expected evidence {v['quoted_expected_evidence']}/{v['caught']}{missed}")
    total_cases = sum(v["cases"] for v in scores["per_rule"].values())
    total_caught = sum(v["caught"] for v in scores["per_rule"].values())
    low, high = scores["wilson_95"]
    print(f"\nHard-rule catches overall: {total_caught}/{total_cases} ({pct(total_caught, total_cases)})")
    print(f"False positives on clean cases: {scores['clean_false_positives']}/{scores['clean_cases']}"
          f"  (on all cases labelled PASS: {scores['expected_pass_false_positives']}/"
          f"{scores['expected_pass_cases']})")
    print(f"Verdict agreement with labels: {scores['agreement']}/{scores['n']}"
          f" ({pct(scores['agreement'], scores['n'])}), 95% Wilson interval "
          f"{100 * low:.0f}% to {100 * high:.0f}%")
    ev = scores.get("evidence")
    if ev:
        print(f"Quoted evidence found in the post: {ev['quote_in_post']}/{ev['findings']} findings")
    if not summary_only:
        print("\nCases where the reviewer disagreed with the label:")
        for d in scores["disagreements"]:
            print(f"  {d['id']:<4} expected {d['expected']} {d['expected_rules']}, "
                  f"got {d['got']} {d['got_rules']}")
    print("\nGATE: " + ("GREEN (no regression against evals/baseline.json)" if not reasons
                        else "RED: " + "; ".join(reasons)))


def live_plan(cases: list[dict]) -> int:
    """Print what a live pass would send and roughly cost. Makes no calls, needs no key."""
    from reviewer_prompt import DEFAULT_EFFORT, MAX_TOKENS, estimate

    plan = estimate(cases)
    print("Live reviewer plan (dry run, no calls made)")
    print(f"  {plan['cases']} posts per pass; cached prefix (skill, checklist, brand voice) "
          f"about {plan['prefix_tokens']:,} tokens; per-case story and post about "
          f"{plan['per_case_tokens_mean']:,} tokens; output assumed {plan['output_tokens_assumed']:,} "
          f"tokens per case including thinking; max_tokens {MAX_TOKENS:,}")
    for model, dollars in plan["models"].items():
        print(f"  {model} at effort {DEFAULT_EFFORT[model]}: about ${dollars:.2f} per pass "
              "at list prices")
    print("  Every response is priced into evals/results/spend.jsonl; the run stops at $50.")
    return 0


def run_live(cases: list[dict], model: str, effort: str | None, repeats: int,
             out_dir: Path, client=None, ledger=None) -> list[Path]:
    """Call Claude on every case, `repeats` times, and write one recorded run per repeat."""
    from ledger import Ledger
    from live_reviewer import review
    from reviewer_prompt import DEFAULT_EFFORT, load_stories

    if client is None:
        import anthropic
        client = anthropic.Anthropic(max_retries=4)
    ledger = ledger or Ledger()
    effort = effort or DEFAULT_EFFORT[model]
    stories = load_stories()
    day = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for repeat in range(1, repeats + 1):
        name = f"reviewer-{day}-{model}" + (f"-run-{repeat}" if repeats > 1 else "")
        results = {}
        for case in cases:
            results[case["id"]] = review(client, model, case["post"], stories, ledger,
                                         label=case["id"], run=name, effort=effort)
            print(f"  {name} {case['id']:<4} {results[case['id']]['verdict']:<10} "
                  f"${results[case['id']]['cost_usd']:.4f}  {results[case['id']]['latency_s']:.1f}s"
                  f"  total ${ledger.total:.4f}", file=sys.stderr)
        run = {
            "reviewer": model,
            "model": model,
            "effort": effort,
            "voice_version": load_rules()["voice_version"],
            "seeded_faults": [],
            "created": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "results": results,
        }
        path = out_dir / f"{name}.json"
        path.write_text(json.dumps(run, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score a reviewer against labelled cases.")
    parser.add_argument("--cases", type=Path, default=CASES_DIR)
    parser.add_argument("--seed-fault", action="append", default=[], choices=ALL_RULES,
                        help="disable a rule in the stand-in to prove the eval goes red")
    parser.add_argument("--from-recorded", type=Path, help="score a recorded run file instead")
    parser.add_argument("--record", type=Path, help="write this run's outputs to a file")
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("--json", action="store_true", help="print scores as JSON")
    parser.add_argument("--summary", action="store_true", help="headline numbers only")
    parser.add_argument("--live", action="store_true", help="call Claude (needs ANTHROPIC_API_KEY)")
    parser.add_argument("--dry-run", action="store_true", help="with --live: plan and estimate only")
    parser.add_argument("--model", choices=("claude-haiku-5-5", "claude-sonnet-5-5"),
                        default="claude-haiku-5-5")
    parser.add_argument("--effort", choices=("low", "medium", "high", "xhigh", "max"),
                        help="defaults to the model's own default")
    parser.add_argument("--repeats", type=int, default=1, help="with --live: passes over the cases")
    parser.add_argument("--out-dir", type=Path, default=RESULTS)
    args = parser.parse_args(argv)

    cases = load_cases(args.cases)
    if args.live:
        if args.dry_run:
            return live_plan(cases)
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("live mode needs ANTHROPIC_API_KEY in the environment; no calls were made. "
                  "Try --live --dry-run for the plan and a cost estimate.")
            return 2
        paths = run_live(cases, args.model, args.effort, max(1, args.repeats), args.out_dir)
        run = json.loads(paths[-1].read_text(encoding="utf-8"))
        for path in paths:
            print(f"recorded {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
    elif args.from_recorded:
        run = json.loads(args.from_recorded.read_text(encoding="utf-8"))
    else:
        run = run_standin(cases, frozenset(args.seed_fault))
    if args.record:
        args.record.write_text(json.dumps(run, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    scores = score(cases, run)
    if args.write_baseline:
        args.baseline.write_text(json.dumps(baseline_from(scores), indent=2) + "\n", encoding="utf-8")
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    reasons = gate(scores, baseline)
    if args.json:
        print(json.dumps({**scores, "gate_red_reasons": reasons}, indent=2))
    else:
        print_report(scores, reasons, args.summary)
    return 1 if reasons else 0


if __name__ == "__main__":
    sys.exit(main())
