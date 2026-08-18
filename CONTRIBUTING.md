# Contributing

Artek Buddy is a personal, self-hosted Raspberry Pi agent. The HTTP API is
the product. The first client is a Linux `.deb`.

## License

By opening a pull request you agree to license your contribution under
the Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

## How to work

1. Read [README.md](README.md), [CHANGELOG.md](CHANGELOG.md), and [SECURITY.md](SECURITY.md).
2. Keep JSON on the wire `snake_case`.
3. Do not add a second model provider. Cursor Cloud is the live runtime;
   `ScriptedRuntime` is for tests.
4. Do not add a vendor cloud desktop or a laptop sandbox.
5. Write the test in the same change as the code.

## Tests

Run everything from the **repository root**. A laptop or the Pi is fine.
Do not use the live compose database or the owner client token.

| Command | What | Needs | When |
| --- | --- | --- | --- |
| `make test` | Host unit + throwaway Postgres + Vitest | Python 3.13, `requirements.txt`, Docker, Node 22 | Every change. CI runs this. |
| `make test-ui` | Vite build + Playwright | Same, plus a browser. Host `:18080` | Desktop UI / e2e flows. Local only. |
| `make demo` | Records `media/demo.mp4` | Same as `test-ui`, host `:18081`, optional `ffmpeg` | README video. Local only. |

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cd client/web && npm ci && cd ../..
make test
make test-ui   # required if you touched the window
```

- Host unit: `python -m unittest discover -s tests -p 'test_*.py' -t .` with `PYTHONPATH=src`. No Postgres, no Cursor, no `.env`.
- Integration: `python tests/run_integration.py` starts `postgres:16-alpine` on loopback **55432** (`artek_buddy_test`) and deletes it after. It refuses `127.0.0.1:5432/artek_buddy`. If `TEST_DATABASE_URL` is already set to a non-live URL, that URL is used.
- Client unit: `cd client/web && npm test` (Vitest).
- UI: `make test-ui` builds `client/web`, starts throwaway Postgres on **55433** and a scripted FastAPI on **18080**, then drives the packaged proxy. Token is `ui-e2e-token`. It never opens live `:8080` or `~/.config/artek-buddy/token`.
- New host behavior → `tests/test_<area>.py`. New shell helper → `client/web/src/**/*.test.ts`. New window flow → `client/web/e2e/*.spec.ts`.
- `make test` must stay green. Do not commit if it fails.

## Linux client package

Owners build their own `.deb`. CI does not attach one.

```bash
client/build-deb.sh
sudo dpkg -i artek-buddy-client_<version>_all.deb
sudo apt-get install -f
```

Build on a machine with Node 22. Install on Debian/Ubuntu. Do not commit `*.deb`.

## What not to commit

- `.env`, `client/token`, `client/url`, `*.deb`, `data/`, `docs/`,
  `docker-compose.local.yml`, Funnel hostnames, tailnet or LAN IPs
- Packaged owner clients. CI does not attach a `.deb`; each owner builds
  their own.

## Pull requests

- One product version for host and client (`VERSION`,
  `src/artek_buddy/__init__.py`, `client/VERSION`).
- Update [CHANGELOG.md](CHANGELOG.md) when behavior ships.
- English in product docs. Keep the change focused.
