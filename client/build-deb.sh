#!/bin/sh
# Build a local owner .deb. Do not commit the resulting file.
# Official / CI packages never bake a host URL. Set ARTEK_BAKE_URL=1 to copy
# untracked client/url into the package (never a token).
set -eu
cd "$(git rev-parse --show-toplevel)"

VERSION=$(tr -d '[:space:]' < VERSION)
BUILD_SUFFIX=${ARTEK_BUILD_SUFFIX:-}
case "$BUILD_SUFFIX" in
  "") ;;
  *[!A-Za-z0-9.+~]*)
    echo "ARTEK_BUILD_SUFFIX may contain only letters, digits, dot, plus, and tilde" >&2
    exit 1
    ;;
  *) VERSION="${VERSION}+${BUILD_SUFFIX}" ;;
esac
NAME=artek-buddy-client
PKG="${NAME}_${VERSION}_all"
OUT="${PKG}.deb"
if [ -e "$OUT" ]; then
  echo "$OUT already exists; refusing to overwrite it" >&2
  exit 1
fi
ROOT=$(mktemp -d)
trap 'rm -rf "$ROOT"' EXIT

if [ -x "$HOME/.local/node/bin/npm" ]; then
  export PATH="$HOME/.local/node/bin:$PATH"
fi
if command -v npm >/dev/null 2>&1; then
  (cd client/web && npm ci && npm run build)
fi
if [ ! -f client/web/dist/index.html ]; then
  echo "client/web/dist is missing; install Node and rebuild" >&2
  exit 1
fi

LIB="$ROOT/usr/lib/artek-buddy-client"
BIN="$ROOT/usr/bin"
APP="$ROOT/usr/share/applications"
DOC="$ROOT/usr/share/doc/$NAME"
ICONS="$ROOT/usr/share/icons/hicolor"
PIXMAPS="$ROOT/usr/share/pixmaps"
DEBIAN="$ROOT/DEBIAN"

mkdir -p "$LIB/web" "$LIB/ssh-wrap" "$BIN" "$APP" "$DOC" "$PIXMAPS" "$DEBIAN"

cp client/artek_buddy.py client/owner_paths.py client/window_chrome.py \
  client/pairing.py client/proxy.py client/proxy_common.py client/proxy_rpc.py \
  client/proxy_static.py client/proxy_upstream.py client/notifications.py \
  client/window.py client/clipboard_image.py client/web_paths.py \
  client/ssh_mux.py client/tray.py "$LIB/"
cp client/ssh-wrap/ssh "$LIB/ssh-wrap/ssh"
cp client/VERSION "$LIB/VERSION"
cp client/assets/app-icon.png "$LIB/app-icon.png"
cp -R client/web/dist/. "$LIB/web/"
for sz in 16 24 32 48 64 128 256 512; do
  mkdir -p "$ICONS/${sz}x${sz}/apps"
  cp "client/assets/hicolor/${sz}x${sz}/apps/artek-buddy.png" \
    "$ICONS/${sz}x${sz}/apps/artek-buddy.png"
done
cp client/assets/hicolor/256x256/apps/artek-buddy.png "$PIXMAPS/artek-buddy.png"
if [ "${ARTEK_BAKE_URL:-}" = "1" ] && [ -f client/url ]; then
  cp client/url "$LIB/url"
  chmod 644 "$LIB/url"
fi
chmod 755 "$LIB/artek_buddy.py"
chmod 644 "$LIB/owner_paths.py" "$LIB/window_chrome.py" \
  "$LIB/pairing.py" "$LIB/proxy.py" "$LIB/proxy_common.py" "$LIB/proxy_rpc.py" \
  "$LIB/proxy_static.py" "$LIB/proxy_upstream.py" "$LIB/notifications.py" \
  "$LIB/window.py" "$LIB/clipboard_image.py" "$LIB/web_paths.py" \
  "$LIB/ssh_mux.py" "$LIB/tray.py"
chmod 755 "$LIB/ssh-wrap/ssh"
chmod 644 "$LIB/app-icon.png"
chmod -R a+rX "$LIB/web"

cat > "$BIN/artek-buddy" <<'EOF'
#!/usr/bin/env python3
import runpy
import sys

sys.argv[0] = "artek-buddy"
runpy.run_path("/usr/lib/artek-buddy-client/artek_buddy.py", run_name="__main__")
EOF
chmod 755 "$BIN/artek-buddy"

cat > "$APP/artek-buddy.desktop" <<'EOF'
[Desktop Entry]
Name=Artek Buddy
Comment=Desktop client for the Artek Buddy host
Exec=/usr/bin/artek-buddy
TryExec=/usr/bin/artek-buddy
Icon=artek-buddy
Terminal=false
Type=Application
StartupNotify=true
StartupWMClass=Artek Buddy
X-GNOME-UsesNotifications=true
Categories=Network;Utility;
EOF

cat > "$DOC/copyright" <<'EOF'
Artek Buddy client. Local owner package.
EOF

cat > "$DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q /usr/share/applications >/dev/null 2>&1 || true
fi
EOF
chmod 755 "$DEBIAN/postinst"

cat > "$DEBIAN/control" <<EOF
Package: $NAME
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Depends: python3, python3-gi, gir1.2-gtk-3.0, gir1.2-webkit2-4.1 | gir1.2-webkit2-4.0, gir1.2-ayatanaappindicator3-0.1 | gir1.2-appindicator3-0.1, gir1.2-notify-0.7, xdg-utils, libnotify-bin
Maintainer: Artek Buddy <artek-buddy@local>
Description: Desktop client for the Artek Buddy host
 Desktop shell for the host HTTP API.
EOF

if [ -z "${SOURCE_DATE_EPOCH:-}" ]; then
  SOURCE_DATE_EPOCH=$(git log -1 --format=%ct)
  export SOURCE_DATE_EPOCH
fi
dpkg-deb --build --root-owner-group "$ROOT" "$OUT"
echo "built $OUT"
