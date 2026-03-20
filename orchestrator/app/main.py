from __future__ import annotations

import argparse
import logging
import time

from .config import load_config
from .locking import FileLock
from .logging_utils import configure_logging
from .reconcile import reconcile

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="phpctl orchestrator")
    parser.add_argument("--config", required=True, help="Path to desired state file")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Run one reconcile loop and exit")
    mode.add_argument("--loop", action="store_true", help="Run forever")
    return parser


def main() -> int:
    configure_logging()
    args = build_parser().parse_args()

    initial_config = load_config(args.config)
    run_forever = bool(args.loop or not args.once)

    if not run_forever:
        with FileLock(initial_config.lock_file):
            reconcile(initial_config)
        return 0

    while True:
        try:
            config = load_config(args.config)
            with FileLock(config.lock_file):
                reconcile(config)
            sleep_for = config.reconcile_interval_seconds
        except Exception as exc:  # noqa: BLE001
            logger.exception("reconcile failed", extra={"extra_fields": {"error": str(exc)}})
            sleep_for = max(1, initial_config.reconcile_interval_seconds)

        time.sleep(sleep_for)


if __name__ == "__main__":
    raise SystemExit(main())