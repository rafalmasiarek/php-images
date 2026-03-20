from __future__ import annotations

import json
from typing import Any

import requests


class CaddyApiError(RuntimeError):
    pass


class CaddyAdminApi:
    def __init__(self, admin_url: str, adapter_content_type: str) -> None:
        self.admin_url = admin_url.rstrip("/")
        self.adapter_content_type = adapter_content_type
        self.session = requests.Session()

    def ping(self) -> None:
        response = self.session.get(f"{self.admin_url}/config/", timeout=5)
        response.raise_for_status()

    def adapt(self, config_text: str) -> dict[str, Any]:
        response = self.session.post(
            f"{self.admin_url}/adapt",
            headers={"Content-Type": self.adapter_content_type},
            data=config_text.encode("utf-8"),
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise CaddyApiError("Invalid /adapt response body")
        adapted = payload.get("result")
        if not isinstance(adapted, dict):
            raise CaddyApiError("Invalid adapted config returned by Caddy")
        return adapted

    def load(self, config_json: dict[str, Any]) -> None:
        response = self.session.post(
            f"{self.admin_url}/load",
            headers={"Content-Type": "application/json"},
            data=json.dumps(config_json).encode("utf-8"),
            timeout=15,
        )
        response.raise_for_status()

    def export(self) -> dict[str, Any]:
        response = self.session.get(f"{self.admin_url}/config/", timeout=10)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise CaddyApiError("Invalid /config response body")
        return payload
