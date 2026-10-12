# Harbourlight

A marketing team at a regulated company wants to post about what is in the news without a compliance review taking three days or a rushed post costing a fine. Harbourlight is a worked, runnable example of giving Claude that job properly: research, a draft, an independent compliance reviewer that quotes its evidence, a human who approves or rejects, and an audit log a compliance officer can read.

**Everything here is invented.** Harbourlight Mutual, its regulator (the Conduct Standards Authority), its people, its products, every news story, every outlet and every figure are made up for this demo. The URLs use the reserved `example.invalid` domain and go nowhere.

It is also a worked example of rolling Claude Cowork out to people who do not write code: the whole pipeline installs as a plugin, and the [rollout guide](docs/rollout-non-technical.md) is written for a marketing or compliance lead.

## Run the demo in a minute

You need Python 3.12 or later and `make`. Nothing to install, no API key, no network.

```
git clone https://github.com/cla1redonald/harbourlight
cd harbourlight
make demo
```

`make demo` checks the three seeded posts, scores the reviewer against 24 labelled posts, switches a rule off to show the eval goes red, measures run-to-run variance, prints the plan and cost estimate for a live run (it never calls the API, even with a key set), and prints the audit log and the September report. `make test` runs every Python unit test. `make reset` puts the demo data back to how it started.

With an API key and `pip install -r requirements-live.txt`, `make live` runs the reviewer on Claude. With Node 22, `make policy-server` builds and tests the policy MCP server.

To use the pipeline itself, open the folder in Claude Code with `claude --plugin-dir .` and type `/content-run`.

## What is in the box

| Path | What it is |
|---|---|
| `CLAUDE.md` | The standing brief. Lesson zero: structure your files first; skills are the recipe, data is the meal. |
| `references/` | The rules: brand voice, five products with one approved line each, five watchlist themes, a compliance checklist with hard rules H1 to H7 and soft rules S1 to S5, and `rules.json` for the checker. |
| `skills/` | `market-research`, `post-writer`, `compliance-reviewer`, `monthly-audit-report`. |
| `agents/` | `story-scout` (one per theme), `compliance-reviewer`, `feedback-analyst`. All read-only. |
| `commands/` | `/content-run`, `/voice-apply`, `/reset-demo`. |
| `hooks/` | The approval gate, a shell script. |
| `data/` | 27 news stories for September 2026 with ten planted traps, the research log, the audit log, the voice changelog and three seeded posts. `data-pristine/` is the reset copy. |
| `evals/` | The deterministic checker and its tests, 24 labelled reviewer cases, the eval harness (stand-in and live), the cost ledger, the comparison report, the variance check, and the second-labeller kit in `evals/labels/`. |
| `mcp/policy-server/` | A read-only MCP server that serves the policy to any agent: approved claims, the checklist, the voice rules and the checker. |
| `agents/harbourlight-daily/` | The weekday content run as a Managed Agents agent, environment and schedule. |
| `scripts/` | Audit-log append, story status, monthly report, reset, deny-list, and the Managed Agents orchestrator with its policy bridge. |
| `docs/` | The rollout guide and five short decision records. |

### The pipeline

1. **Research.** One story per watchlist theme, skipping traps: a named customer, a competitor's data breach, a figure nobody can source, a thin story, a duplicate under a new headline, something out of scope, and a story with an instruction hidden in it for any AI that reads it.
2. **Draft.** One post from one story, 120 to 220 words, using only facts from the story and only the approved product lines.
3. **Deterministic check.** Word count, spelling, filler words, em dashes, product wording, unsourced figures, named people, competitors, sensitive topics.
4. **Independent review.** A separate agent with only the draft and the checklist returns PASS, FLAG or FAIL, with a rule id and an exact quote for every finding, and what would change a FAIL.
5. **Human decision.** Approve, edit or reject, by name. A FAIL cannot be approved.
6. **Record.** Draft and final saved, the story marked, one row appended to the audit log.

## The governance

- **The reviewer is independent.** It runs in its own context and never sees the writer's reasoning, the research notes or the checker's output. It judges the words a member would read. ([0001](docs/design/0001-reviewer-independence.md))
- **The approval gate is a script, not a prompt.** A PreToolUse hook blocks any change to `references/` or `skills/` unless a person has named themselves as approver. Claude cannot create the approval marker itself. ([0002](docs/design/0002-named-approver-and-version-bump.md))
- **Logs are append-only.** The audit log is written only by a script that refuses rows breaking the rules (a FAIL marked approved, a decision with no name). A test checks that the seeded rows have never been altered.
- **Voice rules are versioned.** Every rule change bumps `voice_version` and names its approver in the changelog, and every audit row carries the version it was judged under.
- **The cheap check runs first.** The deterministic checker catches the mechanical failures before the model reviewer looks for the ones that need judgement. ([0003](docs/design/0003-deterministic-checker-first.md))

## What is tested

166 Python unit tests and 11 Node tests. The Python tests cover a poison and a clean sample for every checker rule, the approval hook run as Claude Code would run it, the audit and reset scripts, the eval harness, the cost ledger and its hard stop, the live reviewer against a fake API client, the comparison report, the variance script, the second-labeller tools, the Managed Agents orchestrator against a fake client and a stub MCP server, the deny-list script, and the integrity of the seed data. The Node tests drive the policy server over a real stdio transport and check that its checker gives the same answer as the Python one on all 24 cases and the five seeded posts.

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
| Seeded fault (H3 switched off) | gate goes red; every hard rule tested the same way |
| Run-to-run verdict changes | 0 of 24 across five recorded runs |

The misses are the point. For each hard rule, one case was written to beat pattern matching: an invented award with a real source, a product claim that never names the product, a figure written in words, advice phrased as "if we were in your shoes", a member identified by first name and town, criticism of unnamed competitors, and a post that makes light of arrears. A scam warning that never says "scam" slipped past as well, which was not planned.

A stand-in reviewer measures the harness, not the model. These numbers show the eval can tell a good reviewer from a broken one and name every disagreement. They say nothing about how well Claude reviews.

### The live reviewer, 12 October 2026

The reviewer skill ran on Claude over the same 24 posts, scored by the same harness: one pass each on `claude-haiku-5-5` (effort `medium`, its default) and `claude-sonnet-5-5` (effort `high`, its default), then five more Haiku passes for variance. The full report, with every flip and every disagreement, is [evals/results/report-2026-10-12.md](evals/results/report-2026-10-12.md); the raw outputs are beside it.

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

Intervals are 95% Wilson. No reply was refused, truncated or failed the schema, and no cost had to be estimated.

**Disagreements.** Haiku: B01 and C02, both labelled PASS, came back FLAG on H1. Sonnet: C01 and B01 (labelled PASS) came back FAIL on H1, and B02 (labelled FLAG) came back FAIL on H1 with S3. Every disagreement is the same thing: a clean or borderline post adds a small everyday fact the cited story does not contain ("it is reasonable to ask to see their card", "find the end date on your annual statement", "a genuine lender will not mind you checking"). The checklist says every factual statement must come from the cited story, so the models have a case, and the labels tolerated these. That is a question for the second labeller and possibly for the checklist, not something to fix by relabelling. Sonnet's one quote not found in the post was an S4 finding that quoted a word count rather than the post.

**Flips and noise.** Both models catch all eight cases the stand-in missed or under-called: the seven written to beat pattern matching, and H7b. Against the stand-in, Haiku's gain is the only difference 24 posts can support (exact McNemar p = 0.039; Sonnet p = 0.109, within noise). **Haiku against Sonnet is within noise** (p = 1.0): they differ on four cases, all clean or borderline, all about H1. On this set Sonnet costs about 22 times as much per case and takes about 1.6 times as long, for no measurable gain.

### Variance: five more Haiku passes

| Measure | Result |
|---|---|
| Cases where every repeat gave the same verdict | 21 of 24 |
| Cases whose verdict changed at least once | 3 of 24 (B01, C01, C02) |
| Cases whose cited rule set changed at least once | 20 of 24 |
| Cases where every repeat agreed on verdict and rules | 4 of 24 |
| Individual verdicts matching the case's most common verdict | 114 of 120 |

The verdict on every post that breaks a hard rule was FAIL in all five repeats. The movement is on the clean and borderline posts, which swing between PASS, FLAG and FAIL on H1, and in the extra rules cited beside the right one (an H1 or H4 added in some repeats and not others). Across the six Haiku passes, agreement ranged from 21 to 23 of 24 and false positives on the two clean posts from 0 to 2, so the single-pass figure above sits at the good end. In one repeat Haiku failed H6a without citing H6, so its catch count that run was 19 of 20. One run cannot be trusted on its own for a clean post; it can for a FAIL.

**What these numbers are not.** There are 24 cases, so the intervals are wide and most differences are noise. One person wrote the rules, the posts and the labels, so agreement means agreement with that person. One case per rule was written to beat pattern matching, so a catch rate describes these cases, not how often such posts turn up.

**Spend.** Every response was priced at list rates into [evals/results/spend.jsonl](evals/results/spend.jsonl): 171 rows, **$0.69 in total**. The Sonnet pass cost $0.51; the six Haiku passes and a two-post smoke test cost $0.14; the Managed Agents session cost $0.05. The code's hard stop is $50.

**A second labeller is pending.** No second person has labelled the cases. [evals/labels/second-labeller-template.md](evals/labels/second-labeller-template.md) explains how someone labels blind and how agreement (Cohen's kappa) will be computed. A model is deliberately not used in their place.

More in [evals/README.md](evals/README.md).

## Consulting the policy from any agent

The rules live in files, but anything that writes for Harbourlight should be able to ask them a question without its own copy. `mcp/policy-server/` is a read-only MCP server over stdio with five tools:

| Tool | What it answers |
|---|---|
| `list_approved_claims` | The five products and the one approved line for each |
| `check_claim(text)` | Is this sentence exactly an approved line? Returns the matching claim, or none, and which product it names |
| `check_post(text)` | The deterministic checker on a whole post: verdict, findings with rule ids and quotes, what would change a FAIL |
| `get_checklist()` | The compliance checklist |
| `get_voice_rules()` | The brand voice guide and its machine-checkable parts |

It has no resources and no prompts, reads a fixed list of six files once at start-up, never writes, and rejects any argument it does not expect. Any MCP client can use it: a writer agent checking a product line before it drafts, an approver's assistant, a plug-in in a publishing tool. To wire it into Claude Code:

```
make policy-server
claude mcp add harbourlight-policy -- node "$(pwd)/mcp/policy-server/dist/src/index.js"
```

Other clients take the same command (`node .../dist/src/index.js`) in their stdio server settings. A PASS from `check_post` is the cheap check only: a draft still needs the independent reviewer and a named approver. ([0005](docs/design/0005-phase-2b.md), items 13 and 14)

## The scheduled run on Managed Agents

`agents/harbourlight-daily/` defines the daily content run for Claude Managed Agents, so it can run without anyone's laptop open:

- **`agent.md`**: Sonnet 5.5, every built-in tool disabled (no shell, files or web), the policy server's five tools as custom tools with the same names, a read-only story feed, and one write, `queue_for_approval`, which is confirm-first. The platform cannot reach a local stdio server, so the orchestrator forwards each policy call to the real server.
- **`environment.yaml`**: limited networking with an explicit, empty host list.
- **`deployment-daily.yaml`**: weekdays at 07:00 Europe/London, with a $1 budget on every session.

`scripts/managed_daily.py` creates the agent and environment once, starts a session with the $1 budget set at creation, answers the tool calls, pauses for a named person before anything joins the approval queue, exports the event log to `evals/results/managed-run-<date>.json` and writes a morning-after report listing what was drafted and queued.

**It ran once, on 12 October 2026.** Managed Agents accepted the account: `setup` created the environment (limited networking, empty host list) and the agent, and one session ran on seed story S02 with its $1 budget. The agent called six tools (`get_new_stories`, `get_voice_rules`, `get_checklist`, `list_approved_claims`, `check_post`, `queue_for_approval`), drafted a 184-word post with no product line, and the orchestrator's own `check_post` gave it PASS. The run paused at the queue write and showed the draft with its SHA-256. The pause was answered as the fictional approver Euan Lennie, with the hash, **by the build agent following its instructions, not by a person**. The draft was queued, and the session ended normally after 92 seconds (18.5 of them active). List cost: 5 cents, against the $1 budget. The event log is [evals/results/managed-run-2026-10-12.json](evals/results/managed-run-2026-10-12.json), and the morning-after report is beside it. One flaw: the agent dated its own report with the story's date (4 September 2026), not the run date.

To run another session:

```
pip install -r requirements-live.txt && make policy-server
python3 scripts/managed_daily.py run --story S03 --approver "Your Name" --answer-file approval.json
```

The run pauses at the queue write and writes `approval.json.pending.json` with the draft, the orchestrator's check and the post hash. To answer, write `approval.json` as `{"decision": "approve", "approver": "Your Name", "post_sha256": "<first 12 or more characters>"}`. A preset `--decision approve` needs `--post-sha256` and covers one queue call only. A FAIL from the orchestrator's own checker is never queued, whatever the agent says.

A scheduled run has no client attached, so it waits at its first tool call until someone runs `managed_daily.py attach`; answering from a webhook is the production step not built here. ([0005](docs/design/0005-phase-2b.md), items 15 to 20)

## Rolling it out

[docs/rollout-non-technical.md](docs/rollout-non-technical.md) covers installing the plugin in Claude Cowork and Claude Code, a crawl, walk, run cadence (manual runs, a scheduled daily draft, then a schedule with an approval queue), what to do when the reviewer says FAIL, how rule changes are approved, and how to reset the demo.

## Still to do

- **A second human labeller**, then kappa against the current labels, and a decision on the H1 question: does a clean post break H1 when it adds an everyday fact the story does not contain?
- **A responder for scheduled runs**, so the 07:00 session does not wait for someone to attach.
- **Host the policy server over HTTP**, so Managed Agents can call it directly instead of through the orchestrator.

## Licence

MIT. See [LICENSE](LICENSE).
