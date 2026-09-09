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

Artek Buddy stores durable state in local directories **and** Docker volumes.
A tar of `data` / `workspace` / `.env` plus `pg_dump` is **not** a complete
copy: bot secrets live in the Compose named volume `credential-data`.

| Piece | Where | In the file tar? |
| --- | --- | --- |
| Desktop homes, memory books, artifacts | `./data` | yes |
| Bot workspace files | `./workspace` | yes |
| Host tokens, `CREDENTIAL_BROKER_TOKEN`, `CREDENTIAL_EXECUTOR_TOKEN` | `.env` | yes |
| Chat history, runs, pairing | Postgres volume (`memory-data`) | **no** — `pg_dump` |
| Bot named secrets (broker SQLite) | Docker volume `credential-data` | **no** — volume tar below |
| Legacy file tokens | `./data/credentials` | yes, if still present |

`.env` is required to **read** a restored broker (loopback tokens). Treat the
credential-data archive like `.env`: mode `0600`, not world-readable, never
pasted into an issue, screenshot, or public CI log.

`./data/credentials` is the **legacy** file store. After a successful
migration the live secrets are only on `credential-data`. Restoring homes and
Postgres without that volume can look fine (chats, UI) while bot secrets
created after migration are gone.

Unfinished owner jobs and in-process waiters do not survive this copy.
Postgres may still show those runs as failed or waiting. That is expected
until a recovery card exists.

Do this drill on a **separate** test host, not the owner's daily machine.

### Backing up host state

1. Stop running containers so files, Postgres, and the broker volume are quiet:
   ```bash
   docker compose down
   ```
2. Archive the data directory, workspace, and environment configuration:
   ```bash
   tar -czf artek-buddy-backup-$(date +%Y%m%d).tar.gz data workspace .env
   chmod 600 artek-buddy-backup-$(date +%Y%m%d).tar.gz
   ```
3. Archive the credential broker volume (Compose still creates/mounts it
   after `down`; `docker-compose.release.yml` uses the same volume name).
   `--no-deps` skips migrator/supervisor. `-T` keeps the archive binary-clean.
   Redirect stdout; do not `tee` it into a log. The host image must already
   exist (`artek-buddy:local` or the release image this compose file pins).
   ```bash
   docker compose run -T --rm --no-deps --entrypoint tar credential-broker \
     czf - -C /var/lib/artek-buddy/credentials . \
     > artek-buddy-credential-data-$(date +%Y%m%d).tar.gz
   chmod 600 artek-buddy-credential-data-$(date +%Y%m%d).tar.gz
   ```
4. Export PostgreSQL:
   ```bash
   docker compose up -d memory
   docker compose exec memory pg_dump -U artek artek_buddy > artek_buddy_db_$(date +%Y%m%d).sql
   chmod 600 artek_buddy_db_$(date +%Y%m%d).sql
   docker compose down
   ```

### Restoring host state

Use a clean directory and the same Compose project name as the backup host
so volume names match, or restore into the volume Compose creates here.

1. Extract the file archive:
   ```bash
   tar -xzf artek-buddy-backup-<date>.tar.gz
   ```
2. Restore the credential volume **before** `up` (migrator will not overwrite
   broker values that already exist):
   ```bash
   docker compose run -T --rm --no-deps --entrypoint tar credential-broker \
     xzf - -C /var/lib/artek-buddy/credentials \
     < artek-buddy-credential-data-<date>.tar.gz
   ```
3. Start Postgres and restore the dump:
   ```bash
   docker compose up -d memory
   docker compose exec -T memory psql -U artek -d artek_buddy < artek_buddy_db_<date>.sql
   ```
4. Start the full stack:
   ```bash
   docker compose up -d
   ```
5. Confirm a **post-migration** bot secret still works through the product
   (Bot profile & access → a named secret you created after the broker
   existed). Do not print the secret. A restore that only brings Postgres
   back is not done.

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

## Cursor client timeouts

After `AsyncClient.launch_bridge`, the host applies `with_options` so a flaky WAN
cannot wait on the SDK's implicit defaults. These knobs are host Settings
(`CURSOR_*` env). Timeouts become a retryable `AgentRuntimeTimeout` ("The model
timed out. Send again.") with `request_id` / SDK `run_id` in the log, never the
API key. `CURSOR_MAX_RETRIES` only applies to idempotent unary reads (catalog,
ping). A send that already has a run id is not retried.

| Env | Default | Meaning |
| --- | --- | --- |
| `CURSOR_UNARY_TIMEOUT_S` | `60` | Seconds for catalog, session, and send RPCs |
| `CURSOR_STREAM_TIMEOUT_S` | `600` | Seconds for one run's event stream |
| `CURSOR_MAX_RETRIES` | `1` | Extra attempts for those read-only RPCs |

## Activity log retention

The `activity` table is a workspace-monotonic SSE cursor (see #159), not the audit chain.

- Bound: the newest **10 000** rows (`DEFAULT_ACTIVITY_RETENTION`). Older rows are pruned when the log grows past twice that count, or by calling `HistoryStore.prune_activity`.
- Product state (messages, grants, members) stays in its own tables after prune.
- A client whose `after_sequence` is older than the retained window receives `thread.replay.gap` / `activity.resync` and must refetch snapshots. Do not treat a missing cursor as “start at now.”
- Do not store tokens, raw tool args, or screenshots in activity. Audit retention (#160) is a separate policy.
