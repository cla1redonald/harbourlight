#!/usr/bin/env bash
# Fail if the tree contains any screened term or an em dash.
#
# The terms are not kept in this repo. They come from, in order:
#   1. the DENY_LIST environment variable (newline-separated; set from a
#      repository secret in CI), or
#   2. a gitignored .denylist file in the root being scanned (one term per line).
# Matching is case-insensitive and literal. An empty or missing list is an error,
# so CI cannot pass by checking nothing.
#
# Usage: bash scripts/denylist.sh [root]   (root defaults to the repo root)
set -euo pipefail

root="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
patterns="$(mktemp "${TMPDIR:-/tmp}/denylist.XXXXXX")"
trap 'rm -f "$patterns"' EXIT

if [ -n "${DENY_LIST:-}" ]; then
  source_name="DENY_LIST environment variable"
  printf '%s\n' "$DENY_LIST" > "$patterns.raw"
elif [ -f "$root/.denylist" ]; then
  source_name=".denylist file"
  cat "$root/.denylist" > "$patterns.raw"
else
  echo "Deny-list check FAILED: no list. Set DENY_LIST or create a .denylist file." >&2
  exit 2
fi
# Drop carriage returns, surrounding spaces and blank lines.
tr -d '\r' < "$patterns.raw" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' | grep -v '^$' > "$patterns" || true
rm -f "$patterns.raw"
count="$(wc -l < "$patterns" | tr -d ' ')"
if [ "$count" -eq 0 ]; then
  echo "Deny-list check FAILED: the list from $source_name is empty." >&2
  exit 2
fi
# The house style bans em dashes everywhere; always screen for them as well.
printf '\xe2\x80\x94\n' >> "$patterns"

# Opaque API identifiers (event, session, request ids and the like) are random strings that
# can contain a short term by chance. They are blanked before the second match, so a term
# is still caught anywhere in prose, but not inside an id such as sevt_01AbC...
id_pattern='(sevt|sesn|agent|env|req|msg|toolu|srvtoolu|file|vlt|depl|drun|wrkspc)_[A-Za-z0-9]{8,}'
matches="$(grep -rIniF -f "$patterns" "$root" \
    --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=dist \
    --exclude=LICENSE --exclude=.denylist || true)"
real=""
[ -n "$matches" ] && real="$(printf '%s\n' "$matches" | while IFS= read -r line; do
  location="${line%%:*}"; rest="${line#*:}"; number="${rest%%:*}"; content="${rest#*:}"
  stripped="$(printf '%s' "$content" | sed -E "s/$id_pattern/<id>/g")"
  if printf '%s\n' "$stripped" | grep -qiF -f "$patterns"; then
    printf '%s:%s:%s\n' "$location" "$number" "$content"
  fi
done)" || true
if [ -n "$real" ]; then
  printf '%s\n' "$real"
  echo "Deny-list check FAILED: the lines above must be changed." >&2
  exit 1
fi
echo "Deny-list check passed: $count terms from $source_name, no matches outside LICENSE."
