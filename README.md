# Artek Buddy

**Self-hosted Grok bot alternative** and Cursor Cloud desktop agent you run on a Raspberry Pi. Open-source personal AI assistant with a real Linux computer-use sandbox, a Debian `.deb` client, FastAPI + Postgres on the host, and **your** Cursor quota (`cursor-sdk` → Grok / Composer). Not ChatGPT, not a hosted Grok bot, not a vendor cloud VM.

Python · FastAPI · Postgres 16 · Docker · Xvfb / Chromium / noVNC · Tailscale · Raspberry Pi 5 · Debian / Ubuntu client · Apache-2.0

If you searched for a self-hosted Grok bot, a Cursor agent host, computer-use on a Raspberry Pi, an open-source personal assistant with a persistent Linux desktop, a Tailscale-paired desktop agent, or a local alternative to hosted ChatGPT / Claude computer sandboxes — this is that stack.

Shipped versions: [CHANGELOG.md](CHANGELOG.md).

## Demo

Pair the Linux window, ask a question, answer the bot’s card, reply in the thread, and watch Chromium open Wikipedia on the Pi desktop.

![Artek Buddy demo](media/demo.gif)

## Why this exists

Most chat assistants are good at answering one request, but poor at being a long-lived personal worker: they lose context, cannot keep a task-specific desktop, and usually require you to adopt another account, quota, or hosted environment.

Artek Buddy combines an always-on Pi with the Cursor models you already pay for. It is for people who want a practical agent available from their own computer: one that can retain explicitly saved context, run scheduled work, use a disposable Linux desktop, and ask for help when a human decision or takeover is needed.

The result is **your Cursor key, your model quota, your Pi, and your client**. The HTTP API is the product; Cursor Cloud is the only live model runtime. There is no second model provider login.

> Conversations, bot settings, memory, schedules, and desktops are hosted on the Pi. Prompts and relevant context still go to Cursor Cloud to run the selected model; this is not an offline model.

## What you can do today

- **Keep separate agents for separate responsibilities.** Create bots for research, recurring monitoring, coding or operations tasks, or a personal assistant. Each bot has an independent thread, profile, memory, schedule, and desktop mode.
- **Give an agent a real Linux workspace.** A bot can open URLs and local paths, launch or close graphical apps, inspect its screen, and interact with a Chromium desktop on this Pi. Opening a website, filling a form, clicking, or typing shows **Allow once / Always / Deny** in the thread and does not run until you answer. You can watch the view-only preview or take control when the agent needs you to complete a login, CAPTCHA, payment, or other human-only step. **Team** bots share one desktop; **Private** gives that bot its own container — see below.
- **Let an agent work on this Linux PC like SSH.** After you pair the `.deb`, it can read a file or list a folder under your home without a card. Writing a file or running a command that can change the PC asks **Allow once / Always / Deny** once for that bot — Always covers later writes and commands on this PC. Read-only shell (`ls`, `cat`, `echo`, …) does not ask. The host token never appears in the page. This is not a VNC of the laptop.
- **Run work without keeping your laptop on.** The Pi runs the host continuously. Routine prompts run on a cron schedule; idle desktops sleep automatically.
- **Retain useful context from chat.** Talk normally — name, city, tone, repo, a standing rule for this bot. The host writes a short card; there is no profile form. Every bot sees the owner book. Work notes (repo, branch) come back when the turn is about that work. A chat-local charter stays on that bot. The Memory panel shows the same cards. Replayable skills are later.
- **Work on more than one thing at a time.** A lead agent can create workers for distinct tasks, show their progress in the chat, and stop, restart, or steer a worker when requirements change. A message sent while a lead is working is injected at the next tool (like Codex steer / Grok follow-up). If nothing is left to inject, it runs as a follow-up after the turn.
- **Use a chat that can ask back.** Agents can post a useful intermediate update, show multiple-choice question cards, and wait for your answer. Completed answers and actions stay in the thread history.
- **Attach a file or a screenshot to the next send.** Plus, drop, or Ctrl+V. Copying a file on this PC (not only a screenshot) attaches the file — not the path as text. Images, video, and audio show a preview in the composer before you press Enter. The host copies them into that bot’s `inbox/`. Deleting the chat removes that chat’s inbox copies; a shared Team home and other bots’ files stay.
- **Open the sandbox home on the desktop.** Take control, then right-click → **Files** (PCManFM). The computer pane is screen, memory, and routines — not a second file list.
- **Download a file the agent made.** The bot posts a file card in the thread. Pictures, video, and audio show a preview there. Download opens the system Save dialog (Downloads / Загрузки by default). The copy stays on the Pi with that chat.
- **Use the same agent from your Linux PC securely.** Pair the desktop window once over Tailscale. The client holds a device token; the Pi's host token and Docker access never leave the Pi.

Typical uses include: a morning briefing routine, a research bot that opens sources on its desktop after you Allow the site, a project assistant that remembers repository conventions, a bot that reads a notes file from your PC, a long-running task delegated to workers, or a desktop automation task where you take over only for the final human step.

### Team vs Private computer

This is not “your PC vs someone else’s”. Both modes are Linux desktops **on this Raspberry Pi**. Chat, memory, and routines are already per-bot either way. The switch only chooses the desktop box.

| Mode | What is created | When to use |
| --- | --- | --- |
| **Team** (default) | One shared container `artek-bot-team-{workspace}` and one home `data/homes/team-{workspace}`. Every Team bot attaches to that same box. If one bot is using it, another Team bot waits. | Daily bots that can take turns on one Chromium. Light on RAM. |
| **Private** | A **new** container `artek-bot-{bot_id}` and a **new** home `data/homes/{bot_id}`. Cookies, downloads, and the open windows stay on that bot. It can run at the same time as the Team desktop (and other Private bots). | A bot that must keep its own browser session, or run while another bot is already on the shared box. Costs a second desktop on the Pi. |

Create-bot and Edit profile both have the Team / Private control. Changing the mode rebinds the bot to the other computer row; it does not copy the old home. Idle boxes sleep; starting a Private bot that has never booted provisions its container then.

The home stays on the Pi disk (`data/homes/{home_key}`). Rebooting the Pi, Stop, or Restart does **not** wipe Chromium logins or downloads. The box does not auto-start after a host reboot (`RestartPolicy: no`); the next boot reuses the same home. **Reset** in Bot Settings destroys the container and deletes that home. Team reset wipes the shared desktop for every Team bot.

## Boundaries

- Artek Buddy is a personal, self-hosted system, not a multi-tenant SaaS or a replacement for a managed browser-automation platform.
- The computer sandbox is isolated from your laptop, but it is still a capable Linux environment. Give bots only the access and instructions you are comfortable delegating.
- Model output can be wrong and browser workflows can fail. Review important results and take control for sensitive or irreversible actions.
- The shipped client is Linux-only today. The host API is independent of that client, so other clients can be built later.

## Architecture at a glance

| Part | Responsibility |
| --- | --- |
| Raspberry Pi host | FastAPI `:8080`, Postgres history and memory, optional loopback memory index `:8420`, cron worker, and the Docker supervisor |
| Agent runtime | Cursor Cloud through `cursor-sdk`; default model is `grok-4.6`, configurable in `.env` |
| Bot desktop | A graphical Linux container with Xvfb, Chromium, view-only VNC, and temporary user takeover |
| Linux client | Pairing, bot list, live thread, notifications, memory/routine controls, and computer preview |

```
.deb  →  Tailscale tailnet (free plan)  →  FastAPI on the Pi  →  Cursor Cloud
         Funnel only after you read the warning below
                                        Linux desktop container on this Pi
```

## Where things run

| Piece | Machine | You install |
| --- | --- | --- |
| Host stack (API, Postgres, supervisor, worker, computer image) | Raspberry Pi (or any Linux box you leave on) | Docker + Compose, `.env`, Tailscale |
| Tests (`make test` / `make test-ui`) | Pi or a laptop with the repo | Python 3.13, Node 22, Docker. Never the live `:8080` stack |
| `.deb` **build** | Pi or laptop | Node 22, `dpkg-deb` |
| `.deb` **install** + daily window | Debian / Ubuntu PC | The package + Tailscale. Pairing talks to the Pi |

## Bring it up

You need: a Cursor account with an active subscription, Docker + Compose on the Pi, Tailscale on the Pi and on the owner PC (the **free Personal plan is enough**), and a Debian/Ubuntu PC for the window.

### 1. Cursor API key

The host is not the Cursor IDE. It calls Cursor Cloud with a **user API key**. Team Admin keys do not work with the SDK yet.

1. In the Cursor app: click your **account / profile** (top right) → **Dashboard**. Or open [cursor.com/dashboard/api](https://cursor.com/dashboard/api) in a browser and sign in with the same account.
2. Open **API Keys**.
3. **New API Key**. Name it something like `artek-buddy-pi`.
4. Copy the key **now**. You will not see it again. It starts with `crsr_`.

Keep that key on the Pi only. Never commit it.

### 2. Choose a model

The key’s catalog is account-specific. This repo defaults to Grok because that quota is separate from the main Cursor models and otherwise sits idle.

| `.env` | Default | Meaning |
| --- | --- | --- |
| `CURSOR_MODEL` | `grok-4.6` | Model id from Cursor’s catalog |
| `CURSOR_MODEL_EFFORT` | `xhigh` | Reasoning effort when the model supports it |
| `CURSOR_MODEL_FAST` | `true` | Prefer the fast variant when one exists |

After the host is up, list what **this key** can actually run:

```bash
TOKEN=$(grep AGENT_HTTP_TOKEN .env | cut -d= -f2)
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/v1/models
```

Put one of those `id` values in `CURSOR_MODEL`. Restart the host. If the id is not in the catalog, the host refuses to start.

Common ids you may see: `grok-4.6`, `composer-2.5`, `auto-smart` (Cursor Router, if your team allows it). Do not guess — use the list above.

### 3. Host on the Raspberry Pi

On the Pi (this machine):

```bash
sudo apt-get update
sudo apt-get install -y git docker.io docker-compose-v2
sudo usermod -aG docker "$USER"   # then log out and back in
```

```bash
git clone https://github.com/itsuppartem/artek-buddy.git
cd artek-buddy
cp .env.example .env
```

Edit `.env` (the file is gitignored):

```bash
CURSOR_API_KEY=crsr_your_key_here
AGENT_HTTP_TOKEN=$(openssl rand -hex 24)
# paste the printed token into AGENT_HTTP_TOKEN=
CURSOR_MODEL=grok-4.6
CURSOR_MODEL_EFFORT=xhigh
CURSOR_MODEL_FAST=true
MEMORY_DB_PASSWORD=$(openssl rand -hex 16)
```

`AGENT_HTTP_TOKEN` stays on the Pi. The desktop window never gets it. Devices pair and receive their own token.

If you already run an older compose stack, add `MEMORY_DB_PASSWORD` to `.env` (use the password Postgres was created with) before the next `docker compose up`. Then stop and boot each desktop so new boxes join the isolated `artek-computers` network.

Build the desktop box image once, then start the stack:

```bash
docker compose --profile build build computer
docker compose up -d --build
curl -s http://127.0.0.1:8080/health
```

You want `{"ok": true, ...}`. Logs if it is not:

```bash
docker compose logs -f artek-buddy
```

A bad or missing key, or a model id that is not in the catalog, shows up there at boot.

### 4. Reach the Pi over Tailscale

The owner PC talks to this Raspberry Pi on a Tailscale tailnet. That is the daily path. You do not open LAN ports and you do not need a paid Tailscale plan.

The **free Personal plan** is enough: one always-on Pi, one or a few owner PCs, MagicDNS if you want a name instead of an IP. Funnel (public HTTPS) is optional, on that plan, and **exposes the whole host API** — see step 6 before you turn it on.

1. Install Tailscale on the Pi and on the desktop PC: [tailscale.com/download](https://tailscale.com/download).
2. Sign in with the same account (or any tailnet both machines belong to).
3. On the Pi:

```bash
sudo tailscale up
tailscale ip -4
```

The host URL from another PC is `http://<that-ip>:8080`. If MagicDNS is on, `http://<pi-hostname>:8080` works too.

Keep the tailnet IP and Funnel hostname out of git.

### 5. Build and install the Linux `.deb`

There is **no ready `.deb` on GitHub**. CI does not attach one. Each owner builds a local package and copies that file to the desktop PC. Do not upload it to Releases or commit it.

| Step | Where | What you need |
| --- | --- | --- |
| Mint a pairing code | **Pi** (running stack) | `docker exec artek-buddy python -m artek_buddy pair` — 15 minutes, one use |
| Build the package | **Pi or any Linux box with Node 22** | `git`, `npm`, `dpkg-deb` |
| Install the package | **Debian / Ubuntu owner PC** | `python3`, GTK, WebKit (pulled by `apt`) |

On the machine that has the repo and Node:

```bash
# Node 22+ on PATH (this Pi keeps a local install under ~/.local/node)
client/build-deb.sh
```

That writes `artek-buddy-client_<version>_all.deb` in the repo root (gitignored). Copy it to the desktop PC.

On the desktop PC:

```bash
sudo dpkg -i artek-buddy-client_0.10.21_all.deb
sudo apt-get install -f
```

`apt-get install -f` pulls: `python3`, `python3-gi`, `gir1.2-gtk-3.0`, WebKitGTK, `xdg-utils`, `libnotify-bin`.

Upgrade later with a newer `.deb` of a **different version** (`dpkg -i` the new file). Do not overwrite the same filename in the repo when you bump `VERSION`. Remove with `sudo apt-get remove artek-buddy-client`. Pairing files stay in `~/.config/artek-buddy/` until you delete them.

Optional untracked `client/url` (one line, e.g. `http://<pi-tailscale-ip>:8080`) is baked into the package and prefills the pair form. Never put a token in that file.

Open **Artek Buddy** from the app menu (or `artek-buddy`).

1. Host URL — `http://<pi-tailscale-ip>:8080` from the owner PC (step 4). Use `http://127.0.0.1:8080` only if the window runs on the Pi itself.
2. Pairing code from the `pair` command on the Pi.
3. Device name (this computer).
4. **Pair**.

The window stores `~/.config/artek-buddy/{token,url}` (mode `600`). Then: **+** to create a bot, type in the composer, Shift+Enter for a new line, Enter to send. More client notes: [client/README.md](client/README.md).

### 6. Optional public HTTPS (Tailscale Funnel)

Daily use is the tailnet URL from step 4. Funnel publishes `:8080` to the
public internet (`https://<your-machine>.ts.net`). Screen URLs now require
a Bearer token, but **every other host route is on that hostname too**.
Do not Funnel until you have a strong `AGENT_HTTP_TOKEN`, pairing
rate-limits are enough for you, and you accept that a leaked device token
is a public credential.

```bash
sudo tailscale funnel --bg 8080
```

Put that URL in the client (`client/url` or the pair form). **Never commit the hostname.** Prefer the tailnet URL unless you truly need the public one.

## Day to day

| Task | Command |
| --- | --- |
| Health | `curl -s http://127.0.0.1:8080/health` |
| New pairing code | `docker exec artek-buddy python -m artek_buddy pair` |
| Rebuild after a pull | `docker compose up -d --build` |
| Change model | edit `CURSOR_MODEL` in `.env`, then `docker compose up -d` |
| Host logs | `docker compose logs -f artek-buddy` |
| Client log | `~/.config/artek-buddy/client.log` |

The worker (`artek-buddy-worker`) wakes due routines through the same `threads.send` path. No extra GUI.

## Tests

Run tests from the **repo root** on a machine that is allowed to start throwaway Docker containers. The Pi is fine. **Do not** point tests at the live owner stack (`:8080` or Postgres `127.0.0.1:5432/artek_buddy`).

| Command | What it runs | Where / extras | Required |
| --- | --- | --- | --- |
| `make test` | Host `unittest` + throwaway Postgres integration + Vitest | Repo root. Python 3.13, `pip install -r requirements.txt` (or `.venv`), Docker, Node 22 | Every change. GitHub Actions runs this. |
| `make test-ui` | Vite build + Playwright against a scripted host | Repo root. Same as above, plus a browser for Playwright. Host is `127.0.0.1:18080`, token `ui-e2e-token` | Desktop UI / flow changes. Not in CI. |
| `make demo` | Same throwaway host pattern, records `media/demo.mp4` | Host is `127.0.0.1:18081`. Optional `ffmpeg` for the MP4 | README video. Not in CI. |

```bash
# once per machine
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cd client/web && npm ci && cd ../..

make test      # host unit + isolated Postgres on loopback :55432 + npm test
make test-ui   # builds client/web, then tests/run_ui.py (never live :8080)
```

Details:

- `PYTHONPATH=src`. Unit tests use `ScriptedRuntime`. They do not call Cursor Cloud and do not need `.env`.
- Integration (`tests/run_integration.py`) starts `postgres:16-alpine` as `artek-buddy-test-pg` on **55432**, database `artek_buddy_test`. It **refuses** the live compose URL. CI uses its own service container and `TEST_DATABASE_URL`.
- `make test-ui` starts another throwaway Postgres on **55433**, a scripted FastAPI on **18080**, and `artek_buddy.py --serve` with a throwaway `HOME`. It never reads `~/.config/artek-buddy/token`. Screenshots land in `client/web/test-results/` (gitignored). `npx playwright test` without `make test-ui` is refused.
- Host tests: `tests/test_*.py`. Client unit: `client/web/src/**/*.test.ts`. Window flows: `client/web/e2e/*.spec.ts`.
- Do not set `TEST_DATABASE_URL` to the owner database.

More: [CONTRIBUTING.md](CONTRIBUTING.md).

## Version

`0.10.21` — one number, see `VERSION`. License: [Apache-2.0](LICENSE). How to contribute: [CONTRIBUTING.md](CONTRIBUTING.md). How to report a vuln: [SECURITY.md](SECURITY.md).

Do not commit secrets, packaged clients (`*.deb`), `data/`, `docs/`, Funnel hostnames, local compose (`docker-compose.local.yml`), or local tooling.

## License

Artek Buddy is licensed under the [Apache License 2.0](LICENSE).

The HTTP contract surface — nouns (`bots`, `threads`, `runs`, `memory`, `routines`, `computers`), procedure names, and run/event status vocabulary — was **adapted from** [elie222/rakazo](https://github.com/elie222/rakazo) (Apache License 2.0). See [NOTICE](NOTICE).

Artek Buddy is not a port of that TypeScript monorepo. The host (Python / FastAPI / Cursor runtime), the Linux `.deb` client, bot colors, and bot avatar are original. The wire uses `snake_case`. Sandboxes run only on this Raspberry Pi.
