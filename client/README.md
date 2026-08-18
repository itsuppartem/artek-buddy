# artek-buddy client

Desktop GUI for the Artek Buddy host. Command: `artek-buddy`.
Source: `artek_buddy.py` plus `web/`. Version: same as the product (`../VERSION`).

The window is the product shell: pairing, bot list, thread, computer pane. It talks to
the host through a loopback proxy so the token never sits in the page.

Build a local owner package (do not commit the file):

```bash
client/build-deb.sh
sudo dpkg -i artek-buddy-client_<version>_all.deb
```

`build-deb.sh` needs Node to compile `web/`. Dist stays out of git.

Config lives in `~/.config/artek-buddy`.

Token search: `~/.config/artek-buddy/token`, then `AGENT_HTTP_TOKEN`.

Host URL: `~/.config/artek-buddy/url`, then `/usr/lib/artek-buddy-client/url`, then `client/url`, then `ARTEK_BUDDY_URL`. Default is `http://127.0.0.1:8080`.

Live now: `bots.list` / `bots.create` / `bots.delete`, `threads.get` / `threads.messages` / `threads.send` / `threads.subscribe`, parallel subagents / worker cards, memory documents, routines, and live computer screen streaming (view-only preview and interactive takeover). Enter sends, Shift+Enter adds a newline in the composer.

`make test-ui` must not use this machine's live token or `:8080`. It starts a throwaway scripted host.

UI pieces for later host stages stay out of the window until those routes exist.
