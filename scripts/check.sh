#!/usr/bin/env bash
# Run local checks matching GitHub Actions quality and backend test jobs.
#
# Covers:
#   - quality: ruff format/check, mypy, pip-audit (with .github/pip-audit-ignore.txt)
#   - backend: pytest (unit, api, client), coverage >= 71%, coverage floors gate, openapi export
#   - client/web: lint, test, typecheck (if Node.js / npm is installed)
#
# CI-only (not run here):
#   - ui / ui_web: Playwright tests requiring installed .deb / X11 virtual display
#   - live / live_web: Real cloud model canary requiring repository secrets
#   - scan: Trivy filesystem vulnerability scanning
#   - CodeQL: GitHub Advanced Security code scanning
#
# Prerequisites:
#   - Python 3.13 with dependencies (pip install -r requirements-dev.txt)
#   - PostgreSQL on 127.0.0.1:5432 (or set ARTEK_TEST_DATABASE_URL, or set ARTEK_ALLOW_DB_SKIP=1)
#   - Optional: Node 22+ and npm for client/web checks
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DRY_RUN=0
RUN_QUALITY=1
RUN_BACKEND=1
RUN_WEB=1

usage() {
  cat <<'EOF'
Usage: ./scripts/check.sh [OPTIONS]

Run local quality and backend checks matching GitHub Actions test.yml.

Options:
  -h, --help        Show this help message and exit
  -n, --dry-run     Print commands that would be executed without running them
  --quality-only    Run only quality checks (ruff, mypy, pip-audit)
  --backend-only    Run only backend checks (pytest, coverage floors, openapi)
  --skip-web        Skip client/web checks even if npm is available

Job mapping:
  Covers:   quality, backend, client/web
  CI-only:  ui, ui_web, live, live_web, scan (Trivy), CodeQL

Database requirements:
  Backend tests require PostgreSQL. Set ARTEK_TEST_DATABASE_URL or run postgres locally.
  To skip DB-dependent tests when PostgreSQL is unavailable, set ARTEK_ALLOW_DB_SKIP=1.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    -n|--dry-run)
      DRY_RUN=1
      shift
      ;;
    --quality-only)
      RUN_QUALITY=1
      RUN_BACKEND=0
      RUN_WEB=0
      shift
      ;;
    --backend-only)
      RUN_QUALITY=0
      RUN_BACKEND=1
      RUN_WEB=0
      shift
      ;;
    --skip-web)
      RUN_WEB=0
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

execute() {
  local desc="$1"
  shift
  echo "==> $desc"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '    %q' "$@"
    echo ""
    return 0
  fi
  "$@"
}

echo "=== Artek Buddy Local Check ==="
echo "Covers:  quality (ruff, mypy, pip-audit), backend (pytest, coverage, openapi)"
if [[ "$RUN_WEB" -eq 1 ]] && command -v npm >/dev/null 2>&1; then
  echo "Web:     client/web (lint, test, check)"
fi
echo "CI-only: ui, ui_web, live, live_web, scan (Trivy), CodeQL"
echo ""

if [[ "$RUN_QUALITY" -eq 1 ]]; then
  echo "--- Job: quality ---"
  execute "Ruff format check" python3 -m ruff format --check src tests client
  execute "Ruff linter check" python3 -m ruff check src tests client
  execute "Mypy type check" python3 -m mypy
  execute "Verify pip-audit ignore list" python3 -c "
import sys; sys.path.insert(0, 'src')
from artek_buddy.pip_audit_ignore import main
sys.exit(main())"

  ignores=()
  if [[ -f .github/pip-audit-ignore.txt ]]; then
    while read -r id _; do
      case "$id" in
        ''|\#*) continue ;;
      esac
      ignores+=(--ignore-vuln "$id")
    done < .github/pip-audit-ignore.txt
  fi
  execute "Pip-audit dependencies" python3 -m pip_audit -r requirements.txt -r requirements-dev.txt "${ignores[@]}"
  echo ""
fi

if [[ "$RUN_BACKEND" -eq 1 ]]; then
  echo "--- Job: backend ---"
  execute "Pytest unit & API suite with coverage" python3 -m pytest tests/unit tests/api tests/client \
    --cov=artek_buddy --cov-branch \
    --cov-report=term \
    --cov-fail-under=71
  execute "Coverage floors gate" python3 tests/coverage_floors_gate.py
  execute "OpenAPI schema export" python3 -c "
import sys; sys.path.insert(0, 'src')
from artek_buddy.openapi_export import main
sys.exit(main())"
  echo ""
fi

if [[ "$RUN_WEB" -eq 1 ]]; then
  if command -v npm >/dev/null 2>&1; then
    echo "--- Web client: client/web ---"
    execute "Web client lint" npm --prefix client/web run lint
    execute "Web client test" npm --prefix client/web run test
    execute "Web client typecheck" npm --prefix client/web run check
    echo ""
  else
    echo "--- Web client: skipped (npm not found) ---"
    echo ""
  fi
fi

echo "=== All local checks passed ==="
