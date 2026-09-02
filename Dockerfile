FROM node:26-bookworm-slim AS web

WORKDIR /src/client/web
COPY client/web/package.json client/web/package-lock.json ./
RUN npm ci
COPY client/assets /src/client/assets
COPY client/web /src/client/web
RUN npm run build

FROM python:3.13-slim-trixie

RUN apt-get update && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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
