# 7. Bind, Tailscale, and Funnel

## Status

Accepted.

## Context

The owner reaches `:8080` from a Linux PC on another network. Binding only
to a tailnet address would be stricter. Binding to `0.0.0.0` with
`network_mode: host` is what the stack does today.

## Decision

Keep `HTTP_HOST=0.0.0.0`. Daily access is **policy**: Tailscale MagicDNS /
tailnet IP. Do not port-forward `:8080`. Funnel is optional and publishes
the **whole** API, not a pairing portal. `/novnc` requires a Bearer; every
other route on that hostname does too.

Supervisor, Postgres, memory gateway, and desktop noVNC stay on loopback
(or `127.0.0.1` publishes). OpenAPI stays off at runtime.

The written bind story and residual LAN/Funnel risk live in
[THREAT-MODEL.md](../THREAT-MODEL.md). This ADR does not change the listen
address.

## Consequences

A LAN neighbor or a leaked Funnel hostname sees the same FastAPI as the
owner. Pairing and device tokens are the credential. Stronger binds
(tailnet-only, Serve instead of Funnel) are a later product choice.
