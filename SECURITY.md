# Security policy

Artek Buddy is a self-hosted personal agent. Treat the Raspberry Pi host
as the trust boundary: anyone who can call `:8080` with a valid token can
drive bots, memory, routines, and desktop sandboxes.

## Report a vulnerability

Do **not** open a public GitHub issue for a security report.

Email the maintainer at the address on the GitHub profile for
[itsuppartem/artek-buddy](https://github.com/itsuppartem/artek-buddy),
or open a private GitHub security advisory on that repository.

Include:

- what you can do (read host env, reach another bot desktop, steal a device token, …)
- how you got there (client, Funnel, LAN, a computer container)
- product version (`VERSION`)

You should hear back within a week. Please give us time to ship a fix
before posting a write-up.

## What this project will not treat as a bug

- A local Cursor agent that can `printenv` inside the **host API container**.
  That process is trusted-equivalent to the host.
- Abuse of a stolen `AGENT_HTTP_TOKEN` or a paired device token.
- Model output that is wrong, or a bot that follows a malicious prompt
  you gave it on a desktop you control.

## Hardening you must do

1. Generate `AGENT_HTTP_TOKEN` and `MEMORY_DB_PASSWORD`. Do not ship the
   example placeholders.
2. Keep the host on a Tailscale tailnet. Do not port-forward `:8080` to the
   public internet.
3. Do not enable Tailscale Funnel until you have read the Funnel warning
   in the README. `/novnc` now requires a Bearer token, but Funnel still
   publishes the whole API.
4. Rebuild `artek-buddy-computer:local` after you pull a computer-image
   change, then recreate running desktops so they join `artek-computers`.
