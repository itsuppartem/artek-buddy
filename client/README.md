# artek-buddy client

Desktop GUI for the Artek Buddy host. Command: `artek-buddy`.
Source: `artek_buddy.py` plus `web/`. Version: same as the product (`../VERSION`).

The window is the product shell: pairing, bot list, thread, computer pane. It talks to
the host through a loopback proxy so the token never sits in the page.

## Build and install

GitHub Releases attach `artek-buddy-client_<version>_all.deb` when `VERSION` is bumped on `main`. Those packages do not bake a host URL. You can still build a local owner `.deb` (do not commit it).

| | Where | Needs |
| --- | --- | --- |
| Build | Pi or any Linux box | Node 22, `npm`, `dpkg-deb` |
| Install | Debian / Ubuntu desktop | `dpkg`, then `apt-get install -f` for GTK / WebKit |

```bash
# from the repo root
client/build-deb.sh
# copy artek-buddy-client_<version>_all.deb to the desktop PC
sudo dpkg -i artek-buddy-client_<version>_all.deb
sudo apt-get install -f
```

`build-deb.sh` compiles `web/` with Vite. `dist/` stays out of git. Release builds
never copy `client/url`. `ARTEK_BAKE_URL=1` copies that untracked file into a local
package only (host URL, never a token).

Upgrade: install a newer versioned `.deb`. Remove: `sudo apt-get remove artek-buddy-client`.
Config in `~/.config/artek-buddy` is left behind until you delete it.

## Config

Directory: `~/.config/artek-buddy`.

Token search: `~/.config/artek-buddy/token` only. The packaged client never reads `AGENT_HTTP_TOKEN`.

Host URL: `~/.config/artek-buddy/url`, then `/usr/lib/artek-buddy-client/url`, then `client/url`, then `ARTEK_BUDDY_URL`. Default is `http://127.0.0.1:8080`.

## Tests

`make test` (repo root) runs Vitest for `web/`. `make test-ui` builds the page and drives
Playwright against a throwaway scripted host. It must not use this machine's live token
or `:8080`. See [CONTRIBUTING.md](../CONTRIBUTING.md).

## Live now

`bots.list` / `bots.create` / `bots.delete`, `threads.get` / `threads.messages` /
`threads.send` / `threads.subscribe`, parallel subagents / worker cards, memory
documents, routines, and live computer screen streaming (view-only preview and
interactive takeover). Enter sends, Shift+Enter adds a newline in the composer.
Plus, drop, or Ctrl+V attaches files (including a file-manager copy that only
puts a path on the clipboard); a screenshot paste and image/video/audio
show a preview before send and on the file card after send. Download opens the
system Save dialog. Browse that bot's home with Files on the sandbox desktop.

UI pieces for later host stages stay out of the window until those routes exist.
