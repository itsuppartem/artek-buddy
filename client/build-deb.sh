#!/bin/sh
# Build a local owner .deb. Do not commit the resulting file.
# Official / CI packages never bake a host URL. Set ARTEK_BAKE_URL=1 to copy
# untracked client/url into the package (never a token).
set -eu
cd "$(git rev-parse --show-toplevel)"

VERSION=$(tr -d '[:space:]' < VERSION)
NAME=artek-buddy-client
PKG="${NAME}_${VERSION}_all"
ROOT=$(mktemp -d)
trap 'rm -rf "$ROOT"' EXIT

if [ -x "$HOME/.local/node/bin/npm" ]; then
  export PATH="$HOME/.local/node/bin:$PATH"
fi
if command -v npm >/dev/null 2>&1; then
  (cd client/web && npm install && npm run build)
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

mkdir -p "$LIB/web" "$BIN" "$APP" "$DOC" "$PIXMAPS" "$DEBIAN"

cp client/artek_buddy.py client/owner_paths.py client/window_chrome.py \
  client/pairing.py client/proxy.py client/notifications.py client/window.py "$LIB/"
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
  "$LIB/pairing.py" "$LIB/proxy.py" "$LIB/notifications.py" "$LIB/window.py"
chmod 644 "$LIB/app-icon.png"
chmod -R a+rX "$LIB/web"

cat > "$BIN/artek-buddy" <<'EOF'
#!/usr/bin/env python3
import runpy
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
EOF
chmod 755 "$DEBIAN/postinst"

cat > "$DEBIAN/control" <<EOF
Package: $NAME
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Depends: python3, python3-gi, gir1.2-gtk-3.0, gir1.2-webkit2-4.1 | gir1.2-webkit2-4.0, xdg-utils, libnotify-bin
Maintainer: Artek Buddy <artek-buddy@local>
Description: Desktop client for the Artek Buddy host
 Desktop shell for the host HTTP API.
EOF

dpkg-deb --build --root-owner-group "$ROOT" "${PKG}.deb"
echo "built ${PKG}.deb"
