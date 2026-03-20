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
