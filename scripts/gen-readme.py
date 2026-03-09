#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
IMAGE_NAME = "php"
REPO = os.getenv("GITHUB_REPOSITORY", "rafalmasiarek/php-images")
GHCR_IMAGE = f"ghcr.io/{REPO.split('/')[0]}/{IMAGE_NAME}"
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


def shields_endpoint_md(endpoint_url: str, alt: str) -> str:
    url = "https://img.shields.io/endpoint?url=" + quote(endpoint_url, safe="")
    return f"![{alt}]({url})"


def shields_static_md(label: str, message: str, color: str, alt: str) -> str:
    url = (
        "https://img.shields.io/static/v1"
        f"?label={quote(label, safe='')}"
        f"&message={quote(message, safe='')}"
        f"&color={quote(color, safe='')}"
    )
    return f"![{alt}]({url})"


def endpoint_badge(name: str) -> str:
    if not SITE_BASE_URL:
        return ""
    endpoint_url = f"{SITE_BASE_URL}/badges/{name}.json"
    return shields_endpoint_md(endpoint_url, name)


def workflow_badge() -> str:
    return f"![build](https://github.com/{REPO}/actions/workflows/build.yml/badge.svg?branch=main)"


def license_badge() -> str:
    return f"![license](https://img.shields.io/github/license/{REPO})"


def trivy_badge(php: str, variant: str) -> str:
    if not SITE_BASE_URL:
        return ""
    endpoint_url = f"{SITE_BASE_URL}/badges/trivy-{php}-{variant}.json"
    return shields_endpoint_md(endpoint_url, "trivy")


def os_badge(os_version: str) -> str:
    if not os_version or os_version == "unknown":
        return shields_static_md("alpine", "unknown", "lightgrey", "alpine")

    badge = shields_static_md("alpine", f"v{os_version}", "blue", "alpine")
    link = f"https://hub.docker.com/layers/library/alpine/{os_version}"
    return f"[{badge}]({link})"


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


def php_key(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.split("."))
    except Exception:
        return (0,)


data: dict[str, dict[str, dict[str, str]]] = {}

for dockerfile in sorted((ROOT / "versions").glob("*/*/Dockerfile")):
    php = dockerfile.parts[-3]
    variant = dockerfile.parts[-2]
    data.setdefault(php, {})
    data[php][variant] = {
        "tag": f"{php}-{variant}",
        "os": detect_alpine(dockerfile),
    }

table = [
    "| PHP | Last build | SHA | Tags | OS | Trivy |",
    "| - | - | - | - | - | - |",
]

for php in sorted(data.keys(), key=php_key):
    variants = data[php]
    last_date, last_sha = load_last_build(php)

    tags_lines: list[str] = []
    os_lines: list[str] = []
    trivy_lines: list[str] = []

    for variant in sorted(variants.keys()):
        tag = variants[variant]["tag"]
        os_ver = variants[variant]["os"]
        tags_lines.append(f"**{variant}**: `{tag}`")
        os_lines.append(f"**{variant}**: {os_badge(os_ver)}")
        trivy_lines.append(f"**{variant}**: {trivy_badge(php, variant)}")

    php_cell = f"[`{php}`]({release_url_for_php(php)})"
    table.append(
        "| "
        + php_cell
        + " | "
        + f"`{last_date}`"
        + " | "
        + f"`{last_sha}`"
        + " | "
        + "<br>".join(tags_lines)
        + " | "
        + "<br>".join(os_lines)
        + " | "
        + "<br>".join(trivy_lines)
        + " |"
    )

badges = [workflow_badge(), license_badge()]
if SITE_BASE_URL:
    badges.extend([endpoint_badge("trivy-total"), endpoint_badge("built")])

readme = "\n".join(
    [
        f"# {IMAGE_NAME}",
        "",
        "Multi-arch Alpine-based PHP images",
        "",
        *[badge for badge in badges if badge],
        "",
        "---",
        "",
        "## Supported images",
        "",
        *table,
        "",
        "---",
        "",
        "## Pulling images",
        "",
        f"All images are published to `{GHCR_IMAGE}`.",
        "",
        "Tag scheme:",
        "",
        "- `<php>-<variant>` (moving)",
        "- `<php>-<variant>-YYYY-MM-DD` (date)",
        "- `<php>-<variant>-sha-<gitsha7>` (immutable)",
        "",
        "## Trivy reports",
        "",
        f"- HTML reports: {SITE_BASE_URL}/reports/" if SITE_BASE_URL else "- HTML reports: `/reports/`",
        "",
        "## Install one more extension on top of an image",
        "",
        "Images ship with `/usr/local/bin/php-ext-install` for PECL modules:",
        "",
        "```sh",
        "php-ext-install pecl igbinary",
        "php-ext-install pecl imagick --runtime imagemagick-dev --apk imagemagick-dev",
        "```",
        "",
        "## License",
        "",
        "MIT",
        "",
    ]
)

(ROOT / "README.md").write_text(readme, encoding="utf-8")
print("README.md generated")