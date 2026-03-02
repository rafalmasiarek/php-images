#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE_NAME = "php-base-images"


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


rows: list[tuple[str, str, str, str]] = []
for dockerfile in sorted((ROOT / "versions").glob("*/*/Dockerfile")):
    php = dockerfile.parts[-3]
    variant = dockerfile.parts[-2]
    prefix = f"{php}-{variant}"
    pecls = ", ".join(load_pecl_list(dockerfile.parent)) or "-"
    rows.append((php, variant, prefix, pecls))

rows.sort(key=lambda r: (r[0], r[1]))

table = [
    "| PHP | Variant | Image tag prefix | PECL modules (declared) |",
    "| - | - | - | - |",
]
for php, variant, prefix, pecls in rows:
    table.append(f"| {php} | {variant} | `{prefix}` | {pecls} |")

readme = "\n".join([
f"# {IMAGE_NAME}",
"",
"Multi-arch (amd64+arm64) PHP images.",
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
])

(ROOT / "README.md").write_text(readme, encoding="utf-8")
print("README.md generated")