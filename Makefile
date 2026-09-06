.PHONY: check quality backend help

check:
	@./scripts/check.sh

quality:
	@./scripts/check.sh --quality-only

backend:
	@./scripts/check.sh --backend-only

help:
	@./scripts/check.sh --help
