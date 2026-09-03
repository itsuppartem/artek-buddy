# Changelog

## Unreleased

### Added
- A background worker can report a short owner-safe step. The host posts a throttled «Still working» line in chat so a long job is visible without a status ping, a worker card, or a native alert.
- Owner jobs have a short client delivery ACK and a separate queued / acknowledged / terminal lifecycle. A new `.deb` claims a job before touching This PC; older clients may still return a result without ACK.
- The Linux client can opt into SSH connection reuse with `~/.config/artek-buddy/ssh-mux`. Its private ControlMaster socket never changes `~/.ssh/config`; related small remote checks are batched into one SSH session.
- A replaced Cursor lead session receives one bounded, redacted resume brief with known workspace, path/branch facts, constraints, and the last visible result.
- Phone desktop overlay only: the remote screen is a pad (drag moves the pointer, tap left click, two fingers right click). Keyboard opens the phone keyboard. Chats and Chat stay as they were. The host page clears the iPhone notch (`safe-area-inset-top`) and does not leave a second empty strip under the nav.
- The same Funnel / tailnet URL serves the window. A phone pairs with a code; the device token stays in an httpOnly cookie. Narrow screens stack Chats / Chat / Desktop (iPhone 11 Pro 375×812). iPhone Add to Home Screen plus Turn on alerts (only while that app is open — no background). This-PC files stay on the Linux `.deb`. CI splits `ui` (`.deb`) from `ui_web` / `live_web` (host page).
- The owner can keep a published skill for this chat (`install_book` from a public URL after Allow). The stored body is the fetched markdown. The next turn sees names only; the agent calls `open_book` itself when the description matches the task. No Settings form or owner trigger.
- Models and Plugins Save name a host error instead of staying silent. A row's model is the host default (no second Default list). Cursor exposes reasoning and Fast; Save prefers grok-4.6 extra-high fast when that id is on the list. A Plugins key already on the host at boot shows as Key saved.
- After an app is connected, the lead and a worker already have that app's tools this turn and call them themselves. The thread shows that app's result as a card. There is no chip above Message.
- The lead can search catalog apps (`list_apps`) and attach them (`connect_app`) from chat. Connected names ride in the turn. Login URLs open in the owner's browser, not the bot desktop.
- Plugins pane: paste a host key, search the catalog, connect or disconnect an app. Only connected apps become tools on the next turn. The window never sees a saved full key.
- A bot can ask another inbox bot by name or id. This chat shows the ask and a card to that chat. The other bot works in its own thread; only its last message comes back so this bot can answer you. Missing, archived, deleted, empty, and self-asks fail closed.
- Models screen: paste provider keys in the window, fetch that account's list, pick one host default. Fresh host boots without `CURSOR_API_KEY`. Send without a default stays in the thread and says to open Models.

### Fixed
- Unsent Message text, files, and Reply stay on the chat they belong to. A slow Send in one chat does not disable Send in another; a late failure restores files on the originating chat.
- Stop UI tests wait for a cancelled turn to settle instead of a 3s sleep. Computer pane open/close no longer swallow a missed click. Loopback unpair is a client RPC test; the window still unpairs via Pair this computer again.
- Ask-before git/commit/branch/PR/MR/merge restatements map to one standing rule (`please e2e-remember-git-approval`). A later permission to merge without asking revises that card.
- A status-only ping (`please e2e-worker-status`) posts a short `send_message` acknowledgement before inspect. Inbox and mid-turn steer use the same order. The ping does not start a new plan.
- Workspace `/v1/events` 401/403 shows Pair again, same as a 401 on send. Background needs-you cannot go silent while the window still looks paired.
- Live browse Allow/Deny fail the job if the model never shows a consent card. Skip remains only when the secret is absent.
- Models list/Forget and Plugins status/Remove show a line on failure. Forget and Remove keep the previous key; a failed Plugins status does not stay on Checking.
- A bot-to-bot reply is marked delivered only in the same transaction as the source follow-up run or inbox item. Overlapping owner send cannot drop that reply.
- API setup errors (broken migration, workspace) fail the suite in CI. Local skip is `ARTEK_ALLOW_DB_SKIP=1` only. The job summary prints pass/fail/skip counts.
- An existing `artek-computers` network with inter-container communication on is deleted when unused, or refused if boxes are still attached. ICC off is required, not only on first create.
- The Linux `.deb` build uses `npm ci`. Host Playwright matches the test pin (1.62.0). Release prints base FROM lines and the host image digest.
- `/readyz` is 503 when Postgres or the runtime is down. `/health` and `/livez` stay process liveness (200). Compose healthchecks use `/readyz`.
- A second `install-host.sh` on a clean checkout fetches and checks out that release tag. A dirty tree aborts; `.env` is kept.
- Supervisor `:7091` compares the bearer with `secrets.compare_digest`. Client 500s are a stable `supervisor error`; engine text stays in the server log.
- After `send_message`, a different finish body is the next bot message. The same text is not duplicated (`please e2e-send-then-answer` / `please e2e-send-then-repeat`).
- `python -m artek_buddy worker --once` is the release worker process against host HTTP. CI starts that command; a due routine wakes once and a second pass does not duplicate it.
- Plugins Connect and `connect_app` send a host-owned HTTPS callback (`CONNECTIONS_CALLBACK_URL`) to the provider. A caller `redirect_url` (window origin, `http`, or another host) cannot become `callback_url`.
- Named CodeQL residuals keep inline `lgtm` (`py/command-line-injection` on owner-exec, `py/path-injection` on the owner-path join). Secret scanning, push protection, and Dependabot alerts/security updates are on for this repository.
- `release.yml` Bind prints CodeQL check-run and workflow run ids on the dispatched `main` SHA and fails closed if that `codeql` workflow run is missing or red. There is no automatic `workflow_run` publish.
- `release.yml` serializes dispatch and moves GHCR `VERSION` / `latest` only after the GitHub Release exists, so a failed Release create cannot retag the installer image.
- Manual `release.yml` dispatch requires a green push `test` and CodeQL on that `main` SHA. `force` cannot republish an existing tag or GitHub Release; it aborts before registry write.
- A minimized or tray-hidden Linux `.deb` still raises one native row when the open chat finishes. Iconify / withdrawn now set `window_active` false even if GTK `is-active` stays true.
- Always is looked up on the frozen turn device, not the last HTTP actor. A second window cannot spend the first window's Always; a host-wide grant is only a row with no device.
- A late desktop click after Release cannot restore Take control. Input is bound to that lease; a stale save does not rewrite the holder.
- A worker This-PC auto read stays on the thread snapshot after the lead turn finishes and the window reloads. ACK still claims once; a second window that loses the claim stands down.
- Owner `git`/`find` that can write (`--output`, `git branch` create/rename, `-fprint` / `-fprintf` / `-fls`) require Allow. Deny does not create the file or branch. A write path outside `$HOME` does not run on the paired client.
- Privileged `release.yml` is no longer a default-branch `workflow_run`. Publish is `workflow_dispatch` on `main` after green `test` on that SHA; a `release.yml` change that exists only on `develop` does not get the write token.
- The GitHub Release tag is created at that tested `main` SHA and peeled before GHCR `VERSION` / `latest` move. A missing tag is not taken from default `develop`; `gh release create` uses `--verify-tag`.
- A background worker that emits no assistant text is no longer treated as idle. Host-owned activity (tool start/finish, sequence, last tool) is what status inspects; a status ping cannot stop or replace that worker, and a stale inspect cannot Stop it. Explicit window Stop still cancels it and admits no new worker tools.
- Native `.deb` alerts follow GTK `is-active` via loopback `window_active`, not WebKit `hasFocus`. Switching to another app no longer stays silent, and the open chat is not marked read while that window is inactive.
- Right-click a chat message offers **Copy** for that text. Link rows still have Open in browser and Copy URL.
- An unfocused Linux `.deb` still raises one native row when the open chat finishes. WebKitGTK does not treat “another app is in front” as a hidden page; GTK `is-active` now drives that, and opening the OS list does not re-notify an already shown event.
- Guest Files is Thunar without volume watching. Leftover pcmanfm is killed at box start so it does not keep covering the desktop.
- A long `Remembered:` clock line is a one-row preview. Click it to open that Memory card with the full text.
- Host-page Take control follows the pointer in use: a desktop browser uses the `.deb` overlay; a phone keeps the pad.
- Linux `.deb` Ctrl+V attaches a screenshot even when the clipboard also has a `file://` path. Ctrl+Z / Ctrl+Shift+Z undo and redo Message.
- Plugins Remove still forgets the key after a login tab. An in-flight catalog load no longer puts Key saved back on an empty Search apps list.
- **Open to connect** on a plugin login card is a real `http(s)` link, so the Linux `.deb` opens the owner browser the same way a markdown link does. Plugins Connect and right-click **Open in browser** still open that browser when `window.open` is dropped.
- Each inbox chat keeps its own model session. A bot without a stored id no longer inherits the host default (or another chat). Two chats can run at the same time.
- Connected catalog apps attach as tools on the lead as well as a worker. The window no longer pins a chip above Message after Connect.
- Re-asserting a standing rule (or a worker calling `remember`) no longer floods the thread with `Remembered:` clock lines. One new fact this turn can print once; a worker save stays in Memory only.
- Switching away from a chat that parked while it was open still raises «needs you». The window no longer consumes that pill just because you were looking at the speaker (`please e2e-takeover`).
- Native attention now has one workspace-event source: only a new final reply, failure, owner question, or takeover can alert. Polling, replay, intermediate/status text, and silent completion cannot re-notify an old line. Reading requires the focused chat and withdraws its row; GNOME dismissal alone does not read it. One libnotify object/id is updated per bot, and GTK3 relaunch activates the existing client instead of adding subscribers.
- A `Remembered:` memory line no longer raises **is asking** (or a finish alert). Auto owner-tool `waiting_input` is not treated as an owner question.
- GNOME's notification list keeps an **Artek Buddy** row while the client is running. The tray badge was only the window urgency hint; `notify-send` left the bus and GNOME destroyed the matched-app source.
- The installed Linux client identifies as **Artek Buddy** so the dock and app menu use the packaged mark instead of a generic `artek_buddy.py` gear. The tray looks up that same PNG from the packaged icon directory.
- The Linux `.deb` sends one native notification for background replies, failures, owner questions, and takeover instead of dropping the event after the in-window banner. Its tray indicator can reopen or quit the client; closing the window hides it to the tray while indicators are supported.
- A blocked browser task can ask the owner for one concrete step and resume the same `ask_user` call and `run_id`. Answers stay on the card, duplicates are rejected, and timeout is explicit; no site-specific integration is required.
- A second `.deb` window that loses an owner-job ACK no longer reports that conflict as the winning client's failure. Claim-capable results carry the winning ACK nonce; queued no-ACK results remain compatible. Thread snapshots expose every queued automatic job instead of hiding parallel work behind one id.
- Clicking a Models chip uses that model. Tan is the host default, not a local pick that still leaves Grok in use.
- Caps Lock during Take control raises letter case on the bot desktop. The overlay does not swallow that key.
- Ctrl+V in the Linux WebKit window no longer cancels an empty/deferred clipboard event before ordinary text can reach Message. Image, file, and file-manager-path paste still use the attachment path.
- Chat links open in the owner's system browser from the `.deb`. Right-clicking a link offers Open in browser, Copy URL, and Reply; URL copy falls back for older WebKit clipboard support.
- A shorter restatement of an already detailed standing rule no longer revises the same Memory chapter or writes another identical Remembered line.
- Back-to-back and parallel This-PC calls no longer reuse a process-global consent id. Late owner results are rejected, completed auto jobs are not offered again, and the phone/host page leaves auto jobs for the paired Linux client.
- A new model session no longer receives the current user send twice in compact history; repeated identical user lines from silent failed runs collapse to one.
- An instant dead Cursor wait after a good turn retries that same send: it expires a stuck run, then restarts the poisoned local SDK bridge and resumes the same chat if needed. A successful recovery no longer asks the owner to Send again.
- Stop on a live turn writes Stopped. A late model complete from that run does not land as a bot bubble.
- Release keeps the last guest frame on the overlay until the view-only picture loads. Take control from Sleeping names Waking the desktop… instead of a black void.
- One click on an inbox row opens that chat. A leftover mouse-up or a late inbox fallback does not land on the previous thread.
- New memory defaults to This bot with a filled scope control. Delete is Remove. Save acknowledgement uses the create/edit buttons, not a shared Saved name.
- The closed Plugins hatch does not steal the thread wheel or open from the right edge. One Close dismisses.
- Plugins Search apps stays open on Enter and keeps catalog scroll where the owner left it.
- Plugins Connect only marks Connected. Leftover mouse-up after Connect does not Send.
- A queued send is marked Waiting for the host until reconnect, then Sent while offline with local time.
- Dismiss on a needs-you pill only hides it. The open chat stays put.
- Ctrl+A in Message selects the draft. It does not Send or duplicate the bubble.
- Plugins pane waits for host key status before showing the paste field, so a leftover key is not a flash of an empty form.
- Inbox Search with no matches shows empty copy and a Clear control instead of a blank rack.
- Escape closes Settings and New bot. Composer text and the guest overlay keep their own Escape.
- Models Cursor has one commit. Empty providers say to paste a key instead of a dead Use this model.
- Settings Restart… and Stop… confirm once, same as Reset… and Delete chat….
- File-card Download and Load earlier look like controls. Owner cards still offer Download; the oldest page leaves a beginning line.
- Inbox Search marks the matching name or preview text so a snippet hit is obvious.
- A Shift+Enter newline stays a newline in the sent user bubble.
- Unread is a named tan circle and a bold row, not a hidden 7px square.
- Message placeholder truncates a long bot name with an ellipsis instead of clipping mid-word.
- Plugins Search apps filters the catalog as you type. Enter is not required.
- Phone file-card Download uses the browser, not a Linux `/local/save-artifact` path.
- Skill-book procedures and controls stay internal to the agent. Historical skill blocks are hidden and omitted from inbox/reply excerpts; successful install/open/forget no longer persists a card or adds a chip above Message.
- Plugins Connect on a no-browser catalog app either connects or names the next setup step. It no longer dies on `could not start that connection` with nothing to do.
- Settings Title keeps the typed role through blur and Save. A host refresh while Edit profile is open no longer empties the field.
- Routine next-run drops the ISO microsecond fraction and keeps UTC.
- Settings, Memory, and Routine Save flash **Saved** for about a second, then the form closes. A host error stays under the row.
- A failed playbook run shows one human **The turn failed.** line — not a raw `run failed: run-` id, YAML, or that same line as a bubble plus a red box.
- Settings, Memory, Routines, ask/file cards, and the computer overlay use the same `@theme` tokens as pairing and the thread. Traffic lights and guest noVNC pixels stay as they were.
- Create and Settings ask three different questions: Title is a short role, Description is what the bot is for, and Instructions are standing orders (not labelled Prompt). Create now has that Instructions field too.
- Auth recovery on the host page says **Pair this phone again**, matching the pairing title. The `.deb` still says **Pair this computer again**.
- Pairing tells the owner where to get a code and what Pair does. The phone page has no token or host-module command. The `.deb` footer is the README Compose exec.
- Chat that writes the identity book lists that chapter in Computer → Memory. Owner place/person rows are labeled identity, and a later city replaces the old one on the same card.
- Phone Close on Computer / Models / Plugins returns to the Chat tab with the thread, not a blank Desktop tab.
- Phone Take control stays held after a pad drag or tap. The overlay caption is not selectable host text, and **Type on the desktop** is a tappable field in the keyboard strip.
- Release leaves a live view-only preview (not a black overlay) and the Computer pane matches: Take control, not You have control.
- Offline and Sleeping **Click to start** boot to a view-only Running preview. Take control stays a separate grant.
- One standing rule in chat writes one Remembered line and one Memory card. A paraphrase in the same turn, or extract after that turn, does not add a twin.
- Phone desktop typing reaches the guest as UTF-8, so a Russian keyboard is not dropped.
- The iPhone home-screen hint sits at the top of the host page so it no longer covers Models, New bot, or the composer.
- Opening a website on the bot desktop no longer also opens the file manager. `open` treats `HTTPS://` like `https://`, and leftover pcmanfm volume autorun is off.
- The bot desktop starts fluxbox again. Docker tmpfs `/tmp` is noexec, so the old generated startup script never ran and windows had no toolbar or close buttons.
- A running desktop opened from the pane shows the live preview. The window fetches the screen URL when the box is already Booting or Running, so a bot-started session is not stuck on the text-only Desktop is running fallback.
- Long tool work runs in a background worker. The lead stays free for status and corrections, then writes one final result. Worker cards and Started / Finished / Stopped lines stay out of the thread. Composer Stop still cancels workers while the lead is idle.
- A bot that opens a path on a stopped desktop updates the computer tile to Running without a click. The host publishes `computer.status`; Offline still polls while that turn is live.
- Reasoning and Fast can be saved while the host already uses that model. The open chat gets a Using line; a live turn keeps going and the next send uses the new default.
- A parked takeover on another chat keeps being watched so «needs you» still appears if the first switch missed the event. The same-kind debounce does not permanently consume that pill. A chat created in this window is not treated as a leftover park, and opening that chat does not stick Dismiss if the takeover arrived while it was already on screen.
- A takeover on another chat shows «needs you», not «replied». The bot stays `waiting_takeover` (same idea as `waiting_input`), and the window does not dismiss that banner during the chat switch. If the takeover event arrives while that chat is open, or the thread stream drops it on switch, the other chat still raises the pill from the parked status.

### Changed
- Local `.deb` builds refuse to overwrite an existing package; `ARTEK_BUILD_SUFFIX` creates a distinct filename and Debian version for manual testing.
- Memory is a book the bot revises from chat: owner sections (identity, tone, contacts, machines, paths) and this-chat standing rules always ride in the next turn. Work notes still match the request. The 3+4 card caps and 200-character Settings cut no longer drop a weeks-grown book.
- After a turn that saved a section, the host rewrites that section (default model when a key is set) so a newer fact replaces a contradiction instead of stacking both. The book block in the model prompt is 256 KiB.
- Send while the host is down parks the user bubble and flushes it when health returns, with a «sent while offline» caption. A reconnect banner replaces the red host-error card.
- Take control auto-releases after two minutes with no mouse or key. The 15-minute hard lease stays as a cap. A quiet computer sleeps after 15 minutes; an open pane and the 60s heartbeat do not keep it warm. A parked `waiting_takeover` no longer pins the box.
- Window identity: Cavalier marks, ink/plate/tan tokens, Atkinson + Fraunces + Azeret Mono, labeled New bot / Computer / Settings / Send / Stop. Send is disabled when empty.
- Release scans the host image digest (HIGH and CRITICAL) before tagging `latest`, refuses `--clobber` on GitHub Release assets, and does not prune old Releases. Client CycloneDX SBOM is the packaged `.deb`.
- Host FastAPI/Starlette pins no longer need runtime pip-audit ignores. Remaining ignores require a reason and expiry.
- Host and worker serialize `apply_migrations` with a Postgres advisory lock and store a sha256 per applied file.
- Supervisor file writes send bytes through the Docker archive API instead of interpolating content into a shell heredoc.
- Rulesets Protect develop and Protect main require quality, backend, ui, scan, live_gate, and CodeQL analyze. `live` stays optional.

## [0.10.27] - 2026-08-22

### Fixed
- Deleting a bot only removes `data/artifacts/<that bot id>`. The window proxy keeps static files inside the packaged web root, drops CR/LF from `Content-Type`, and requires TLS 1.2+ to the host.

### Changed
- README and CONTRIBUTING match GitHub Releases: the client `.deb` is attached after `test` on `main` is green. Local `client/build-deb.sh` is optional.
- `client/artek_buddy.py` is the entrypoint. Pairing, loopback proxy, notifications, and the GTK window live in sibling modules; `build-deb.sh` ships them next to the entry.

### Added
- `pyproject.toml` is the Python tool config (Ruff, mypy, pytest, coverage). CI `quality` and `backend` jobs run Ruff + mypy; `backend` records pytest-cov on the Actions summary and fails under 56% (measured on this change).
- `client/web` has Biome lint and Vitest on pure helpers (`npm run lint` / `npm test`), wired next to `tsc` on the `backend` job.
- Dependabot (pip, npm, Actions, Docker), CodeQL, pip-audit, `npm audit --audit-level=high`, and Trivy (filesystem on `test`, host image on `release`). Third-party Actions are pinned by commit SHA.
- `THREAT-MODEL.md` names the host / supervisor / sandbox / pairing boundary, including `:8080` on `0.0.0.0` and Funnel residual risk.
- Computer boxes keep image-default root (uid 1000 failed the live Chromium canary). They get `CapDrop: ALL`, 1536 MiB / 1 CPU / 512 pids, tmpfs `/tmp`. Playwright in the computer image is pinned to `1.55.0`. Chromium stays `--no-sandbox --disable-setuid-sandbox`; the rootfs stays writable.
- `ARCHITECTURE.md` and `adr/0001`–`0007` record the running Compose trade-offs (supervisor socket, Team/Private, scripted vs Cursor, Compose, SQL migrations, consent cards, bind/Funnel).
- CI dumps the FastAPI schema (`python -m artek_buddy.openapi_export`) and generates `client/web/src/generated/openapi.d.ts`. `/docs` stays off. Dirty schema/types fail `backend`.
- GitHub Releases attach CycloneDX SBOMs, `SHA256SUMS`, and GitHub Artifact Attestations. Notes come from the `CHANGELOG.md` section for that `VERSION`.
- Hypothesis properties cover owner-command classification (write verbs, `find -exec`, redirects) and the owner-path jail (`..`, absolute escapes, NUL).
- Host logs are JSON in Docker (`LOG_FORMAT=json`) with a greppable `request_id` from HTTP middleware through `threads.send` and tool lines. Tokens, pairing codes, `/novnc` query strings, and `/home/<user>` are redacted.
- GitHub issue forms, a pull-request template, and CODEOWNERS (`@itsuppartem`).
- The migration runner splits on statement boundaries (quotes, comments, dollar-quotes), not raw `;`. Replay on an empty database applies every historical file.

## [0.10.26] - 2026-08-21

### Fixed
- Restart or steer on a missing subagent is 404, same as stop.
- Switching chats no longer follows the latest-updated row, blanks the thread, or jumps inbox order under the pointer.
- The computer pane stays open after Settings, Release, and creating a bot.
- An attachment chip cleared by Send cannot come back from a late native attach or clipboard read.
- Focusing Name on Create does not mint a bot; Create is a form submit with an in-flight lock.
- Stop keeps the run cancelled: a late complete cannot append the essay.
- A follow-up while `waiting_takeover` starts a turn instead of only enqueueing.
- Stop keeps queued owner lines and prepends them to the next send.
- Each lead prompt includes a compact summary of this chat, not only the last line.
- Dismissed attention pills stay gone after switching chats.
- A thread pinned to the bottom stays on the latest cards; a switch lands on the latest messages.
- Computer pane Sleeping matches Settings Stop; preview click does not take control.
- Handing the desktop to the owner clears typing dots and Stop; Release resumes the same run.
- Default `computer_observe` is slim (no screenshot JSON); Caps Lock reaches the control session.
- Cursor `wait()` status and store `error_code` are logged and stored; a dead auth bridge is recycled.

### Changed
- SSE sends a keepalive as soon as the client connects, so the stream is live before the next event.
- History, `/v1` routes, agent tools, and the window shell are split along existing seams. HTTP paths and public imports are unchanged.

### Added
- HTTP tests for thread attachments, message pagination, `GET /v1/messages`, bounded SSE, and computer `files/raw` download.

## [0.10.25] - 2026-08-21

### Changed
- A GitHub Release waits until `test` on that `main` commit is green. A red `backend` or `ui` PR into `main` cannot merge.

### Fixed
- Pairing rejects a glued Host URL instead of crashing the loopback proxy. The form uses the host from boot status and does not overwrite the field while you type.
- Stop on a missing chat is 404.
- Answering a missing consent is 404, not a generic "not pending".
- Revoking a device a second time is 404.
- Run timestamps include microseconds so a follow-up in the same second is the latest run.
- Scripted consent waits for Allow/Deny instead of finishing the turn with the card still pending.

### Added
- HTTP API tests on the `backend` job for pairing leftovers, session, bots duplicate/pin, thread stop/follow-up/read, consent deny, computer files/input, and exact memory/cron error codes.

## [0.10.24] - 2026-08-21

### Fixed
- The attention pill no longer covers Send or Load earlier. It sits under the thread header. Opening that chat or Dismiss clears it. Another bot finishing does not steal the open chat.
- Pairing no longer opens the computer pane or auto-boots the desktop.
- Switching chats no longer drops `run.completed`, so the replied / failed pill can show for the other chat.
- Auto owner-file jobs no longer hang the host when the client never posts the file.
- A 403 on an owner path still shows on the consent card after Answered.
- Settings opened from the computer pane returns to that pane. Team Reset stays disabled while another bot holds the box.
- Stop on a running computer leaves it Sleeping, not a dead preview.
- The fake CI desktop does not mint a noVNC URL, so the pane does not sit on Connecting.

### Added
- Scripted UI coverage for boot, sidebar, thread, attach, consent, computer pane, Create/Settings, and attention banners.

## [0.10.23] - 2026-08-20

### Changed
- Desktop launcher, GTK window, `notify-send`, pairing card, and bot avatars use an original bandicoot mascot (tech vest, headphone, teal ears) instead of the chevron mark and `utilities-terminal`.

## [0.10.22] - 2026-08-19

### Added
- Merging a `VERSION` bump into `main` publishes a GitHub Release: a `.deb` with no baked host URL, `install-host.sh`, and the host GHCR image. The computer image is built on the Pi (QEMU arm64 in Actions hangs). On a Pi, run the script, paste `CURSOR_API_KEY` into `.env`, run it again. Only the five newest Releases are kept.

## [0.10.21] - 2026-08-19

### Changed
- The computer pane no longer lists sandbox files. Use **Files** on the desktop (Take control) to browse that home.

## [0.10.20] - 2026-08-19

### Fixed
- Deleting a chat removes that chat's copies from the sandbox `inbox/`. A shared Team home and other bots' files stay.

## [0.10.19] - 2026-08-19

### Fixed
- Long owner-exec commands and file paths wrap inside consent cards and chat bubbles instead of stretching the thread.

## [0.10.18] - 2026-08-19

### Added
- The Team/Private desktop menu has **Files** (PCManFM) next to Browser and Terminal. `launch_app(application='files')` opens the home folder. The client Files pane is unchanged.

## [0.10.17] - 2026-08-19

### Fixed
- Opening a chat marks it read. A reply while that chat is open no longer leaves the unread dot. Right-click Mark as Unread still sticks until you leave and open the chat again.

## [0.10.16] - 2026-08-19

### Fixed
- Copying a file on Linux (file manager, screenshot folder, any type) and pasting into the composer attaches the file. The clipboard often has only a `file://` URI or a home path; the `.deb` reads that file instead of inserting the path as text.

## [0.10.15] - 2026-08-19

### Fixed
- Shift+Enter inserts a newline in the composer. The field is a textarea; Enter still sends.

## [0.10.14] - 2026-08-19

### Fixed
- Ctrl+Z in the chat composer undoes typing (Ctrl+Shift+Z / Ctrl+Y redo). The controlled input had no native undo in the `.deb` window.

## [0.10.13] - 2026-08-19

### Changed
- A message sent while the lead is working is injected on the next tool result (Codex/Grok-style steer). If the turn has no more tools, it still runs as a follow-up after.

## [0.10.12] - 2026-08-19

### Changed
- Reading a file or listing a folder on the paired PC no longer shows Allow. Same for read-only shell (`ls`, `cat`, `echo`, `pwd`, `uname`, …). Writing a file or a command that can change the PC still asks. Always covers later writes and commands on that PC, not each folder.

## [0.10.11] - 2026-08-19

### Added
- Image, video, and audio file cards in the thread show a preview, not only a Download row.
- Download opens the system Save dialog (default folder Downloads / Загрузки). Cancel writes nothing.

### Tests
- Loopback chooser hook, cancel 409, thread `file-preview`, and a cancelled card that stays idle.

## [0.10.10] - 2026-08-19

### Fixed
- Download (thread card and Files) succeeds only when the `.deb` writes the file through `/local/save-artifact` or `/local/save-home-file`. A silent WebKit `<a download>` click no longer reports Saved to.

### Tests
- Unhappy paths for the real window: loopback write to `Загрузки`, path escape, missing host file, paste that must not steal text, Allow still answers if the local job fails, Deny does not touch the PC, Stop is one banner with no extra bubble.

## [0.10.9] - 2026-08-19

### Added
- The computer pane lists this bot's sandbox home (inbox, downloads, files the bot wrote). Open a folder, preview text or media, and Download saves to this PC. Works while the desktop is asleep.

## [0.10.8] - 2026-08-19

### Fixed
- Ctrl+V of a screenshot into the composer attaches it. The clipboard image is read from `items` (WebKit often leaves `files` empty) after `preventDefault`, and unnamed clips become `screenshot-1.png`.

### Added
- Pending image, video, and audio attachments show a thumbnail or player above the send field so you can look or listen before the message goes out.

## [0.10.7] - 2026-08-19

### Fixed
- Download on a file card saves into the owner `Downloads` (or `Загрузки`) through the `.deb`. WebKit has no browser download dialog; the old click did nothing.

## [0.10.6] - 2026-08-19

### Fixed
- Stop no longer posts a second "stopped by user" bubble next to the banner. One "Stopped." line. A user stop does not mark the bot as failed.

## [0.10.5] - 2026-08-19

### Fixed
- Clicking Allow on an owner-PC card still tells the host, even if the local path job fails. The agent gets the error instead of hanging.
- `~/Downloads` on a Russian desktop maps to `~/Загрузки`. A missing folder says "folder not found", not "outside the home".
- After Allow the tool result says the owner already answered. The model is told not to ask them to press Allow again.

## [0.10.4] - 2026-08-19

### Added
- The composer plus button, paste, and drop attach several files to the next send. The host stores them as artifacts and copies them into that bot's `inbox/` so the agent can read the paths. Caps: 10 files, 25 MB each, 50 MB together.

## [0.10.3] - 2026-08-19

### Added
- The agent can attach a file in the thread (`send_file`). The `.deb` shows a card with Download. Files stay on this Pi (`data/artifacts/{bot_id}`) and download through `GET /v1/artifacts/{id}`.

## [0.10.2] - 2026-08-19

### Changed
- Filling a form, typing, or clicking on a site in the remote browser asks Allow once / Always / Deny first (`page_input`). Watching the screen still does not.
- New `browser_act` (goto / fill / click / type / submit). The lead prompt no longer tells the model to use Playwright to skip that card.

## [0.10.1] - 2026-08-19

### Added
- The paired PC is an SSH-like session, not only a file read. After Allow once / Always / Deny the client can create or overwrite a file, list a folder, or run a shell command under the owner home.
- Tools: `write_owner_file`, `list_owner_dir`, `run_owner_command`. Loopback `/local/owner-write`, `/local/owner-list`, `/local/owner-exec`. `GET /v1/consents/{id}` and `POST /v1/consents/{id}/result`.

## [0.10.0] - 2026-08-19

### Added
- Consent cards in the thread: **Allow once / Always / Deny**. Opening a site, clicking, typing, or reading a file from the owner PC waits for an answer. Always is stored on the Pi for that bot, device, action, and scope.
- `read_owner_file` reads a file from the paired Linux PC through loopback `/local/owner-read`. The page never sees the host token. Paths must stay under the owner home. Max 1 MB. The file lands in that bot's `inbox/`.
- `POST /v1/consents/{id}` and `POST /v1/consents/{id}/file`. Scripted tests auto-allow unless `CONSENT_AUTO=ask`.

## [0.9.5] - 2026-08-19

### Changed
- Memory has three shelves written from chat: owner (name, city, tz, tone, format, language), work (repo, branch, project), and this bot's charter. No profile form.
- The next prompt always gets owner + this bot. Work is pulled only when the turn is about that work. Temporary work notes can expire (`until`).
- `tone` and `format` are separate slots. A subagent `remember` stays in this chat's charter. Thread meta `Remembered: …` also fires for ask and extract.

## [0.9.4] - 2026-08-19

### Changed
- Same-slot notes replace the old one (name, city, timezone, tone, language).
- Extract writes a short phrase, not the raw user line. One-off ask answers are not saved.
- Profile always includes name / city / timezone / tone when known. Empty chit-chat does not pull random recalled facts.
- Memory panel shows the card text. Outdated drops the note. Thread meta says `Remembered: …`.
- Bot-scoped notes are deleted with the bot instead of being promoted to shared.

### Fixed
- The loopback memory index no longer returns the first N rows on a miss, and it hides other chats' bot-scoped notes.

## [0.9.3] - 2026-08-18

### Added
- Shared memory: `remember` appends a short typed note the owner (default) so every bot can see it. Chat-local notes use `scope=bot`.
- Ask-card answers and an end-of-turn safety net write the same book. The lead prompt and `AGENTS.md` now tell the model to call `remember`.
- Turns receive a short profile plus recalled notes instead of dumping every memory file.
- Optional loopback memory index at `127.0.0.1:8420` (`python -m artek_buddy memory-gateway`). Postgres stays the panel source of truth.

## [0.9.2] - 2026-08-18

### Added
- Bot Settings can Restart (same home), Stop (sleep, keep files), or Reset (destroy the box and wipe `data/homes/{home_key}`). Team reset wipes the shared desktop for every Team bot.
- `computer.restart` and `computer.reset`.

### Clarified
- A Pi reboot or Stop does not wipe Chromium logins. Homes are bind-mounted on disk. Containers use `RestartPolicy: no` and come back on the next boot with the same home.
- README now says where to run tests (`make test` vs `make test-ui`), what they must not touch, and how to build/install the owner `.deb`.

## [0.9.1] - 2026-08-18

### Fixed
- The screen proxy waits for noVNC to accept connections and returns an HTML placeholder instead of `{"detail":"screen unreachable"}`. The preview detects that page and retries.
- Deleting or archiving the open chat clears the thread immediately. An in-flight refresh can no longer paint the deleted conversation over the empty state.
- Archived chats are listed under Archived and can be restored. Archiving the last chat no longer leaves a dead end.
- A computer marked running whose container is gone is provisioned again instead of leaving the preview on “Connecting desktop…”. The pane shows Retry when the screen URL is missing.

### Added
- Team vs Private is documented: Team bots share one container and home; Private creates `artek-bot-{bot_id}` and `data/homes/{bot_id}`. The create/edit form explains that.

## [0.9.0] - 2026-08-18

Open-source ready.

### Security
- `/novnc` HTTP and WebSocket require a Bearer token. The desktop proxy already sent one.
- The host token is no longer accepted as the supervisor bearer. When `SANDBOX_SUPERVISOR_TOKEN` is unset, both sides derive `sha256("supervisor:"+AGENT_HTTP_TOKEN)`.
- Computer containers join `artek-computers` with inter-container communication off and `no-new-privileges`.
- Chromium remote debugging inside the box binds `127.0.0.1`.
- Compose requires `MEMORY_DB_PASSWORD`. `/docs` and `/openapi.json` are off. `/health` no longer returns `agent_id`.
- The desktop proxy rejects cross-site browser requests and pairing URLs that are not loopback, RFC1918, Tailscale CGNAT, or `*.ts.net`.
- Access logs and `client.log` redact `/novnc` paths. `client.log` is mode `600`.

### Fixed
- Stopping a Cursor turn now calls `cancel` / `stop` / `abort` on the remote run when the SDK exposes it.
- An SSE client that reconnects past a discarded event id gets `thread.replay.gap` and refreshes the thread and screen.
- A worker crash after claiming a routine no longer loses the fire: the row is leased and acknowledged only after HTTP 200 or 409.
- A running desktop that cannot mint a screen URL returns 502 instead of an empty URL. The overlay shows Retry.

### Added
- Apache-2.0 `LICENSE`, `SECURITY.md`, and `CONTRIBUTING.md`.

### Upgrade
- Set `MEMORY_DB_PASSWORD` in `.env` before `docker compose up`. The old default `artek` is no longer implied.
- Recreate running `artek-bot-*` desktops so they join the isolated `artek-computers` network.

## [0.8.5] - 2026-08-18

### Fixed
- A slow thread fetch after switching bots can no longer paint the previous chat.
- Older-history pages from another thread are ignored.
- A bad pairing code stays “invalid or expired”, not “pair this computer again”.
- A dead local proxy no longer dumps a paired install onto the pairing screen.
- The empty-bot prompt waits until the bot list has actually loaded.
- A failed computer boot is not auto-retried in a loop, and idle-stop does not immediately wake the box again.
- Stop stays available while the bot is waiting for an answer or takeover.
- Failed and cancelled turns leave a durable error in the thread, not only a 4s toast.
- An idle worker no longer stops a shared team computer while another bot is still running.
- The desktop client no longer treats `AGENT_HTTP_TOKEN` as a device token.
- Host boot rejects placeholder tokens such as `change-me`.

## [0.8.4] - 2026-08-18

### Fixed
- Host restart no longer leaves bots stuck `running`. Leftover turns and workers are marked failed, then queued messages resume.
- Send, queue, and auth failures no longer show a "Retry connection" banner. Host outages, revoked devices, and action errors each get their own recovery action.
- A revoked device can forget its local token and return to the pairing screen.
- Pairing guesses from one address are rate-limited so a public host cannot be brute-forced cheaply.
- Failed subagent runs stay `failed` in the thread instead of looking completed.

### Added
- Playwright coverage for host disconnect, inbox overflow, and revoked-device pairing.

## [0.8.3] - 2026-08-18

### Fixed
- The noVNC proxy waits briefly for a newly started desktop port instead of serving a transient `screen unreachable` page in the first computer preview.
- Fresh hosts no longer create an `artek-buddy` bot automatically. The empty state guides the owner to create the first bot explicitly.

## [0.8.2] - 2026-08-18

### Fixed
- Answering an `ask_user` card marks that card answered and hides the options. Refreshing the thread no longer brings the buttons back.
- Switching bots clears the previous thread and desktop preview immediately, so the old chat cannot flash in the new one.

### Added
- Scripted UI host understands `e2e-*` prompts (hidden drafts, close browser, ask cards, slow turns, markdown preview, failure).
- Playwright regressions for streamed reasoning, `close_app`, computer iframe identity, in-window alerts, queue-while-busy, Stop, ask cards, and sidebar preview text.

## [0.8.1] - 2026-08-18

### Changed
- Bot colors and avatar mark are an original Artek palette (rounded badge + chevron), not the previous swatch.
- README / NOTICE attribute the adapted HTTP contract surface.
- README documents Tailscale as the daily path to the Pi; the free Personal plan is enough. Funnel stays optional.
- README states there is no GitHub `.deb`: you build a local owner package.
- `make test-ui` uses a throwaway scripted host and isolated client home. Playwright no longer sends into the live workspace.
- First `threads.send` on a scripted host starts a turn again (`begin_turn` was stuck inside the busy-queue branch).
- Live Cursor text/thinking drafts stay off the thread. The window shows the pulsing activity dots until `send_message` or the finished answer.
- `close_app` closes the on-screen browser (or another app) in one step. The lead no longer has to hunt for the window X.
- Computer preview keeps one noVNC connection. Sending a message does not remint the screen URL or remount the iframe.
- Attention stays in the window banner only. The `.deb` does not also fire `notify-send` for the same event.

### Added
- Desktop attention alerts when a bot replies, asks, fails, or requests takeover.
- Loopback `POST /local/notify` (`notify-send` + window urgency hint). The page still never sees the host token.
- Bot Settings toggle for `notifyOnFinish`. Questions and takeover always notify.

## [0.8.0] - 2026-08-18

### Added
- `AgentRuntime` protocol with `CursorRuntime` (product default) and `ScriptedRuntime` (tests / host-only debug).
- Shared product tool registry used by both runtimes. Cursor only wraps it as `CustomTool`.
- `AGENT_RUNTIME=cursor|scripted`. Scripted starts without a Cursor key or bridge.

### Changed
- Host turns and subagents consume product stream events. Cursor event mapping stays inside the Cursor adapter.
- Host errors are `AgentRuntimeError`, not `CursorAgentError`.
- Unit tests cover a full `_run_turn` on the scripted runtime (reply, `remember`, failure, inbox follow-up).
- Workflow E2E waits for a bot markdown answer instead of a loose "Belgrade" match that also hit the user bubble.

## [0.7.18] - 2026-08-18

### Added
- Interactive Grok-style `send_message` and `ask_user` tools with stacked option cards (A, B, C, D badges) and live reply stream cleanup.
- Fast `open_path` and `launch_app` tools in runtime and supervisor with automatic `artek-browser` / `xdg-open` routing in background with `nohup`.
- Python Playwright installed in sandbox container and backend with `--remote-debugging-port=9222` on Chromium for isolated `BrowserContext` automation and CDP connection.
- Markdown stripping (`strip_markdown` in Python, `stripMarkdown` in TypeScript) for clean plain-text rendering in sidebar bot previews, quote excerpts, search filters, and profile modals.

### Changed
- Suppressed raw internal reasoning/monologue streams in chat thread, replacing with a subtle pulsing activity indicator.
- Replaced eager desktop container booting on every user turn with lazy booting on demand.
- Updated Playwright E2E tests (`shell.spec.ts`, `workflow.spec.ts`) for robust UI navigation and fullscreen screen preview.

## [0.7.17] - 2026-08-18

### Changed
- Computer preview pane UI: clear status badge (`Running`, `Booting…`, `Offline`, `Error`), smooth hover overlay with `Open screen ↗` action, and connecting spinner while the display WebSocket handshakes.
- Fullscreen computer overlay verification in Playwright E2E suite.

## [0.7.16] - 2026-08-18

Full live worker execution observation and responsive subagent card layout.

- Extended E2E workflow test to wait for live subagents to complete and verify generated weather answers.
- Widened subagent card layout and fixed table header word wrapping in markdown cards.
- Network-idle wait added to pairing screen E2E test.

## [0.7.15] - 2026-08-18

Visual polish from Playwright screenshot review.

- Background computer autoboot no longer blocks UI with a full-screen overlay modal.
- Replaced plain "working…" placeholder with refined status indicator.
- Verified visual rendering of live thinking and subagent worker cards in E2E workflow screenshots.

## [0.7.14] - 2026-08-18

Clean thought process rendering, prompt guidance for parallel subagents, and full workflow E2E test.

- Thinking/reasoning stream renders in a distinct, compact box instead of a full assistant message bubble.
- Subagent cards display reasoning inside a collapsible element.
- Lead prompt and inbox drain instructions explicitly require spawning parallel subagents for independent tasks.
- Added Playwright workflow test for bot creation, single request, and 3 queued tasks with screenshots.

## [0.7.13] - 2026-08-18

Playwright drives the same loopback UI the `.deb` serves.

- `make test-ui` starts `artek_buddy.py --serve` and walks pairing, the thread, the computer pane, reply, and the composer.
- Screenshots stay local (`client/web/test-results/`). This is not part of `make test`.

## [0.7.12] - 2026-08-17

The thread no longer paints every Cursor tool call.

- `mcp` / `read` / `shell` and other raw tools stay off the chat. Desktop actions stay in the computer pane.
- The thread keeps answers, thinking, worker cards, and `remember` notes.

## [0.7.11] - 2026-08-17

The lead can correct a worker while it works.

- Tell the lead to refine worker 2. It calls `steer_subagent`. That worker keeps the same session and applies the note.
- Corrections are stored on the worker and shown on its card.

## [0.7.10] - 2026-08-17

One lead agent in the chat. Workers run the extra tasks.

- Send while the lead is busy stores the message and queues it. The lead handles the pile after it finishes. No second user-facing Cursor agent.
- The lead can `spawn_subagent`, `inspect_subagent`, `stop_subagent`, and `restart_subagent`. Ask about worker 2 and it reads that worker's reasoning and stage.
- Cards in the thread show index, thinking, and Stop / Restart. Composer Stop cancels the lead and the workers.
- Reply is unchanged.

## [0.7.9] - 2026-08-17

Send while a turn is running, and reply to a message.

- A second send starts another Cursor agent on the same thread. Up to four tasks at once. Stop cancels all of them.
- Right-click a message to reply. The next prompt includes that quote.

## [0.7.8] - 2026-08-17

Desktop tools reach the running box during a turn.

- `computer_observe` / `computer_act` used a ContextVar that the SDK callback thread cannot see, so they returned `computer is not available` while the pane was live.
- The host now keeps the current bot on the runtime and binds the Cursor agent to that bot.

## [0.7.7] - 2026-08-17

Fullscreen view does not take control.

- Click the thumbnail for the same overlay, view-only.
- Take control is only the button. Release keeps the overlay open.

## [0.7.6] - 2026-08-17

The `.deb` WebSocket proxy speaks HTTP/1.1, so noVNC can paint.

- Loopback `/novnc` upgrades were `HTTP/1.0 101`. WebKit and noVNC then sat on a black canvas.
- Failures still append to `~/.config/artek-buddy/client.log`.

## [0.7.5] - 2026-08-17

The computer pane shows the desktop instead of a black frame.

- x11vnc was stuck at ~100% CPU (Xinerama on Xvfb) and never sent the RFB greeting.
- View and control VNC now start with `-noxinerama -threads -noxdamage -noshm`.

## [0.7.4] - 2026-08-17

Release actually drops the control noVNC port.

- websockify's process name is `websockify`, not `python3`. Stop now matches that.

## [0.7.3] - 2026-08-17

Take control no longer kills its own start script.

- Control VNC is stopped by process name and `/proc` cmdline, not `pkill -f`.
- The previous pattern matched the supervisor `bash -lc` wrapper, so `:6081` never stayed up.

## [0.7.2] - 2026-08-17

Take control starts the control VNC.

- The supervisor no longer joins background jobs with `;` after `&` (`&;` is invalid bash).
- Control x11vnc/websockify now stay listening on `:5901`/`:6081` after Take control.

## [0.7.1] - 2026-08-17

Take control keeps a live screen.

- Control VNC is started with `setsid`/`nohup` so it survives `docker exec`.
- If that stack is not up, the signed URL stays on the view-only port instead of a dead `:6081`.

## [0.7.0] - 2026-08-17

Stage 7. Linux desktop on this Pi.

- Isolated computer image (`artek-buddy-computer:local`): Xvfb, fluxbox, Chromium, view-only VNC, noVNC.
- Supervisor on `:7091` owns the Docker socket. The API container no longer mounts it.
- Table `computers`. Live `computer.*` routes: boot, stop, takeover, release, heartbeat, screen, input, files.
- Signed `/novnc` capability URLs. Host and `.deb` proxy HTTP and WebSocket.
- Window: live 16:10 preview, Take control overlay, 60s heartbeat.
- Agent tools: `computer_observe`, `computer_act`, `request_takeover`. Cursor cwd is that bot's home.
- Worker sleeps a quiet box after about 10 minutes.

## [0.6.2] - 2026-08-17

Streaming fills one bubble instead of overwriting tokens.

- The host emits `thread.message.updated` / `thread.progress` as the full draft so far (`{text, kind}`), not a leftover `delta` on top of that text.
- A shorter assistant snapshot does not shrink a longer draft.
- The window keeps the live draft across a thread refresh while the run is still active. Thinking and tokens no longer wipe each other.

## [0.6.1] - 2026-08-17

Bot lifecycle, stop, and memory the agent can write itself.

- Live: `me`, `deployment.get` / `update`, `bots.get` / `update` / `duplicate` / `archive` / `restore` / `list_archived` / `set_computer`.
- `DELETE /v1/bots/{bot_id}` keeps that bot's documents as user memory unless `delete_memories=true`.
- Live: `threads.stop`, `threads.follow_up`, `threads.mark_read`, `threads.mark_unread`. Stop cancels the in-process turn and marks the run `cancelled`.
- Cursor turns register a `remember` custom tool. The host writes `memory_documents` (default path `MEMORY.md`) and injects those facts on the next prompt.
- SSE maps tool calls into thread blocks (`meta`, `subagent`, `child_bot`, `computer`). The window paints cards, ask prompts, and a Stop control.
- Right-click a bot: pin, mark read/unread, edit, duplicate, archive, delete.

## [0.6.0] - 2026-08-17

Stage 6. Memory is not the chat transcript.

- Tables `memory_documents` and `memory_revisions`. Scope is `bot` or `user`.
- Live: `memory.list` / `create` / `update` / `remove` / `export_markdown`.
- The next Cursor prompt gets those facts as background. The user message in `messages` stays the raw chat text.
- The computer pane lists, edits, exports, and deletes memory.

## [0.5.3] - 2026-08-17

A follow-up message in an existing chat works after the host restarts.

- Cursor `resume` now gets `AgentOptions`, which JSON-encodes. A raw `LocalAgentOptions` object in a dict was crashing the send path.
- If resume still fails, the host creates a new agent and remaps that chat. The TypeError is not written into the thread.

## [0.5.2] - 2026-08-17

Integration tests use a throwaway Postgres, not the live compose database.

- `make test-integration` starts `postgres:16-alpine` on loopback port 55432 and deletes the container after the run.
- `TEST_DATABASE_URL` pointing at `127.0.0.1:5432/artek_buddy` is refused.
- CI uses its own `artek_buddy_test` database.

## [0.5.1] - 2026-08-17

Chats can be deleted, and tests leave the database as they found it.

- `DELETE /v1/bots/{bot_id}` removes the bot, thread, messages, runs, and routines.
- The settings pane deletes a chat after a confirm step.
- Integration tests delete the bots, devices, and pairing rows they create.

## [0.5.0] - 2026-08-17

Stage 5. Worker and routines.

- Table `routines` (cron, prompt, bot). Five-field cron, timezone, next run.
- Live: `routines.list` / `create` / `update` / `remove` / `test_run`.
- Compose service `artek-buddy-worker` runs `python -m artek_buddy worker`. A due routine wakes the bot with the same `threads.send` path as the window.
- The computer pane lists, creates, pauses, runs, and deletes routines.

## [0.4.0] - 2026-08-17

Stage 4. Device tokens.

- `POST /v1/devices/pairing` (host token) mints a one-time pairing code.
- `POST /v1/devices` mints a per-device token. Gate is the host token or a pairing code. The token is shown once and stored as a hash.
- Host or device bearer works on live `/v1` routes. `/health` stays open.
- `python -m artek_buddy pair` prints only the code and expiry.
- An unpaired window shows a pairing screen. The page talks to loopback `/local/pair`; the device token is written to `~/.config/artek-buddy/token` and never reaches JavaScript.

## [0.3.3] - 2026-08-17

Tests are part of the product.

- `make test` runs host `unittest` and the desktop-shell Vitest suite.
- GitHub Actions runs the same on `main` and pull requests, plus history tests against Postgres.
- Client helpers have colocated tests (thread events, markdown, camelCase, window chrome).
- A change is not finished if tests were not written or they fail.

## [0.3.2] - 2026-08-17

The desktop window opens from the application menu.

- The window opens from the application menu. Failures go to `~/.config/artek-buddy/client.log`.
- WebKit setup no longer depends on the script-message API.
- After `dpkg -i`, install depends: `sudo apt-get install -f`.

## [0.3.1] - 2026-08-17

Desktop client is the product shell in a desktop window.

- The `.deb` ships the TypeScript UI and a loopback proxy. The page talks to `/v1` on localhost; the proxy attaches the bearer.
- Live surface only: bots, thread, send, SSE. Computer / plugins / routines stay as stubs until those host stages exist.
- Tokens and tools still paint live.

## [0.3.0] - 2026-08-17

Stage 3. Streaming.

- `GET /v1/threads/{bot_id}/events` streams product events.
- `threads.send` returns `{task_id, run_id, seq}` immediately.
- The host pipes Cursor run events (tokens, tools). It does not only wait for the end.
- The `.deb` paints the live turn.

## [0.2.3] - 2026-08-17

- Desktop client is the product shell: bot list, thread, computer pane.
- New bot, search, earlier messages, and a computer stub live in the `.deb`.

## [0.2.2] - 2026-08-17

- Local scan and other machine tooling stay on the host. They are not in git.
- Owner `.deb` is built with `client/build-deb.sh` (not stored in git).

## [0.2.1] - 2026-08-17

Hygiene after the 0.2.0 cutover. Stages 0–2 unchanged.

- Docs match the live wire. Stale client version notes are gone.
- Postgres is published on loopback only (`127.0.0.1:5432`).
- Reserved computer host is this machine (`host`), not a laptop. Sandbox kinds are `docker` / `desktop` / `fake`.

## [0.2.0] - 2026-08-17

Stages 0–2.

- Host on this Raspberry Pi: FastAPI, Cursor runtime, Tailscale Funnel.
- Shared contracts for bots, threads, messages, and runs.
- Postgres history. Send path: `POST /v1/threads/{bot_id}/messages`.
- Run status: `completed` / `failed` / `cancelled`.
- Desktop client source `artek-buddy`.
