#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
cfg = json.loads((ROOT / "versions.json").read_text(encoding="utf-8"))
defaults = cfg.get("defaults", {})
image_name = defaults.get("image_name", "php-base-images")

def load_pecl_list(context: str) -> list[str]:
    p = ROOT / context / "pecl.txt"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out

rows = []
for img in cfg["images"]:
    php = img["php"]
    variant = img["variant"]
    alpine_tag = img.get("alpine_tag", defaults.get("alpine_tag", "alpine"))
    flavor = img["flavor"]
    prefix = f"{php}-{variant}-{alpine_tag}-{flavor}"
    pecls = load_pecl_list(img["context"])
    rows.append((php, f"{variant}-{alpine_tag}", flavor, prefix, ", ".join(pecls) if pecls else "-"))

rows.sort(key=lambda r: (r[0], r[1], r[2]))

table = [
    "| PHP | Base tag | Flavor | Image tag prefix | PECL modules (declared) |",
    "| - | - | - | - | - |",
]
for r in rows:
    table.append(f"| {r[0]} | {r[1]} | {r[2]} | `{r[3]}` | {r[4]} |")

readme = "\n".join([
f"# {image_name}",
"",
"Multi-arch (amd64+arm64) PHP base images.",
"",
"---",
"",
"## Supported images",
"",
*table,
"",
"---",
"",
"## Install one more extension on top of a base image",
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
