# Owner manual QA — Linux `.deb` and iPhone 11 Pro web

Issue: [#220](https://github.com/itsuppartem/artek-buddy/issues/220). Daily tracker: [#174](https://github.com/itsuppartem/artek-buddy/issues/174). Pad / keys: [#218](https://github.com/itsuppartem/artek-buddy/issues/218) / [PR #219](https://github.com/itsuppartem/artek-buddy/pull/219).

Checkbox = you saw the expected thing on that surface. Walk **0 → 12** in order, then **13+** for the rest of the visible product. If time is short, do **2, 3, 5, 7, 11, 12, 15, 23, 25, 26, 27, 28, 29** first.

This is the owner eyes-on pass. Scripted CI already covers slices (`ui` = packaged `.deb` `--serve`, `ui_web` = host page at 375×812). Do not treat a green check as a substitute for this list.

## What you are testing

| | |
| --- | --- |
| `main` | Release **0.10.27**. |
| `develop` | Daily since then: window look, Models / keys, memory book, bot-to-bot, plugins, skill from the web, phone page. `VERSION` is still **0.10.27** until a bump lands on `main`. |
| Pad / keyboard / Cyrillic | In `develop` (phone overlay). Drag/tap must keep control until Release; the Type on the desktop field is tappable. After pad or typing, the guest picture must update within a couple of seconds. |
| GitHub Release `.deb` | **Old.** Do not use it for this pass. |
| Linux | Window **built from this tree** (`client/build-deb.sh`, optionally `ARTEK_BAKE_URL=1` for a local URL). Wide shell, about 1280×720, three columns. |
| Phone | Home Screen on the **same host URL**. After a UI change, fully kill the icon and open it again. Viewport is iPhone 11 Pro: **375×812** CSS pixels (notch + home indicator). |
| Host page on a computer | Same `:8080` URL in a desktop browser (mouse). Take control is the `.deb` overlay (pointer into the screen, no pad), even if the window is narrow. |

One demo: Linux first, then the phone. A cell with an em dash means that check does not apply on that surface (still read the note).

## Surfaces

| Code | How to open | Size |
| --- | --- | --- |
| **Deb** | Installed Linux client from this tree | Wide. Must stay three-column, not the phone stack. |
| **Phone** | Safari → Share → Add to Home Screen → that icon | 375×812. Bottom **Chats / Chat / Desktop**. |

Phone Safari and the Home Screen icon do **not** share the login. Pair from the icon.

## 0. Start

Host is live. **Models** already has a working Cursor row (Connected / Key saved). A model is chosen.

Two clients: `.deb` on the PC and Home Screen on the phone, both on this host.

Mint three bots for the run. Names can differ; they must be distinct:

| Bot | Mode |
| --- | --- |
| **Demo** | Private |
| **Research** | Private |
| **Lead** | Team |

| Check | Deb | Phone |
| --- | --- | --- |
| Host health ok; Models shows a connected Cursor key and a default model | [ ] | [ ] |
| Client is paired to this host (not a leftover token from another build) | [ ] | [ ] |
| Demo, Research, Lead exist with the modes above | [ ] | [ ] |

---

## 1. Window look (not in 0.10.27)

| Check | Deb | Phone |
| --- | --- | --- |
| **New bot**, **Computer**, **Settings**, **Send**, **Stop** are words, not mystery icons | [ ] | [ ] |
| **Send** is grey while Message is empty (no text and no files) | [ ] | [ ] |
| **You** opens **Models**, not the bot profile | [ ] | [ ] |
| **Plugins** opens even with an empty inbox | [ ] | [ ] |
| Create a bot → focus lands in the new chat | [ ] | [ ] |
| **Settings** from the gear does **not** boot the desktop. Escape closes Settings and New bot (composer text stays; overlay Esc still drops fullscreen first) | [ ] | [ ] |
| Settings, Memory, Routines, ask/file cards, and the overlay share the same warm tokens as pairing and the thread (ink / paper / mute / tan / sage). Not a cool gray hatch | [ ] | [ ] |

Phone: Create / Models / Plugins open the **Desktop** tab (also in §11).

---

## 2. Models

| Check | Deb | Phone |
| --- | --- | --- |
| Open Models. Model names are readable (not white on white) | [ ] | [ ] |
| Save on an empty key → error under that row, not silence | [ ] | [ ] |
| Change Reasoning (e.g. Low) — no second Save — open chat shows `Using … · Low · Fast` (if Fast is on) | [ ] | [ ] |
| While a reply is streaming, change Reasoning again → the turn does **not** break; the line ends `This turn keeps going.` | [ ] | [ ] |
| Click a model chip — that id is **Using** (tan). **Use this model** is the same commit. Empty providers say to paste a key; no dead Use this model | [ ] | [ ] |
| The next Send uses the new settings | [ ] | [ ] |

Also (visible, easy):

| Check | Deb | Phone |
| --- | --- | --- |
| After a good Save the key field is gone (`••••` + last four + Connected). The full key never appears | [ ] | [ ] |
| Forget empties that row | [ ] | [ ] |
| Send with no default model does not start a turn; the thread says to open Models | [ ] | [ ] |

---

## 3. Memory book

In **Demo**:

1. «Я живу в Белграде.» → wait for the turn to finish. On a scripted host: `please e2e-identity-city Belgrade`.
2. «Я живу в Нови-Саде.» → another turn. Scripted: `please e2e-identity-city NoviSad`.
3. New chat / new question about the city: the answer is **Нови-Сад**, not Belgrade.
4. «Привет» alone must not rewrite the book (`hello` on a scripted host).

Computer → Memory: the **identity** chapter updated while that pane is open (no need to close and reopen); the old city is not sitting next to it. Owner place/person rows are labeled identity, not place.

| Check | Deb | Phone |
| --- | --- | --- |
| After (1)+(2)+(3) the next city answer is Novi Sad | [ ] | [ ] |
| «Привет» / `hello` does not rewrite identity | [ ] | [ ] |
| Memory pane identity chapter has the new city only | [ ] | [ ] |
| One detailed standing rule followed by a shorter restatement (`please e2e-remember-twice` on a scripted host) → **one** Remembered line and one Memory card. Reading This PC afterward does not repeat it | [ ] | [ ] |
| Same standing rule three times (`please e2e-remember-same-thrice`) → still **one** Remembered line. A worker `remember` (`please e2e-background-worker-remember`) saves the card and does **not** print Remembered in the thread | [ ] | [ ] |
| **+ New memory** defaults to **This bot** (filled segment). Save flashes Saved and keeps the card in view. Delete is **Remove**, not Outdated | [ ] | [ ] |
| A long `Remembered:` clock line is one short row. Click it (`please e2e-remember`) opens Memory on that card with the full text. `Using …` is not a button | [ ] | [ ] |

---

## 4. Skill from the web

Same Demo chat. Ordinary language: «найди скилл для invoice и сохрани». On a scripted host send `please e2e-install-book`, then `please e2e-run-book` for the matching-task turn.

| Check | Deb | Phone |
| --- | --- | --- |
| Allow / Deny card for that origin. Deny stores nothing | [ ] | [ ] |
| After Allow: the normal bot reply appears, with no skill card and no skill chip above Message | [ ] | [ ] |
| A matching task makes the agent use the kept skill itself; the owner does not type or tap a `please run` trigger | [ ] | [ ] |
| Fetched steps and frontmatter never appear in the thread or inbox preview. A fail is one human **run-error** line (`The turn failed.` or the real reason), not YAML or `run failed: run-` plus a uuid | [ ] | [ ] |
| Another bot does not see the book | [ ] | [ ] |

---

## 5. One bot asks another

In **Lead**: «Спроси Research: в двух предложениях, что такое Нови-Сад.»

| Check | Deb | Phone |
| --- | --- | --- |
| Lead shows «Asked Research: …» and a card to that chat | [ ] | [ ] |
| Research shows who asked and the question; work happens there | [ ] | [ ] |
| Back in Lead: short «Research is ready» and an answer **only from Research’s last message** (no its tools or desktop) | [ ] | [ ] |
| Click the card opens Research | [ ] | [ ] |
| **Stop** kills either of the two chats | [ ] | [ ] |

---

## 6. Plugins

| Check | Deb | Phone |
| --- | --- | --- |
| Plugins → key → Save → **Key saved** + last four. Key field gone. Full key never on the page | [ ] | [ ] |
| Wheel the thread with Plugins closed: hatch stays shut. Open Plugins, one Close, pane is gone | [ ] | [ ] |
| Search apps filters as you type (no Enter needed). Enter does **not** close the pane. Catalog scroll stays put | [ ] | [ ] |
| Search → Connect a simple app (no browser) → Connected. No new user bubble. Composer stays empty. No chip above Message | [ ] | [ ] |
| If Connect cannot start, a human line under the pane says what to do next (not a dead Connect and not only `could not start that connection`) | [ ] | [ ] |
| Or chat `please e2e-connect-docs` (scripted host) / «подключи Docs» — **plugin-card**, not git setup. Still no chip | [ ] | [ ] |
| `please e2e-connect-mail` (or GitHub from chat): **Open to connect** on the card opens the owner browser / a tab. Not the bot desktop. Right-click can Copy URL | [ ] | [ ] |
| Ask the connected app (`please e2e-plugin-docs` / `please use Docs` on a scripted host, or a real task after GitHub Connect) — the bot calls the tools; thread **plugin-card** (name + result) | [ ] | [ ] |
| Disconnect / Remove → next turn has no that tool. Remove after **Open to connect** shows Paste a key (not Key saved with an empty catalog) | [ ] | [ ] |
| If Connect opens a browser tab, Finish after login marks Connected | [ ] | [ ] |

---

## 7. Desktop (the most visible `develop` change)

Computer pane on **Demo** (Private) or Team.

| Check | Deb | Phone |
| --- | --- | --- |
| **Offline • Click to start** → Booting → Running **view-only** (Preview · view only / fake: Running tile). Not the fullscreen control overlay. **Take control** is a separate grant. Settings still does not boot | [ ] | [ ] |
| Preview is a live screen, caption **Preview · view only**. Not black text «Desktop is running». Click on the preview does **not** take control | [ ] | [ ] |
| fluxbox panel: window title, close, menu. Not a bare X | [ ] | [ ] |
| **Take control** → mouse / keys go to the guest. Caps Lock raises case (`abc` → `ABC`). **Release** → the same turn continues; typing dots and Stop work again | [ ] | [ ] |
| Take control from Sleeping (or Open screen before pixels): overlay says **Waking the desktop…** until the guest is on the glass, not a black void | [ ] | [ ] |
| No pointer for **2 minutes** on the overlay → host Releases itself (holder is bot again) | [ ] | [ ] |
| In chat, **without** pressing start: «Открой https://example.com» (or `HTTPS://…`). Card Allow once / Always / Deny | [ ] | [ ] |
| After Allow: tile itself **Running**; guest has **only the browser**; the file manager does not fill home | [ ] | [ ] |
| Open screen / fullscreen has a picture. Gear does not boot | [ ] | [ ] |

Optional evening:

| Check | Deb | Phone |
| --- | --- | --- |
| Quiet box **15 minutes** with no input → **Sleeping** (sage). Open pane and pulse do not keep it warm. Click Sleeping wakes view-only; Take control is separate | [ ] | [ ] |

Team:

| Check | Deb | Phone |
| --- | --- | --- |
| Second bot on the same desk sees `{name} is using the computer`; Take / Restart / Stop / Reset are grey | [ ] | [ ] |

Take control on the **host page** follows the pointer in use, not only width: a desktop browser is the `.deb` overlay (no pad); a phone keeps the pad / Keyboard (§12). **You still owe §7a on both surfaces.**


## 7a. Hands on the guest (do not skip)

A preview is not enough. You must **drive** the box and **read** what opened.

On **Deb** (and the host URL in a desktop browser): Take control, real mouse and keyboard. No pad.

On **Phone**: Desktop overlay, finger is a trackpad (drag moves the beige dot; tap clicks at the dot). Then Keyboard.

| Check | Deb | Phone |
| --- | :---: | :---: |
| After Allow on «открой https://example.com», the **guest** shows Example Domain (heading / title), not a black tile and not only a chat card | [ ] | [ ] |
| You can **read** the address bar or tab title. It is example.com (or the site you allowed), not a leftover Google / Files window | [ ] | [ ] |
| Take control: pointer moves in the guest. A click lands where you aimed (address bar, a link, a button) | [ ] | [ ] |
| Host URL in a desktop browser: Take control has no pad and no Keyboard button; the pointer goes into the screen like Deb | [ ] | — |
| Phone: drag on the pad moves the beige dot across the 1280×800 picture; it does not jump under the finger. After a drag or tap the overlay still shows **Release**, not Take control | — | [ ] |
| Type `hello` into a guest field (address bar or input). The letters appear **in the guest**, not only in our Message box | [ ] | [ ] |
| After pad or keyboard input, the guest picture updates within a couple of seconds. A freeze over ~5s is a fail | [ ] | [ ] |
| Phone Keyboard: Esc / Tab / Enter / Bksp work in the guest. Russian layout types Cyrillic into that same field | — | [ ] |
| Scroll (wheel on Deb, two-finger on Phone) moves the guest page | [ ] | [ ] |
| Right-click (Deb) or two-finger tap (Phone) opens a guest context menu | [ ] | [ ] |
| fluxbox **Files** / Browser / Terminal open a real window you can see | [ ] | [ ] |
| Release: overlay is view-only again (same guest page, **not a black tile** — last frame stays until the view-only picture loads). Pane says **Take control**, not You have control. Message and Stop work | [ ] | [ ] |
| A click or key still in flight after Release does not bring back You have control | [ ] | [ ] |

If Chrome emulation cannot drag the pad, say **fail / blocked**, not skip. This section is why the phone desk exists.

---

## 8. «Needs you» from another chat

Need a turn where the bot asks for the desk (`waiting_takeover` + **Open computer**).

| Check | Deb | Phone |
| --- | --- | --- |
| Stay on **this** chat — no «needs you» pill (you are already here) | [ ] | [ ] |
| Switch to another chat → under the header **`{name} needs you`**, not «replied» | [ ] | [ ] |
| Park while **this** chat is still open, then switch — the other chat still gets **`{name} needs you`** (`please e2e-takeover`) | [ ] | [ ] |
| Dismiss or enter that chat — the pill does not come back on later switches. Dismiss does not change the open chat | [ ] | [ ] |
| A leftover park from the previous window launch stays silent | [ ] | [ ] |

---

## 9. Queue while the host is silent

On **Deb**: stop the `artek-buddy` container for about 30 seconds (or pull the network to the host). Then do the same visible checks on Phone if you can reach a down host from it.

| Check | Deb | Phone |
| --- | --- | --- |
| Reconnect banner, not only a red card | [ ] | [ ] |
| Type and Send → pending mark on the bubble (not a delivered line). After the host returns it keeps **Sent while offline ·** plus the **local** time (with zone), not a bare UTC clock | [ ] | [ ] |
| The next ordinary Send has no that caption | [ ] | [ ] |
| A pairing error (need to pair again) does **not** enter the queue | [ ] | [ ] |

---

## 10. Attachments and workers (Linux first)

| Check | Deb | Phone |
| --- | --- | --- |
| Paste a screenshot into Message → chip `screenshot-1.png` (or the file name). Ordinary text is not an attachment | [ ] | [ ] |
| Scripted `please e2e-background-worker-chat`: one **Working in the background.**, Message stays usable, **Stop** stays up, **no** worker card and **no** `Started …` / `Finished …` / `Stopped …` lines. `please e2e-worker-status` answers **Still working.** Then exactly one **The background job is done.** | [ ] | [ ] |
| Scripted `please e2e-worker-progress`: a short **Still working:** line appears without a ping; Message stays usable; **no** worker card. A later different step can add one more line after ~45s. Exactly one **The background job is done.** and no extra still-working after that | [ ] | [ ] |
| Scripted `please e2e-worker-activity-no-text`: status (`please e2e-worker-status` or `please e2e-worker-false-idle`) keeps the **same** worker. Empty progress is not treated as idle; **Stop** is only the window control, not a status ping. | [ ] | [ ] |
| Scripted `please e2e-lead-owner-ssh`: the lead turn finishes without grinding This-PC SSH. A following Send is a new run. Window **Stop** then Send is also a new turn, not a silent queue on a cancelled run | [ ] | [ ] |
| Composer **Stop** while only the worker is running writes **Stopped.** and cancels that work | [ ] | [ ] |
| This-PC Allow (read / write this Linux home) works on Deb. Refresh or open a second window while it runs: the same write/exec happens **once** and the losing window does not fail the winner's result | [ ] | — |
| Scripted `please e2e-worker-auto-read`: lead finishes; refresh still lists the queued This-PC read; ACK once; worker continues with the file. A second window that loses the claim stands down | [ ] | — |
| Back-to-back This-PC read + list are both ACKed promptly and return their own results; neither waits for the SSE heartbeat or receives the other job | [ ] | — |
| Phone `/local/owner-*` is **403**. It does not fail an auto job while the paired Deb can claim it | — | [ ] |

---

## 11. Phone (already in `develop`, #25)

Home Screen, phone width (375×812). Also confirm the wide Deb window does **not** become this stack.

| Check | Deb | Phone |
| --- | --- | --- |
| Pair title **Pair this phone**, device name Phone, **no** host URL field. Code `XXXX-XXXX` → Pair | — | [ ] |
| Deb pair is **Pair this computer**, has a Host URL field, device name is this PC | [ ] | — |
| Bottom **Chats / Chat / Desktop**, targets about 44px. Top notch / safe area present; **no** second empty belt under the nav | — | [ ] |
| Inbox: chats sit between Search and Plugins / Models, not a black hole | — | [ ] |
| Create / Models / Plugins open the Desktop tab | — | [ ] |
| Close on Computer / Models / Plugins, the Desktop pane, and overlay ✕ → **Chat** tab with the thread (blank Desktop is a fail) | — | [ ] |
| Share → Add to Home Screen: hint at the **top**, not over Models / nav. Got it hides it | — | [ ] |
| Turn on alerts — only from the home-screen icon, and only while the app is open. No background | — | [ ] |
| Wide window (Deb 1280×720) stays three-column, not «phone» | [ ] | — |

---

## 12. Pad and Cyrillic

Fully kill the Home Screen icon and open it again. Desktop → desk overlay.

Deb uses a real mouse and keyboard; skip pad gestures there.

| Check | Deb | Phone |
| --- | --- | --- |
| Finger is a trackpad: drag moves the cursor, it does not jump under the finger. Tap = left click **at the dot**. Two fingers = right click or scroll | — | [ ] |
| Beige dot sits on the 1280×800 picture, not on the black letterbox | — | [ ] |
| After a pad drag or tap, overlay still shows **Release** / You have control, not Preview · view only / Take control | — | [ ] |
| Drag does not select host copy (the “Turn the phone sideways…” line stays unhighlighted) | — | [ ] |
| Keyboard → **Type on the desktop** field accepts a tap, then the system keyboard + row Esc / Tab / Enter / Bksp / Del / arrows | — | [ ] |
| iOS Done check **dismisses** the keyboard. Tap on the desk does not | — | [ ] |
| Russian layout types into the guest field (address bar / input). Latin still works | — | [ ] |
| After pad drag or typing, the guest picture updates within a couple of seconds (a freeze over ~5s is a fail) | — | [ ] |
| Overlay ✕ works on the first tap → Chat | — | [ ] |

---

## 13. Pairing and session (both surfaces)

| Check | Deb | Phone |
| --- | --- | --- |
| Fresh pair with a 15-minute one-use code works. A second use of the same code fails under the form | [ ] | [ ] |
| Pairing body: create a code on the Pi, type it here, Pair. Phone has **no** token / mint / `python -m`. Deb shows `docker exec artek-buddy python -m artek_buddy pair` | [ ] | [ ] |
| After pair, the credential is not visible in the page (Deb: `~/.config/artek-buddy/token` mode 600; Phone: httpOnly cookie) | [ ] | [ ] |
| Auth error: **Pair this computer again** (Deb) / **Pair this phone again** (Phone). Click unpairs to the matching pair screen. Does not queue as an offline send | [ ] | [ ] |
| Unpair returns to the pair screen. Re-pair with a new code restores the inbox | [ ] | [ ] |
| Pairing does **not** open the computer pane or Models and does **not** boot a desktop | [ ] | [ ] |

---

## 14. Inbox and bots

| Check | Deb | Phone |
| --- | --- | --- |
| Search filters inbox (and Archived) by name / preview. A name or preview hit is marked. No matches: empty copy plus Clear Search; clear restores the list | [ ] | [ ] |
| Click a row opens **that** chat on the first click (not the previous one). After Research, one click Lead → header and composer are Lead. Same after a third bot | [ ] | [ ] |
| Switching chats does not blank the thread or jump inbox order under the pointer | [ ] | [ ] |
| Opening a chat in the focused window marks it read. Looking at or dismissing an OS notification does **not**. A reply while that chat is focused on screen does not leave the unread pin | [ ] | [ ] |
| Unread pin is a tan circle named Unread (not a hidden 7px square). The name is bold | [ ] | [ ] |
| Right-click (Deb) / long-press if offered (Phone): Pin / Unpin, Mark as unread (sticks until you leave and open again), Edit profile, Duplicate, Archive, Delete | [ ] | [ ] |
| Empty inbox: Restore from Archived, or create a first bot | [ ] | [ ] |
| Create: Name (inbox), Title (role), Description (what it is for), Instructions (standing orders, no Prompt), Team / Private. Focusing Name does not mint a bot; only Create does. Escape closes New bot the same as × | [ ] | [ ] |
| Duplicate makes a second bot. Delete removes that bot; optional purge memories | [ ] | [ ] |
| Two inbox chats keep separate model sessions: a send in one does not continue the other chat's history, and both can run at the same time | [ ] | [ ] |
| Inbox order is pinned first, then created. A later message does not jump a row | [ ] | [ ] |

---

## 15. Thread chrome

| Check | Deb | Phone |
| --- | --- | --- |
| Enter sends. Shift+Enter inserts a newline (Deb) and that break stays in the sent bubble. Phone return key follows the on-screen keyboard. Ctrl+A selects the draft and does not Send; Enter then sends one copy | [ ] | [ ] |
| Message placeholder stays readable: full name, or `Message …` with an ellipsis — not a clipped mid-word (`Message Resea`) | [ ] | [ ] |
| Deb WebKit: Ctrl+Z undoes typing in Message (Ctrl+Shift+Z / Ctrl+Y redo), not only Chromium `--serve` | [ ] | — |
| Load earlier is a bordered button. After the oldest page, **Beginning of this chat.** stays | [ ] | [ ] |
| Right-click Reply (Deb) puts a quote in the next user bubble. **Copy** copies that message; on a link, **Copy URL** is still there | [ ] | — |
| `please e2e-markdown-preview`: **Open docs** opens the system browser / a browser tab. Right-click the link on Deb shows **Copy**, **Open in browser**, **Copy URL**, and Reply; Copy URL changes to **URL copied** | [ ] | [ ] |
| `please e2e-blocked-browser`: Ask card visibly waits. An option or free-text answer stays on the card and continues the **same run**, without a second user bubble. A second answer is rejected without breaking the thread | [ ] | [ ] |
| Consent card: Allow once / Always / Deny. Deny does not run the action. Always covers later same-kind asks **on this window**. The other paired device still sees a card | [ ] | [ ] |
| Attention pill sits **under** the header, not over Send or Load earlier. Title opens that chat; Dismiss hides it and does **not** switch the open chat | [ ] | [ ] |
| A finished background chat still raises replied / failed. Finishing does not steal the open chat | [ ] | [ ] |
| Thread stays on the latest cards when pinned to the bottom. A switch lands on the latest messages | [ ] | [ ] |
| Failed / cancelled run shows a run-error, not a silent hole. After 60+ minutes idle, the first live Cursor Send may restart its local bridge but still completes on that Send with no red line. Scripted `please e2e-dead-wait` proves the bounded hidden retry (bot `ok`, no Send-again); `please e2e-dead-wait-stuck` still shows one terminal error | [ ] | [ ] |
| A follow-up while `waiting_takeover` starts a turn (does not only enqueue) | [ ] | [ ] |
| Stop keeps the run cancelled: a late complete does not append the essay (scripted `please e2e-late-complete` or a live Cursor turn). **Stopped.** is one `run-error` line. Queued owner lines survive Stop and prepend to the **next** send. Stop must not leave a running zombie; `please e2e-lead-owner-ssh` then another Send is a new run | [ ] | [ ] |

---

## 16. Composer attachments (beyond §10)

| Check | Deb | Phone |
| --- | --- | --- |
| Plus / paperclip attaches a file. Chip + preview for image / video / audio before Send | [ ] | [ ] |
| Drop a file onto Message attaches it (Deb) | [ ] | — |
| Copy a **file** on Linux (file manager path / `file://`) and paste → the file, not the path as text | [ ] | — |
| After Send the chip is gone and does not come back from a late clipboard read | [ ] | [ ] |
| Images land in that bot’s `inbox/` on the Pi. Deleting the **chat** removes that chat’s inbox copies; a shared Team home and other bots stay | [ ] | [ ] |

---

## 17. File cards and download

| Check | Deb | Phone |
| --- | --- | --- |
| Bot posts a file card. Pictures / video / audio show a preview, not only a Download row | [ ] | [ ] |
| Download is a named bordered button on bot **and** owner file cards | [ ] | [ ] |
| Deb Download opens the system Save dialog (Downloads / Загрузки by default). Cancel writes nothing | [ ] | — |
| Phone Download uses the browser / share sheet; it does not write the Linux home | — | [ ] |

---

## 18. This-PC (Deb only)

Read a file or list a folder under the Linux home: no Allow card. Read-only shell (`ls`, `cat`, `echo`, `git status`, `find … -name` / `-print`) does not ask.

Write a file or a command that can change the PC: Allow once / Always / Deny. That includes `git show --output=…`, `git diff --output=…`, `git branch new-name`, `git branch -m …`, and `find … -fprint` / `-fprintf` / `-fls`. Always covers later writes and commands on this PC **from this Deb**, not each folder. Paths outside `$HOME` stay 403 on the card. A git/find write path outside `$HOME` does not run.

For SSH reuse, use a real alias already present on the owner PC. Do not add one
for this test and do not change `~/.ssh/config`. First test without
`~/.config/artek-buddy/ssh-mux`; then `touch` that opt-in file and restart the
rebuilt client. This stays in the long walk because it needs a real owner alias.

| Check | Deb | Phone |
| --- | --- | --- |
| Read / list under home: no card | [ ] | — |
| `git status` / `find . -name '*.py' -print`: no card | [ ] | — |
| Write / mutating command: card, then the action only after Allow | [ ] | — |
| `git show --output=…`, `git branch new-name`, or `find … -fprint …`: card. Deny does not create the file or branch | [ ] | — |
| Write path outside `$HOME` (`git show --output=/tmp/…`) does not run | [ ] | — |
| Deny does not touch the PC | [ ] | — |
| Ask for several small remote checks. The agent sends one `ssh alias 'check; check; check'` owner command / one card, not one SSH call per check | [ ] | — |
| Without `ssh-mux`, SSH behaves as before. With the opt-in file, two sequential calls to the same alias reuse a private socket under `$XDG_RUNTIME_DIR/artek-buddy/ssh` (or the documented cache fallback) | [ ] | — |
| Quit the client or wait for ControlPersist: the master exits. `~/.ssh/config` is unchanged and no owner private key appears on the Pi | [ ] | — |
| Phone never runs owner tools | — | [ ] |

---

## 19. Memory pane (beyond the book in §3)

Computer → Memory.

| Check | Deb | Phone |
| --- | --- | --- |
| Owner / work / charter list is visible. New (this bot \| shared), Edit, **Remove** = delete, Export `.md` | [ ] | [ ] |
| A weeks-grown book is not cut to a 200-character Settings stub | [ ] | [ ] |

---

## 20. Routines

Computer → Routines.

| Check | Deb | Phone |
| --- | --- | --- |
| New: name, cron, prompt. Invalid cron disables Save | [ ] | [ ] |
| On / off, Run (test), Delete | [ ] | [ ] |
| Next run is a short time (`next 2026-08-31 09:30:00 UTC`), not `09:30:00.000000` | [ ] | [ ] |
| A due routine fires through the same send path while the laptop can be closed (watch the thread later) | [ ] | [ ] |

---

## 21. Settings, Team / Private, Reset

| Check | Deb | Phone |
| --- | --- | --- |
| Settings: Name, Title (role), Description (what it is for), Instructions (standing orders, no Prompt), Team \| Private, notifyOnFinish, Restart… / Stop… / Reset… (each confirms), Delete. Escape closes Settings the same as Close | [ ] | [ ] |
| Title keeps what you typed through blur / Tab and Save (the field must not empty). Save flashes Saved. Reopen Edit profile shows the same title | [ ] | [ ] |
| Settings opened from the computer pane returns to that pane. Create / Models Close do the same if the pane was open | [ ] | [ ] |
| Changing Team ↔ Private rebinds the desktop; the old home is **not** copied | [ ] | [ ] |
| Settings Stop… confirms, then leaves the box **Sleeping**, not a dead Offline preview | [ ] | [ ] |
| Reset wipes that home. Team Reset wipes the shared desktop for every Team bot. Team Reset stays disabled while another bot holds the box | [ ] | [ ] |
| Restart or Stop on a running computer does not leave a stuck Connecting spinner | [ ] | [ ] |

---

## 22. Files on the sandbox desktop

The computer pane is screen, memory, and routines — not a second file list.

| Check | Deb | Phone |
| --- | --- | --- |
| Take control → fluxbox / right-click **Files** opens that bot’s home. Closing it stays closed; it does not pop over the browser on its own. Opening a site still must not also open Files | [ ] | [ ] |
| `launch_app` / menu Browser and Terminal still work next to Files | [ ] | [ ] |

---

## 23. Notifications

| Check | Deb | Phone |
| --- | --- | --- |
| Show Applications lists **Artek Buddy** with the packaged mark. After launch, the dock shows that mark and name, not `artek_buddy.py` or a generic gear | [ ] | — |
| The installed client shows an **Artek Buddy** tray icon. Its menu **Open Artek Buddy** presents the window; **Quit** exits | [ ] | — |
| Close the window with ×: it hides to the tray and keeps running. Start it again only if the desktop has no indicator support and close therefore exits | [ ] | — |
| Click the Artek Buddy launcher three times: GTK3 presents one existing window / tray process. It does not create three hidden clients or three subscriptions | [ ] | — |
| Run `please e2e-slow` in Demo and switch to Research: completion raises exactly one native **Demo replied** notification and does not steal the open chat | [ ] | — |
| Run `research a city` in Demo and switch to Research: one pending question raises exactly one **Demo is asking** row, not one row for the ask card plus another for `waiting_input` | [ ] | — |
| Start `please e2e-slow`, leave Demo open, then switch to another app (window still mapped): completion still raises the native notification. The same completion while Demo is focused stays quiet. Native attention follows the GTK window, not whether WebKit still thinks the page has focus | [ ] | — |
| Start `please e2e-slow`, leave Demo open, then **minimize** (titlebar dash / iconify) or hide it to the tray: completion raises exactly one native **Demo replied** row and no in-window banner. Restoring the window does not post a second row. `GET /local/status` `window_active` is false while it is iconified or withdrawn (`please e2e-slow`) | [ ] | — |
| Leave Demo on screen and open the Ubuntu notification list: an already shown Demo row is not posted again and Demo does not become read. A new Demo reply while the window is unfocused still posts one native row. Close the list so Demo is focused: the unread pin clears and Demo's native row is withdrawn | [ ] | — |
| Dismiss a GNOME row without opening Demo: the chat stays unread. Opening Demo reads it; merely viewing the calendar flyout does not | [ ] | — |
| Ubuntu Notifications lists **Artek Buddy** with title and final body. Two results from Demo update one row; a result from Research keeps a separate row | [ ] | — |
| Intermediate text/progress, a silent completion after old text, `Remembered:` / `Forgot:`, This-PC auto work, worker cards, and relaunch/replay do not raise **is asking** / **replied** | [ ] | [ ] |
| Phone: Turn on alerts from the Home Screen icon. Alerts only while that app is open or still in memory. Kill the icon → no wake | — | [ ] |
| `notifyOnFinish` off mutes only replied / failed, not «needs you» | [ ] | [ ] |

---

## 24. Wide vs narrow

| Check | Deb | Phone |
| --- | --- | --- |
| Deb ~1280×720: rack + thread + hatch. Not the phone nav | [ ] | — |
| Phone 375×812: one column + bottom nav. Safe-area top and bottom. No double spacer under the nav | — | [ ] |
| If you stretch a phone browser past ~720px it becomes the three-column shell (Safari, not the icon) | — | [ ] |

---

## 25. Generate a file and send it

Owner language, in Demo (model already chosen):

«Сгенерируй текстовый файл notes.txt с тремя строками и пришли его мне.»

Or, on the scripted host: `please e2e-send-file`.

| Check | Deb | Phone |
| --- | :---: | :---: |
| Thread shows a **file-card** with the name (e.g. `notes.txt`), not a raw dump of the bytes | [ ] | [ ] |
| Download works. Deb: system Save dialog, default Downloads / Загрузки; Cancel writes nothing. Phone: browser / share sheet, **not** the Linux home | [ ] | [ ] |
| Card stays after Download. A second Download does not duplicate the Pi copy | [ ] | [ ] |
| Deleting **this chat** removes that chat’s inbox copy; other bots and a Team home stay | [ ] | [ ] |

---

## 26. Generate a picture (and media)

«Нарисуй / сгенерируй картинку: лиса за компьютером.» Wait for the turn.

Scripted: `please e2e-send-image`. Also try a video or audio file if you have one.

| Check | Deb | Phone |
| --- | :---: | :---: |
| While it works: a **Generating** state, not a hung empty bubble | [ ] | [ ] |
| Success: **file-card** with a visible **file-preview** (the picture), not only a Download row | [ ] | [ ] |
| One picture → one card. No second ghost card | [ ] | [ ] |
| Failure (bad prompt / host error): an error in the thread, not a spinner that never ends | [ ] | [ ] |
| **Stop** during generate → Stopped, and a late complete does **not** still drop a card | [ ] | [ ] |
| Same for a short video / audio if you send one: preview in the card | [ ] | [ ] |

---

## 27. Attach: Ctrl+V, Plus, drop

Do this on **both** surfaces. Phone has no Linux file-manager paste.

| Check | Deb | Phone |
| --- | :---: | :---: |
| Ctrl+V (Deb) or paste (Phone, if the OS allows) a **screenshot** → chip `screenshot-1.png` (or the file name) + preview. Composer text stays empty. Still works when the clip also has a `file://` path | [ ] | [ ] |
| Paste ordinary text → **no** chip, the text lands in Message | [ ] | [ ] |
| Plus / Attach picks a file → chip. Image / video / audio show a preview before Send | [ ] | [ ] |
| Drop a file onto Message attaches it (Deb) | [ ] | — |
| Copy a **file** in the Linux file manager and paste → the file, not the `file://` path as text (Deb) | [ ] | — |
| Send → chip gone. A later send does **not** bring the chip back | [ ] | [ ] |

`ui` scripts paste / drop / Plus, file-card, and image preview on the packaged window. `ui_web` at 375×812 covers paste screenshot, scripted file-card + image preview, and phone Computer / hatch Close.

---

## 28. Save feedback (no silent Save)

After you press Save, the button reads **Saved** for about a second, then the form closes. A host error keeps Save and shows the line under that row. Plugins already says Key saved. Models key Save becomes Connected. Reasoning / Fast Save is the Using line in the thread.

| Check | Deb | Phone |
| --- | :---: | :---: |
| Settings: change name or instructions → Save. You see **Saved** (or a check) for a moment, not only Saving… then a mute form | [ ] | [ ] |
| Memory New / Edit → Save. Same Saved mark. The row is in the list | [ ] | [ ] |
| Routine New → Save. Same Saved mark. Invalid cron still disables Save (no fake success) | [ ] | [ ] |
| Models Reasoning / Fast → Save still writes the Using line; that line counts as feedback for that row | [ ] | [ ] |
| A failed Save keeps the button as Save and shows the error under the row | [ ] | [ ] |

Product issue: #229.

---

## 29. Phone Computer must not blank the chat

This is the hole we hit on the 375×812 pass (#226). Deb is three-column; it does not use this tab.

From **inside a chat** on Phone:

| Check | Deb | Phone |
| --- | :---: | :---: |
| Computer (thread header) or Desktop tab opens the computer pane. The chat is still there if you go back | — | [ ] |
| Close on the computer pane → **Chat** tab, thread visible, not a black / empty Desktop | — | [ ] |
| Overlay ✕ on Models / Plugins / Create → **Chat** tab with the thread, not a blank Desktop | — | [ ] |
| Open Computer, Close, open again — pane comes back, no stuck empty shell | — | [ ] |

`nextPhoneTab("close-desk")` is already `chat`. Scripted: `test_phone_computer_open_close_returns_to_chat` and `test_phone_models_plugins_close_returns_to_chat`.

---

## 30. Ask cards, Reply, Load earlier

| Check | Deb | Phone |
| --- | :---: | :---: |
| `please e2e-blocked-browser`: Ask card waits. Option or free-text answer continues the same run; no second user bubble. Stop, timeout, and a second answer do not leave a live stale card | [ ] | [ ] |
| Right-click Reply (Deb) quotes in the next user bubble. Cancel drops the quote | [ ] | — |
| Load earlier is a bordered button and pulls older messages. After the last page, **Beginning of this chat.** stays. If you were pinned to the bottom, new cards stay in view | [ ] | [ ] |

---

## Do not test by hand

Already in `develop`, not visible on screen:

- `/local/*` jail and nonce
- Migration advisory lock / sha256 replay
- Supervisor file writes without a heredoc
- Release scans, SBOM, attestations, rulesets Protect develop / Protect main

Out of this pass: collaboration (#154–#169) and research tickets (#98, #100).

---

## Short path

If time is short, in this order:

1. **§2 Models**
2. **§3 Memory book** (New memory defaults to This bot; Remove, not Outdated). Click a long Remembered line → that Memory card. Same rule thrice / worker remember → one Remembered line or none from the worker
3. **§4 Skill from the web**
4. **§5 Bot asks bot**
5. **§6 Plugins** (pane Connect or chat attach; no chip; the bot uses the app). `please e2e-connect-mail` / GitHub **Open to connect** opens the owner browser
6. **§7 Desktop** + **§7a Hands on the guest** (Release keeps the picture; Sleeping → Take control shows Waking the desktop…)
7. **§11 Phone chrome** + **§29 Computer must not blank**
8. **§12 Pad and Cyrillic**
9. **§25 File + §26 Picture + §27 Ctrl+V**
10. **§28 Save feedback**
11. **§10 workers** `please e2e-background-worker-chat` then status; Message stays usable; one final result. `please e2e-worker-progress`: a **Still working:** line without a ping and no worker card. `please e2e-worker-activity-no-text` then status keeps the same worker. `please e2e-lead-owner-ssh` finishes; the next Send is a new run. `please e2e-worker-auto-read`: refresh still lists the queued This-PC read; ACK once. **This-PC** back-to-back read/list and one Allow action exactly once on Deb (including a git/find write form: card, Deny leaves the file/branch uncreated)
12. **§1 / §21 Escape** on Settings and New bot
13. **§14 Inbox** Search empty + one click opens that row
14. **§15 Composer + links** Ctrl+A selects, does not Send; `please e2e-markdown-preview` opens and copies its URL. Plugin **Open to connect** is the same kind of link
15. **§8 / §15 Dismiss** on needs-you keeps the current chat. Park while this chat is open, then switch — still «needs you»
16. **§9 Queue** pending mark, then local Sent while offline
17. **§15 Stop** on a live turn shows Stopped. A late complete does not land
18. **§15 dead wait** after 60+ minutes idle, the first live Send completes without a red line; scripted `please e2e-dead-wait` completes on that send and `please e2e-dead-wait-stuck` still shows one terminal error
19. **§23 Notifications** launch three times → one client; unfocused, minimized, or hidden `please e2e-slow` → one Artek Buddy row, and opening that chat withdraws it

Then **§1 Window look** (coat: Settings / Memory match pairing), 6, 8, 9, 10, 13–24, 30.

---

## How to log

Tick the box on the surface you used. A fail is a GitHub issue: expected, got, surface (Deb / Phone), host SHA / branch, screenshot if it helps. Hang new product bugs under [#222](https://github.com/itsuppartem/artek-buddy/issues/222).
