---
description: Run the Harbourlight pipeline once - research, draft, deterministic check, independent review, then a human decision that is logged.
argument-hint: "[story id, e.g. S02, to skip research]"
---

# Content run

Run the pipeline once, end to end. Read `CLAUDE.md` first if you have not already; its hard rules apply to every step. Never publish anything: this command ends with files on disk and a row in the audit log. A person publishes.

Note the current `voice_version` from `references/rules.json`. Every file and log row in this run uses it.

## 1. Research

- If `$ARGUMENTS` names a story id, use that story and record the trigger as `editor-picked`. Check its `Status` is `new`; if not, stop and say why.
- Otherwise use the `market-research` skill. The trigger is `manual` (or `scheduled` when run by a scheduler). Show the chosen stories and ask which one to draft. If the person does not mind, take the first.

## 2. Draft

Use the `post-writer` skill on that one story. It writes `data/posts/YYYY-MM-DD-slug.draft.md` and runs the checker on it.

## 3. Deterministic check

Run `python3 evals/check_post.py --json <draft path>` and keep the result. Do not show it to the reviewer.

## 4. Independent review

Start the `compliance-reviewer` agent with only this message: `Review <draft path>.` Do not pass the story choice, the writer's reasoning, the checker output or anything else. If agents are not available (for example in Cowork), start a fresh task and use the `compliance-reviewer` skill on the draft path alone.

## 5. Combine

The run's verdict is the more severe of the checker and the reviewer (FAIL over FLAG over PASS). List every finding from both, each with its rule id and quote, and say which of the two raised it. If they disagree, say so plainly; the disagreement is useful evidence.

If the verdict is **FAIL**: show what would have to change. Offer to rewrite (back to step 2, at most twice) or to reject. A FAIL cannot be approved.

## 6. Human decision

Show the person the full draft, the verdict, and every quoted finding. For anything touching arrears, bereavement, vulnerability or scams, remind them that Fergus Haig (Member Services) should be consulted. Then ask, and wait for an answer:

> Approve, edit or reject? And what is your name?

Never assume an answer. Never treat silence, "looks fine" from yourself, or a PASS as approval.

- **Approve**: copy the draft to `data/posts/<same name>.final.md`, change `stage: draft` to `stage: final`, and add `approved_by: <name>` and `approved: <date>` to the front matter.
- **Edit**: apply the person's edits to a copy, run steps 3 and 4 again on the edited version, show the new verdict, and ask again. Record a one-line `edit_summary`.
- **Reject**: keep the draft, write no final file, and ask for the main rule or reason.

Then ask whether the post has been, or will now be, published by them. Record `posted` as `yes` only if they say so.

## 7. Record

1. Mark the story: `python3 scripts/mark_story.py <id> used` on approval, or `python3 scripts/mark_story.py <id> rejected --rule <rule>` on rejection.
2. Append the audit row with `python3 scripts/append_audit.py` and all its fields: run trigger, the story headline and URL, verdict, verdict reasons (`rule: "quote"` pairs separated by `; `, or `none`), human decision as `approved (Name)`, `approved with edit (Name)` or `rejected (Name)`, edit summary, posted, and the post file. The script refuses rows that break the rules; if it refuses, fix the cause, never the log.
3. Update "Posts drafted from this run" in the latest research-log entry, if there is one for this run, by appending a line.

## 8. Report back

Three lines: the story, the verdict and decision, and the files written.
