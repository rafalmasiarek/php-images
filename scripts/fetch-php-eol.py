#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "_data" / "php-eol.json"
API_URL = "https://endoflife.date/api/v1/products/php/"


def main() -> None:
    req = urllib.request.Request(
        API_URL,
        headers={
            "User-Agent": "php-images-eol-sync/1.0",
            "Accept": "application/json",
        },
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)

    releases = payload.get("result", {}).get("releases", [])

    data: dict[str, dict[str, str | bool]] = {}

    for rel in releases:
        php = str(rel.get("name") or "").strip()
        if not php:
            continue

        latest = rel.get("latest") or {}

        data[php] = {
            "php": php,
            "version": str(latest.get("name") or php),
            "release_date": str(rel.get("releaseDate") or ""),
            "latest_date": str(latest.get("date") or ""),
            "eoas": str(rel.get("eoasFrom") or ""),
            "eol": str(rel.get("eolFrom") or ""),
            "is_maintained": bool(rel.get("isMaintained")),
            "is_eol": bool(rel.get("isEol")),
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()