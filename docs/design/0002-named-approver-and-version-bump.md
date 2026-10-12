# 0002: Rule changes need a named approver and a version bump

Status: accepted, Phase 2a

## Context

The files in `references/` and `skills/` are the rules. If Claude could edit them freely, a run could quietly loosen the checklist it is about to be judged against, and nobody could say afterwards which rules a post was approved under.

## Decision

1. A shell script hook (`hooks/require-approver.sh`) runs before every file write and shell command. It blocks changes under `references/` and `skills/` unless `HARBOURLIGHT_APPROVER` names a person, or a `.approver` file naming a person was created in the last 60 minutes.
2. Claude cannot create the approval marker: the hook blocks writes to `.approver` and shell commands that mention it or `make approve`.
3. Every applied change bumps `voice_version` in `references/rules.json` and appends an entry to `data/voice-changelog.md` naming the approver.
4. Every audit-log row records the `voice_version` in force, so any decision can be traced to the exact rules behind it.

The gate is a script, not a prompt. A prompt can be argued with; an exit code cannot.

## Consequences

- Rule changes are slower, on purpose.
- The hook records that a name was given, not who typed it. Real identity (single sign-on, signed commits) is out of scope for a demo and noted for a real deployment.
- Shell commands are matched by pattern, which is a heuristic: it catches the common ways of writing a file, not every possible one. File-tool writes are matched exactly.
- Plugin hooks depend on the host running them. The rollout guide tells a Cowork user how to check.
