# Second labeller: how to label the 24 cases blind

Status: **pending**. No second person has labelled the cases yet. Every agreement figure in this repo compares a reviewer with one person's labels, and the same person wrote the rules and the posts. A model is not used as a second labeller, because that would only show whether two machines agree. It would not show whether the labels are right.

## Who should do it

Someone who reads compliance copy for a living and has not seen this repo's labels, notes or eval results. A compliance officer, a senior marketing approver or a member-services lead would be ideal. It takes about an hour.

## What they are given

1. `references/compliance-checklist.md`, with its appendix of approved product lines.
2. `references/brand-voice.md`.
3. For each case, the post text and the story it cites (from `data-pristine/incoming-stories.md`).
4. A blank copy of the sheet below.

## What they are not given

They must not see the case files in `evals/reviewer-cases/`, which hold the labels and notes, or the case ids, which give the answer away (H4c means "H4, the hard one"). Keep `evals/README.md`, every eval report and any output from the stand-in or a model away from them as well. To keep the exercise blind, whoever runs it exports the posts with neutral ids:

```
python3 evals/labels/agreement.py export --out blind-pack/
```

This writes one Markdown file per post, `P01.md` to `P24.md` in shuffled order, each with the story it cites. It also writes `key.json`, which maps the neutral ids back to the case ids. The labeller gets only the Markdown files, and the organiser keeps `key.json`.

## The sheet

Fill in one row per post, then copy the sheet to `evals/labels/second-labeller.csv`.

```
post,verdict,rules,quote,notes
P01,FAIL,H4,"exact words from the post",one line on why
P02,PASS,,,
```

- `verdict` is PASS, FLAG or FAIL, as the checklist defines them.
- `rules` lists every rule id that applies, separated by spaces (`H6 H7`). Leave it empty for a PASS.
- `quote` is the phrase that mainly decided the verdict, copied exactly.
- Label from the checklist as it is written. Where it is unclear, make a choice and say so in `notes`. Those notes show where the checklist may need rewriting.

## How agreement is computed

```
python3 evals/labels/agreement.py score evals/labels/second-labeller.csv --key blind-pack/key.json
```

- Verdict agreement is Cohen's kappa over the three verdicts, with the raw percentage beside it. Kappa corrects for the agreement two people would reach by chance, given how often each of them uses each verdict, and is worked out as kappa = (observed - expected) / (1 - expected).
- For each hard rule, the script gives kappa on "applies or not" across the 24 posts. It also gives the Jaccard overlap of the two rule sets for each post.
- It then lists every post where the verdicts differ, with both labels and both quotes, for the two labellers to talk through.

On 24 posts the interval around kappa is wide. Above 0.8 counts as strong agreement, and 0.6 to 0.8 as substantial. Below 0.6, the checklist or the labels (or both) need work before any reviewer score means much. The script prints a bootstrap 95% interval so that nobody reads meaning into the second decimal place.

## After scoring

1. The two labellers meet and settle each disagreement, writing down why.
2. If the checklist caused a disagreement, fix it with a rule change through `/voice-apply`, with a named approver and a version bump. Don't quietly relabel the case.
3. Replace the original labels in `evals/reviewer-cases/` with the settled ones, in a single commit that lists every case that changed. Then re-run the README's agreement figures against the new labels.
