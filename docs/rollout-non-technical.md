# Rolling Harbourlight out to a marketing or compliance team

This guide is for the people who will use the pipeline rather than build it, and you don't need to write any code. Where a step needs a terminal the guide says so, and there is usually another way to do it.

The company, people, stories and figures in this repo are all invented.

> **A note on screenshots, written on 11 October 2026.** Claude Cowork's menus and buttons move between releases, so this guide describes where things are instead of showing screenshots that would soon be out of date. If a step doesn't match what you see, look nearby for the same words.

## What you need

- A Claude plan that includes Cowork (in the Claude desktop app) or Claude Code.
- A copy of the `harbourlight` folder on your computer. Your administrator can download it from GitHub for you.
- About twenty minutes for the first run.

## Install it

### In Claude Cowork

1. Open the Claude desktop app and switch to Cowork.
2. Find the plugins area. At the time of writing it is under the customise or settings menu in the sidebar, with a label like "Plugins".
3. Add the plugin. Depending on your version, either add it from a marketplace (enter `cla1redonald/harbourlight`, then install `harbourlight-content`) or upload a zip of the folder.
4. Give Cowork access to the `harbourlight` folder when it asks. The pipeline reads and writes files in `data/` and `references/` inside that folder, so it has to be able to see them.
5. To check it worked, start a new task and type `/content-run`. If the command appears in the list, you're set.

**Then check the approval gate.** Ask Claude to "Add a line to references/watchlist.md." It should refuse, with a message from the Harbourlight approval hook. If it makes the change instead, your version of Cowork isn't running plugin hooks. Undo the change, and make any rule changes in Claude Code until Cowork does run them.

### In Claude Code

In a terminal, inside the `harbourlight` folder, either run:

```
claude --plugin-dir .
```

or install it from the marketplace inside Claude Code:

```
/plugin marketplace add cla1redonald/harbourlight
/plugin install harbourlight-content@harbourlight
```

Commands may show up with the plugin name in front, for example `/harbourlight-content:content-run`. Both forms do the same thing.

## Crawl, walk, run

Don't switch the automation on from day one. Each stage below has an exit test, and you move to the next stage only once it passes.

### Crawl: manual runs (weeks 1 to 2)

- One person (in the demo, Isla Drummond, Content Editor) types `/content-run` once a day and reads every step.
- Compliance (Morag Baird) keeps reviewing every post as she does now, alongside the reviewer, and notes where she and the reviewer disagree.
- The exit test is ten runs in which no FAIL was ever approved, with every disagreement between Morag and the reviewer talked through.

### Walk: a scheduled daily draft (weeks 3 to 6)

- A scheduled task does the research, drafting and review each morning. Nothing is approved automatically. Drafts and their verdicts wait in `data/posts/` until a person looks at them.
- In Cowork, use its scheduled tasks feature. In Claude Code, your administrator can run it on a timer. There is also a hosted schedule for Claude Managed Agents in `agents/harbourlight-daily/`, which runs on weekdays at 07:00 with a $1 limit per run and queues nothing until a named person confirms. It has run once, as a test on 12 October 2026. Ask your administrator before relying on it.
- Move on after a month of drafts that the approver rarely needs to edit, with a monthly report that shows no exceptions.

### Run: scheduled with an approval queue

- Drafts arrive with their verdicts and quoted evidence. The approver works through them and approves, edits or rejects each one.
- The monthly report (`monthly-audit-report` skill) goes to the Head of Compliance.
- Once a month, the `feedback-analyst` agent proposes rule changes, and Morag decides which to apply with `/voice-apply`.

## When the reviewer says FAIL

1. Read the quote. Every finding names a rule (H1 to H7 are hard rules) and quotes the exact words that caused it.
2. Read "what would change", which tells you what has to be different for the post to pass.
3. Either ask Claude to rewrite the post (it gets two tries) or reject it. **A FAIL cannot be approved**, and the audit script will refuse to log it if you try.
4. If you think the reviewer is wrong, reject the post anyway and write down why. The feedback analyst reads rejections, so a rule that keeps catching good posts gets noticed and can be changed with `/voice-apply`.

## When the reviewer says FLAG

FLAG means a person should look at the post. Read each quote. If the post touches on arrears, bereavement, vulnerability or scams, talk to Member Services (Fergus Haig in the demo) before you approve it. However well it is written, a post on a sensitive topic never passes automatically.

## Changing the rules

The rules live in `references/`, and only a named approver can change them. Each change bumps the `voice_version` and is recorded in `data/voice-changelog.md`. To make a change, use `/voice-apply`. Claude will then ask the approver to open the gate themselves, in one of two ways.

- With a terminal, run `make approve APPROVER="Morag Baird"`. The approval lasts 60 minutes.
- Without a terminal, create a plain text file called `.approver` in the folder, containing the line `approver: Morag Baird`.

Delete `.approver` when the change is done.

## Starting again

To put the demo back the way it started, type `/reset-demo`, or run `make reset` in a terminal. It wipes everything in `data/` and restores the seeded September 2026 state. Use it for practice only. Logs on real data are never wiped.

## Who does what

| Person (invented) | Role in the pipeline |
|---|---|
| Isla Drummond, Content Editor | Starts runs, asks for rewrites |
| Euan Lennie, Marketing Lead | Approves, edits or rejects posts |
| Fergus Haig, Member Services | Consulted on every sensitive post |
| Morag Baird, Head of Compliance | Approves rule changes, reads the monthly report |
