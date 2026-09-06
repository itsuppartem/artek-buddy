# Operations and deployment guide

This document covers running, monitoring, backing up, and maintaining an
Artek Buddy host. For architectural components, see [ARCHITECTURE.md](ARCHITECTURE.md).
For quality gates, see [ENGINEERING.md](ENGINEERING.md). For threat modeling,
see [THREAT-MODEL.md](THREAT-MODEL.md).

## Network policy and access

### Host binding and Tailscale

- **Host bind:** The API service runs with `network_mode: host` and listens on
  `0.0.0.0:8080`. This allows loopback access from co-located services and tailnet
  access across network interfaces.
- **Access policy:** Access to the host must be mediated through a secure private
  network such as a Tailscale tailnet. Do **not** port-forward `:8080` to the
  public internet on your home router.
- **Tailscale Funnel warning:** Tailscale Funnel makes port `:8080` publicly
  accessible from the internet. While pairing requires a one-time code and device
  cookies, Funnel publishes the entire API endpoint. Use Funnel only if you
  accept the risk of exposing the HTTP surface to the internet.
- **Database isolation:** PostgreSQL publishes port `5432` bound strictly to
  `127.0.0.1`. It is never exposed on external interfaces.
- **Supervisor isolation:** The Docker supervisor (`:7091`), memory gateway (`:8420`),
  and credential broker (`:8431`) listen only on `127.0.0.1` and require derived
  authentication tokens.

## Health checks and readiness

The host exposes dedicated endpoints for liveness and readiness monitoring:

- `GET /health`: Process liveness check. Returns `200 OK` if the Python FastAPI
  application process is alive and responding.
- `GET /livez`: Equivalent process liveness endpoint.
- `GET /readyz`: Dependency readiness check. Returns `200 OK` only when PostgreSQL
  database connectivity is healthy and active. Returns `503 Service Unavailable`
  if the database is down or still performing migrations.
- `GET /local/status`: Local pairing status and nonce endpoint for client surfaces.

Docker Compose healthchecks in `docker-compose.yml` probe `/readyz` before
considering the `artek-buddy` service healthy.

## Backup and restore

Artek Buddy stores durable state in local directories and Docker volumes:

- `./data`: SQLite credential databases, agent memory books, bot profiles, and
  sandboxed desktop home directories (`./data/homes/{home_key}`).
- `./workspace`: Working directory for bot file creation and execution.
- Docker PostgreSQL volume: Durable chat history, messages, turns, and event records.

### Backing up host state

1. Stop running containers to ensure database and volume consistency:
   ```bash
   docker compose down
   ```
2. Archive the data directory, workspace, and environment configuration:
   ```bash
   tar -czf artek-buddy-backup-$(date +%Y%m%d).tar.gz data workspace .env
   ```
3. Export PostgreSQL database dump:
   ```bash
   docker compose up -d memory
   docker compose exec memory pg_dump -U artek artek_buddy > artek_buddy_db_$(date +%Y%m%d).sql
   docker compose down
   ```

### Restoring host state

1. Extract the file archive:
   ```bash
   tar -xzf artek-buddy-backup-<date>.tar.gz
   ```
2. Start the database service:
   ```bash
   docker compose up -d memory
   ```
3. Restore the SQL database dump:
   ```bash
   docker compose exec -T memory psql -U artek -d artek_buddy < artek_buddy_db_<date>.sql
   ```
4. Start the full stack:
   ```bash
   docker compose up -d
   ```

## Production release process

Releases are published through GitHub Actions using a strict verification pipeline:

1. Feature and bugfix PRs merge into `develop`.
2. A release PR merges `develop` into `main`, bumping the `VERSION` file.
3. The merge push triggers the full `test.yml` and `codeql.yml` workflows on `main`.
4. Once and only once the push `test` and CodeQL runs on `main` are 100% green:
   - The maintainer initiates `.github/workflows/release.yml` via `workflow_dispatch`.
   - The release workflow asserts that the release commit matches the verified
     `main` commit SHA.
   - It builds multi-arch container images (`linux/amd64`, `linux/arm64`), runs Trivy
     vulnerability scans, publishes the images to GHCR, builds Debian `.deb` packages,
     attests GitHub build provenance, and creates a tagged GitHub Release.

## Performance measurement on the host (`infra/perf_budget.py`)

When testing releases or observing performance metrics on physical hardware (such as a Raspberry Pi):

1. Run the benchmark tool to collect structured performance data:
   ```bash
   python3 infra/perf_budget.py --output-json perf-report.json --output-md perf-report.md
   ```
2. The command outputs:
   - Comparable machine-readable JSON (`perf-report.json`) tracking latency and RSS medians.
   - A summary Markdown report (`perf-report.md`) detailing hardware specs, commit SHA, and test outcomes.
   - All output is automatically scrubbed of sensitive secrets or tokens.
3. Use `--calibrate-sleep <seconds>` to verify measurement sensitivity when benchmarking timing changes.
