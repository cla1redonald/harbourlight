# Evals

This folder measures the compliance reviewer: a rule-based stand-in, which measures the harness, and the live reviewer on Claude, first recorded on 12 October 2026 (Haiku 5.5 and Sonnet 5.5, one pass each, plus five Haiku repeats). The headline numbers are in the main README; everything is in `results/report-2026-10-12.md`.

## What is here

| File | What it does |
|---|---|
| `check_post.py` | The deterministic checker. Stdlib Python. Runs in front of the reviewer on every draft. |
| `test_check_post.py` | A poison sample and a clean sample for every rule, so every rule is proven able to fail. |
| `reviewer-cases/` | 24 labelled posts: 2 clean, 2 borderline, and 20 that break a hard rule (3 each for H1 to H5 and H7, 2 for H6). |
| `standin_reviewer.py` | The stand-in: the checker plus the sensitive-topic gate, returning output in the same shape the real reviewer is asked for. |
| `run_reviewer_eval.py` | Scores a reviewer against the labels. Stand-in by default; `--from-recorded` scores a saved run; `--live` calls Claude; `--live --dry-run` prints the plan and an estimate. |
| `reviewer_prompt.py` | Builds the live request: the skill, checklist and brand voice as a cached prefix, then the cited story and the post. Stdlib only. |
| `live_reviewer.py` | Sends it with `messages.parse` and a pydantic schema, handles refusals and truncation, and prices every response. |
| `ledger.py` | The cost ledger. Appends every response's usage to `results/spend.jsonl` and stops the process when the running total passes $50. |
| `live_report.py` | Compares the stand-in and recorded live runs: the scores below plus cost, latency, flipped cases and a McNemar test. |
| `labels/` | The second-labeller procedure and the kappa tooling. No second labeller yet. |
| `results/` | Recorded live runs (`reviewer-<date>-<model>.json`), the Haiku repeats (`variance/`), the spend ledger, the comparison report and the Managed Agents event log. |
| `baseline.json` | The scores the eval must not fall below. |
| `traps.json` | The private answer key for the traps planted in the seed corpus. |
| `variance/` | Run-to-run consistency: given N recorded runs, how often did the verdict change? |

## Each labelled case

A JSON file with the post text, the expected verdict, the expected rule ids, the phrase a good reviewer should quote, and a note on why. When the evidence is an absence (no Sources block), the expected quote is `(no sources block)`.

For each hard rule, one case is written so that a pattern cannot catch it: an invented award with a real source (H1c), a product claim that never names the product (H2c), a figure written in words (H3c), advice phrased as "if we were in your shoes" (H4c), a member identified by first name and town (H5c), criticism of unnamed competitors (H6c), and a post that makes light of arrears (H7c). One further miss was not planned: H7b is a scam warning turned into an app promotion that never uses the words "scam" or "fraud", so the keyword gate does not see a sensitive topic at all.

## How the numbers are worked out

- **Catch rate per hard rule**: of the cases labelled FAIL for that rule, how many the reviewer flagged with that rule id and a verdict other than PASS.
- **Evidence quoted**: of those catches, how many quoted the expected phrase (or a phrase containing it).
- **False positives on clean cases**: clean cases the reviewer did not PASS. Also reported over every case labelled PASS, which includes borderline B01.
- **Agreement**: cases where the verdict matched the label exactly, with a 95% Wilson interval.
- **Quoted evidence found in the post**: of every finding, how many quote words that are really in the post (whitespace and curly quotes normalised, case not). This is how a model reviewer that invents its evidence gets caught.
- **No verdict**: a refusal, a truncated reply or one that fails the schema is recorded as REFUSED, INCOMPLETE or UNPARSED, and scores as a disagreement and a miss.
- **Flips between reviewers**: cases where two reviewers give different verdicts, with an exact McNemar test on the cases only one got right. Above p = 0.05 the report says "within noise".
- **Gate**: red if any hard rule's catches, the agreement, or the clean false positives are worse than `baseline.json`. `--seed-fault H3` switches a rule off in the stand-in to prove the gate goes red.

## What the numbers can support

- The harness works: it scores a reviewer, lists every disagreement, and goes red when a rule is broken. Every one of H1 to H7 has been switched off in a test and turned the gate red.
- The stand-in's blind spots are specific and named, which shows what a model reviewer has to add.
- Both live models caught every hard-rule case, including the seven written to beat pattern matching, and every quote but one was really in the post. Their disagreements with the labels are all H1 findings on clean or borderline posts that add a small fact the story does not contain, which is a labelling question as much as a reviewer one.

## What they cannot support

- **A general claim about Claude.** The live runs say how two models did on these 24 posts with this prompt. Haiku and Sonnet are within noise of each other here, and the clean and borderline posts swing between runs.
- **A real-world miss rate.** The 65% hard-rule catch rate is mostly a consequence of how the cases were written: one case per rule was designed to beat pattern matching. It says the cases do their job, not how often such posts occur.
- **Precision.** With 24 cases, an agreement of 15 out of 24 has a 95% interval of roughly 43% to 79%. Small differences between two reviewers on this set mean nothing.
- **Independent labels.** One person wrote the rules, the posts and the labels. A second labeller is pending; see `labels/second-labeller-template.md`.
- **Consistency.** The variance fixtures show 0 changes across five runs because the stand-in is deterministic. A model will not be, and that number is the reason the variance script exists. `make live` records five Haiku repeats under `results/variance/`, and the script reports verdict changes, cited-rule-set changes and how many cases agreed on both across every repeat.

## Commands

```
python3 evals/run_reviewer_eval.py                     # full report
python3 evals/run_reviewer_eval.py --seed-fault H3     # must go red (exit 1)
python3 evals/run_reviewer_eval.py --record run.json   # save outputs
python3 evals/run_reviewer_eval.py --from-recorded run.json
python3 evals/variance/verdict_variance.py evals/variance/fixtures/
python3 evals/run_reviewer_eval.py --live --dry-run    # the plan and a cost estimate, no calls
python3 evals/run_reviewer_eval.py --live --model claude-sonnet-5-5   # needs ANTHROPIC_API_KEY
python3 evals/run_reviewer_eval.py --live --model claude-haiku-5-5 --repeats 5 --out-dir evals/results/variance
python3 evals/live_report.py evals/results/reviewer-*.json --variance evals/results/variance
python3 evals/ledger.py                                # spend so far, by model and run
```

Regenerate `baseline.json` with `--write-baseline` only when a reviewer change is a deliberate improvement, and say so in the commit.
