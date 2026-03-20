#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-.}"
TARGET_DIR="${ROOT_DIR%/}/loadbalancer"

mkdir -p \
  "${TARGET_DIR}/app" \
  "${TARGET_DIR}/templates" \
  "${TARGET_DIR}/examples"

cat > "${TARGET_DIR}/Dockerfile" <<'EOF'
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
EOF

cat > "${TARGET_DIR}/requirements.txt" <<'EOF'
requests==2.32.3
PyYAML==6.0.2
Jinja2==3.1.6
EOF

cat > "${TARGET_DIR}/entrypoint.py" <<'EOF'
#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

from jinja2 import Environment, FileSystemLoader, StrictUndefined

TEMPLATE_DIR = Path("/app/templates")


def _env(name: str, default: str) -> str:
    value = os.getenv(name, default).strip()
    return value or default


def _render_bootstrap() -> Path:
    template_name = os.getenv("LB_BOOTSTRAP_TEMPLATE", "/app/templates/caddy.json.j2")
    template_path = Path(template_name)
    if not template_path.exists():
        raise FileNotFoundError(f"Bootstrap template not found: {template_path}")

    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(template_path.name)

    context = {
        "admin_listen": _env("LB_CADDY_ADMIN_LISTEN", "127.0.0.1:2019"),
        "persist_config": os.getenv("LB_CADDY_PERSIST_CONFIG", "true").strip().lower() in {"1", "true", "yes", "on"},
        "log_level": _env("LB_CADDY_LOG_LEVEL", "INFO").lower(),
        "disable_admin": os.getenv("LB_CADDY_DISABLE_ADMIN", "false").strip().lower() in {"1", "true", "yes", "on"},
    }

    rendered = template.render(**context)
    parsed = json.loads(rendered)

    bootstrap_path = Path(_env("LB_BOOTSTRAP_PATH", "/tmp/caddy-bootstrap.json"))
    bootstrap_path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_path.write_text(json.dumps(parsed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return bootstrap_path


def _caddy_command() -> list[str]:
    bootstrap = _render_bootstrap()
    return [
        "caddy",
        "run",
        "--config",
        str(bootstrap),
        "--adapter",
        "json",
    ]


def _daemon_command(argv: Sequence[str]) -> list[str]:
    if argv:
        return list(argv)
    return ["python", "-m", "app.main"]


def main() -> int:
    workdir = Path(_env("LB_CADDY_WORKDIR", "/var/lib/caddy"))
    workdir.mkdir(parents=True, exist_ok=True)

    caddy_cmd = _caddy_command()
    daemon_cmd = _daemon_command(sys.argv[1:])

    caddy = subprocess.Popen(caddy_cmd, cwd=str(workdir))
    daemon = subprocess.Popen(daemon_cmd)

    children = [caddy, daemon]

    def _forward(signum: int, _frame: object) -> None:
        for child in children:
            if child.poll() is None:
                child.send_signal(signum)

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, _forward)

    exit_code = 0
    while True:
        caddy_rc = caddy.poll()
        daemon_rc = daemon.poll()

        if daemon_rc is not None:
            exit_code = daemon_rc
            if caddy.poll() is None:
                caddy.terminate()
                try:
                    caddy.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    caddy.kill()
            break

        if caddy_rc is not None:
            exit_code = caddy_rc
            if daemon.poll() is None:
                daemon.terminate()
                try:
                    daemon.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    daemon.kill()
            break

        time.sleep(0.5)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
EOF
chmod +x "${TARGET_DIR}/entrypoint.py"

cat > "${TARGET_DIR}/app/__init__.py" <<'EOF'
__all__ = []
EOF

cat > "${TARGET_DIR}/app/logging_utils.py" <<'EOF'
from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def configure_logging() -> None:
    level_name = os.getenv("LB_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    log_format = os.getenv("LB_LOG_FORMAT", "json").strip().lower()
    if log_format == "text":
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        )
    else:
        handler.setFormatter(JsonFormatter())

    root.addHandler(handler)
EOF

cat > "${TARGET_DIR}/app/config.py" <<'EOF'
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class Upstream:
    dial: str
    health_uri: str | None = None
    health_headers: dict[str, str] = field(default_factory=dict)
    request_header_up: dict[str, str] = field(default_factory=dict)
    request_header_down: dict[str, str] = field(default_factory=dict)
    transport: str = "http"
    tls_server_name: str | None = None


@dataclass(slots=True)
class SiteRoute:
    site_id: str
    host: str
    path_prefix: str
    upstreams: list[Upstream]
    lb_policy: str
    health_interval: str
    health_timeout: str
    health_fails: int
    health_passes: int
    fail_duration: str
    max_fails: int
    response_headers: dict[str, str] = field(default_factory=dict)
    encode_gzip: bool = True
    tls_enabled: bool = True
    server_name: str = "lb0"
    listen_http: list[str] = field(default_factory=list)
    listen_https: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Settings:
    routes_file: str
    caddyfile_template: str
    bootstrap_template: str
    admin_url: str
    adapter_content_type: str
    reload_interval_seconds: int
    default_listen_http: list[str]
    default_listen_https: list[str]
    default_lb_policy: str
    default_health_uri: str
    default_health_interval: str
    default_health_timeout: str
    default_health_fails: int
    default_health_passes: int
    default_fail_duration: str
    default_max_fails: int


def _env_list(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def load_settings() -> Settings:
    return Settings(
        routes_file=os.getenv("LB_ROUTES_FILE", "/config/routes.json"),
        caddyfile_template=os.getenv("LB_CADDYFILE_TEMPLATE", "/app/templates/Caddyfile.j2"),
        bootstrap_template=os.getenv("LB_BOOTSTRAP_TEMPLATE", "/app/templates/caddy.json.j2"),
        admin_url=os.getenv("LB_CADDY_ADMIN_URL", "http://127.0.0.1:2019").rstrip("/"),
        adapter_content_type=os.getenv("LB_CADDY_ADAPTER", "text/caddyfile"),
        reload_interval_seconds=max(1, int(os.getenv("LB_RELOAD_INTERVAL_SECONDS", "5"))),
        default_listen_http=_env_list("LB_DEFAULT_LISTEN_HTTP", ":80"),
        default_listen_https=_env_list("LB_DEFAULT_LISTEN_HTTPS", ":443"),
        default_lb_policy=os.getenv("LB_DEFAULT_LB_POLICY", "round_robin").strip() or "round_robin",
        default_health_uri=os.getenv("LB_DEFAULT_HEALTH_URI", "/healthz").strip() or "/healthz",
        default_health_interval=os.getenv("LB_DEFAULT_HEALTH_INTERVAL", "10s").strip() or "10s",
        default_health_timeout=os.getenv("LB_DEFAULT_HEALTH_TIMEOUT", "3s").strip() or "3s",
        default_health_fails=max(1, int(os.getenv("LB_DEFAULT_HEALTH_FAILS", "2"))),
        default_health_passes=max(1, int(os.getenv("LB_DEFAULT_HEALTH_PASSES", "1"))),
        default_fail_duration=os.getenv("LB_DEFAULT_FAIL_DURATION", "30s").strip() or "30s",
        default_max_fails=max(1, int(os.getenv("LB_DEFAULT_MAX_FAILS", "3"))),
    )


def _read_routes_file(path: str) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Routes file not found: {file_path}")

    text = file_path.read_text(encoding="utf-8")
    suffix = file_path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        payload = yaml.safe_load(text)
    else:
        payload = json.loads(text)

    if not isinstance(payload, dict):
        raise ValueError("Routes file root must be an object")
    return payload


def _normalize_upstream(item: Any, route_id: str, defaults: Settings) -> Upstream:
    if isinstance(item, str):
        dial = item.strip()
        if not dial:
            raise ValueError(f"route {route_id}: upstream dial cannot be empty")
        return Upstream(dial=dial, health_uri=defaults.default_health_uri)

    if not isinstance(item, dict):
        raise ValueError(f"route {route_id}: upstream entry must be a string or object")

    dial = str(item.get("dial", "")).strip()
    if not dial:
        raise ValueError(f"route {route_id}: upstream dial is required")

    health_headers = item.get("health_headers", {}) or {}
    request_header_up = item.get("request_header_up", {}) or {}
    request_header_down = item.get("request_header_down", {}) or {}

    if not isinstance(health_headers, dict):
        raise ValueError(f"route {route_id}: upstream health_headers must be an object")
    if not isinstance(request_header_up, dict):
        raise ValueError(f"route {route_id}: upstream request_header_up must be an object")
    if not isinstance(request_header_down, dict):
        raise ValueError(f"route {route_id}: upstream request_header_down must be an object")

    return Upstream(
        dial=dial,
        health_uri=str(item.get("health_uri") or defaults.default_health_uri).strip() or defaults.default_health_uri,
        health_headers={str(k): str(v) for k, v in health_headers.items()},
        request_header_up={str(k): str(v) for k, v in request_header_up.items()},
        request_header_down={str(k): str(v) for k, v in request_header_down.items()},
        transport=str(item.get("transport", "http")).strip() or "http",
        tls_server_name=str(item.get("tls_server_name")).strip() if item.get("tls_server_name") else None,
    )


def load_routes(settings: Settings) -> list[SiteRoute]:
    payload = _read_routes_file(settings.routes_file)
    routes_raw = payload.get("routes", [])
    if not isinstance(routes_raw, list):
        raise ValueError("routes must be a list")

    defaults_raw = payload.get("defaults", {})
    if defaults_raw is None:
        defaults_raw = {}
    if not isinstance(defaults_raw, dict):
        raise ValueError("defaults must be an object")

    default_lb_policy = str(defaults_raw.get("lb_policy", settings.default_lb_policy)).strip() or settings.default_lb_policy
    default_health_uri = str(defaults_raw.get("health_uri", settings.default_health_uri)).strip() or settings.default_health_uri
    default_health_interval = str(defaults_raw.get("health_interval", settings.default_health_interval)).strip() or settings.default_health_interval
    default_health_timeout = str(defaults_raw.get("health_timeout", settings.default_health_timeout)).strip() or settings.default_health_timeout
    default_health_fails = max(1, int(defaults_raw.get("health_fails", settings.default_health_fails)))
    default_health_passes = max(1, int(defaults_raw.get("health_passes", settings.default_health_passes)))
    default_fail_duration = str(defaults_raw.get("fail_duration", settings.default_fail_duration)).strip() or settings.default_fail_duration
    default_max_fails = max(1, int(defaults_raw.get("max_fails", settings.default_max_fails)))

    result: list[SiteRoute] = []
    seen_ids: set[str] = set()

    for index, item in enumerate(routes_raw, start=1):
        if not isinstance(item, dict):
            raise ValueError("route entry must be an object")

        site_id = str(item.get("site_id") or f"route-{index}").strip()
        if not site_id:
            raise ValueError(f"route {index}: site_id cannot be empty")
        if site_id in seen_ids:
            raise ValueError(f"duplicate site_id: {site_id}")
        seen_ids.add(site_id)

        host = str(item.get("host", "")).strip()
        if not host:
            raise ValueError(f"route {site_id}: host is required")

        path_prefix = str(item.get("path_prefix", "/")).strip() or "/"

        upstreams_raw = item.get("upstreams", [])
        if not isinstance(upstreams_raw, list) or not upstreams_raw:
            raise ValueError(f"route {site_id}: upstreams must be a non-empty list")

        route_defaults = Settings(
            routes_file=settings.routes_file,
            caddyfile_template=settings.caddyfile_template,
            bootstrap_template=settings.bootstrap_template,
            admin_url=settings.admin_url,
            adapter_content_type=settings.adapter_content_type,
            reload_interval_seconds=settings.reload_interval_seconds,
            default_listen_http=settings.default_listen_http,
            default_listen_https=settings.default_listen_https,
            default_lb_policy=default_lb_policy,
            default_health_uri=default_health_uri,
            default_health_interval=default_health_interval,
            default_health_timeout=default_health_timeout,
            default_health_fails=default_health_fails,
            default_health_passes=default_health_passes,
            default_fail_duration=default_fail_duration,
            default_max_fails=default_max_fails,
        )

        upstreams: list[Upstream] = []
        seen_dials: set[str] = set()
        for upstream_raw in upstreams_raw:
            upstream = _normalize_upstream(upstream_raw, site_id, route_defaults)
            if upstream.dial in seen_dials:
                continue
            seen_dials.add(upstream.dial)
            upstreams.append(upstream)

        if not upstreams:
            raise ValueError(f"route {site_id}: no valid upstreams found")

        response_headers_raw = item.get("response_headers", {}) or {}
        if not isinstance(response_headers_raw, dict):
            raise ValueError(f"route {site_id}: response_headers must be an object")

        tls_enabled = bool(item.get("tls_enabled", True))
        encode_gzip = bool(item.get("encode_gzip", True))
        server_name = str(item.get("server_name", "lb0")).strip() or "lb0"

        listen_http = item.get("listen_http", settings.default_listen_http)
        listen_https = item.get("listen_https", settings.default_listen_https)
        if not isinstance(listen_http, list):
            raise ValueError(f"route {site_id}: listen_http must be a list")
        if not isinstance(listen_https, list):
            raise ValueError(f"route {site_id}: listen_https must be a list")

        result.append(
            SiteRoute(
                site_id=site_id,
                host=host,
                path_prefix=path_prefix,
                upstreams=upstreams,
                lb_policy=str(item.get("lb_policy", default_lb_policy)).strip() or default_lb_policy,
                health_interval=str(item.get("health_interval", default_health_interval)).strip() or default_health_interval,
                health_timeout=str(item.get("health_timeout", default_health_timeout)).strip() or default_health_timeout,
                health_fails=max(1, int(item.get("health_fails", default_health_fails))),
                health_passes=max(1, int(item.get("health_passes", default_health_passes))),
                fail_duration=str(item.get("fail_duration", default_fail_duration)).strip() or default_fail_duration,
                max_fails=max(1, int(item.get("max_fails", default_max_fails))),
                response_headers={str(k): str(v) for k, v in response_headers_raw.items()},
                encode_gzip=encode_gzip,
                tls_enabled=tls_enabled,
                server_name=server_name,
                listen_http=[str(v).strip() for v in listen_http if str(v).strip()],
                listen_https=[str(v).strip() for v in listen_https if str(v).strip()],
            )
        )

    return result
EOF

cat > "${TARGET_DIR}/app/renderer.py" <<'EOF'
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .config import SiteRoute, Settings


class Renderer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        template_path = Path(settings.caddyfile_template)
        self.env = Environment(
            loader=FileSystemLoader(str(template_path.parent)),
            undefined=StrictUndefined,
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.template_name = template_path.name

    def render_caddyfile(self, routes: list[SiteRoute]) -> str:
        template = self.env.get_template(self.template_name)
        payload = template.render(routes=routes)
        return payload.strip() + "\n"

    @staticmethod
    def sha256_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def pretty_json(payload: object) -> str:
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"
EOF

cat > "${TARGET_DIR}/app/caddy_api.py" <<'EOF'
from __future__ import annotations

import json
from typing import Any

import requests


class CaddyApiError(RuntimeError):
    pass


class CaddyAdminApi:
    def __init__(self, admin_url: str, adapter_content_type: str) -> None:
        self.admin_url = admin_url.rstrip("/")
        self.adapter_content_type = adapter_content_type
        self.session = requests.Session()

    def ping(self) -> None:
        response = self.session.get(f"{self.admin_url}/config/", timeout=5)
        response.raise_for_status()

    def adapt(self, config_text: str) -> dict[str, Any]:
        response = self.session.post(
            f"{self.admin_url}/adapt",
            headers={"Content-Type": self.adapter_content_type},
            data=config_text.encode("utf-8"),
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise CaddyApiError("Invalid /adapt response body")
        adapted = payload.get("result")
        if not isinstance(adapted, dict):
            raise CaddyApiError("Invalid adapted config returned by Caddy")
        return adapted

    def load(self, config_json: dict[str, Any]) -> None:
        response = self.session.post(
            f"{self.admin_url}/load",
            headers={"Content-Type": "application/json"},
            data=json.dumps(config_json).encode("utf-8"),
            timeout=15,
        )
        response.raise_for_status()

    def export(self) -> dict[str, Any]:
        response = self.session.get(f"{self.admin_url}/config/", timeout=10)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise CaddyApiError("Invalid /config response body")
        return payload
EOF

cat > "${TARGET_DIR}/app/watcher.py" <<'EOF'
from __future__ import annotations

from pathlib import Path


class FileWatcher:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._last_mtime_ns: int | None = None
        self._last_size: int | None = None

    def changed(self) -> bool:
        stat = self.path.stat()
        current_mtime_ns = stat.st_mtime_ns
        current_size = stat.st_size

        if self._last_mtime_ns is None or self._last_size is None:
            self._last_mtime_ns = current_mtime_ns
            self._last_size = current_size
            return True

        if current_mtime_ns != self._last_mtime_ns or current_size != self._last_size:
            self._last_mtime_ns = current_mtime_ns
            self._last_size = current_size
            return True

        return False
EOF

cat > "${TARGET_DIR}/app/main.py" <<'EOF'
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from typing import Any

from .caddy_api import CaddyAdminApi, CaddyApiError
from .config import Settings, load_routes, load_settings
from .logging_utils import configure_logging
from .renderer import Renderer
from .watcher import FileWatcher

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dynamic Caddy load balancer controller")
    parser.add_argument("--once", action="store_true", help="Load the current routes snapshot once and exit")
    parser.add_argument("--loop", action="store_true", help="Keep watching and reload Caddy on snapshot changes")
    return parser


def apply_snapshot(settings: Settings, renderer: Renderer, api: CaddyAdminApi) -> dict[str, Any]:
    routes = load_routes(settings)
    caddyfile = renderer.render_caddyfile(routes)
    caddyfile_hash = renderer.sha256_text(caddyfile)
    adapted = api.adapt(caddyfile)
    api.load(adapted)

    summary = {
        "routes_total": len(routes),
        "hosts": sorted([route.host for route in routes]),
        "caddyfile_sha256": caddyfile_hash,
        "upstreams_total": sum(len(route.upstreams) for route in routes),
    }
    logger.info("caddy configuration loaded", extra={"extra_fields": summary})
    return summary


def main() -> int:
    configure_logging()
    args = build_parser().parse_args()

    settings = load_settings()
    renderer = Renderer(settings)
    api = CaddyAdminApi(settings.admin_url, settings.adapter_content_type)

    watcher = FileWatcher(settings.routes_file)
    last_hash: str | None = None

    api.ping()

    run_forever = bool(args.loop or not args.once)

    if not run_forever:
        summary = apply_snapshot(settings, renderer, api)
        logger.info("one-shot run finished", extra={"extra_fields": summary})
        return 0

    while True:
        try:
            if watcher.changed():
                settings = load_settings()
                renderer = Renderer(settings)
                routes = load_routes(settings)
                caddyfile = renderer.render_caddyfile(routes)
                current_hash = renderer.sha256_text(caddyfile)

                if current_hash != last_hash:
                    adapted = api.adapt(caddyfile)
                    api.load(adapted)
                    last_hash = current_hash
                    logger.info(
                        "caddy configuration reloaded",
                        extra={
                            "extra_fields": {
                                "routes_total": len(routes),
                                "hosts": sorted([route.host for route in routes]),
                                "caddyfile_sha256": current_hash,
                                "upstreams_total": sum(len(route.upstreams) for route in routes),
                            }
                        },
                    )
                else:
                    logger.info(
                        "routes snapshot changed but rendered configuration is identical",
                        extra={"extra_fields": {"caddyfile_sha256": current_hash}},
                    )
        except FileNotFoundError as exc:
            logger.warning("routes file missing", extra={"extra_fields": {"error": str(exc)}})
        except (ValueError, CaddyApiError, json.JSONDecodeError) as exc:
            logger.exception("failed to apply routes snapshot", extra={"extra_fields": {"error": str(exc)}})
        except Exception as exc:  # noqa: BLE001
            logger.exception("unexpected load balancer error", extra={"extra_fields": {"error": str(exc)}})

        time.sleep(settings.reload_interval_seconds)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
EOF

cat > "${TARGET_DIR}/templates/Caddyfile.j2" <<'EOF'
{
    admin {{ env "LB_CADDY_ADMIN_LISTEN" | default("127.0.0.1:2019") }}
{% if env "LB_CADDY_PERSIST_CONFIG" | default("true") in ["0", "false", "False", "no", "off"] %}
    persist_config off
{% endif %}
    log {
        level {{ env "LB_CADDY_LOG_LEVEL" | default("INFO") | lower }}
        output stdout
        format json
    }
}

{% for route in routes %}
{{ route.host }} {
{% if route.encode_gzip %}
    encode gzip zstd
{% endif %}
{% if not route.tls_enabled %}
    auto_https disable_redirects
    tls internal
{% endif %}
{% if route.path_prefix != "/" %}
    @match_{{ route.site_id | replace("-", "_") }} path {{ route.path_prefix }}*
{% endif %}
    reverse_proxy {% if route.path_prefix != "/" %}@match_{{ route.site_id | replace("-", "_") }} {% endif %}{% for upstream in route.upstreams %}{{ upstream.dial }}{% if not loop.last %} {% endif %}{% endfor %} {
        lb_policy {{ route.lb_policy }}
        health_uri {{ route.upstreams[0].health_uri or "/healthz" }}
        health_interval {{ route.health_interval }}
        health_timeout {{ route.health_timeout }}
        health_fails {{ route.health_fails }}
        health_passes {{ route.health_passes }}
        fail_duration {{ route.fail_duration }}
        max_fails {{ route.max_fails }}
{% for upstream in route.upstreams %}
{% if upstream.request_header_up %}
{% for key, value in upstream.request_header_up.items() %}
        header_up {{ key }} {{ value }}
{% endfor %}
{% endif %}
{% if upstream.request_header_down %}
{% for key, value in upstream.request_header_down.items() %}
        header_down {{ key }} {{ value }}
{% endfor %}
{% endif %}
{% endfor %}
    }
{% if route.response_headers %}
    header {
{% for key, value in route.response_headers.items() %}
        {{ key }} {{ value }}
{% endfor %}
    }
{% endif %}
}
{% endfor %}
EOF

cat > "${TARGET_DIR}/templates/caddy.json.j2" <<'EOF'
{
  "admin": {
{% if disable_admin %}
    "disabled": true
{% else %}
    "listen": "{{ admin_listen }}"
{% endif %}
  },
  "logging": {
    "logs": {
      "default": {
        "level": "{{ log_level }}",
        "writer": {
          "output": "stdout"
        },
        "encoder": {
          "format": "json"
        }
      }
    }
  },
  "apps": {
    "http": {
      "servers": {}
    }
  }
}
EOF

cat > "${TARGET_DIR}/examples/routes.json" <<'EOF'
{
  "defaults": {
    "lb_policy": "round_robin",
    "health_uri": "/healthz",
    "health_interval": "10s",
    "health_timeout": "3s",
    "health_fails": 2,
    "health_passes": 1,
    "fail_duration": "30s",
    "max_fails": 3
  },
  "routes": [
    {
      "site_id": "api-main",
      "host": "api.local.test",
      "path_prefix": "/",
      "tls_enabled": false,
      "encode_gzip": true,
      "upstreams": [
        {
          "dial": "worker-a:8080",
          "health_uri": "/healthz",
          "request_header_up": {
            "X-Forwarded-Proto": "http"
          }
        },
        {
          "dial": "worker-b:8080",
          "health_uri": "/healthz",
          "request_header_up": {
            "X-Forwarded-Proto": "http"
          }
        }
      ],
      "response_headers": {
        "X-Load-Balancer": "caddy"
      }
    },
    {
      "site_id": "admin-main",
      "host": "admin.local.test",
      "path_prefix": "/",
      "tls_enabled": false,
      "encode_gzip": true,
      "lb_policy": "least_conn",
      "upstreams": [
        "worker-c:8080"
      ]
    }
  ]
}
EOF

cat > "${TARGET_DIR}/examples/docker-compose.yml" <<'EOF'
services:
  worker-a:
    image: ghcr.io/rafalmasiarek/php:8.5-fpm
    environment:
      PHPCTL_WORKER_ID: worker-a
      PHPCTL_WORKER_GROUP: blue
      PHPCTL_WORKER_LABEL_REGION: eu
      PHPCTL_WORKER_LABEL_TIER: prod
    command: ["phpctl", "server", "--listen", "0.0.0.0:8080"]

  worker-b:
    image: ghcr.io/rafalmasiarek/php:8.5-fpm
    environment:
      PHPCTL_WORKER_ID: worker-b
      PHPCTL_WORKER_GROUP: blue
      PHPCTL_WORKER_LABEL_REGION: eu
      PHPCTL_WORKER_LABEL_TIER: prod
    command: ["phpctl", "server", "--listen", "0.0.0.0:8080"]

  worker-c:
    image: ghcr.io/rafalmasiarek/php:8.5-fpm
    environment:
      PHPCTL_WORKER_ID: worker-c
      PHPCTL_WORKER_GROUP: blue
      PHPCTL_WORKER_LABEL_REGION: eu
      PHPCTL_WORKER_LABEL_TIER: prod
    command: ["phpctl", "server", "--listen", "0.0.0.0:8080"]

  loadbalancer:
    build:
      context: ..
      dockerfile: loadbalancer/Dockerfile
    environment:
      LB_ROUTES_FILE: /config/routes.json
      LB_CADDY_ADMIN_LISTEN: 127.0.0.1:2019
      LB_CADDY_ADMIN_URL: http://127.0.0.1:2019
      LB_RELOAD_INTERVAL_SECONDS: "5"
      LB_LOG_LEVEL: INFO
      LB_LOG_FORMAT: json
    volumes:
      - ./routes.json:/config/routes.json:ro
    ports:
      - "8081:80"
    depends_on:
      - worker-a
      - worker-b
      - worker-c
EOF

echo "Created ${TARGET_DIR}"
echo
echo "Files generated:"
echo "  ${TARGET_DIR}/Dockerfile"
echo "  ${TARGET_DIR}/requirements.txt"
echo "  ${TARGET_DIR}/entrypoint.py"
echo "  ${TARGET_DIR}/app/__init__.py"
echo "  ${TARGET_DIR}/app/logging_utils.py"
echo "  ${TARGET_DIR}/app/config.py"
echo "  ${TARGET_DIR}/app/renderer.py"
echo "  ${TARGET_DIR}/app/caddy_api.py"
echo "  ${TARGET_DIR}/app/watcher.py"
echo "  ${TARGET_DIR}/app/main.py"
echo "  ${TARGET_DIR}/templates/Caddyfile.j2"
echo "  ${TARGET_DIR}/templates/caddy.json.j2"
echo "  ${TARGET_DIR}/examples/routes.json"
echo "  ${TARGET_DIR}/examples/docker-compose.yml"
echo
echo "Build:"
echo "  docker build -f loadbalancer/Dockerfile -t phpctl-caddy-lb ."
echo
echo "Run once:"
echo "  docker run --rm -v \"\$(pwd)/loadbalancer/examples/routes.json:/config/routes.json:ro\" phpctl-caddy-lb python -m app.main --once"
echo
echo "Run loop:"
echo "  docker run --rm -v \"\$(pwd)/loadbalancer/examples/routes.json:/config/routes.json:ro\" -p 8081:80 phpctl-caddy-lb"
