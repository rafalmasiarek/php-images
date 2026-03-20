FROM python:3.13-alpine3.23 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LB_LOG_LEVEL=INFO \
    LB_LOG_FORMAT=json \
    LB_ROUTES_FILE=/config/routes.json \
    LB_CADDYFILE_TEMPLATE=/app/templates/Caddyfile.j2 \
    LB_BOOTSTRAP_TEMPLATE=/app/templates/caddy.json.j2 \
    LB_CADDY_ADAPTER=text/caddyfile \
    LB_CADDY_ADMIN_URL=http://127.0.0.1:2019 \
    LB_CADDY_ADMIN_LISTEN=127.0.0.1:2019 \
    LB_CADDY_RUN_USER=caddy \
    LB_CADDY_WORKDIR=/var/lib/caddy \
    LB_CADDY_CONFIG_DIR=/config \
    LB_DEFAULT_LISTEN_HTTP=:80 \
    LB_DEFAULT_LISTEN_HTTPS=:443 \
    LB_RELOAD_INTERVAL_SECONDS=5 \
    LB_BOOTSTRAP_PATH=/tmp/caddy-bootstrap.json

WORKDIR /app

RUN apk add --no-cache ca-certificates tini su-exec

COPY --from=caddy:2-alpine /usr/bin/caddy /usr/bin/caddy

COPY loadbalancer/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY loadbalancer/entrypoint.py /app/entrypoint.py
COPY loadbalancer/app /app/app
COPY loadbalancer/templates /app/templates

RUN addgroup -S caddy >/dev/null 2>&1 || true && \
    adduser -S -D -H -G caddy caddy >/dev/null 2>&1 || true && \
    mkdir -p /var/lib/caddy /config && \
    chown -R caddy:caddy /var/lib/caddy /config /app

ENTRYPOINT ["/sbin/tini", "--", "python", "/app/entrypoint.py"]
CMD ["python", "-m", "app.main"]
