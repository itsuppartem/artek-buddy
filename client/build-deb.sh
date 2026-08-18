#!/bin/sh
# Build a local owner .deb. May bake untracked client/url (never the host token).
# Do not commit the resulting file.
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
DEBIAN="$ROOT/DEBIAN"

mkdir -p "$LIB/web" "$BIN" "$APP" "$DOC" "$DEBIAN"

cp client/artek_buddy.py "$LIB/artek_buddy.py"
cp client/VERSION "$LIB/VERSION"
cp -R client/web/dist/. "$LIB/web/"
if [ -f client/url ]; then
  cp client/url "$LIB/url"
  chmod 644 "$LIB/url"
fi
chmod 755 "$LIB/artek_buddy.py"
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
Icon=utilities-terminal
Terminal=false
Type=Application
StartupNotify=true
StartupWMClass=Artek Buddy
Categories=Network;Utility;
EOF

cat > "$DOC/copyright" <<'EOF'
Artek Buddy client. Local owner package.
EOF

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
