FROM node:22-bookworm-slim AS web

WORKDIR /src/client/web
COPY client/web/package.json client/web/package-lock.json ./
RUN npm ci
COPY client/assets /src/client/assets
COPY client/web /src/client/web
RUN npm run build

FROM python:3.13-slim-trixie

ARG TARGETARCH
ARG GH_VERSION=2.99.0
ARG GH_AMD64_SHA256=ed4960225d2833e04a61590d9fa2b5773d147f3aa375459e5466a40c102f3832
ARG GH_ARM64_SHA256=564eff56a61e8caf193efde16937fba879eb62a3a479c9dd6be2001e7647680b
ARG UV_VERSION=0.12.9

RUN apt-get update && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/* \
    && arch="${TARGETARCH:-$(dpkg --print-architecture)}" \
    && case "$arch" in \
         amd64) checksum="$GH_AMD64_SHA256" ;; \
         arm64) checksum="$GH_ARM64_SHA256" ;; \
         *) echo "unsupported gh architecture: $arch" >&2; exit 1 ;; \
       esac \
    && archive="gh_${GH_VERSION}_linux_${arch}.tar.gz" \
    && curl -fsSLo "/tmp/${archive}" \
         "https://github.com/cli/cli/releases/download/v${GH_VERSION}/${archive}" \
    && printf '%s  %s\n' "$checksum" "/tmp/${archive}" | sha256sum -c - \
    && tar -xzf "/tmp/${archive}" -C /usr/local --strip-components=1 \
         "gh_${GH_VERSION}_linux_${arch}/bin/gh" \
    && rm "/tmp/${archive}"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir "uv==${UV_VERSION}"

COPY src ./src
COPY --from=web /src/client/web/dist /app/web

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    AGENT_CWD=/workspace \
    AGENT_DATA_DIR=/data \
    HTTP_HOST=0.0.0.0 \
    HTTP_PORT=8080 \
    ARTEK_WEB_ROOT=/app/web

EXPOSE 8080

CMD ["sh", "-c", "uvicorn artek_buddy.main:app --host ${HTTP_HOST} --port ${HTTP_PORT}"]
