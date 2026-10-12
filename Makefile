PY ?= python3
SEEDED_POSTS = data/posts/2026-09-08-base-rate-holds.draft.md \
               data/posts/2026-09-15-payment-holiday-texts.draft.md \
               data/posts/2026-09-22-storm-repairs.draft.md

.PHONY: help test demo reset approve denylist live live-report policy-server

help:
	@echo "make demo      run the checker, the reviewer eval, the variance check and show the audit log"
	@echo "make test      run every unit test"
	@echo "make reset     restore data/ from data-pristine/ (demo only)"
	@echo "make approve APPROVER=\"Full Name\"   open the rule-change gate for 60 minutes"
	@echo "make denylist  screen the tree against DENY_LIST or a local .denylist file"
	@echo "make live      call Claude: both models on 24 cases, Haiku five times, then the report (needs ANTHROPIC_API_KEY)"
	@echo "make live-report   rebuild the comparison report from recorded runs, no calls"
	@echo "make policy-server build and test the policy MCP server (needs Node 22)"

test:
	$(PY) -m unittest discover -s evals -p 'test_*.py'
	$(PY) -m unittest discover -s tests -p 'test_*.py'

demo:
	@echo "== 1. Deterministic checker over the three seeded drafts =="
	@$(PY) evals/check_post.py $(SEEDED_POSTS)
	@echo
	@echo "== 2. Reviewer eval: rule-based stand-in against 24 labelled posts =="
	@$(PY) evals/run_reviewer_eval.py
	@echo
	@echo "== 3. Seeded fault: switch H3 off; the eval must go red =="
	@$(PY) evals/run_reviewer_eval.py --seed-fault H3 --summary; status=$$?; \
	  if [ $$status -eq 1 ]; then echo "OK: the eval caught the seeded fault"; \
	  else echo "PROBLEM: the seeded fault was not detected"; exit 1; fi
	@echo
	@echo "== 4. Run-to-run variance =="
	@if ls evals/results/variance/*.json >/dev/null 2>&1; then \
	  echo "(recorded live Haiku runs in evals/results/variance/)"; \
	  $(PY) evals/variance/verdict_variance.py evals/results/variance/; \
	else \
	  echo "(no live runs recorded yet; five stand-in runs)"; \
	  $(PY) evals/variance/verdict_variance.py evals/variance/fixtures/; \
	fi
	@echo
	@echo "== 5. Live mode: the plan and a cost estimate, no calls =="
	@$(PY) evals/run_reviewer_eval.py --live --dry-run
	@echo
	@echo "== 6. Audit log, last three rows =="
	@tail -n 3 data/audit-log.csv
	@echo
	@echo "== 7. Monthly report, September 2026 =="
	@$(PY) scripts/monthly_report.py --month 2026-09

reset:
	@$(PY) scripts/reset_data.py

approve:
	@test -n "$(APPROVER)" || (echo 'Usage: make approve APPROVER="Full Name"' && exit 1)
	@printf 'approver: %s\ndate: %s\n' "$(APPROVER)" "$$(date -u +%Y-%m-%dT%H:%MZ)" > .approver
	@echo "Approval marker written for $(APPROVER). Valid for 60 minutes. Delete .approver when done."

denylist:
	@bash scripts/denylist.sh

LIVE_DAY := $(shell date -u +%Y-%m-%d)

live:
	@test -n "$$ANTHROPIC_API_KEY" || (echo "make live needs ANTHROPIC_API_KEY; no calls made" && exit 2)
	$(PY) evals/run_reviewer_eval.py --live --model claude-haiku-5-5 --summary; test $$? -le 1
	$(PY) evals/run_reviewer_eval.py --live --model claude-sonnet-5-5 --summary; test $$? -le 1
	$(PY) evals/run_reviewer_eval.py --live --model claude-haiku-5-5 --repeats 5 \
	  --out-dir evals/results/variance --summary; test $$? -le 1
	$(MAKE) live-report
	$(PY) evals/ledger.py

live-report:
	$(PY) evals/live_report.py $$(ls evals/results/reviewer-*.json) --variance evals/results/variance \
	  --out evals/results/report-$(LIVE_DAY).md > /dev/null
	@echo "wrote evals/results/report-$(LIVE_DAY).md"

policy-server:
	cd mcp/policy-server && npm ci && npm test
