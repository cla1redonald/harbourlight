# Harbourlight

A marketing team at a regulated company wants to post about what is in the news. It can't wait three days for every compliance review, and it can't afford a rushed post that ends in a fine. Harbourlight shows how to give Claude that job properly, and you can run it. Claude researches the news and drafts a post. A separate reviewer checks the draft against the rules and quotes the words behind every finding. A named person then approves or rejects it, and each decision goes into an audit log that a compliance officer can read.

**Everything here is invented.** Harbourlight Mutual and its regulator, the Conduct Standards Authority, were made up for this demo, and so were the people, the products, the news stories, the outlets and every figure. The URLs use the reserved `example.invalid` domain and go nowhere.

The repo is also a worked example of rolling Claude Cowork out to people who don't write code. The whole pipeline installs as a plugin, and the [rollout guide](docs/rollout-non-technical.md) is written for a marketing or compliance lead.

## Run the demo in a minute

You need Python 3.12 or later and `make`. There is nothing to install, and it doesn't need an API key or a network connection.

```
git clone https://github.com/cla1redonald/harbourlight
cd harbourlight
make demo
```

`make demo` checks the three seeded posts and scores the reviewer against 24 labelled posts. It then switches one rule off to show that the eval goes red, and measures how much the verdicts vary from one run to the next. It prints the plan and cost estimate for a live run without calling the API, even if you have a key set, and finishes with the audit log and the September report. `make test` runs every Python unit test, and `make reset` puts the demo data back the way it started.

To run the reviewer on Claude, set an API key, run `pip install -r requirements-live.txt` and then `make live`. If you have Node 22, `make policy-server` builds and tests the policy MCP server.

To use the pipeline itself, open the folder in Claude Code with `claude --plugin-dir .` and type `/content-run`.

## What is in the box

| Path | What it is |
|---|---|
| `CLAUDE.md` | The standing brief. It opens with which folder holds what and who may change it, then sets out the hard rules. |
| `references/` | The brand voice, five products with one approved line each, five watchlist themes, the compliance checklist (hard rules H1 to H7, soft rules S1 to S5) and `rules.json`, which the checker reads. |
| `skills/` | `market-research`, `post-writer`, `compliance-reviewer`, `monthly-audit-report`. |
| `agents/` | `story-scout` (one per theme), `compliance-reviewer` and `feedback-analyst`. All three are read-only. |
| `commands/` | `/content-run`, `/voice-apply`, `/reset-demo`. |
| `hooks/` | The approval gate, which is a shell script. |
| `data/` | 27 news stories for September 2026 with ten traps planted among them, the research log, the audit log, the voice changelog and three seeded posts. `data-pristine/` is the copy used for a reset. |
| `evals/` | The deterministic checker and its tests, 24 labelled reviewer cases, the eval harness (stand-in and live), the cost ledger, the comparison report, the variance check, and the kit for a second labeller in `evals/labels/`. |
| `mcp/policy-server/` | A read-only MCP server that gives any agent the approved claims, the checklist, the voice rules and the checker. |
| `agents/harbourlight-daily/` | The agent, environment and schedule for running the weekday content run on Managed Agents. |
| `scripts/` | Audit-log append, story status, monthly report, reset, deny-list, and the Managed Agents orchestrator with its policy bridge. |
| `docs/` | The rollout guide and five short decision records. |

### The pipeline

1. Research picks one story for each watchlist theme and steps around the traps. They include a named customer, a competitor's data breach, a figure nobody can source, a thin story, a duplicate under a new headline, something out of scope, and a story with an instruction hidden in it for any AI that reads it.
2. The writer drafts one post from one story. It runs to 120 to 220 words and uses only facts from that story and only the approved product lines.
3. A deterministic checker goes first, looking at word count, spelling, filler words, em dashes, product wording, unsourced figures, named people, competitors and sensitive topics.
4. A separate reviewer agent sees only the draft and the checklist, and returns PASS, FLAG or FAIL. Every finding carries a rule id and an exact quote, and a FAIL says what would have to change.
5. A person approves, edits or rejects the post, and puts their name to the decision. Nobody can approve a FAIL.
6. The draft and the final version are saved, the story's status is updated, and one row is added to the audit log.

## The governance

- The reviewer runs in its own context. It never sees the writer's reasoning, the research notes or the checker's output, only the words a member would read. ([0001](docs/design/0001-reviewer-independence.md))
- The approval gate is a shell script rather than an instruction in a prompt. A PreToolUse hook blocks any change to `references/` or `skills/` until a person has named themselves as approver, and Claude cannot create the approval marker itself. ([0002](docs/design/0002-named-approver-and-version-bump.md))
- Only one script writes to the audit log, and it only ever appends. It refuses any row that breaks the rules, such as a FAIL marked approved or a decision with no name on it. A test checks that the seeded rows have never been altered.
- Each rule change bumps `voice_version` and names its approver in the changelog. Every audit row records the version the post was judged under.
- The deterministic checker runs first because it is cheap, and catches the mechanical failures before the model reviewer looks for the ones that need judgement. ([0003](docs/design/0003-deterministic-checker-first.md))

## What is tested

There are 168 Python unit tests and 11 Node tests. On the Python side, every checker rule has a poison sample and a clean sample, and the approval hook is tested the way Claude Code runs it. The rest cover the audit and reset scripts, the eval harness, the cost ledger and its hard stop, the live reviewer against a fake API client, the comparison report, the variance script, the second-labeller tools, the Managed Agents orchestrator against a fake client and a stub MCP server, the deny-list script and the integrity of the seed data. The Node tests drive the policy server over a real stdio transport. They check that its checker gives the same answer as the Python one on all 24 cases and the five seeded posts.

### The stand-in reviewer

| Measure | Result |
|---|---|
| Posts | 24 (2 clean, 2 borderline, 20 breaking a hard rule) |
| Catches, H1 to H5 and H7 | 2 of 3 each |
| Catches, H6 | 1 of 2 |
| Hard-rule catches overall | 13 of 20 (65%) |
| False positives on clean posts | 0 of 2 |
| Verdict agreement with labels | 15 of 24 (62%), 95% Wilson interval 43% to 79% |
| Quoted evidence found in the post | 19 of 19 findings |
| Seeded fault (H3 switched off) | gate goes red (every hard rule has been tested this way) |
| Run-to-run verdict changes | 0 of 24 across five recorded runs |

The stand-in was meant to miss some of these. For each hard rule, one case was written so that pattern matching would not catch it. Those seven are an invented award with a real source, a product claim that never names the product, a figure written in words, advice phrased as "if we were in your shoes", a member identified by first name and town, criticism of unnamed competitors, and a post that makes light of arrears. A scam warning that never says "scam" also got through, and nobody planned that one.

The stand-in is the checker plus a keyword gate for sensitive topics, with no model in it, so these numbers test the harness. They show that the eval can tell a working reviewer from a broken one and list every disagreement. They tell you nothing about how well Claude reviews.

### The live reviewer, 12 October 2026

The reviewer skill then ran on Claude over the same 24 posts, and the same harness scored it. Each model had one pass: `claude-haiku-5-5` at effort `medium` and `claude-sonnet-5-5` at effort `high`, which are their defaults. Haiku then ran five more times so the variance could be measured. The [full report](evals/results/report-2026-10-12.md) lists every flip and every disagreement, and the raw outputs are in the same folder.

| Measure | Stand-in | Haiku 5.5 | Sonnet 5.5 |
|---|---|---|---|
| Catches, each hard rule H1 to H7 | 2 of 3 (H6: 1 of 2) | 3 of 3 (H6: 2 of 2) | 3 of 3 (H6: 2 of 2) |
| Hard-rule catches overall | 13 of 20 | 20 of 20 | 20 of 20 |
| False positives on clean posts | 0 of 2 | 1 of 2 (C02, FLAG) | 1 of 2 (C01, FAIL) |
| Verdict agreement with labels | 15 of 24 (62%), 43% to 79% | 22 of 24 (92%), 74% to 98% | 21 of 24 (88%), 69% to 96% |
| Quoted evidence found in the post | 19 of 19 | 58 of 58 | 86 of 87 |
| Cost per case, USD (median, p95, max, mean) | 0 | 0.00098, 0.00121, 0.00146, 0.00096 | 0.0216, 0.0242, 0.0311, 0.0211 |
| Latency per case, seconds (p50, p90, p95, max) | under 0.1 | 8.0, 10.8, 11.5, 12.6 | 13.2, 14.5, 14.6, 15.3 |
| Cost of one 24-post pass, USD | 0 | 0.023 | 0.51 |

Intervals are 95% Wilson. No reply was refused, cut short or outside the schema, and no cost had to be estimated.

Haiku returned FLAG on H1 for B01 and C02, which are both labelled PASS. Sonnet returned FAIL on H1 for C01 and B01, both labelled PASS, and FAIL on H1 and S3 for B02, which is labelled FLAG. In every one of these, a clean or borderline post adds a small everyday fact that the cited story does not contain, such as "it is reasonable to ask to see their card", "find the end date on your annual statement" or "a genuine lender will not mind you checking". The checklist says every factual statement must come from the cited story, so the models have a point, and the labels let these through. The second labeller should settle it, and the checklist may need to change. Relabelling the cases to match the models would only hide the question. Sonnet's one quote that was not in the post came from an S4 finding, which quoted a word count instead of the post's own words.

Both models caught the eight cases the stand-in missed or under-called, which are the seven written to beat pattern matching plus H7b. Haiku's improvement on the stand-in is the only difference that 24 posts can support (exact McNemar p = 0.039). Sonnet's improvement on the stand-in is within noise (p = 0.109), and so is the gap between Haiku and Sonnet (p = 1.0). The two models differ on four cases, all of them clean or borderline and all about H1. On this set Sonnet costs about 22 times as much per case as Haiku and takes about 1.6 times as long, with no gain you can measure.

### Variance: five more Haiku passes

| Measure | Result |
|---|---|
| Cases where every repeat gave the same verdict | 21 of 24 |
| Cases whose verdict changed at least once | 3 of 24 (B01, C01, C02) |
| Cases whose cited rule set changed at least once | 20 of 24 |
| Cases where every repeat agreed on verdict and rules | 4 of 24 |
| Individual verdicts matching the case's most common verdict | 114 of 120 |

Every post that breaks a hard rule got FAIL in all five repeats. The verdicts that moved were on the clean and borderline posts, which swung between PASS, FLAG and FAIL on H1. The rules cited alongside the right one moved as well, with an extra H1 or H4 turning up in some repeats and not in others. Across all six Haiku passes, agreement ranged from 21 to 23 of 24, and false positives on the two clean posts from 0 to 2, so the single pass in the table above was one of the better runs. In one repeat Haiku failed H6a without citing H6, which brought its catch count for that run to 19 of 20. On a post that breaks a hard rule, one run was enough, because every repeat gave FAIL. On a clean or borderline post, one run on its own is not enough.

These numbers have limits. With only 24 cases the intervals are wide, and most differences between reviewers are noise. One person wrote the rules, the posts and the labels, so agreement here means agreement with that person. And because one case per rule was built to beat pattern matching, the catch rates describe this set of cases. They don't tell you how often posts like these turn up in real life.

Each response was priced at list rates and recorded in [evals/results/spend.jsonl](evals/results/spend.jsonl). There are 171 rows, coming to $0.69 in total. The Sonnet pass cost $0.51, the six Haiku passes and a two-post smoke test cost $0.14 between them, and the Managed Agents session cost $0.05. The code stops itself once spending passes $50.

Nobody else has labelled the cases yet. [evals/labels/second-labeller-template.md](evals/labels/second-labeller-template.md) explains how a second person can label them blind and how agreement between the two will be measured with Cohen's kappa. A model won't be used in their place, because two machines agreeing would not show whether the labels are right.

[evals/README.md](evals/README.md) has the detail.

## Consulting the policy from any agent

The rules live in files, but any tool that writes for Harbourlight should be able to check them without keeping its own copy. `mcp/policy-server/` is a read-only MCP server over stdio with five tools:

| Tool | What it answers |
|---|---|
| `list_approved_claims` | The five products and the one approved line for each |
| `check_claim(text)` | Is this sentence exactly an approved line? Returns the matching claim, or none, and which product it names |
| `check_post(text)` | The deterministic checker on a whole post: verdict, findings with rule ids and quotes, what would change a FAIL |
| `get_checklist()` | The compliance checklist |
| `get_voice_rules()` | The brand voice guide and its machine-checkable parts |

The server has no resources or prompts. It reads a fixed list of six files once when it starts, never writes, and rejects any argument it isn't expecting. Any MCP client can use it, whether that's a writer agent checking a product line before it drafts, an approver's assistant or a plug-in in a publishing tool. To add it to Claude Code, run:

```
make policy-server
claude mcp add harbourlight-policy -- node "$(pwd)/mcp/policy-server/dist/src/index.js"
```

Other clients use the same command (`node .../dist/src/index.js`) in their stdio server settings. A PASS from `check_post` only means the draft got through the cheap check. It still has to go to the independent reviewer and a named approver. ([0005](docs/design/0005-phase-2b.md), items 13 and 14)

## The scheduled run on Managed Agents

`agents/harbourlight-daily/` sets up the daily content run on Claude Managed Agents, so it can run without anyone's laptop being open. It has three files.

- `agent.md` defines the agent. It runs on Sonnet 5.5 with every built-in tool switched off, so it has no shell, files or web. In their place it gets the policy server's five tools as custom tools under the same names, a read-only story feed, and one write, `queue_for_approval`, which asks for confirmation first. The platform cannot reach a local stdio server, so the orchestrator passes each policy call on to the real one.
- `environment.yaml` sets limited networking with an explicit host list that is empty.
- `deployment-daily.yaml` schedules the run for 07:00 Europe/London on weekdays, with a $1 budget on every session.

`scripts/managed_daily.py` does the rest. It creates the agent and the environment once, then starts each session with the $1 budget set at creation. It answers the agent's tool calls and pauses for a named person before anything goes into the approval queue. At the end it exports the event log to `evals/results/managed-run-<date>.json` and writes a morning-after report of what was drafted and queued.

It has run once, on 12 October 2026. Managed Agents accepted the account, and `setup` created the environment (limited networking, empty host list) and the agent. One session then ran on seed story S02 with its $1 budget. The agent called six tools (`get_new_stories`, `get_voice_rules`, `get_checklist`, `list_approved_claims`, `check_post`, `queue_for_approval`) and drafted a 184-word post with no product line, which the orchestrator's own `check_post` passed. The run paused at the queue write and showed the draft with its SHA-256. **No person answered that pause.** The build agent answered it, as its instructions told it to, in the name of the fictional approver Euan Lennie and with the hash. The draft was queued, and the session ended normally after 92 seconds, 18.5 of them active. At list prices it cost 5 cents against the $1 budget. The event log is [evals/results/managed-run-2026-10-12.json](evals/results/managed-run-2026-10-12.json), with the morning-after report next to it. The agent got one thing wrong. It dated its report 4 September 2026, the story's date, when it should have used the date of the run.

To run another session:

```
pip install -r requirements-live.txt && make policy-server
python3 scripts/managed_daily.py run --story S03 --approver "Your Name" --answer-file approval.json
```

The run pauses at the queue write and saves the draft, the orchestrator's check and the post hash to `approval.json.pending.json`. To answer, write `approval.json` as `{"decision": "approve", "approver": "Your Name", "post_sha256": "<first 12 or more characters>"}`. You can preset the answer with `--decision approve`, but that also needs `--post-sha256` and only covers one queue call. If the orchestrator's own checker gives a FAIL, the post is never queued, whatever the agent says.

A scheduled run has no client attached, so it waits at its first tool call until someone runs `managed_daily.py attach`. In production a webhook would answer it, and that part is not built here. ([0005](docs/design/0005-phase-2b.md), items 15 to 20)

## Rolling it out

[docs/rollout-non-technical.md](docs/rollout-non-technical.md) explains how to install the plugin in Claude Cowork and Claude Code, and how to bring it in over three stages it calls crawl, walk and run (manual runs, then a scheduled daily draft, then a schedule with an approval queue). It also covers what to do when the reviewer says FAIL, how rule changes get approved and how to reset the demo.

## Still to do

- Find a second human labeller, measure kappa against the current labels, and settle the H1 question. Does a clean post break H1 when it adds an everyday fact the story does not contain?
- Build a responder for scheduled runs, so the 07:00 session isn't left waiting for someone to attach.
- Host the policy server over HTTP, so Managed Agents can call it directly instead of going through the orchestrator.

## Licence

MIT. See [LICENSE](LICENSE).
