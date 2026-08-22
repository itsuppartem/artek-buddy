# 4. Compose on one Pi, not Kubernetes

## Status

Accepted.

## Context

The host is one always-on Raspberry Pi. Orchestrators buy multi-node
scheduling, rolling deploys, and service meshes this product does not have.

## Decision

Ship `docker-compose.yml` (plus `docker-compose.ci.yml` /
`docker-compose.release.yml`). Host network mode, named volumes, and a
build-only `computer` profile. Release publishes a multi-arch GHCR **host**
image; the computer image is built on the Pi (and in `live` on amd64).

## Consequences

Ops is `compose up` and `.env`. No Helm, no Redis, no extra control plane.
If we ever run more than one Pi, that is a new ADR — not a silent kube
manifest.
