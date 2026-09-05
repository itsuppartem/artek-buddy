# Security policy

Artek Buddy is a self-hosted personal agent. Treat the Raspberry Pi host
as the trust boundary: anyone who can call `:8080` with a valid token can
drive bots, memory, routines, and desktop sandboxes. The written model is
[THREAT-MODEL.md](THREAT-MODEL.md).

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
- Abuse of an already-compromised `AGENT_HTTP_TOKEN` or paired device token: an attacker who already holds a valid token using the documented API (bots, memory, sandboxes) is an operator credential compromise, not a product vulnerability. In contrast, any defect where the product itself discloses a token (in logs, traces, GitHub Actions output, client files, or documentation mistakes) is firmly in scope. See [THREAT-MODEL.md](THREAT-MODEL.md).
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
4. GitHub Actions may hold `CURSOR_API_KEY` as a repository secret for the
   live canary job. The `ui` job does not receive it. That value is not
   written to logs or artifacts. Rotate it if a workflow file is ever
   changed to print env or upload traces.
5. Rebuild `artek-buddy-computer:local` after you pull a computer-image
   change. The next desktop start recreates any box that is missing
   CapDrop / memory / CPU / pids limits.

## What CI scans

Dependabot (pip, `client/web` npm, GitHub Actions, Docker bases), Dependabot
alerts and security updates, secret scanning with push protection, CodeQL
(Python and JavaScript), `pip-audit` and `npm audit --audit-level=high` on
`test.yml`, Trivy filesystem on `test.yml` (`scan` job), Trivy image on
`release.yml` after the host image is pushed (CRITICAL, ignore unfixed).
Known exceptions live in `.github/pip-audit-ignore.txt` and `.trivyignore`.
Third-party Actions are pinned by commit SHA.
