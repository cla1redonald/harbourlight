---
name: monthly-audit-report
description: Write the month's content audit report for compliance from data/audit-log.csv, with counted numbers and short commentary. Use at month end, or when asked how the pipeline performed in a given month.
---

# Monthly audit report

The reader is the Head of Compliance. They want to know what was posted, what was stopped and why, and whether anything is drifting. Keep it to one page.

## Steps

1. Run `python3 scripts/monthly_report.py --month YYYY-MM`. The numbers come from this script. Never count by hand and never change a number it gives you.
2. Read the month's rows in `data/audit-log.csv` and the entries in `data/voice-changelog.md` dated that month.
3. Write `data/reports/YYYY-MM.md`: the script's output first, then a section headed **Commentary** with no more than five bullets covering:
   - which rules caused FAILs and whether the same rule keeps coming up;
   - how many posts were on sensitive topics (H7) and who was consulted;
   - what the human edits had in common (from `edit_summary`);
   - any change in `voice_version` during the month, and who approved it;
   - anything the feedback-analyst agent should look at next month.
4. If any row shows a FAIL that was posted, or a post with no named approver, put that first, in bold, as an exception. It should never happen; if it does, it is the most important line in the report.

## Style

Plain sentences, British spelling, no em dashes, no exclamation marks. Quote the log rather than paraphrasing it. If there is not enough data to say something, say that instead of guessing.

The report is a new file. Never edit the audit log or an earlier month's report.
