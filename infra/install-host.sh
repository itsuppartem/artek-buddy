#!/bin/sh
# One-shot host bring-up from a GitHub Release. No secrets in the script.
# Fill CURSOR_API_KEY in .env yourself, then run again.
set -eu

REPO="${ARTEK_REPO:-https://github.com/itsuppartem/artek-buddy.git}"
DEST="${ARTEK_HOME:-$HOME/artek-buddy}"
IMAGE_HOST="${ARTEK_HOST_IMAGE:-ghcr.io/itsuppartem/artek-buddy}"
IMAGE_COMPUTER="${ARTEK_COMPUTER_IMAGE:-ghcr.io/itsuppartem/artek-buddy-computer}"
PLACEHOLDER="crsr_your_key_here"

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "install $1 first (docker, git, curl, openssl)" >&2
    exit 1
  }
}

latest_version() {
  if [ -n "${ARTEK_VERSION:-}" ]; then
    echo "$ARTEK_VERSION"
    return
  fi
  need curl
  tag=$(curl -fsSL "https://api.github.com/repos/itsuppartem/artek-buddy/releases/latest" |
    sed -n 's/.*"tag_name": *"v\{0,1\}\([^"]*\)".*/\1/p' | head -n 1)
  if [ -z "$tag" ]; then
    echo "could not read the latest GitHub Release" >&2
    exit 1
  fi
  echo "$tag"
}

key_is_placeholder() {
  key=$(sed -n 's/^CURSOR_API_KEY=//p' "$1" | tr -d '[:space:]')
  [ -z "$key" ] || [ "$key" = "$PLACEHOLDER" ]
}

need git
need openssl
VERSION=$(latest_version)
export ARTEK_VERSION="$VERSION"

if [ ! -f "$DEST/.env.example" ]; then
  git clone --depth 1 --branch "v$VERSION" "$REPO" "$DEST"
fi

cd "$DEST"

if [ ! -f .env ]; then
  cp .env.example .env
  token=$(openssl rand -hex 24)
  password=$(openssl rand -hex 16)
  tmp=$(mktemp)
  sed -e "s/^AGENT_HTTP_TOKEN=$/AGENT_HTTP_TOKEN=$token/" \
    -e "s/^MEMORY_DB_PASSWORD=$/MEMORY_DB_PASSWORD=$password/" .env >"$tmp"
  mv "$tmp" .env
  if ! grep -q '^ARTEK_VERSION=' .env; then
    echo "ARTEK_VERSION=$VERSION" >>.env
  fi
  echo "COMPUTER_IMAGE=$IMAGE_COMPUTER:$VERSION" >>.env
  echo "wrote $DEST/.env (tokens generated)."
  echo "open that file, set CURSOR_API_KEY=crsr_… from Cursor Dashboard, run this script again."
  exit 2
fi

if key_is_placeholder .env; then
  echo "$DEST/.env still has the placeholder CURSOR_API_KEY. Paste your crsr_ key and re-run." >&2
  exit 2
fi

if [ "${ARTEK_INSTALL_SKIP_STACK:-}" = "1" ]; then
  echo "ARTEK_INSTALL_SKIP_STACK=1, not starting docker"
  exit 0
fi

need docker
if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose plugin is required" >&2
  exit 1
fi

export COMPUTER_IMAGE="${COMPUTER_IMAGE:-$IMAGE_COMPUTER:$VERSION}"
if ! docker pull "$IMAGE_HOST:$VERSION"; then
  echo "could not pull $IMAGE_HOST:$VERSION — after the first release, make the GHCR package public" >&2
  exit 1
fi
if docker pull "$COMPUTER_IMAGE"; then
  :
else
  echo "computer image missing on GHCR; building it on this Pi"
  docker compose --profile build build computer
  export COMPUTER_IMAGE=artek-buddy-computer:local
fi

docker compose -f docker-compose.release.yml pull
docker compose -f docker-compose.release.yml up -d
curl -fsS http://127.0.0.1:8080/health
echo
echo "host is up. pairing code:"
echo "  docker exec artek-buddy python -m artek_buddy pair"
