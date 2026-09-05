FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    x11vnc \
    fluxbox \
    xterm \
    thunar \
    xdotool \
    x11-utils \
    x11-xserver-utils \
    imagemagick \
    novnc \
    websockify \
    python3 \
    ca-certificates \
    procps \
    bash \
    chromium \
    fonts-liberation \
    fonts-dejavu-core \
    dbus-x11 \
    xdg-utils \
    python3-pip \
    python3-venv \
    curl \
  && rm -rf /var/lib/apt/lists/* \
  && python3 -m pip install --break-system-packages --no-cache-dir playwright==1.55.0 \
  && mkdir -p /etc/artek/fluxbox /usr/local/lib/artek \
  && printf '%s\n' '#!/bin/sh' 'exec xsetroot -solid "#111113" "$@"' > /usr/bin/fbsetbg \
  && chmod +x /usr/bin/fbsetbg \
  && ln -sfn /bin/true /usr/bin/xmessage
ENV DISPLAY=:1
ENV HOME=/home/artek
ENV LANG=C.UTF-8
RUN apt-get update && apt-get install -y --no-install-recommends xclip \
  && rm -rf /var/lib/apt/lists/*
WORKDIR /home/artek
COPY start.sh /usr/local/bin/artek-computer
COPY artek-browser /usr/local/bin/artek-browser
COPY prepare_chromium_profile.py /usr/local/lib/artek/prepare_chromium_profile.py
COPY fluxbox.init /etc/artek/fluxbox/init
COPY fluxbox.apps /etc/artek/fluxbox/apps
COPY fluxbox.menu /etc/artek/fluxbox/menu
COPY embed.html /usr/share/novnc/embed.html
COPY mimeapps.list /etc/xdg/mimeapps.list
RUN chmod +x /usr/local/bin/artek-computer /usr/local/bin/artek-browser \
  /usr/local/lib/artek/prepare_chromium_profile.py \
  && update-alternatives --install /usr/bin/x-www-browser x-www-browser /usr/local/bin/artek-browser 100 \
  && update-alternatives --set x-www-browser /usr/local/bin/artek-browser \
  && if [ -f /usr/share/applications/chromium.desktop ]; then sed -i 's|Exec=/usr/bin/chromium|Exec=/usr/local/bin/artek-browser|g' /usr/share/applications/chromium.desktop; fi
EXPOSE 6080 6081
CMD ["/usr/local/bin/artek-computer"]
