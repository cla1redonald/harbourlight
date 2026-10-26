# Evals

The code in this folder scores two kinds of compliance reviewer. The rule-based stand-in is there to test the harness itself. The live reviewer runs on Claude, and was first recorded on 12 October 2026 with one pass each on Haiku 5.5 and Sonnet 5.5 plus five Haiku repeats. The main README has the headline numbers, and `results/report-2026-10-12.md` has all of them.

## What is here

| File | What it does |
|---|---|
| `check_post.py` | The deterministic checker, in stdlib Python. It runs in front of the reviewer on every draft. |
| `test_check_post.py` | A poison sample and a clean sample for every rule, which proves that each rule can fail. |
| `reviewer-cases/` | 24 labelled posts: 2 clean, 2 borderline, and 20 that break a hard rule (3 each for H1 to H5 and H7, 2 for H6). |
| `standin_reviewer.py` | The stand-in reviewer. It is the checker plus the sensitive-topic gate, and its output has the same shape the real reviewer is asked for. |
| `run_reviewer_eval.py` | Scores a reviewer against the labels. It uses the stand-in by default. `--from-recorded` scores a saved run, `--live` calls Claude, and `--live --dry-run` prints the plan and an estimate. |
| `reviewer_prompt.py` | Builds the live request, with the skill, checklist and brand voice as a cached prefix followed by the cited story and the post. Stdlib only. |
| `live_reviewer.py` | Sends the request with `messages.parse` and a pydantic schema, handles refusals and truncation, and prices every response. |
| `ledger.py` | The cost ledger. It appends every response's usage to `results/spend.jsonl` and stops the process when the running total passes $50. |
| `live_report.py` | Compares the stand-in with the recorded live runs on the scores below, and adds cost, latency, flipped cases and a McNemar test. |
| `labels/` | The second-labeller procedure and the kappa tooling. There is no second labeller yet. |
| `results/` | Recorded live runs (`reviewer-<date>-<model>.json`), the Haiku repeats (`variance/`), the spend ledger, the comparison report and the Managed Agents event log. |
| `baseline.json` | The scores the eval must not fall below. |
| `traps.json` | The private answer key for the traps planted in the seed corpus. |
| `variance/` | Run-to-run consistency, meaning how often the verdict changed across N recorded runs. |

## Each labelled case

Each case is a JSON file holding the post text, the expected verdict and rule ids, the phrase a good reviewer should quote, and a note explaining the label. Where the evidence is that the Sources block is missing, the expected quote is `(no sources block)`.

For each hard rule, one case is written so that no pattern can catch it. They are an invented award with a real source (H1c), a product claim that never names the product (H2c), a figure written in words (H3c), advice phrased as "if we were in your shoes" (H4c), a member identified by first name and town (H5c), criticism of unnamed competitors (H6c), and a post that makes light of arrears (H7c). One more miss was not planned. H7b is a scam warning turned into an app promotion, and because it never uses the words "scam" or "fraud", the keyword gate does not see a sensitive topic at all.

## How the numbers are worked out

| Measure | How it is worked out |
|---|---|
| Catch rate per hard rule | Of the cases labelled FAIL for that rule, how many the reviewer flagged with that rule id and a verdict other than PASS. |
| Evidence quoted | Of those catches, how many quoted the expected phrase or a phrase containing it. |
| False positives on clean cases | The clean cases the reviewer did not PASS. The report also gives this over every case labelled PASS, which includes borderline B01. |
| Agreement | Cases where the verdict matched the label exactly, with a 95% Wilson interval. |
| Quoted evidence found in the post | Of all the findings, how many quote words that really are in the post. Whitespace and curly quotes are normalised before matching, and case is not. This is how a model reviewer that makes up its evidence gets caught. |
| No verdict | A refusal, a truncated reply or a reply that fails the schema is recorded as REFUSED, INCOMPLETE or UNPARSED, and counts as both a disagreement and a miss. |
| Flips between reviewers | Cases where two reviewers give different verdicts, with an exact McNemar test on the cases only one of them got right. Above p = 0.05 the report says "within noise". |
| Gate | Red if any hard rule's catches, the agreement or the clean false positives are worse than `baseline.json`. `--seed-fault H3` switches a rule off in the stand-in to prove the gate goes red. |

## What the numbers can support

- The harness works. It scores a reviewer, lists every disagreement and goes red when a rule is broken, and each of H1 to H7 has been switched off in a test to check that the gate turns red.
- The stand-in's blind spots are known and named, so it is clear what a model reviewer has to add.
- Both live models caught all 20 hard-rule cases, the seven written to beat pattern matching among them, and all but one of their quotes were really in the post. Every disagreement with the labels was an H1 finding on a clean or borderline post that adds a small fact the story does not contain. Whether those posts break H1 is as much a question about the labels as about the reviewers.

## What they cannot support

- They say nothing general about Claude. The live runs show how two models did on these 24 posts with this prompt. Haiku and Sonnet are within noise of each other here, and the verdicts on clean and borderline posts change from run to run.
- They give no miss rate for real posts. The stand-in's 65% hard-rule catch rate comes mostly from how the cases were written, since one case per rule was designed to beat pattern matching. It shows the cases work as intended and says nothing about how often posts like that occur.
- They can't separate two reviewers that are close. With 24 cases, an agreement of 15 out of 24 has a 95% interval of roughly 43% to 79%, so a small difference between two reviewers on this set means nothing.
- The labels are not independent. The rules, the posts and the labels were all written by one person. A second labeller is still to come, and `labels/second-labeller-template.md` sets out how that will work.
- The stand-in alone says nothing about consistency. Its variance fixtures show 0 changes across five runs only because the stand-in is deterministic. A model is not, which is why the variance script exists. `make live` records five Haiku repeats under `results/variance/`, and the script reports how often the verdicts and the cited rule sets changed, and how many cases agreed on both in every repeat.

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

Only regenerate `baseline.json` with `--write-baseline` when a reviewer change is a deliberate improvement, and say so in the commit.
