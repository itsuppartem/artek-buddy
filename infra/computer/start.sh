#!/usr/bin/env bash
set -uo pipefail
export DISPLAY="${DISPLAY:-:1}"
export HOME="${HOME:-/home/artek}"
AGENT_HOME="$HOME"
mkdir -p "$AGENT_HOME" "$AGENT_HOME/.local/bin" "$AGENT_HOME/.config" /tmp/artek /tmp/.X11-unix /tmp/fluxbox-home
# Leftover homes may still have pcmanfm volume watching, which pops a window on every mount.
mkdir -p "$AGENT_HOME/.config/pcmanfm/default"
conf="$AGENT_HOME/.config/pcmanfm/default/pcmanfm.conf"
if [ -f "$conf" ]; then
  sed -i 's/^autorun=.*/autorun=0/;s/^mount_on_startup=.*/mount_on_startup=0/;s/^mount_removable=.*/mount_removable=0/' "$conf"
  grep -q '^mount_removable=' "$conf" || printf '\n%s\n' 'mount_removable=0' >> "$conf"
else
  printf '%s\n' '[volume]' 'mount_on_startup=0' 'autorun=0' 'mount_removable=0' > "$conf"
fi
rm -f "$AGENT_HOME/.config/autostart/pcmanfm.desktop" \
  "$AGENT_HOME/.config/autostart/pcmanfm-desktop.desktop"
pkill -x pcmanfm >/dev/null 2>&1 || true
if [ -f "$AGENT_HOME/.config/mimeapps.list" ]; then
  sed -i 's/pcmanfm\.desktop/thunar.desktop/g' "$AGENT_HOME/.config/mimeapps.list"
fi
# Guest Files is Thunar without volume watching or a desktop daemon.
mkdir -p "$AGENT_HOME/.config/xfce4/xfconf/xfce-perchannel-xml"
printf '%s\n' \
  '<?xml version="1.0" encoding="UTF-8"?>' \
  '<channel name="thunar" version="1.0">' \
  '  <property name="misc-volume-management" type="bool" value="false"/>' \
  '</channel>' > "$AGENT_HOME/.config/xfce4/xfconf/xfce-perchannel-xml/thunar.xml"
printf '%s\n' \
  '<?xml version="1.0" encoding="UTF-8"?>' \
  '<channel name="thunar-volman" version="1.0">' \
  '  <property name="automount-drives" type="bool" value="false"/>' \
  '  <property name="automount-media" type="bool" value="false"/>' \
  '  <property name="autobrowse" type="bool" value="false"/>' \
  '  <property name="autoopen" type="bool" value="false"/>' \
  '</channel>' > "$AGENT_HOME/.config/xfce4/xfconf/xfce-perchannel-xml/thunar-volman.xml"
export PATH="$AGENT_HOME/.local/bin:/usr/local/bin:$PATH"
export NPM_CONFIG_PREFIX="$AGENT_HOME/.local"
export PIP_USER=1
cd "$AGENT_HOME"

rm -f /tmp/.X1-lock /tmp/.X11-unix/X1

Xvfb :1 -screen 0 1280x800x24 -ac +extension RANDR +render -noreset >/tmp/artek/xvfb.log 2>&1 &
XVFB_PID=$!

ready=0
for _ in $(seq 1 100); do
  if xdpyinfo -display :1 >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 0.1
done
if [[ "$ready" -ne 1 ]]; then
  echo "Xvfb failed to start" >&2
  cat /tmp/artek/xvfb.log >&2 || true
  exit 1
fi

if command -v dbus-launch >/dev/null 2>&1; then
  eval "$(dbus-launch --sh-syntax)"
fi

xsetroot -solid "#111113" >/dev/null 2>&1 || true
mkdir -p /tmp/fluxbox-home/.fluxbox
cp /etc/artek/fluxbox/init /tmp/fluxbox-home/.fluxbox/init
cp /etc/artek/fluxbox/apps /tmp/fluxbox-home/.fluxbox/apps 2>/dev/null || true
cp /etc/artek/fluxbox/menu /tmp/fluxbox-home/.fluxbox/menu 2>/dev/null || true
# /tmp is tmpfs noexec. Do not exec a generated script from there.
HOME=/tmp/fluxbox-home fluxbox -rc /tmp/fluxbox-home/.fluxbox/init >/tmp/artek/fluxbox.log 2>&1 &

HOME="$AGENT_HOME" artek-browser >/tmp/artek/browser.log 2>&1 &
browser_up=0
for _ in $(seq 1 40); do
  if xdotool search --onlyvisible --class chromium >/dev/null 2>&1; then
    browser_up=1
    break
  fi
  if xdotool search --onlyvisible --class Chromium >/dev/null 2>&1; then
    browser_up=1
    break
  fi
  sleep 0.25
done
if [[ "$browser_up" -ne 1 ]]; then
  echo "browser failed to start" >&2
  cat /tmp/artek/browser.log >&2 || true
  if [[ ! -f /tmp/artek/xterm.fallback ]]; then
    mkdir -p /tmp/artek
    touch /tmp/artek/xterm.fallback
    xterm -geometry 100x28+48+48 -bg "#111113" -fg "#E8E8EA" -cr "#E8E8EA" -title "Terminal" >/tmp/artek/xterm.log 2>&1 &
  fi
fi

# Poll fast enough for pointer/key feedback; briefly coalesce repaint bursts.
x11vnc -display :1 -forever -shared -viewonly -nopw -listen 127.0.0.1 -rfbport 5900 -xkb -ncache 0 -noxdamage -noshm -noxinerama -threads -wait 30 -defer 20 >/tmp/artek/x11vnc.log 2>&1 &

NOVNC_ROOT=/usr/share/novnc
if [[ ! -d "$NOVNC_ROOT" ]]; then
  echo "noVNC is missing from the computer image" >&2
  exit 1
fi
if [[ ! -f "$NOVNC_ROOT/embed.html" ]]; then
  echo "noVNC embed.html is missing from the computer image" >&2
  exit 1
fi
websockify --web="$NOVNC_ROOT" 0.0.0.0:6080 127.0.0.1:5900 >/tmp/artek/novnc.log 2>&1 &

while kill -0 "$XVFB_PID" 2>/dev/null; do
  sleep 2
done
echo "Xvfb exited" >&2
exit 1
