from __future__ import annotations

import base64
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import requests

from .models import GlobalLoadBalancerConfig

logger = logging.getLogger(__name__)


class LoadBalancerPublishError(RuntimeError):
    pass


class LoadBalancerClient:
    def __init__(self, config: GlobalLoadBalancerConfig) -> None:
        self.config = config
        self.session = requests.Session()

    def publish(self, snapshot: dict[str, Any], state: dict[str, Any]) -> bool:
        if not self.config.enabled:
            return False

        raw = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
        snapshot_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()

        if self.config.publish_only_when_changed:
            previous_hash = str(state.get("last_load_balancer_snapshot_hash") or "").strip()
            if previous_hash == snapshot_hash:
                logger.info(
                    "load balancer publish skipped because snapshot did not change",
                    extra={"extra_fields": {"snapshot_hash": snapshot_hash}},
                )
                return False

        if self.config.snapshot_path:
            path = Path(self.config.snapshot_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            logger.info(
                "load balancer snapshot written",
                extra={"extra_fields": {"path": str(path), "snapshot_hash": snapshot_hash}},
            )

        if self.config.publish_url:
            headers = {"Content-Type": "application/json"}
            if self.config.basic_auth:
                token = base64.b64encode(self.config.basic_auth.encode("utf-8")).decode("ascii")
                headers["Authorization"] = f"Basic {token}"

            try:
                response = self.session.post(
                    self.config.publish_url,
                    headers=headers,
                    data=json.dumps(snapshot),
                    timeout=self.config.request_timeout_seconds,
                )
                response.raise_for_status()
            except requests.RequestException as exc:
                raise LoadBalancerPublishError(f"load balancer publish failed: {exc}") from exc

            logger.info(
                "load balancer snapshot published",
                extra={
                    "extra_fields": {
                        "publish_url": self.config.publish_url,
                        "snapshot_hash": snapshot_hash,
                        "status_code": response.status_code,
                    }
                },
            )

        state["last_load_balancer_snapshot_hash"] = snapshot_hash
        return True