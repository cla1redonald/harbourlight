# Rolling Harbourlight out to a marketing or compliance team

This guide is for people who will use the pipeline, not build it. You do not need to write code. Where a step needs a terminal, it says so, and there is usually a way round it.

Everything in this repo is invented: the company, the people, the stories and the figures.

> **A dated note on screenshots (11 October 2026).** Claude Cowork's menus and buttons move between releases. This guide describes where things are rather than showing screenshots, because a picture of last month's button is worse than none. If a step does not match what you see, look for the same words nearby.

## What you need

- A Claude plan that includes Cowork (in the Claude desktop app) or Claude Code.
- A copy of the `harbourlight` folder on your computer. Your administrator can download it from GitHub for you.
- About twenty minutes for the first run.

## Install it

### In Claude Cowork

1. Open the Claude desktop app and switch to Cowork.
2. Find the plugins area. At the time of writing it sits under the customise or settings menu in the sidebar, labelled something like "Plugins".
3. Add the plugin, either from a marketplace (enter `cla1redonald/harbourlight`, then install `harbourlight-content`) or by uploading a zip of the folder, whichever your version offers.
4. Give Cowork access to the `harbourlight` folder when it asks. The pipeline reads and writes files in `data/` and `references/` inside that folder, so it must be able to see them.
5. Check it worked: start a new task and type `/content-run`. If the command appears in the list, you are set.

**Check the approval gate.** Ask Claude: "Add a line to references/watchlist.md." It should refuse with a message from the Harbourlight approval hook. If it makes the change instead, your version of Cowork is not running plugin hooks: undo the change, and make rule changes in Claude Code until it does.

### In Claude Code

In a terminal, inside the `harbourlight` folder, either:

```
claude --plugin-dir .
```

or install it from the marketplace inside Claude Code:

```
/plugin marketplace add cla1redonald/harbourlight
/plugin install harbourlight-content@harbourlight
```

Commands may appear with the plugin name in front, for example `/harbourlight-content:content-run`. Both forms do the same thing.

## Crawl, walk, run

Do not switch on the automation on day one. Each stage has an exit test; move on only when it passes.

### Crawl: manual runs (weeks 1 to 2)

- One person (in the demo, Isla Drummond, Content Editor) types `/content-run` once a day and reads every step.
- Compliance (Morag Baird) reviews every post as they do today, alongside the reviewer, and notes where they disagree.
- **Exit test:** ten runs, no FAIL ever approved, and every disagreement between Morag and the reviewer talked through.

### Walk: a scheduled daily draft (weeks 3 to 6)

- A scheduled task runs research, drafting and review each morning. Nothing is approved automatically: drafts and verdicts wait in `data/posts/` for a person.
- In Cowork, use its scheduled tasks feature; in Claude Code, your administrator can run it on a timer. A hosted schedule on Claude Managed Agents is defined in `agents/harbourlight-daily/` (weekdays at 07:00, a $1 limit per run, nothing queued without a named person confirming), but it has not been run yet; ask your administrator before relying on it.
- **Exit test:** a month of drafts where the approver rarely needs to edit, and the monthly report shows no exceptions.

### Run: scheduled with an approval queue

- Drafts arrive with their verdicts and quoted evidence; the approver works through them and approves, edits or rejects.
- The monthly report (`monthly-audit-report` skill) goes to the Head of Compliance.
- Once a month, the `feedback-analyst` agent proposes rule changes, and Morag decides which to apply with `/voice-apply`.

## When the reviewer says FAIL

1. Read the quote. Every finding names a rule (H1 to H7 are hard rules) and quotes the exact words that caused it.
2. Read "what would change". It tells you what has to be different for the post to pass.
3. Choose: ask Claude to rewrite (it gets two tries), or reject. **A FAIL cannot be approved.** The audit script will refuse to log it.
4. If you think the reviewer is wrong, reject anyway and say why. That is useful: the feedback analyst reads rejections, and a rule that keeps catching good posts can be changed properly.

## When the reviewer says FLAG

FLAG means "a person should look at this". Read each quote. If the post touches arrears, bereavement, vulnerability or scams, talk to Member Services (Fergus Haig in the demo) before approving. A sensitive post is never auto-passed, however well written.

## Changing the rules

The rules live in `references/`. Only a named approver can change them, and every change bumps the `voice_version` and is written to `data/voice-changelog.md`. Use `/voice-apply`. Claude will ask the approver to open the gate themselves:

- with a terminal: `make approve APPROVER="Morag Baird"` (lasts 60 minutes);
- without one: create a plain text file called `.approver` in the folder, containing `approver: Morag Baird`.

Delete `.approver` when the change is done.

## Starting again

To put the demo back to how it started, type `/reset-demo` (or `make reset` in a terminal). It wipes everything in `data/` and restores the seeded September 2026 state. It is for practice only. On real data, logs are never wiped.

## Who does what

| Person (invented) | Role in the pipeline |
|---|---|
| Isla Drummond, Content Editor | Starts runs, asks for rewrites |
| Euan Lennie, Marketing Lead | Approves, edits or rejects posts |
| Fergus Haig, Member Services | Consulted on every sensitive post |
| Morag Baird, Head of Compliance | Approves rule changes, reads the monthly report |
