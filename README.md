# Artek Buddy

A self-hosted desktop agent you own. The host runs on a Raspberry Pi that stays on. Turns go through **your Cursor subscription** (`cursor-sdk` → Cursor Cloud). The first client is a Linux `.deb`. Each bot gets a thread, memory, routines, and a Linux desktop on the Pi — not on your laptop, not a vendor VM.

Shipped versions: [CHANGELOG.md](CHANGELOG.md).

## Why this exists

The project started after using Grok as a desktop-style bot. The product was good. The lock-in was not: you could not point that bot at the Cursor models you already pay for.

There is a Cursor subscription. Cursor also exposes Grok (and other) models on a **separate quota**. Those Grok limits sit unused in the IDE while the model itself is good enough for a daily agent. A Raspberry Pi 5 is already on 24/7, so it can be the always-on host.

Artek Buddy is that combination: **your Cursor key, your Grok (or other) quota, your Pi, your client.** The HTTP API is the product. Cursor stays the only live runtime. There is no second model login.

## What you get

- Host on this Pi: FastAPI `:8080`, Postgres, a worker for cron, a supervisor that owns Docker, and a graphical Linux box per computer (Xvfb, browser, view-only VNC).
- Desktop window (`artek-buddy`): pairing, bot list, live thread, computer preview, memory, routines.
- One lead agent per chat. Extra sends queue. The lead can spawn workers on the same desktop.
- Default model: `grok-4.6` (change it in `.env`).

```
.deb  →  Tailscale tailnet (free plan)  →  FastAPI on the Pi  →  Cursor Cloud
         optional Funnel HTTPS                 ↓
                                        Linux desktop container on this Pi
```

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
CURSOR_API_KEY=crsr_paste_the_key_here
AGENT_HTTP_TOKEN=$(openssl rand -hex 24)
# paste the printed token into AGENT_HTTP_TOKEN=
CURSOR_MODEL=grok-4.6
CURSOR_MODEL_EFFORT=xhigh
CURSOR_MODEL_FAST=true
MEMORY_DB_PASSWORD=$(openssl rand -hex 16)
```

`AGENT_HTTP_TOKEN` stays on the Pi. The desktop window never gets it. Devices pair and receive their own token.

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

The **free Personal plan** is enough: one always-on Pi, one or a few owner PCs, MagicDNS if you want a name instead of an IP. Funnel (public HTTPS) is optional and also works on that plan.

1. Install Tailscale on the Pi and on the desktop PC: [tailscale.com/download](https://tailscale.com/download).
2. Sign in with the same account (or any tailnet both machines belong to).
3. On the Pi:

```bash
sudo tailscale up
tailscale ip -4
```

The host URL from another PC is `http://<that-ip>:8080`. If MagicDNS is on, `http://<pi-hostname>:8080` works too.

Keep the tailnet IP and Funnel hostname out of git.

### 5. Pair the Linux client

There is **no ready `.deb` on GitHub**. CI does not attach one. You build a local owner package and copy that file to the desktop PC. Do not upload it to Releases or commit it.

On the Pi, mint a one-time code (15 minutes, one use):

```bash
docker exec artek-buddy python -m artek_buddy pair
```

Build on a machine with Node (this Pi or the desktop), then install on the desktop PC:

```bash
client/build-deb.sh
sudo dpkg -i artek-buddy-client_<version>_all.deb
sudo apt-get install -f
```

The package is the UI and the loopback proxy. Optional untracked `client/url` prefills the host URL on the pair form.

Open **Artek Buddy** from the app menu (or `artek-buddy`).

1. Host URL — `http://<pi-tailscale-ip>:8080` from the owner PC (step 4). Use `http://127.0.0.1:8080` only if the window runs on the Pi itself.
2. Pairing code from the `pair` command.
3. Device name (this computer).
4. **Pair**.

The window stores `~/.config/artek-buddy/{token,url}` (mode `600`). Then: **+** to create a bot, type in the composer, Enter to send.

### 6. Optional public HTTPS (Tailscale Funnel)

Daily use is the tailnet URL from step 4. Funnel is only if you want HTTPS from **outside** the tailnet (still the free plan):

```bash
sudo tailscale funnel --bg 8080
```

That yields `https://<your-machine>.ts.net`. Put that URL in the client (`client/url` or the pair form). **Never commit the hostname.**

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

## Version & testing

`0.8.1` — one number, see `VERSION`.

```bash
make test      # host unit + isolated Postgres + client unit tests
make test-ui   # Playwright against a throwaway host (never the live workspace)
```

Do not commit secrets, packaged clients (`*.deb`), `data/`, `docs/`, Funnel hostnames, or local tooling.

## Attribution

The HTTP contract surface — nouns (`bots`, `threads`, `runs`, `memory`, `routines`, `computers`), procedure names, and run/event status vocabulary — was **adapted from** [elie222/rakazo](https://github.com/elie222/rakazo) (Apache License 2.0). See [NOTICE](NOTICE).

Artek Buddy is not a port of that TypeScript monorepo. The host (Python / FastAPI / Cursor runtime), the Linux `.deb` client, bot colors, and bot avatar are original. The wire uses `snake_case`. Sandboxes run only on this Raspberry Pi.
