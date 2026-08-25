#!/bin/sh
# Print compose/client logs with tokens stripped. Public repo: never dump raw logs.
set -eu
# Do not enable xtrace. It would print env substitutions.
redact() {
  sed -E \
    -e 's/crsr_[A-Za-z0-9_-]+/[redacted]/g' \
    -e 's/Bearer [A-Za-z0-9._~+/-]+/Bearer [redacted]/g' \
    -e 's/dev_[A-Za-z0-9_-]+/[redacted]/g' \
    -e 's/AGENT_HTTP_TOKEN=[^[:space:]]+/AGENT_HTTP_TOKEN=[redacted]/g' \
    -e 's/CURSOR_API_KEY=[^[:space:]]+/CURSOR_API_KEY=[redacted]/g' \
    -e 's/COMPOSIO_API_KEY=[^[:space:]]+/COMPOSIO_API_KEY=[redacted]/g' \
    -e 's/MEMORY_DB_PASSWORD=[^[:space:]]+/MEMORY_DB_PASSWORD=[redacted]/g' \
    -e 's/DATABASE_URL=postgresql:[^[:space:]]+/DATABASE_URL=[redacted]/g' \
    -e 's/[A-Z0-9]{4}-[A-Z0-9]{4}/XXXX-XXXX/g'
}

if [ "${1:-}" = "compose" ]; then
  docker compose -f docker-compose.ci.yml logs --no-color --tail=200 2>&1 | redact || true
  exit 0
fi
cat | redact
