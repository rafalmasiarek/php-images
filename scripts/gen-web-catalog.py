#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE_NAME = "php-base-images"


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


rows: list[tuple[str, str, str, str]] = []
for dockerfile in sorted((ROOT / "versions").glob("*/*/Dockerfile")):
    php = dockerfile.parts[-3]
    variant = dockerfile.parts[-2]
    prefix = f"{php}-{variant}"
    pecl = ", ".join(load_pecl(dockerfile.parent)) or "-"
    rows.append((php, variant, prefix, pecl))

rows.sort(key=lambda r: (r[0], r[1]))

html: list[str] = []
html.append("<h2>Images</h2>")
html.append("<p>Generated from <code>versions/</code> during CI build.</p>")
html.append("<table>")
html.append("<thead><tr><th>PHP</th><th>Variant</th><th>Tag prefix</th><th>PECL (declared)</th></tr></thead>")
html.append("<tbody>")
for php, variant, prefix, pecl in rows:
    html.append("<tr>")
    html.append(f"<td>{php}</td>")
    html.append(f"<td>{variant}</td>")
    html.append(f"<td><code>{prefix}</code></td>")
    html.append(f"<td>{pecl}</td>")
    html.append("</tr>")
html.append("</tbody></table>")

out = ROOT / "web" / "_includes" / "generated-table.html"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("\n".join(html) + "\n", encoding="utf-8")
print(f"Wrote {out}")