# Contributing

Artek Buddy is a personal, self-hosted Raspberry Pi agent. The HTTP API is
the product. The first client is a Linux `.deb`.

## License

By opening a pull request you agree to license your contribution under
the Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

## How to work

1. Read [README.md](README.md), [CHANGELOG.md](CHANGELOG.md), and [SECURITY.md](SECURITY.md).
2. Branch from `develop`. Do not commit or push `main`.
3. Keep JSON on the wire `snake_case`.
4. Do not add a second model provider. Cursor Cloud is the live runtime.
5. Do not add a vendor cloud desktop or a laptop sandbox.

CI is `.github/workflows/test.yml`: `backend` (no Docker desktop), `ui`
(scripted `.deb` window), and optional `live` (Grok, needs the Actions
secret). Do not point a runner at the live `:8080` stack or the owner
Postgres. Do not print `CURSOR_API_KEY`, host tokens, or
`docker compose config` in Actions — the repo is public.

## Linux client package

GitHub Releases attach `artek-buddy-client_<version>_all.deb` (no baked host URL)
after a `VERSION` bump on `main` when `test` on that commit is green
(`release.yml` is `workflow_run` on `test`). The `test` workflow builds a
`.deb` for Playwright; it does not upload that artifact.

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
PRs into `main` cannot merge while `backend` or `ui` is red.
A merge into `main` that changes `VERSION` publishes a GitHub Release only after
the **push** `test` run on that commit is green (`release.yml` is `workflow_run`
on `test`, not a parallel `push`). The computer image is not built in Actions.
Only the five newest Releases stay; `infra/prune-releases.sh` deletes the rest
and matching GHCR tags.

- One product version for host and client (`VERSION`,
  `src/artek_buddy/__init__.py`, `client/VERSION`).
- Update [CHANGELOG.md](CHANGELOG.md) when behavior ships.
- English in product docs. Keep the change focused.
