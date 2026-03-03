#!/usr/bin/env python3
from __future__ import annotations

import html
import re
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]

REPO = "rafalmasiarek/php-images"

# Public site base URL (GitHub Pages via Deployments / Jekyll)
SITE_BASE_URL = "https://php-images.masiarek.dev"

# This is the package name used by build.yml (ghcr.io/<owner>/php)
IMAGE_NAME = "php"


def load_pecl(dirpath: Path) -> list[str]:
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
    Tries to detect Alpine version from Dockerfile FROM line.
    Supports:
      - alpine:3.20
      - php:8.x-alpine3.20
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


def badge_img(url: str, alt: str) -> str:
    return f'<img src="{html.escape(url)}" alt="{html.escape(alt)}" loading="lazy" />'


def shields_endpoint_badge(endpoint_url: str, alt: str) -> str:
    # Shields expects the endpoint URL to be URL-encoded
    shields = "https://img.shields.io/endpoint?url=" + quote(endpoint_url, safe="")
    return badge_img(shields, alt)


def endpoint_badge(name: str) -> str:
    endpoint_url = f"{SITE_BASE_URL}/badges/{name}.json"
    return shields_endpoint_badge(endpoint_url, name)


def trivy_badge(php: str, variant: str) -> str:
    endpoint_url = f"{SITE_BASE_URL}/badges/trivy-{php}-{variant}.json"
    return shields_endpoint_badge(endpoint_url, f"trivy {php}-{variant}")


def trivy_report_link(php: str, variant: str) -> str:
    url = f"{SITE_BASE_URL}/reports/trivy-{php}-{variant}.html"
    return f'<a href="{html.escape(url)}" target="_blank" rel="noopener">HTML report</a>'


def workflow_badge() -> str:
    url = f"https://github.com/{REPO}/actions/workflows/build.yml/badge.svg?branch=main"
    return badge_img(url, "build")


def release_badge() -> str:
    url = f"https://img.shields.io/github/v/release/{REPO}?display_name=tag"
    return badge_img(url, "release")


def license_badge() -> str:
    url = f"https://img.shields.io/github/license/{REPO}"
    return badge_img(url, "license")


# Collect info: php -> variant -> info
data: dict[str, dict[str, dict[str, object]]] = {}

for dockerfile in sorted((ROOT / "versions").glob("*/*/Dockerfile")):
    php = dockerfile.parts[-3]
    variant = dockerfile.parts[-2]
    prefix = f"{php}-{variant}"
    pecl_list = load_pecl(dockerfile.parent)
    alpine = detect_alpine(dockerfile)

    data.setdefault(php, {})
    data[php][variant] = {
        "prefix": prefix,
        "pecl": pecl_list,
        "alpine": alpine,
    }


def php_key(s: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in s.split("."))
    except Exception:
        return (0,)


# Build HTML
html_out: list[str] = []

html_out.append("<h2>Catalog</h2>")
html_out.append("<p>Generated from <code>versions/</code> during CI build.</p>")

html_out.append('<div class="badges">')
html_out.append(workflow_badge())
html_out.append(release_badge())
html_out.append(license_badge())
html_out.append("</div>")

html_out.append('<div class="badges">')
html_out.append(endpoint_badge("trivy-total"))
html_out.append(endpoint_badge("php"))
html_out.append(endpoint_badge("built"))
html_out.append(endpoint_badge("images"))
html_out.append("</div>")

html_out.append("<h3>Tag scheme</h3>")
html_out.append("<ul>")
html_out.append("<li><code>&lt;php&gt;-&lt;variant&gt;</code> — moving tag (latest for that variant)</li>")
html_out.append("<li><code>&lt;php&gt;-&lt;variant&gt;-YYYY-MM-DD</code> — date tag</li>")
html_out.append("<li><code>&lt;php&gt;-&lt;variant&gt;-sha-&lt;gitsha7&gt;</code> — immutable tag</li>")
html_out.append("</ul>")

html_out.append("<h3>Images</h3>")
html_out.append("<table>")
html_out.append(
    "<thead><tr>"
    "<th>PHP</th>"
    "<th>Variants</th>"
    "<th>Tags</th>"
    "<th>Alpine</th>"
    "<th>PECL (declared)</th>"
    "<th>Security</th>"
    "</tr></thead>"
)
html_out.append("<tbody>")

for php in sorted(data.keys(), key=php_key):
    variants = data[php]
    variant_names = sorted(variants.keys())

    variants_cell = "<br>".join(f"<code>{html.escape(v)}</code>" for v in variant_names)

    tags_cell_lines: list[str] = []
    alpine_cell_lines: list[str] = []
    pecl_cell_lines: list[str] = []
    sec_cell_lines: list[str] = []

    for v in variant_names:
        prefix = str(variants[v]["prefix"])
        alpine = str(variants[v]["alpine"])
        pecls = variants[v]["pecl"]
        pecl_str = ", ".join(pecls) if pecls else "-"

        tags_cell_lines.append(
            f"<strong>{html.escape(v)}</strong>: "
            f"<code>{html.escape(prefix)}</code>, "
            f"<code>{html.escape(prefix)}-YYYY-MM-DD</code>, "
            f"<code>{html.escape(prefix)}-sha-&lt;gitsha7&gt;</code>"
        )
        alpine_cell_lines.append(f"<strong>{html.escape(v)}</strong>: <code>{html.escape(alpine)}</code>")
        pecl_cell_lines.append(f"<strong>{html.escape(v)}</strong>: {html.escape(pecl_str)}")
        sec_cell_lines.append(
            f"<strong>{html.escape(v)}</strong>: "
            f"{trivy_badge(php, v)} "
            f"({trivy_report_link(php, v)})"
        )

    html_out.append("<tr>")
    html_out.append(f"<td><code>{html.escape(php)}</code></td>")
    html_out.append(f"<td>{variants_cell}</td>")
    html_out.append(f"<td>{'<br>'.join(tags_cell_lines)}</td>")
    html_out.append(f"<td>{'<br>'.join(alpine_cell_lines)}</td>")
    html_out.append(f"<td>{'<br>'.join(pecl_cell_lines)}</td>")
    html_out.append(f"<td>{'<br>'.join(sec_cell_lines)}</td>")
    html_out.append("</tr>")

html_out.append("</tbody></table>")

out = ROOT / "web" / "_includes" / "generated-table.html"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("\n".join(html_out) + "\n", encoding="utf-8")
print(f"Wrote {out}")
