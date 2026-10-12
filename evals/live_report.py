#!/usr/bin/env python3
"""Compare reviewers on the labelled cases and write the report as Markdown.

Scores the stand-in and any number of recorded runs with the same harness
(run_reviewer_eval.score), then adds what a live run needs on top: cost and
latency distributions, and the cases that flip between each pair of reviewers
with an exact McNemar test, so a difference is only called a difference when
24 cases can support it.

    python3 evals/live_report.py evals/results/reviewer-2026-10-12-claude-haiku-5-5.json \
        evals/results/reviewer-2026-10-12-claude-sonnet-5-5.json \
        --variance evals/results/variance --out evals/results/report-2026-10-12.md
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from itertools import combinations
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "variance"))

from run_reviewer_eval import load_cases, run_standin, score  # noqa: E402
from verdict_variance import load_runs, variance  # noqa: E402


def percentile(values: list[float], q: float) -> float:
    """Linear-interpolated percentile, q in [0, 100]. Same method as numpy's default."""
    if not values:
        return float("nan")
    ordered = sorted(values)
    position = (len(ordered) - 1) * q / 100
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def distribution(values: list[float]) -> dict:
    if not values:
        return {}
    return {"n": len(values), "median": percentile(values, 50), "p95": percentile(values, 95),
            "max": max(values), "mean": sum(values) / len(values), "total": sum(values)}


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value: b cases only the first reviewer got right, c only the second."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def compare(cases: list[dict], runs: dict[str, dict]) -> list[dict]:
    labels = {c["id"]: c["expected_verdict"] for c in cases}
    out = []
    for (name_a, run_a), (name_b, run_b) in combinations(runs.items(), 2):
        flips, only_a, only_b = [], 0, 0
        for case_id, label in labels.items():
            got_a = run_a["results"][case_id]["verdict"]
            got_b = run_b["results"][case_id]["verdict"]
            right_a, right_b = got_a == label, got_b == label
            only_a += right_a and not right_b
            only_b += right_b and not right_a
            if got_a != got_b:
                flips.append({"id": case_id, "label": label, name_a: got_a, name_b: got_b})
        p = mcnemar_exact(only_a, only_b)
        out.append({"a": name_a, "b": name_b, "flips": flips, "only_a_right": only_a,
                    "only_b_right": only_b, "p": p, "within_noise": p >= 0.05})
    return out


def _fmt_pct(a: int, b: int) -> str:
    return "n/a" if b == 0 else f"{100 * a / b:.0f}%"


def reviewer_section(name: str, run: dict, scores: dict) -> list[str]:
    lines = [f"### {name}", ""]
    if run.get("effort"):
        lines += [f"Model `{run.get('model')}`, effort `{run['effort']}`, recorded {run.get('created')}.", ""]
    lines += ["| Hard rule | Caught | n | Quoted the expected phrase | Missed |", "|---|---|---|---|---|"]
    for rule, v in scores["per_rule"].items():
        lines.append(f"| {rule} | {v['caught']} | {v['cases']} | {v['quoted_expected_evidence']} "
                     f"| {', '.join(v['missed']) or 'none'} |")
    caught = sum(v["caught"] for v in scores["per_rule"].values())
    total = sum(v["cases"] for v in scores["per_rule"].values())
    low, high = scores["wilson_95"]
    ev = scores["evidence"]
    lines += [
        "",
        "| Measure | Result |",
        "|---|---|",
        f"| Hard-rule catches | {caught} of {total} ({_fmt_pct(caught, total)}) |",
        f"| False positives on clean cases | {scores['clean_false_positives']} of {scores['clean_cases']} |",
        f"| Not PASS on any case labelled PASS | {scores['expected_pass_false_positives']} of "
        f"{scores['expected_pass_cases']} |",
        f"| Verdict agreement with labels | {scores['agreement']} of {scores['n']} "
        f"({_fmt_pct(scores['agreement'], scores['n'])}), 95% Wilson interval "
        f"{100 * low:.0f}% to {100 * high:.0f}% |",
        f"| Quoted evidence found in the post | {ev['quote_in_post']} of {ev['findings']} findings "
        f"({_fmt_pct(ev['quote_in_post'], ev['findings'])}) |",
    ]
    results = run["results"].values()
    costs = [r["cost_usd"] for r in results if "cost_usd" in r]
    latencies = [r["latency_s"] for r in results if "latency_s" in r]
    if costs:
        c = distribution(costs)
        lines.append(f"| Cost per case (USD) | median {c['median']:.5f}, p95 {c['p95']:.5f}, "
                     f"max {c['max']:.5f}, mean {c['mean']:.5f}; pass total {c['total']:.4f} |")
    if latencies:
        lt = distribution(latencies)
        lines.append(f"| Latency per case (s) | p50 {lt['median']:.1f}, p90 {percentile(latencies, 90):.1f}, "
                     f"p95 {lt['p95']:.1f}, max {lt['max']:.1f} |")
    no_verdict = [cid for cid, r in run["results"].items()
                  if r["verdict"] not in ("PASS", "FLAG", "FAIL")]
    if no_verdict:
        lines.append(f"| Cases with no verdict (refusal, truncation) | {', '.join(no_verdict)} |")
    lines += ["", "Disagreements with the label:", ""]
    if scores["disagreements"]:
        lines += ["| Case | Label | Got | Rules cited |", "|---|---|---|---|"]
        for d in scores["disagreements"]:
            lines.append(f"| {d['id']} | {(d['expected'] + ' ' + ', '.join(d['expected_rules'])).strip()} | {d['got']} "
                         f"| {', '.join(d['got_rules']) or 'none'} |")
    else:
        lines.append("None.")
    if ev["not_in_post"]:
        lines += ["", "Quotes not found in the post:", ""]
        for w in ev["not_in_post"]:
            lines.append(f"- {w['id']} {w['rule']}: \"{w['quote'][:100]}\"")
    return lines + [""]


def variance_section(directory: Path) -> list[str]:
    runs = load_runs([directory])
    if len(runs) < 2:
        return []
    report = variance(runs)
    lines = [
        "## Run-to-run variance", "",
        f"{report['runs']} repeat runs of {', '.join(report['reviewers'])} over {report['inputs']} cases.", "",
        "| Measure | Result |", "|---|---|",
        f"| Cases where every repeat gave the same verdict | {report['inputs'] - report['inputs_with_any_change']}"
        f" of {report['inputs']} |",
        f"| Cases whose verdict changed at least once | {report['inputs_with_any_change']} of {report['inputs']} |",
        f"| Cases whose cited rule set changed at least once | {report['inputs_with_rule_change']} of "
        f"{report['inputs']} |",
        f"| Cases where every repeat agreed on verdict and rules | {report['inputs_all_agree']} of "
        f"{report['inputs']} |",
        f"| Individual verdicts matching the case's most common verdict | {report['verdicts_matching_modal']}"
        f" of {report['verdicts_total']} |",
        "",
    ]
    changed = sorted(set(report["changed_ids"]) | set(report["rule_changed_ids"]))
    if changed:
        lines += ["| Case | Verdicts across repeats | Rule sets across repeats |", "|---|---|---|"]
        for case_id in changed:
            pc = report["per_case"][case_id]
            rule_sets = " / ".join(",".join(r) or "none" for r in pc["rule_sets"])
            lines.append(f"| {case_id} | {' '.join(pc['verdicts'])} | {rule_sets} |")
        lines.append("")
    return lines


def build(paths: list[Path], variance_dir: Path | None) -> tuple[str, dict]:
    cases = load_cases()
    runs = {"stand-in": run_standin(cases, frozenset())}
    for path in paths:
        run = json.loads(path.read_text(encoding="utf-8"))
        runs[run.get("model") or run.get("reviewer") or path.stem] = run
    all_scores = {name: score(cases, run) for name, run in runs.items()}
    lines = ["# Reviewer comparison", "",
             f"{len(cases)} labelled posts, one labeller, who also wrote the rules and the posts. "
             "Read every interval and every flip with that in mind.", ""]
    for name, run in runs.items():
        lines += reviewer_section(name, run, all_scores[name])
    lines += ["## Cases that flip between reviewers", ""]
    comparisons = compare(cases, runs)
    for comp in comparisons:
        verdict = ("within noise" if comp["within_noise"]
                   else "a difference 24 cases can support")
        lines += [f"### {comp['a']} against {comp['b']}", "",
                  f"Only {comp['a']} right: {comp['only_a_right']}; only {comp['b']} right: "
                  f"{comp['only_b_right']}; exact McNemar p = {comp['p']:.3f}: {verdict}.", ""]
        if comp["flips"]:
            lines += [f"| Case | Label | {comp['a']} | {comp['b']} |", "|---|---|---|---|"]
            for f in comp["flips"]:
                lines.append(f"| {f['id']} | {f['label']} | {f[comp['a']]} | {f[comp['b']]} |")
        else:
            lines.append("No flips.")
        lines.append("")
    if variance_dir and variance_dir.exists():
        lines += variance_section(variance_dir)
    data = {"scores": all_scores, "comparisons": comparisons}
    return "\n".join(lines).rstrip() + "\n", data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare reviewers on the labelled cases.")
    parser.add_argument("runs", nargs="*", type=Path, help="recorded live runs")
    parser.add_argument("--variance", type=Path, help="directory of repeat runs")
    parser.add_argument("--out", type=Path, help="write the Markdown here as well as printing it")
    args = parser.parse_args(argv)
    text, _ = build(args.runs, args.variance)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
