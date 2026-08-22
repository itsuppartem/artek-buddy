# 3. Scripted `AgentRuntime` vs Cursor Cloud

## Status

Accepted.

## Context

`quality` / `backend` / `ui` must be deterministic and must not spend Cursor
quota. The live product needs a real model.

## Decision

`AgentRuntime` is a protocol. `AGENT_RUNTIME=scripted` (`ScriptedRuntime`)
replays named prompts (`e2e-fail`, `e2e-consent-browse`, …) for CI.
`AGENT_RUNTIME=cursor` (`CursorRuntime` + `cursor-sdk`) is the only live
model path. Unknown runtimes fail closed. Cursor boot requires
`CURSOR_API_KEY`.

The `live` job is gated on that secret. `ui` does not receive it.

## Consequences

There is no second model vendor and no offline weights on the Pi. Prompts
leave the machine. CI that needs a model is opt-in, not a PR blocker for
forks without the secret.
