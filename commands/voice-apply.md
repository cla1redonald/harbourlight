---
description: Apply one proposed change to the Harbourlight rules or voice guide, only with a named human approver; bumps voice_version and logs the change.
argument-hint: "<proposal text, or the feedback-analyst block>"
---

# Apply a rule or voice change

Files under `references/` and `skills/` are the rules the pipeline follows. Changing them is a governance decision. A shell hook (`hooks/require-approver.sh`) blocks every write to them unless a person has named themselves as approver. You cannot get round it and must not try.

## 1. Show the proposal

Restate the proposal from `$ARGUMENTS`: which file, the exact current text, the exact new text, and the evidence. If any of these is missing, stop and ask for it. Do not invent evidence.

## 2. Get a named approver

Ask: "Who is approving this change?" Rule changes are approved by the Head of Compliance (see `references/company.md`) or someone they have named. Wait for a full name. A role, "me" or "yes" is not enough.

## 3. The approver opens the gate

You cannot do this step for them; the hook blocks you from creating the marker. Ask the approver to do one of these themselves:

- In a terminal, in the project folder: `make approve APPROVER="Full Name"`. The marker lasts 60 minutes.
- Without a terminal (for example in Cowork): create a plain text file called `.approver` in the project folder containing the line `approver: Full Name`.
- Or restart Claude Code with `HARBOURLIGHT_APPROVER="Full Name"` set.

Wait for them to say it is done.

## 4. Apply the change

Make exactly the proposed edit, nothing more. If the change touches product lines, update all three places together: `references/rules.json`, `references/approved-claims.md` and the appendix of `references/compliance-checklist.md`.

## 5. Bump the version

Increase `voice_version` in `references/rules.json` by one.

## 6. Log it

Append to `data/voice-changelog.md`, never editing earlier entries:

```
## vN (YYYY-MM-DD)

- Approved by: Full Name, role
- Proposed by: name, or feedback-analyst
- Change: one or two sentences
- Evidence: quoted dates or case ids
- Files: list
```

## 7. Check nothing broke

Run `make test`. If the reviewer eval baseline no longer holds because of this change, report the numbers; do not regenerate the baseline unless the approver agrees the change is an improvement, and log that too.

## 8. Close the gate

Remind the approver to delete `.approver` now (or let it expire). Report the new `voice_version` and the changelog entry.
