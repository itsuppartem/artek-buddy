#!/bin/sh
# One-shot host bring-up from a GitHub Release. No secrets in the script.
# A second run on a clean checkout fetches and checks out v$VERSION.
# A dirty tree aborts. .env is gitignored and kept.
# A provider key is optional here: paste it in Models after pairing, or set
# CURSOR_API_KEY in .env to seed the same store.
set -eu

REPO="${ARTEK_REPO:-https://github.com/itsuppartem/artek-buddy.git}"
DEST="${ARTEK_HOME:-$HOME/artek-buddy}"
IMAGE_HOST="${ARTEK_HOST_IMAGE:-ghcr.io/itsuppartem/artek-buddy}"
IMAGE_COMPUTER="${ARTEK_COMPUTER_IMAGE:-ghcr.io/itsuppartem/artek-buddy-computer}"
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

need git
need openssl
VERSION=$(latest_version)
export ARTEK_VERSION="$VERSION"
TAG="v$VERSION"

prepare_dest() {
  if [ -d "$DEST/.git" ]; then
    if [ -n "$(git -C "$DEST" status --porcelain)" ]; then
      echo "$DEST has uncommitted changes. Clean the tree or set ARTEK_HOME to an empty directory. Not overwriting." >&2
      echo "Upgrade after a clean tree: ARTEK_VERSION=$VERSION ARTEK_HOME=$DEST sh infra/install-host.sh" >&2
      exit 1
    fi
    git -C "$DEST" fetch --depth 1 origin "refs/tags/$TAG:refs/tags/$TAG"
    git -C "$DEST" checkout --detach "$TAG"
    return
  fi
  if [ -e "$DEST" ] && [ -n "$(ls -A "$DEST" 2>/dev/null || true)" ]; then
    echo "$DEST exists and is not a git checkout. Move it or set ARTEK_HOME." >&2
    exit 1
  fi
  git clone --depth 1 --branch "$TAG" "$REPO" "$DEST"
}

prepare_dest
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
  echo "pair the window and add a key in Models, or set CURSOR_API_KEY in .env to seed Cursor."
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
