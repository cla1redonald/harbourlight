# 0001: The reviewer is a separate agent that never sees the writer's reasoning

Status: accepted, Phase 2a

## Context

A writer that explains its choices can talk a reviewer round. If the reviewer reads "I left the figure in because the story is from a reliable outlet", it starts judging the argument rather than the post. A member never sees the argument. They see the words.

## Decision

The compliance reviewer runs as its own agent (`agents/compliance-reviewer.md`), in a fresh context, with read-only tools. It is given the path of a draft and nothing else. It reads the draft, the checklist, and the one story the draft cites (so it can check facts). It does not read the research log, the writer's notes, earlier drafts, or the deterministic checker's output. Every finding must quote the draft exactly.

Where agents are not available, as in some Cowork set-ups, the same independence comes from starting a fresh task and running the reviewer skill on the draft path alone.

## Consequences

- The reviewer can disagree with the checker, and the disagreement is recorded rather than smoothed over.
- The reviewer cannot be steered by the writer's framing, and it can be evaluated on its own, which is what `evals/` does.
- It costs a second context per draft. That is the price of a second pair of eyes.
- Read-only tools do not stop the reviewer opening a file it was told not to. The instruction does that, and the eval set should one day include a case that tests it.
