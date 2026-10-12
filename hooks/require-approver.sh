#!/usr/bin/env bash
# PreToolUse hook: block changes to the rules unless a human approver is named.
#
# Protected: anything under skills/ or references/ in the project (or the
# installed plugin). These files ARE the rules the pipeline follows, so changing
# them is a governance decision, not an editing task.
#
# A write is allowed only if one of these is true:
#   1. HARBOURLIGHT_APPROVER is set to a non-empty name in the environment
#      Claude Code was started from, or
#   2. a file named .approver exists in the project root, was created in the
#      last 60 minutes, and contains a line "approver: <name>".
#
# Claude cannot create the marker itself: writes to .approver, and shell
# commands that mention it or `make approve`, are always blocked. A person
# creates it with `make approve APPROVER="Morag Baird"` or a text editor.
#
# Exit 0 allows the tool call. Exit 2 blocks it and shows the message to Claude.
# This is a script, not a prompt, so it cannot be talked out of its decision.

set -u

input="$(cat | tr -d '\n\r')"
project="${CLAUDE_PROJECT_DIR:-$PWD}"
plugin_root="${CLAUDE_PLUGIN_ROOT:-}"
marker="$project/.approver"
max_age_minutes=60

json_field() {
  # Pull a top-level-ish string field out of the hook JSON without needing jq.
  # Handles escaped quotes inside the value; returns the raw (still escaped) text.
  printf '%s' "$input" | sed -nE "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"(([^\"\\\\]|\\\\.)*)\".*/\1/p" | head -n 1
}

block() {
  printf 'Blocked by the Harbourlight approval hook: %s\n' "$1" >&2
  printf 'Changing the rules needs a named human approver. Ask them to run\n' >&2
  printf '  make approve APPROVER="Their Name"\n' >&2
  printf 'in the project folder (valid for %s minutes), or start Claude Code with\n' "$max_age_minutes" >&2
  printf '  HARBOURLIGHT_APPROVER="Their Name"\n' >&2
  printf 'Then use /voice-apply so the change is versioned and logged.\n' >&2
  exit 2
}

approver_named() {
  if [ -n "$(printf '%s' "${HARBOURLIGHT_APPROVER:-}" | tr -d '[:space:]')" ]; then
    return 0
  fi
  if [ -f "$marker" ] && [ -n "$(find "$marker" -mmin -"$max_age_minutes" 2>/dev/null)" ]; then
    name="$(sed -n 's/^approver:[[:space:]]*//p' "$marker" | head -n 1 | tr -d '[:space:]')"
    [ -n "$name" ] && return 0
  fi
  return 1
}

relative_to_root() {
  # Print the path relative to the project or plugin root, or nothing if outside both.
  path="$1"
  case "$path" in
    /*) ;;
    *) printf '%s' "${path#./}"; return ;;
  esac
  for root in "$plugin_root" "$project"; do
    [ -z "$root" ] && continue
    case "$path" in
      "$root"/*) printf '%s' "${path#"$root"/}"; return ;;
    esac
  done
}

tool="$(json_field tool_name)"

case "$tool" in
  Write|Edit|MultiEdit|NotebookEdit)
    path="$(json_field file_path)"
    [ -z "$path" ] && path="$(json_field notebook_path)"
    rel="$(relative_to_root "$path")"
    case "$rel" in
      .approver) block "Claude may not create or edit the approval marker." ;;
      skills/*|references/*)
        approver_named || block "$rel is a rule file." ;;
    esac
    ;;
  Bash)
    command="$(json_field command)"
    case "$command" in
      *.approver*|*"make approve"*)
        block "Claude may not create or edit the approval marker." ;;
    esac
    case "$command" in
      *skills/*|*references/*)
        case "$command" in
          *">"*|*"tee "*|*"sed -i"*|*"perl -i"*|*"mv "*|*"cp "*|*"rm "*|*"git checkout"*|*"git restore"*)
            approver_named || block "shell command would change a rule file." ;;
        esac
        ;;
    esac
    ;;
esac

exit 0
