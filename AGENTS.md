# Repository Agent Guide (AGENTS.md)

This document maps the repository architecture, execution boundaries, and CI-aligned development commands for coding agents and contributors.

For the in-chat agent prompt inside the desktop sandbox container, see [`workspace/AGENTS.md`](workspace/AGENTS.md).

---

## Read Order for Non-Trivial Changes

When starting a non-trivial change, read files in this order:

1. [`VISION.md`](VISION.md) — Product invariants, core assumptions, and explicit non-goals (no Kubernetes, no Redis, no multi-tenant SaaS).
2. [`ARCHITECTURE.md`](ARCHITECTURE.md) — System components, supervisor boundary, service communication, and data flow.
3. [`THREAT-MODEL.md`](THREAT-MODEL.md) — Security boundaries, trust levels, capability isolation, and residual risk tracking.
4. [`CONTRIBUTING.md`](CONTRIBUTING.md) — Git workflow (branch from `develop`, never push `main`), CI job expectations, and PR conventions.
5. [`client/WINDOW.md`](client/WINDOW.md) — The living specification and locator map for the GTK `.deb` and mobile host-page UI.
6. Relevant ADRs in [`adr/`](adr/) — Architectural decisions (Docker socket ownership, Team vs Private desktops, Compose vs Kubernetes, etc.).

---

## Architecture Map

- **Host API (`src/artek_buddy/`)**: FastAPI application serving HTTP REST and SSE events. Communicates with Postgres for persistence and with the local supervisor for sandbox lifecycle.
- **Supervisor (`infra/supervisor/`)**: Isolated service listening on `127.0.0.1:7091`. The **only** process with access to `/var/run/docker.sock`. Manages desktop container creation, execution, and cleanup.
- **Client (`client/`)**: 
  - `client/artek_buddy.py`: Native Linux GTK3/WebKit wrapper with loopback proxy.
  - `client/web/`: React + Vite single-page application served by both the native desktop client and the host HTTP server on `:8080` (phone / browser).
- **Tests**:
  - `tests/unit/`: Pure Python unit tests (fast, no DB or network).
  - `tests/api/`: FastAPI TestClient tests with scripted runtime and fake sandbox.
  - `tests/client/`: Native Python client and proxy tests.
  - `tests/live/`: Playwright UI tests against the packaged `.deb` client (`ui` CI job).
  - `tests/live_web/`: Playwright UI tests against the host page on iPhone 11 Pro 375×812 (`ui_web` CI job).

---

## Invariants and Hard Rules

- **Do not push `main`**: All work branches from `develop` and merges via PR into `develop`.
- **Do not hit live `:8080` from pytest**: Tests use FastAPI `TestClient`, scripted runtime (`AGENT_RUNTIME=scripted`), and fake sandbox (`SANDBOX_PROVIDER=fake`). Never point tests at a live host or the owner's running database.
- **OpenAPI `/docs` stays OFF at runtime**: Generated types (`client/web/src/types/openapi.ts`) are exported ahead-of-time via `python -m artek_buddy.openapi_export`. Interactive `/docs` and `/redoc` are disabled in production.
- **Docker socket stays on the supervisor**: The host API container, the client, and desktop sandboxes never mount `/var/run/docker.sock`.
- **No technology zoo**: Stick to Compose, Postgres, and Python/TypeScript. Reject PRs adding Redis, Kubernetes, Celery, or extra third-party daemons.

---

## Development and CI Commands

These commands match the jobs in `.github/workflows/test.yml`:

### 1. Quality (`quality` job)
```bash
# Check formatting and style
python -m ruff format --check src tests client
python -m ruff check src tests client

# Type checking
python -m mypy

# Dependency security audit
python -m pip_audit --strict
```

### 2. Backend tests and OpenAPI (`backend` job)
```bash
# Export OpenAPI schema and generate TypeScript types
PYTHONPATH=src python -m artek_buddy.openapi_export
cd client/web && npm run openapi:generate && npm run check && cd ../..

# Run backend pytest suite with coverage
pytest tests/unit tests/api tests/client --cov=src/artek_buddy --cov-fail-under=71
```

### 3. Local All-in-One Check
```bash
# Runs quality, backend, and web checks
make check
# Or directly via script:
./scripts/check.sh
```

### 4. UI Tests (`ui` and `ui_web` jobs)
UI tests run in CI with Playwright against a mock server:
```bash
# Desktop .deb UI suite (ui job)
ARTEK_UI=1 pytest tests/live

# Mobile host-page suite (ui_web job, iPhone 375x812)
ARTEK_UI=1 pytest tests/live_web
```
