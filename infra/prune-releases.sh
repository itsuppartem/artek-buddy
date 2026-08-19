#!/bin/sh
# Keep the newest GitHub Releases. Older ones (and their tags) go away.
# Usage: prune-releases.sh [keep]
set -eu

KEEP="${1:-${ARTEK_RELEASE_KEEP:-5}}"
OWNER="${ARTEK_GH_OWNER:-itsuppartem}"
REPO="${ARTEK_GH_REPO:-artek-buddy}"

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "need $1" >&2
    exit 1
  }
}

need gh
need jq

json=$(gh release list --repo "$OWNER/$REPO" --limit 100 --json tagName,createdAt,isDraft)

echo "$json" | jq -r --argjson keep "$KEEP" '
  [.[] | select(.isDraft | not)]
  | sort_by(.createdAt)
  | reverse
  | .[$keep:][]
  | .tagName
' | while IFS= read -r tag; do
  [ -n "$tag" ] || continue
  echo "deleting GitHub Release $tag"
  gh release delete "$tag" --repo "$OWNER/$REPO" --yes --cleanup-tag
done

kept=$(echo "$json" | jq -r --argjson keep "$KEEP" '
  [.[] | select(.isDraft | not)]
  | sort_by(.createdAt)
  | reverse
  | .[0:$keep][]
  | .tagName
  | sub("^v";"")
')

prune_pkg() {
  pkg="$1"
  versions=$(gh api --paginate "/users/$OWNER/packages/container/$pkg/versions" 2>/dev/null || true)
  [ -n "$versions" ] && [ "$versions" != "[]" ] || return 0
  echo "$versions" | jq -r --arg kept "$kept" '
    ($kept | split("\n") | map(select(length > 0))) as $keep
    | .[]
    | . as $v
    | ($v.metadata.container.tags // []) as $tags
    | select(($tags | index("latest")) | not)
    | select(($tags | any(. as $t | $keep | index($t))) | not)
    | "\($v.id) \($tags | join(","))"
  ' | while IFS= read -r row; do
    [ -n "$row" ] || continue
    id=${row%% *}
    echo "deleting ghcr.io/$OWNER/$pkg version $row"
    gh api --method DELETE "/users/$OWNER/packages/container/$pkg/versions/$id" >/dev/null
  done
}

prune_pkg artek-buddy || true
prune_pkg artek-buddy-computer || true
