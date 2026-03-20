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
