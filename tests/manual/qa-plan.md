# Owner manual QA — Linux `.deb` and iPhone 11 Pro web

Issue: [#220](https://github.com/itsuppartem/artek-buddy/issues/220). Daily tracker: [#174](https://github.com/itsuppartem/artek-buddy/issues/174). Pad / keys: [#218](https://github.com/itsuppartem/artek-buddy/issues/218) / [PR #219](https://github.com/itsuppartem/artek-buddy/pull/219).

Checkbox = you saw the expected thing on that surface. Walk **0 → 12** in order, then **13+** for the rest of the visible product. If time is short, do **2, 3, 5, 7, 11, 12** first (everything that was not on `main` and is visible).

This is the owner eyes-on pass. Scripted CI already covers slices (`ui` = packaged `.deb` `--serve`, `ui_web` = host page at 375×812). Do not treat a green check as a substitute for this list.

## What you are testing

| | |
| --- | --- |
| `main` | Release **0.10.27**. |
| `develop` | Daily since then: window look, Models / keys, memory book, bot-to-bot, plugins, playbook, phone page. `VERSION` is still **0.10.27** until a bump lands on `main`. |
| Pad / keyboard / Cyrillic | **Not** in `develop`. Lives in PR #219. The Pi host for this pass is that tree. |
| GitHub Release `.deb` | **Old.** Do not use it for this pass. |
| Linux | Window **built from this tree** (`client/build-deb.sh`, optionally `ARTEK_BAKE_URL=1` for a local URL). Wide shell, about 1280×720, three columns. |
| Phone | Home Screen on the **same host URL**. After a UI change, fully kill the icon and open it again. Viewport is iPhone 11 Pro: **375×812** CSS pixels (notch + home indicator). |

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
| **Settings** from the gear does **not** boot the desktop | [ ] | [ ] |

Phone: Create / Models / Plugins open the **Desktop** tab (also in §11).

---

## 2. Models

| Check | Deb | Phone |
| --- | --- | --- |
| Open Models. Model names are readable (not white on white) | [ ] | [ ] |
| Save on an empty key → error under that row, not silence | [ ] | [ ] |
| Change Reasoning (e.g. Low) → **Save** → open chat shows `Using … · Low · Fast` (if Fast is on) | [ ] | [ ] |
| While a reply is streaming, Save again → the turn does **not** break; the line ends `This turn keeps going.` | [ ] | [ ] |
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

1. «Я живу в Белграде.» → wait for the turn to finish.
2. «Я живу в Нови-Саде.» → another turn.
3. New chat / new question about the city: the answer is **Нови-Сад**, not Belgrade.
4. «Привет» alone must not rewrite the book.

Computer → Memory: the identity chapter updated; the old city is not sitting next to it.

| Check | Deb | Phone |
| --- | --- | --- |
| After (1)+(2)+(3) the next city answer is Novi Sad | [ ] | [ ] |
| «Привет» does not rewrite identity | [ ] | [ ] |
| Memory pane identity chapter has the new city only | [ ] | [ ] |

---

## 4. Playbook

Same Demo chat, ordinary language: «Запомни playbook Invoice: когда я говорю invoice, открой сайт счёта и скачай PDF.»

| Check | Deb | Phone |
| --- | --- | --- |
| Book card **Saved** | [ ] | [ ] |
| Chip above Message → click inserts `please run Invoice` and does **not** send | [ ] | [ ] |
| Send → card with steps / Following, not a form in Settings | [ ] | [ ] |

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
| Search → Connect a simple app (no browser) → Connected | [ ] | [ ] |
| Chip above Message. Click = `please use {name}`, no auto-Send | [ ] | [ ] |
| Send → thread **plugin-card** (name + result) | [ ] | [ ] |
| Disconnect / Remove → chip gone; next turn has no that tool | [ ] | [ ] |
| If Connect opens a browser tab, Finish after login marks Connected | [ ] | [ ] |

---

## 7. Desktop (the most visible `develop` change)

Computer pane on **Demo** (Private) or Team.

| Check | Deb | Phone |
| --- | --- | --- |
| **Offline • Click to start** → Booting → Running. Settings still does not boot | [ ] | [ ] |
| Preview is a live screen, caption **Preview · view only**. Not black text «Desktop is running». Click on the preview does **not** take control | [ ] | [ ] |
| fluxbox panel: window title, close, menu. Not a bare X | [ ] | [ ] |
| **Take control** → mouse / keys go to the guest. Caps Lock arrives. **Release** → the same turn continues; typing dots and Stop work again | [ ] | [ ] |
| No pointer for **2 minutes** on the overlay → host Releases itself (holder is bot again) | [ ] | [ ] |
| In chat, **without** pressing start: «Открой https://example.com» (or `HTTPS://…`). Card Allow once / Always / Deny | [ ] | [ ] |
| After Allow: tile itself **Running**; guest has **only the browser**; the file manager does not fill home | [ ] | [ ] |
| Open screen / fullscreen has a picture. Gear does not boot | [ ] | [ ] |

Optional evening:

| Check | Deb | Phone |
| --- | --- | --- |
| Quiet box **15 minutes** with no input → **Sleeping** (sage). Open pane and pulse do not keep it warm. Click Sleeping wakes | [ ] | [ ] |

Team:

| Check | Deb | Phone |
| --- | --- | --- |
| Second bot on the same desk sees `{name} is using the computer`; Take / Restart / Stop / Reset are grey | [ ] | [ ] |

Phone Take control on the current `develop` page is still a desktop overlay. Pad / keys / Cyrillic are §12 (PR #219 host).

---

## 8. «Needs you» from another chat

Need a turn where the bot asks for the desk (`waiting_takeover` + **Open computer**).

| Check | Deb | Phone |
| --- | --- | --- |
| Stay on **this** chat — no «needs you» pill (you are already here) | [ ] | [ ] |
| Switch to another chat → under the header **`{name} needs you`**, not «replied» | [ ] | [ ] |
| Dismiss or enter that chat — the pill does not come back on later switches | [ ] | [ ] |
| A leftover park from the previous window launch stays silent | [ ] | [ ] |

---

## 9. Queue while the host is silent

On **Deb**: stop the `artek-buddy` container for about 30 seconds (or pull the network to the host). Then do the same visible checks on Phone if you can reach a down host from it.

| Check | Deb | Phone |
| --- | --- | --- |
| Reconnect banner, not only a red card | [ ] | [ ] |
| Type and Send → bubble stays; after the host returns it keeps **Sent while offline ·** plus the time | [ ] | [ ] |
| The next ordinary Send has no that caption | [ ] | [ ] |
| A pairing error (need to pair again) does **not** enter the queue | [ ] | [ ] |

---

## 10. Attachments and workers (Linux first)

| Check | Deb | Phone |
| --- | --- | --- |
| Paste a screenshot into Message → chip `screenshot-1.png` (or the file name). Ordinary text is not an attachment | [ ] | [ ] |
| Ask to hand a long task to a helper / long search: **no** worker card with the full assignment. Lines `Started …` / `Finished …` / `Stopped …` | [ ] | [ ] |
| Composer **Stop** kills the lead and the workers | [ ] | [ ] |
| This-PC Allow (read / write this Linux home) works on Deb | [ ] | — |
| Phone `/local/owner-*` is **403**. No This-PC card that reads the phone | — | [ ] |

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
| Close on the Desktop pane and overlay ✕ → **Chat** tab | — | [ ] |
| Share → Add to Home Screen: hint at the **top**, not over Models / nav. Got it hides it | — | [ ] |
| Turn on alerts — only from the home-screen icon, and only while the app is open. No background | — | [ ] |
| Wide window (Deb 1280×720) stays three-column, not «phone» | [ ] | — |

---

## 12. Pad and Cyrillic (on the Pi now, not in `develop`)

Fully kill the Home Screen icon and open it again. Desktop → desk overlay.

This section is **Phone on the PR #219 host**. Deb uses a real mouse and keyboard; skip pad gestures there.

| Check | Deb | Phone |
| --- | --- | --- |
| Finger is a trackpad: drag moves the cursor, it does not jump under the finger. Tap = left click **at the dot**. Two fingers = right click or scroll | — | [ ] |
| Beige dot sits on the 1280×800 picture, not on the black letterbox | — | [ ] |
| Keyboard → system keyboard + row Esc / Tab / Enter / Bksp / Del / arrows. No on-screen input field | — | [ ] |
| iOS Done check **dismisses** the keyboard. Tap on the desk does not | — | [ ] |
| Russian layout types into the guest field (address bar / input). Latin still works | — | [ ] |
| Overlay ✕ works on the first tap → Chat | — | [ ] |

---

## 13. Pairing and session (both surfaces)

| Check | Deb | Phone |
| --- | --- | --- |
| Fresh pair with a 15-minute one-use code works. A second use of the same code fails under the form | [ ] | [ ] |
| After pair, the token is not visible in the page (Deb: `~/.config/artek-buddy/token` mode 600; Phone: httpOnly cookie) | [ ] | [ ] |
| Auth error in the thread: **Pair this computer again** / re-pair. Does not queue as an offline send | [ ] | [ ] |
| Unpair returns to the pair screen. Re-pair with a new code restores the inbox | [ ] | [ ] |
| Pairing does **not** open the computer pane or Models and does **not** boot a desktop | [ ] | [ ] |

---

## 14. Inbox and bots

| Check | Deb | Phone |
| --- | --- | --- |
| Search filters inbox (and Archived) by name / preview | [ ] | [ ] |
| Click a row opens that chat. Selected row, header, composer, and computer pane name the **same** bot | [ ] | [ ] |
| Switching chats does not blank the thread or jump inbox order under the pointer | [ ] | [ ] |
| Opening a chat marks it read. A reply while that chat is open does not leave the unread dot | [ ] | [ ] |
| Right-click (Deb) / long-press if offered (Phone): Pin / Unpin, Mark as unread (sticks until you leave and open again), Edit profile, Duplicate, Archive, Delete | [ ] | [ ] |
| Empty inbox: Restore from Archived, or create a first bot | [ ] | [ ] |
| Create: name + Team / Private. Focusing Name does not mint a bot; only Create does | [ ] | [ ] |
| Duplicate makes a second bot. Delete removes that bot; optional purge memories | [ ] | [ ] |
| Inbox order is pinned first, then created. A later message does not jump a row | [ ] | [ ] |

---

## 15. Thread chrome

| Check | Deb | Phone |
| --- | --- | --- |
| Enter sends. Shift+Enter inserts a newline (Deb). Phone return key follows the on-screen keyboard | [ ] | [ ] |
| Deb: Ctrl+Z undoes typing in Message (Ctrl+Shift+Z / Ctrl+Y redo) | [ ] | — |
| Load earlier pulls older messages without jumping off the latest if you were pinned to the bottom | [ ] | [ ] |
| Right-click Reply (Deb) puts a quote in the next user bubble | [ ] | — |
| Ask card (options or free text) waits; answering continues the turn. A missing / already-answered card does not break the thread | [ ] | [ ] |
| Consent card: Allow once / Always / Deny. Deny does not run the action. Always covers later same-kind asks | [ ] | [ ] |
| Attention pill sits **under** the header, not over Send or Load earlier. Title opens that chat; Dismiss does not | [ ] | [ ] |
| A finished background chat still raises replied / failed. Finishing does not steal the open chat | [ ] | [ ] |
| Thread stays on the latest cards when pinned to the bottom. A switch lands on the latest messages | [ ] | [ ] |
| Failed / cancelled run shows a run-error, not a silent hole | [ ] | [ ] |
| A follow-up while `waiting_takeover` starts a turn (does not only enqueue) | [ ] | [ ] |
| Stop keeps the run cancelled: a late complete does not append the essay. Queued owner lines survive Stop and prepend to the next send | [ ] | [ ] |

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
| Deb Download opens the system Save dialog (Downloads / Загрузки by default). Cancel writes nothing | [ ] | — |
| Phone Download uses the browser / share sheet; it does not write the Linux home | — | [ ] |

---

## 18. This-PC (Deb only)

Read a file or list a folder under the Linux home: no Allow card. Read-only shell (`ls`, `cat`, `echo`, …) does not ask.

Write a file or a command that can change the PC: Allow once / Always / Deny. Always covers later writes and commands on this PC, not each folder. Paths outside `$HOME` stay 403 on the card.

| Check | Deb | Phone |
| --- | --- | --- |
| Read / list under home: no card | [ ] | — |
| Write / mutating command: card, then the action only after Allow | [ ] | — |
| Deny does not touch the PC | [ ] | — |
| Phone never runs owner tools | — | [ ] |

---

## 19. Memory pane (beyond the book in §3)

Computer → Memory.

| Check | Deb | Phone |
| --- | --- | --- |
| Owner / work / charter list is visible. New (this bot \| shared), Edit, Outdated = delete, Export `.md` | [ ] | [ ] |
| A weeks-grown book is not cut to a 200-character Settings stub | [ ] | [ ] |

---

## 20. Routines

Computer → Routines.

| Check | Deb | Phone |
| --- | --- | --- |
| New: name, cron, prompt. Invalid cron disables Save | [ ] | [ ] |
| On / off, Run (test), Delete | [ ] | [ ] |
| A due routine fires through the same send path while the laptop can be closed (watch the thread later) | [ ] | [ ] |

---

## 21. Settings, Team / Private, Reset

| Check | Deb | Phone |
| --- | --- | --- |
| Settings: name, title, description, instructions, Team \| Private, notifyOnFinish, Restart / Stop / Reset, Delete | [ ] | [ ] |
| Settings opened from the computer pane returns to that pane. Create / Models Close do the same if the pane was open | [ ] | [ ] |
| Changing Team ↔ Private rebinds the desktop; the old home is **not** copied | [ ] | [ ] |
| Settings Stop leaves the box **Sleeping**, not a dead Offline preview | [ ] | [ ] |
| Reset wipes that home. Team Reset wipes the shared desktop for every Team bot. Team Reset stays disabled while another bot holds the box | [ ] | [ ] |
| Restart or Stop on a running computer does not leave a stuck Connecting spinner | [ ] | [ ] |

---

## 22. Files on the sandbox desktop

The computer pane is screen, memory, and routines — not a second file list.

| Check | Deb | Phone |
| --- | --- | --- |
| Take control → fluxbox / right-click **Files** (PCManFM) opens that bot’s home | [ ] | [ ] |
| `launch_app` / menu Browser and Terminal still work next to Files | [ ] | [ ] |

---

## 23. Notifications

| Check | Deb | Phone |
| --- | --- | --- |
| Deb: a finished background chat can raise a desktop notification if notifyOnFinish is on (replied / failed). It does not steal the open chat | [ ] | — |
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
2. **§3 Memory book**
3. **§5 Bot asks bot**
4. **§7 Desktop**
5. **§11 Phone chrome**
6. **§12 Pad and Cyrillic** (PR #219 host only)

Then come back for 1, 4, 6, 8, 9, 10 and 13–24 when you have a longer sitting.

---

## How to log

Tick the box on the surface you used. A fail is a GitHub issue: expected, got, surface (Deb / Phone), host SHA / branch, screenshot if it helps. Do not close #220 from a fail; file a product issue and leave a leftover note on #220.
