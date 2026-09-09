.PHONY: check quality backend perf help

check:
	@./scripts/check.sh

quality:
	@./scripts/check.sh --quality-only

backend:
	@./scripts/check.sh --backend-only

perf:
	@python3 infra/perf_budget.py --print-summary

help:
	@./scripts/check.sh --help
