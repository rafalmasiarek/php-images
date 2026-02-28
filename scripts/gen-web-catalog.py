#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
cfg = json.loads((ROOT / "versions.json").read_text(encoding="utf-8"))
defaults = cfg.get("defaults", {})
image_name = defaults.get("image_name", "php-base-images")

def load_pecl(context: str) -> list[str]:
    p = ROOT / context / "pecl.txt"
    if not p.exists():
        return []
    out=[]
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.split("#",1)[0].strip()
        if line:
            out.append(line)
    return out

rows=[]
for img in cfg["images"]:
    php=img["php"]
    variant=img["variant"]
    alpine=img.get("alpine_tag", defaults.get("alpine_tag","alpine"))
    flavor=img["flavor"]
    prefix=f"{php}-{variant}-{alpine}-{flavor}"
    pecl=", ".join(load_pecl(img["context"])) or "-"
    rows.append((php, variant, alpine, flavor, prefix, pecl))

rows.sort(key=lambda r:(r[0], r[1], r[3]))

html = []
html.append(f"<h2>Images</h2>")
html.append(f"<p>Generated from <code>versions.json</code> during CI build.</p>")
html.append("<table>")
html.append("<thead><tr><th>PHP</th><th>Variant</th><th>Alpine tag</th><th>Flavor</th><th>Tag prefix</th><th>PECL (declared)</th></tr></thead>")
html.append("<tbody>")
for r in rows:
    html.append("<tr>")
    html.append(f"<td>{r[0]}</td>")
    html.append(f"<td>{r[1]}</td>")
    html.append(f"<td>{r[2]}</td>")
    html.append(f"<td>{r[3]}</td>")
    html.append(f"<td><code>{r[4]}</code></td>")
    html.append(f"<td>{r[5]}</td>")
    html.append("</tr>")
html.append("</tbody></table>")

out = ROOT / "web" / "_includes" / "generated-table.html"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("\n".join(html) + "\n", encoding="utf-8")
print(f"Wrote {out}")
