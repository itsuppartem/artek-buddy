# Vision and Invariants

Artek Buddy is a self-hosted personal AI agent host designed for one trusted Linux machine (PC, server, mini PC, or Raspberry Pi). It provides durable bots, isolated computer sandboxes, and honest owner consent before computer actions.

## Core Invariants

1. **One trusted host, durable bots, consent before computer use**
   - The host is one trusted, always-on Linux machine owned by one operator.
   - Bots are durable entities with persistent state and memory across turns.
   - Any sensitive action (modifying the host, navigating untrusted sites, executing scoped commands, takeover of the desktop) requires explicit human consent via interactive cards (Allow once / Always / Deny).

2. **Team vs Private Desktops**
   - **Team** (default): shared sandbox container (`artek-bot-team-{workspace}`) and shared home directory. Team bots take turns sharing the desktop.
   - **Private**: dedicated sandbox container (`artek-bot-{bot_id}`) and isolated home directory, dedicated to a single bot for privacy or parallel execution.
   - Both modes enforce memory, CPU, PID, and dropped capability bounds (`CapDrop`).

3. **Collaboration Direction**
   - Small invited group of trusted people collaborating on one host.
   - Explicit grants per resource (bots, threads, computers).
   - No public signup, no multi-tenant SaaS, no open registration.

4. **Non-Goals (What We Will Not Build)**
   - **Kubernetes / Orchestrators**: Artek Buddy runs via Docker Compose on a single machine. No Kubernetes, Helm charts, or multi-node schedulers.
   - **Redis / External Queue Daemons**: Persistence and queuing use PostgreSQL with `FOR UPDATE SKIP LOCKED` and in-process fan-out. No Redis, Celery, RabbitMQ, or Kafka.
   - **Multi-tenant SaaS**: Artek Buddy is personal self-hosted software. It is not an enterprise multi-tenant cloud service.
   - **Second live model provider marketplace**: One default live provider harness (Cursor SDK); no technology zoo or multi-vendor routing complexity.
   - **Funnel-as-safe**: Tailscale Funnel publishes the API for the owner; it does not turn the host into an unauthenticated public website. Mutual trust, pairing codes, and device tokens are the boundary.

## Related Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — System boundaries, data flow, services, and supervisor contract.
- [THREAT-MODEL.md](THREAT-MODEL.md) — Security boundaries, trust domains, assets, and residual risks.
- [CONTRIBUTING.md](CONTRIBUTING.md) — How to contribute, development workflow, and testing.
