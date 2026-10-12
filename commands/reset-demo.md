---
description: Put the Harbourlight demo data back to its seeded September 2026 state, after confirming with the person.
---

# Reset the demo

This wipes everything under `data/` (posts, logs, research entries, story statuses) and restores the seeded copy from `data-pristine/`. It exists so a team can practise and start again. It is the one deliberate exception to "logs are append-only", and it must never be used on a real deployment's data.

1. Tell the person what will be lost: list any files in `data/posts/` and any audit-log rows that are not in `data-pristine/`.
2. Ask: "Reset the demo data? This cannot be undone." Wait for a clear yes.
3. Run `python3 scripts/reset_data.py` (the same as `make reset`).
4. Confirm with `tail -n 3 data/audit-log.csv`.
