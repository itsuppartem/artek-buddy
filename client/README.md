# artek-buddy client

Desktop GUI for the Artek Buddy host. Command: `artek-buddy`.
Source: `artek_buddy.py` (entrypoint) plus `pairing.py`, `proxy.py`, `ssh_mux.py`,
`ssh-wrap/`, `web_paths.py`, `notifications.py`, `window.py`, `owner_paths.py`,
`window_chrome.py`, and `web/`. Version: same as the product (`../VERSION`).

The window is the product shell: pairing, bot list, thread, computer pane. It talks to
the host through a loopback proxy so the token never sits in the page.

Window map (screens, controls, thread blocks): [WINDOW.md](WINDOW.md).
Marks (desktop icon, pairing, bot avatars): [assets/README.md](assets/README.md).

## Build and install

GitHub Releases attach `artek-buddy-client_<version>_all.deb` when `VERSION` is bumped on `main` and `test` on that commit is green. Those packages do not bake a host URL. You can still build a local owner `.deb` (do not commit it).

| | Where | Needs |
| --- | --- | --- |
| Build | Pi or any Linux box | Node 22, `npm`, `dpkg-deb` |
| Install | Debian / Ubuntu desktop | `dpkg`, then `apt-get install -f` for GTK / WebKit |

```bash
# from the repo root
client/build-deb.sh
# local build beside an existing release package; creates a distinct Debian version
ARTEK_BUILD_SUFFIX=pr321.6b5ffef client/build-deb.sh
# copy artek-buddy-client_<version>_all.deb to the desktop PC
sudo dpkg -i artek-buddy-client_<version>_all.deb
sudo apt-get install -f
```

`build-deb.sh` compiles `web/` with Vite. `dist/` stays out of git. Release builds
never copy `client/url`. `ARTEK_BAKE_URL=1` copies that untracked file into a local
package only (host URL, never a token).
The script refuses to replace an existing `.deb`. Use `ARTEK_BUILD_SUFFIX`
(letters, digits, `.`, `+`, `~`) for a separate local filename and Debian
version.

Upgrade: install a newer versioned `.deb`. Remove: `sudo apt-get remove artek-buddy-client`.
Config in `~/.config/artek-buddy` is left behind until you delete it.

## Config

Directory: `~/.config/artek-buddy`.

Token search: `~/.config/artek-buddy/token` only. The packaged client never reads `AGENT_HTTP_TOKEN`.

Host URL: `~/.config/artek-buddy/url`, then `/usr/lib/artek-buddy-client/url`, then `client/url`, then `ARTEK_BUDDY_URL`. Default is `http://127.0.0.1:8080`.

Optional SSH reuse for commands run through This PC:

```bash
# Empty means a 60-second idle lifetime. A number from 1 through 3600 overrides it.
touch ~/.config/artek-buddy/ssh-mux
```

The client then wraps only `ssh` found through `PATH` with
`ControlMaster=auto`, a private short `%C` socket, and bounded
`ControlPersist`. It does not edit `~/.ssh/config`, select a key, or copy a key
to the Pi. Remove `ssh-mux` to return to ordinary SSH behavior.

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
