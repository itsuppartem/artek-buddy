# Project frozen

**Artek Buddy is frozen indefinitely.** There is no planned date to resume active development.

## What that means

- The repository stays **public** and the last releases remain on [GitHub Releases](https://github.com/itsuppartem/artek-buddy/releases).
- Documentation describes the code as it was when development stopped; it may drift from your checkout if you fork or cherry-pick.
- **Issues and pull requests** may be left open or closed without review. Do not expect merges, roadmap updates, or support SLAs.
- **Security reports** are still welcome per [SECURITY.md](SECURITY.md). Critical fixes are not guaranteed while the project is frozen.

## Why

The shipped MVP proved the host, client, sandboxes, consent, and pairing model. Most live agent behavior still depended on the **Cursor API** as the runtime. The author is pausing this repo to pursue a stack with **full control of the under-the-hood agent loop**, without duplicating what Cursor already covers for remote development.

## If you want to use or fork it

You may install, fork, and modify under [Apache-2.0](LICENSE). You are responsible for your own host, keys, Tailscale exposure, and Docker security. See [THREAT-MODEL.md](THREAT-MODEL.md) and [OPERATIONS.md](OPERATIONS.md).
