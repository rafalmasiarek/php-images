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
