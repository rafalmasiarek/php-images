#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
REPO = os.getenv("GITHUB_REPOSITORY", "rafalmasiarek/php-images")
IMAGE_NAME = "php"
REGISTRY_IMAGE = f"ghcr.io/{REPO.split('/')[0]}/{IMAGE_NAME}"
SITE_BASE_URL = os.getenv("SITE_BASE_URL", "").rstrip("/")


def detect_alpine(dockerfile: Path) -> str:
    text = dockerfile.read_text(encoding="utf-8", errors="replace")

    from_line = ""
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.upper().startswith("FROM "):
            from_line = line
            break

    if not from_line:
        return "unknown"

    match = re.search(r"\balpine:(\d+(?:\.\d+)*)\b", from_line)
    if match:
        return match.group(1)

    match = re.search(r"\balpine(\d+(?:\.\d+)*)\b", from_line)
    if match:
        return match.group(1)

    return "unknown"


def php_key(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.split("."))
    except Exception:
        return (0,)


def shields_endpoint_url(endpoint_url: str) -> str:
    return "https://img.shields.io/endpoint?url=" + quote(endpoint_url, safe="")


def shields_static_url(label: str, message: str, color: str) -> str:
    return (
        "https://img.shields.io/static/v1"
        f"?label={quote(label, safe='')}"
        f"&message={quote(message, safe='')}"
        f"&color={quote(color, safe='')}"
    )


def release_url_for_php(php: str) -> str:
    return f"https://github.com/{REPO}/releases/tag/php-{php}"


def load_last_build(php: str) -> tuple[str, str]:
    path = ROOT / "web" / "badges" / f"last-{php}.json"
    if not path.exists():
        return "-", "-"

    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        date = str(obj.get("date") or "-")
        sha = str(obj.get("sha") or "-")
        return date or "-", sha or "-"
    except Exception:
        return "-", "-"


def load_trivy_counts(php: str, variant: str) -> dict[str, int]:
    path = ROOT / "web" / "badges" / f"trivy-{php}-{variant}.data.json"
    if not path.exists():
        return {"critical": 0, "high": 0, "medium": 0}

    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return {
            "critical": int(obj.get("critical") or 0),
            "high": int(obj.get("high") or 0),
            "medium": int(obj.get("medium") or 0),
        }
    except Exception:
        return {"critical": 0, "high": 0, "medium": 0}


catalog_images: list[dict] = []
report_rows: list[dict] = []

versions: dict[str, list[Path]] = {}
for dockerfile in sorted((ROOT / "versions").glob("*/*/Dockerfile")):
    php = dockerfile.parts[-3]
    versions.setdefault(php, []).append(dockerfile)

for php in sorted(versions.keys(), key=php_key):
    last_build, last_sha = load_last_build(php)
    variants: list[dict] = []

    for dockerfile in sorted(versions[php], key=lambda p: p.parts[-2]):
        variant = dockerfile.parts[-2]
        os_version = detect_alpine(dockerfile)
        trivy_counts = load_trivy_counts(php, variant)

        os_badge_url = (
            shields_static_url("alpine", "unknown", "lightgrey")
            if os_version == "unknown"
            else shields_static_url("alpine", f"v{os_version}", "blue")
        )

        trivy_badge_url = (
            shields_endpoint_url(f"{SITE_BASE_URL}/badges/trivy-{php}-{variant}.json")
            if SITE_BASE_URL
            else ""
        )

        variant_entry = {
            "name": variant,
            "tag": f"{php}-{variant}",
            "os": os_version,
            "os_badge_url": os_badge_url,
            "os_layers_url": f"https://hub.docker.com/layers/library/alpine/{os_version}" if os_version != "unknown" else "",
            "trivy_badge_url": trivy_badge_url,
            "report_relative_url": f"/reports/trivy-{php}-{variant}.html",
            "report_file": f"trivy-{php}-{variant}.html",
            "critical": trivy_counts["critical"],
            "high": trivy_counts["high"],
            "medium": trivy_counts["medium"],
        }
        variants.append(variant_entry)

        report_rows.append(
            {
                "php": php,
                "variant": variant,
                "last_build": last_build,
                "last_sha": last_sha,
                "critical": trivy_counts["critical"],
                "high": trivy_counts["high"],
                "medium": trivy_counts["medium"],
                "report_relative_url": f"/reports/trivy-{php}-{variant}.html",
            }
        )

    catalog_images.append(
        {
            "php": php,
            "release_url": release_url_for_php(php),
            "last_build": last_build,
            "last_sha": last_sha,
            "variants": variants,
        }
    )

catalog = {
    "repo": REPO,
    "image_name": IMAGE_NAME,
    "registry_image": REGISTRY_IMAGE,
    "site_base_url": SITE_BASE_URL,
    "badges": {
        "build": f"https://github.com/{REPO}/actions/workflows/build.yml/badge.svg?branch=main",
        "license": f"https://img.shields.io/github/license/{REPO}",
        "trivy_total": shields_endpoint_url(f"{SITE_BASE_URL}/badges/trivy-total.json") if SITE_BASE_URL else "",
        "built": shields_endpoint_url(f"{SITE_BASE_URL}/badges/built.json") if SITE_BASE_URL else "",
    },
    "images": catalog_images,
    "report_rows": sorted(report_rows, key=lambda row: (php_key(row["php"]), row["variant"])),
}

out = ROOT / "web" / "_data" / "catalog.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(catalog, indent=2, sort_keys=False) + "\n", encoding="utf-8")
print(f"Wrote {out}")