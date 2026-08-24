# Contributing

Artek Buddy is a personal, self-hosted Raspberry Pi agent. The HTTP API is
the product. The first client is a Linux `.deb`.

## License

By opening a pull request you agree to license your contribution under
the Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

## How to work

1. Read [README.md](README.md), [CHANGELOG.md](CHANGELOG.md), [SECURITY.md](SECURITY.md), and [THREAT-MODEL.md](THREAT-MODEL.md).
2. Branch from `develop`. Do not commit or push `main`.
3. Keep JSON on the wire `snake_case`.
4. Do not add a second model provider. Cursor Cloud is the live runtime.
5. Do not add a vendor cloud desktop or a laptop sandbox.

CI is `.github/workflows/test.yml` on PRs into `develop`/`main` and on pushes to those branches: `quality` (Ruff + mypy + pip-audit), `backend`
(pytest + coverage + `npm audit --audit-level=high`, no Docker desktop), `scan`
(Trivy filesystem), `ui` (scripted `.deb` window),
and optional `live` (Grok, needs the Actions secret). CodeQL is
`.github/workflows/codeql.yml` (Python + JavaScript). Alerts on a PR are
work: fix the bug, or name the residual in [THREAT-MODEL.md](THREAT-MODEL.md).
Do not ignore them as scanner noise. Do not point a runner at the live `:8080` stack or the owner
Postgres. Do not print `CURSOR_API_KEY`, host tokens, or
`docker compose config` in Actions — the repo is public.

Python tool config lives in `pyproject.toml`. Same checks as the `quality` job:

```bash
python -m pip install -r requirements-dev.txt
python -m ruff format --check src tests client
python -m ruff check src tests client
python -m mypy
```

Window TypeScript (from `client/web`):

```bash
PYTHONPATH=src python -m artek_buddy.openapi_export
npm ci
npm run generate:openapi
npm run lint
npm test
npm run check
```

Runtime `/docs` stays off. The dump writes `client/web/openapi.json`; `npm run generate:openapi` writes `client/web/src/generated/openapi.d.ts`. Dirty schema/types fail the `backend` job.

## Linux client package

GitHub Releases attach `artek-buddy-client_<version>_all.deb` (no baked host URL),
`SHA256SUMS`, CycloneDX SBOMs, and `install-host.sh` after a `VERSION` bump on
`main` when `test` on that commit is green (`release.yml` is `workflow_run` on
`test`). Notes are the changelog section for that version. The `test` workflow
builds a `.deb` for Playwright; it does not upload that artifact.

You can still build a local package (unreleased tree, or `ARTEK_BAKE_URL=1`):

```bash
client/build-deb.sh
sudo dpkg -i artek-buddy-client_<version>_all.deb
sudo apt-get install -f
```

Build on a machine with Node 22. Install on Debian/Ubuntu. Do not commit `*.deb`.

## What not to commit

- `.env`, `client/token`, `client/url`, `*.deb`, `data/`, `docs/`,
  `docker-compose.local.yml`, Funnel hostnames, tailnet or LAN IPs
- Packaged owner clients. Releases attach a clean `.deb`; do not commit
  a local build.

## Pull requests

Daily work is a pull request **into `develop`**. `main` is release-only:
open `develop` → `main` when shipping. Never push `main` directly.
New issues can use the GitHub forms (bug, feature, engineering).
PRs into `develop` or `main` cannot merge while any of these checks is red:
`quality`, `backend`, `ui`, `scan`, `live_gate`, `analyze (python)`,
`analyze (javascript-typescript)`, and `CodeQL`. That is rulesets
**Protect develop** and **Protect main**. `live` is not required (it needs
the Actions secret; `live_gate` already records skipped vs failed). Review
count is 0; do not push `main` or `develop` directly.
A merge into `main` that changes `VERSION` publishes a GitHub Release only after
the **push** `test` run on that commit is green (`release.yml` is `workflow_run`
on `test`, not a parallel `push`). The computer image is not built in Actions.
The host image is pushed by digest, Trivy-scanned (HIGH and CRITICAL), then
tagged as the version and `latest` — same digest, no rebuild. A second upload
of the same Release asset name fails (no `--clobber`). GitHub Releases stay;
`infra/prune-releases.sh` is a **manual** operator script, not the default
release path.

- One product version for host and client (`VERSION`,
  `src/artek_buddy/__init__.py`, `client/VERSION`).
- Update [CHANGELOG.md](CHANGELOG.md) when behavior ships.
- English in product docs. Keep the change focused.
