# Engineering practices and quality gates

This document describes how Artek Buddy is tested, validated, and maintained.
For trust boundaries, authentication architecture, and residual risk, see
[THREAT-MODEL.md](THREAT-MODEL.md). For operational runtime setup and backups,
see [OPERATIONS.md](OPERATIONS.md).

## Continuous Integration jobs

Every commit and pull request targeting `develop` or `main` is gated by
`.github/workflows/test.yml` and `.github/workflows/codeql.yml`. Merges are
blocked unless all required jobs pass.

| Job | Responsibility | Execution context |
| --- | --- | --- |
| `quality` | Ruff formatting and linting (`B`, `S`), mypy static types, dependency audit (`pip-audit`), and Conventional Commits title validation | Ephemeral runner |
| `backend` | Fast API unit, contract, and database tests against PostgreSQL 16; branch and line coverage; OpenAPI schema and TypeScript type synchronization; web client test/lint/typecheck | Runner + Postgres service container |
| `ui` | Python Playwright UI tests against the packaged Debian `.deb` client communicating with host HTTP | Runner + Docker Compose host stack + WebKit client |
| `ui_web` | Python Playwright UI tests against the direct host-served web page (`/` and `/app`) formatted at mobile viewport (iPhone 11 Pro 375×812) | Runner + Docker Compose host stack |
| `scan` | Trivy filesystem scanner checking for HIGH and CRITICAL vulnerabilities, honoring `.trivyignore` | Ephemeral runner |
| `live_gate` | Evaluates whether `CURSOR_API_KEY` is configured in repository secrets before dispatching cloud model runs | Runner gate |
| `live` | Live end-to-end integration testing executing real prompt turns against Cursor Cloud (`grok-4.6`) on the desktop `.deb` client | Runner + real model API |
| `live_web` | Live end-to-end integration testing executing real prompt turns against Cursor Cloud on the host-served mobile surface | Runner + real model API |
| `CodeQL` | GitHub Advanced Security static code analysis for Python and JavaScript/TypeScript | GitHub CodeQL action |

## Coverage and static typing as ratchets

Code coverage and type checking are used as directional ratchets against
regressions rather than vanity metrics:

1. **Global coverage floor:** The entire host backend maintains a minimum 71%
   statement and branch coverage requirement (`--cov-fail-under=71`).
2. **Security-critical module floors:** Security and authorization boundaries
   enforce strict per-file floors in `tests/coverage_floors_gate.py` that cannot
   be masked by broader application code:
   - `src/artek_buddy/auth.py`: 100%
   - `src/artek_buddy/fs_jail.py`: 80%
   - `src/artek_buddy/db/connection.py`: 100%
   - `src/artek_buddy/db/sql_split.py`: 75%
   - `src/artek_buddy/db/history/store.py`: 80%
   - `src/artek_buddy/supervisor/logic.py`: 60%
3. **Mypy type ratchets:** Core security modules (`auth`, `fs_jail`, and the
   migration runner) strictly enforce `attr-defined`, `arg-type`, `union-attr`,
   and `assignment` type rules, with remaining legacy modules ratcheted downward.
4. **OpenAPI and TypeScript consistency:** The backend exports its OpenAPI schema
   via `python -m artek_buddy.openapi_export`, and the client regenerates its
   TypeScript types via `npm run generate:openapi`. A git diff check ensures that
   wire protocol changes are always committed alongside generated types in the
   same pull request.

## Why Docker Compose, not Kubernetes

Artek Buddy intentionally uses Docker Compose rather than an orchestration engine
like Kubernetes:

- **Target environment:** The software is designed to run on a single personal
  Linux machine, mini PC, or Raspberry Pi.
- **Resource footprint:** An idle agent host should consume minimal CPU and RAM.
  Kubernetes control planes, API servers, and etcd clusters consume substantial
  memory before running any actual workloads.
- **Subprocess and sandbox isolation:** Sandboxed bot desktops require direct
  Docker Engine socket mediation through the loopback supervisor. Docker container
  limits (`CapDrop: ALL`, `ShmSize`, `PidsLimit`, `Memory`, `no-new-privileges`)
  are configured directly and predictably without complex CNI or CSI layers.
- **Maintainability:** Systemd units wrapping `docker compose` allow host
  reboots, auto-start, and volume storage to remain clear, auditable, and
  trivially debuggable using standard Linux tooling.

## Residual risks and failure modes

The project documents intentional design decisions, sandbox boundaries, and
residual security trade-offs in [THREAT-MODEL.md](THREAT-MODEL.md). Key boundary
principles include:

- The host API token (`AGENT_HTTP_TOKEN`) and Docker socket never cross to the
  desktop client or browser page.
- Bot desktops drop all Linux capabilities (`CapDrop: ALL`) and run on an
  isolated bridge network with inter-container communication disabled (`icc: false`).
- Host-level file modifications and shell execution require explicit owner
  consent cards in the chat thread.
- Public network binding relies on a private Tailscale tailnet rather than open
  internet port forwards.

## Performance budgets and Pi measurement (`infra/perf_budget.py`)

To prevent memory or latency regressions on real hardware (Raspberry Pi or mini PC) without requiring physical hardware runners in GitHub Actions, the repo provides an in-tree benchmark tool:

```bash
# Run performance benchmarks and output JSON + Markdown
python3 infra/perf_budget.py --output-json perf-report.json --output-md perf-report.md --print-summary

# Or via make:
make perf
```

### Observation policy
- Benchmarks operate in **observe** mode to record empirical baselines across package installation, cold window launch, session resume, large thread parsing (500-message fixture), initial SSE event dispatch latency, replay of N events, and process RSS (idle/peak).
- CI and local gates avoid brittle latency thresholds until a stable median is established across multiple hardware runs.
- Reports record hardware architecture, CPU count, memory, OS kernel, and git commit.
- All benchmark artifacts are automatically secret-scanned with token redaction before being written to disk.
- To calibrate and verify that metric tracking is responsive, pass `--calibrate-sleep <seconds>` (e.g. `--calibrate-sleep 0.1`) which introduces a deterministic delay to assert that metric timers track wall-clock shifts accurately.
