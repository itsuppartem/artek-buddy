# 6. Consent is capability cards, not a root toggle

## Status

Accepted.

## Context

The agent can browse, click, type, read the owner home, write files, and
run commands. A single “give the bot root” switch is the wrong grain: the
owner needs to allow a site without allowing `rm` on the laptop.

## Decision

Consent is per class: `browse`, `desktop_input`, `page_input`, `owner_read`,
`owner_write`, `owner_exec`. The thread shows **Allow once / Always / Deny**.
Always is scoped to that bot, the answering device, and class (owner
write/exec cover later writes and commands on that PC from that Deb).
A grant with no device (host token) is host-wide for that bot and class.
Read-only owner shell (`ls`, `cat`, …) does not ask. Auto owner-read of
files still happens without a card.

Desktop tools wait on the card before the supervisor exec. The host token
never appears in the page.

## Consequences

Injection can still *request* tools; the card is the brake, not a prompt
parser. There is no blanket sandbox-off control in the window.
