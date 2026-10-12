# 0003: The deterministic checker runs in front of the model reviewer

Status: accepted, Phase 2a

## Context

Some rules are mechanical: word count, British spelling, em dashes, a figure with no source line, a product named outside its approved wording, a sensitive keyword. A model can check these, but it will occasionally miss one, and each miss costs the same as a judgement call. Other rules need judgement: is this sentence advice, is this person identifiable, is this fact in the source.

## Decision

`evals/check_post.py` runs on every draft before the reviewer. It is stdlib Python, has a poison and a clean test for every rule, and costs nothing to run. The run's verdict is the more severe of the checker and the reviewer. The reviewer does not see the checker's output, so the two are independent and their disagreements are visible.

A sensitive keyword sets "needs human" in the checker, and that can never be overridden into a PASS.

## Consequences

- The reviewer's attention goes on judgement, and its mistakes on mechanical rules are caught regardless.
- The checker is honest about its limits: the eval set includes one case per hard rule that it cannot catch, and they are listed in every eval report.
- The checker produces false positives (a boiler "struggling" is not a member in hardship). Those cost a person a minute, which is the right way round.
- Two lists (the checker's `rules.json` and the checklist prose) must stay in step. A test checks the product lines; the rest relies on review.
