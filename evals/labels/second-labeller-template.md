# Second labeller: how to label the 24 cases blind

Status: **pending**. No second person has labelled the cases yet. Every agreement figure in this repo is against one person's labels, and that person also wrote the rules and the posts. A model is not used as a second labeller: it would measure agreement between two machines, not whether the labels are right.

## Who should do it

Someone who reads compliance copy for a living and has not seen this repo's labels, notes or eval results. A compliance officer, a senior marketing approver, or a member-services lead is ideal. They need about an hour.

## What they are given

1. `references/compliance-checklist.md`, with its appendix of approved product lines.
2. `references/brand-voice.md`.
3. For each case, the post text and the story it cites (from `data-pristine/incoming-stories.md`).
4. A blank copy of the sheet below.

## What they are not given

The case files in `evals/reviewer-cases/` (they hold the labels and notes), the case ids' meanings (H4c says "H4, the hard one"), `evals/README.md`, any eval report, and the stand-in's or a model's output. To keep it blind, the person running the exercise exports the posts with neutral ids:

```
python3 evals/labels/agreement.py export --out blind-pack/
```

That writes one Markdown file per post, named `P01.md` to `P24.md` in a shuffled order, with its cited story, plus `key.json` mapping the neutral ids back to case ids. The labeller gets the Markdown files only. `key.json` stays with the organiser.

## The sheet

One row per post. Copy it to `evals/labels/second-labeller.csv` when it is filled in.

```
post,verdict,rules,quote,notes
P01,FAIL,H4,"exact words from the post",one line on why
P02,PASS,,,
```

- `verdict` is PASS, FLAG or FAIL, as the checklist defines them.
- `rules` lists every rule id that applies, separated by spaces (`H6 H7`), or is empty for a PASS.
- `quote` is the main phrase that decided it, copied exactly.
- Label from the checklist as written. Where it is unclear, choose, and say so in `notes`. The unclear cases are the most useful output.

## How agreement is computed

```
python3 evals/labels/agreement.py score evals/labels/second-labeller.csv --key blind-pack/key.json
```

- **Verdict agreement**: Cohen's kappa over the three verdicts, with the raw percentage beside it. Kappa corrects for the agreement two people would reach by chance given how often each uses each verdict: kappa = (observed - expected) / (1 - expected).
- **Rule agreement**: for each hard rule, kappa on "applies or not" across the 24 posts, and the Jaccard overlap of the two rule sets per post.
- **Disagreements**: every post where the verdicts differ, with both labels and both quotes, for the two labellers to talk through.

How to read kappa on 24 posts: the interval is wide. Above 0.8 is strong agreement; 0.6 to 0.8 is substantial; below 0.6 means the checklist, the labels, or both need work before any reviewer score means much. The script prints a bootstrap 95% interval so nobody reads a second decimal place into it.

## After scoring

1. The two labellers meet and settle each disagreement, writing down why.
2. Where the checklist caused the disagreement, the fix is a rule change through `/voice-apply`, with a named approver and a version bump, not a quiet relabel.
3. Settled labels replace the originals in `evals/reviewer-cases/` in one commit that lists every changed case, and the README's agreement figures are re-run against them.
