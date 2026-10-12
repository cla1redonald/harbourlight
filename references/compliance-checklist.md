# Compliance checklist

This is the only document the compliance reviewer reads besides the draft itself. Hard rules (H) fail a post. Soft rules (S) flag it for the human approver. Every finding must name the rule id and quote the exact phrase from the draft that triggered it. A finding with no quote is not a finding.

## Verdicts

- **PASS**: no hard-rule failures and no flags. The post still goes to a human for approval; PASS means "nothing for the approver to worry about", not "publish".
- **FLAG**: no hard-rule failures, but at least one soft rule, a neutral competitor mention, or a sensitive topic. The approver must read the quoted evidence before deciding.
- **FAIL**: at least one hard-rule failure. The reviewer must say what would have to change for the post to pass.

## Hard rules (fail)

| Id | Rule | Evidence the reviewer must quote |
|---|---|---|
| H1 | No invented facts. Every factual statement must come from the cited story. | The sentence stating a fact that is not in the cited source, or the source URL that does not exist. If there is no `Sources:` block, quote `(no sources block)`. |
| H2 | No unsupported product claims. A product may be named only in its approved line, word for word. | The sentence naming a product that is not the approved line. |
| H3 | No unsourced statistics. Every figure in the body must appear on a source line. | The figure, exactly as written in the body. |
| H4 | No financial advice, promises or guarantees. | The phrase that tells the reader what to do with their money, or promises an outcome. |
| H5 | No named customers or members, including first names, initials with a town, or ages. | The name or identifying phrase. |
| H6 | No disparaging competitors, named or implied. | The phrase that criticises another firm. A neutral mention of a named competitor is a FLAG under H6, not a FAIL. |
| H7 | Sensitive topics (arrears, bereavement, vulnerability, scams) are handled with care and never auto-pass. A sensitive post is at least a FLAG. It is a FAIL if it sells, makes light of the situation, or names any product other than the Steady Ground signpost. | The sensitive phrase, and for a FAIL the selling or dismissive phrase. |

## Soft rules (flag)

| Id | Rule | Evidence the reviewer must quote |
|---|---|---|
| S1 | Tone matches the voice guide: no exclamation marks, no em dashes, no marketing filler words. | The word or character. |
| S2 | At most one product mention. | The second product name. |
| S3 | Honest framing: no hype or absolutes ("unbeatable", "no-brainer", "nothing to worry about"). | The phrase. |
| S4 | Length of body between 120 and 220 words. | The word count. |
| S5 | British spelling. | The word spelt the American way. |

## What the reviewer does not see

The reviewer never sees the writer's notes, the research log, the deterministic checker's output or the reasoning behind the draft. It judges the words a member would read, against this list. To judge H1 it may open the one story the draft cites, looked up by URL in `data/incoming-stories.md`, because a fact cannot be checked against nothing. See `docs/design/0001-reviewer-independence.md`.

## Appendix: approved product lines (for H2)

A product may appear only as one of these lines, word for word. This copy must match `references/rules.json`; a test fails if they drift apart.

- The FixedFive Remortgage fixes your monthly payment for five years.
- The Overpayment Planner shows how an extra payment would change your mortgage term before you make it.
- HomeAssist Emergency Cover is an optional add-on to our home insurance that arranges help with emergencies such as a burst pipe or a broken boiler.
- The Steady Ground support line gives members who are worried about payments a named contact to talk through their options. (Signpost: the only product allowed in a post on a sensitive topic.)
- The Harbour App lets members check their balance, make overpayments and update their details.
