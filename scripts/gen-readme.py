#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# This is the GHCR package name (ghcr.io/<owner>/php)
IMAGE_NAME = "php"
REPO = "rafalmasiarek/php-images"
BADGES_BRANCH = "badges"
GHCR_IMAGE = "ghcr.io/rafalmasiarek/php"


def load_pecl_list(dirpath: Path) -> list[str]:
    p = dirpath / "pecl.txt"
    if not p.exists():
        return []
    out: list[str] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def detect_alpine(dockerfile: Path) -> str:
    """
    Tries to detect Alpine version from a Dockerfile by parsing the first FROM line.
    Supports:
      - alpine:3.20
      - php:8.x-alpine3.20
      - ...alpine3.20...
    Returns "unknown" if not detected.
    """
    txt = dockerfile.read_text(encoding="utf-8", errors="replace")
    from_line = ""
    for line in txt.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.upper().startswith("FROM "):
            from_line = line
            break
    if not from_line:
        return "unknown"

    m = re.search(r"\balpine:(\d+(?:\.\d+)*)\b", from_line)
    if m:
        return m.group(1)

    m = re.search(r"\balpine(\d+(?:\.\d+)*)\b", from_line)
    if m:
        return m.group(1)

    return "unknown"


def trivy_badge(php: str, variant: str) -> str:
    url = (
        "https://img.shields.io/endpoint"
        f"?url=https://raw.githubusercontent.com/{REPO}/{BADGES_BRANCH}/badges/trivy-{php}-{variant}.json"
    )
    return f"![trivy]({url})"


def endpoint_badge(name: str) -> str:
    url = (
        "https://img.shields.io/endpoint"
        f"?url=https://raw.githubusercontent.com/{REPO}/{BADGES_BRANCH}/badges/{name}.json"
    )
    return f"![{name}]({url})"


def workflow_badge() -> str:
    return f"![build](https://github.com/{REPO}/actions/workflows/build.yml/badge.svg?branch=main)"


def release_badge() -> str:
    return f"![release](https://img.shields.io/github/v/release/{REPO}?display_name=tag)"


def license_badge() -> str:
    return f"![license](https://img.shields.io/github/license/{REPO})"


# Collect data: php -> variant -> info
data: dict[str, dict[str, dict[str, object]]] = {}

for dockerfile in sorted((ROOT / "versions").glob("*/*/Dockerfile")):
    php = dockerfile.parts[-3]
    variant = dockerfile.parts[-2]
    tag = f"{php}-{variant}"

    data.setdefault(php, {})
    data[php][variant] = {
        "tag": tag,
        "pecl": load_pecl_list(dockerfile.parent),
        "alpine": detect_alpine(dockerfile),
    }

# Build table: one row per PHP version, variants rendered with <br>
table = [
    "| PHP | Tags | Alpine | PECL modules (declared) | Trivy |",
    "| - | - | - | - | - |",
]

for php in sorted(data.keys(), key=lambda s: tuple(int(x) for x in s.split("."))):
    variants = data[php]

    tags_lines: list[str] = []
    alpine_lines: list[str] = []
    pecl_lines: list[str] = []
    trivy_lines: list[str] = []

    for variant in sorted(variants.keys()):
        tag = str(variants[variant]["tag"])
        alpine = str(variants[variant]["alpine"])
        pecls = variants[variant]["pecl"]
        pecl_str = ", ".join(pecls) if pecls else "-"

        # ONLY the moving tag (no date/sha patterns)
        tags_lines.append(f"**{variant}**: `{tag}`")
        alpine_lines.append(f"**{variant}**: `{alpine}`")
        pecl_lines.append(f"**{variant}**: {pecl_str}")
        trivy_lines.append(f"**{variant}**: {trivy_badge(php, variant)}")

    table.append(
        "| "
        + f"`{php}`"
        + " | "
        + "<br>".join(tags_lines)
        + " | "
        + "<br>".join(alpine_lines)
        + " | "
        + "<br>".join(pecl_lines)
        + " | "
        + "<br>".join(trivy_lines)
        + " |"
    )

readme = "\n".join(
    [
        f"# {IMAGE_NAME}",
        "",
        "Multi-arch Alpine-based PHP images",
        "",
        workflow_badge(),
        release_badge(),
        license_badge(),
        "",
        endpoint_badge("trivy-total"),
        endpoint_badge("php"),
        endpoint_badge("built"),
        endpoint_badge("images"),
        "",
        "---",
        "",
        "## Supported images",
        "",
        *table,
        "",
        "---",
        "",
        "## Install one more extension on top of an image",
        "",
        "Images ship with `/usr/local/bin/php-ext-install` for PECL modules:",
        "",
        "```sh",
        "php-ext-install pecl igbinary",
        "php-ext-install pecl imagick --runtime imagemagick --apk imagemagick-dev",
        "```",
        "",
        "## License",
        "MIT",
        "",
    ]
)

(ROOT / "README.md").write_text(readme, encoding="utf-8")
print("README.md generated")