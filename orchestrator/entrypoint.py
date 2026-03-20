#!/usr/bin/env python3
from __future__ import annotations

import signal
import subprocess
import sys
from typing import Sequence


def _default_command(cmd: Sequence[str]) -> list[str]:
    if not cmd:
        return ["python", "-m", "app.main"]
    return list(cmd)


def main() -> int:
    argv = _default_command(sys.argv[1:])
    child = subprocess.Popen(argv)

    def _forward(signum: int, _frame: object) -> None:
        if child.poll() is None:
            child.send_signal(signum)

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, _forward)

    return child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
