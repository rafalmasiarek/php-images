FROM python:3.13-alpine3.23

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ORCH_LOG_LEVEL=INFO \
    ORCH_LOG_FORMAT=json \
    ORCH_STATE_FILE=/var/lib/php-orchestrator/state.json \
    ORCH_LOCK_FILE=/var/lib/php-orchestrator/reconcile.lock

WORKDIR /app

RUN apk add --no-cache ca-certificates tini

COPY orchestrator/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY orchestrator/entrypoint.py /app/entrypoint.py
COPY orchestrator/app /app/app

RUN mkdir -p /var/lib/php-orchestrator /config

ENTRYPOINT ["/sbin/tini", "--", "python", "/app/entrypoint.py"]
CMD ["python", "-m", "app.main"]
