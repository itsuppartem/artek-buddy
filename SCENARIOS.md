# First-user scenario

One named job on the **shipped Cursor** runtime. HTTP without Cursor is Phase 2 ([#563](https://github.com/itsuppartem/artek-buddy/issues/563)) — the same recipe, later.

This is not a catalog of templates. Guests run it on **their own** Linux host with **their own** Cursor key. Do not pair a tester onto someone else's production host.

## Saved research brief

Write a one-page markdown brief from **one public page**, save it, and leave a Downloadable file in the thread. Sources are real links. Unknowns are listed instead of invented.

### Input

Copy this into a bot that already has a Cursor key (Library → Models). Dedicated **Private** desktop is fine.

```text
Using only https://docs.python.org/3/whatsnew/3.13.html write a one-page markdown brief:

What should a FastAPI service notice when moving from Python 3.12 to 3.13?

Required sections:
- Answer
- Sources (real links from that page only)
- Unknowns (do not invent)

Save the file so I can Download it. Stay on the bot desktop. Do not log into anything, send mail, pay, or write on this PC.
```

On a scripted host send `please e2e-scenario-research` instead, then Allow (or Deny to see the failure path).

### Access it needs

| Need | Why |
|---|---|
| Cursor key + a default model | Shipped agent runtime |
| Allow once / Always for `https://docs.python.org` on the **bot desktop** | The page is opened there, not in the owner's browser |
| Allow to write the brief in that bot's workspace | The Download card is a host artifact |
| Pairing on this host | Device token |

Not required: This-PC jail, Funnel, GitHub Connect, a second model provider.

### Done looks like

- A consent card named the origin **before** the page opened
- After Allow: one markdown file card in this chat
- Download opens the system Save dialog (Deb) or the browser download (host page)
- The file has **Answer**, **Sources**, and **Unknowns**
- Sources are links that appear on that Python page, not a generic search dump
- Today still shows this bot; you can open the same file from the thread after you have read it

Then, without being prompted, send a second assignment (example: “Add one Unknown if the page does not mention uvloop and save again”). A second usable file without the author standing there is the real pass.

### Must not

- Payments, shopping checkouts, mass mail
- Logging into the owner's accounts
- Irreversible writes on This PC
- Publishing the bot desktop to the public internet
- Treating a one-shot HTTP Models row as this recipe (that path has no tools until #563)

### Failure signs

| What you see | Meaning |
|---|---|
| Models / “paste a key” instead of a turn | No Cursor default |
| Deny → no file card, run ends | Correct; the page was not used |
| Site challenge / login wall | Take control or Deny; do not invent the brief |
| File with no Sources, or Sources that are not on that page | Failed recipe, even if the prose looks confident |
| Writes under `$HOME` on the Linux PC | Wrong place; this recipe stays on the bot desktop |

### Phase 2 (HTTP)

Same assignment after [#563](https://github.com/itsuppartem/artek-buddy/issues/563). Do not mark this page as “HTTP works” from a one-shot Models completion.

## First guests

Small voluntary group. Each person uses their own host and Cursor quota. Record only where the author had to intervene (setup, consent wording, missing Download). Do not collect chats or keys. Outcome: keep this recipe, change the page, or drop it.
