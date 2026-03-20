from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .config import SiteRoute, Settings


class Renderer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        template_path = Path(settings.caddyfile_template)
        self.env = Environment(
            loader=FileSystemLoader(str(template_path.parent)),
            undefined=StrictUndefined,
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.template_name = template_path.name

    def render_caddyfile(self, routes: list[SiteRoute]) -> str:
        template = self.env.get_template(self.template_name)
        payload = template.render(routes=routes)
        return payload.strip() + "\n"

    @staticmethod
    def sha256_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def pretty_json(payload: object) -> str:
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"
