# 1. Supervisor owns `docker.sock`

## Status

Accepted.

## Context

Bot desktops are Docker containers on the Pi. Someone has to talk to the
engine. Putting `docker.sock` on the host API container would make every
FastAPI bug root-equivalent to Docker.

## Decision

Only the **supervisor** compose service mounts `/var/run/docker.sock`. It
listens on `127.0.0.1:7091` with a bearer derived from the host token (or
`SANDBOX_SUPERVISOR_TOKEN`). The API creates/execs/removes boxes over that
loopback HTTP API. Desktop containers do not get the socket.

## Consequences

A supervisor bug is still Pi-root. That is the product shape, not an
oversight. The host API and the window never hold Docker credentials.
See [THREAT-MODEL.md](../THREAT-MODEL.md).
