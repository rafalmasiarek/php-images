from __future__ import annotations

import base64
import json
import tempfile
from pathlib import Path
from typing import Any

import requests

from .models import PoolInfo, WorkerRef, as_int


class PhpctlError(RuntimeError):
    pass


class PhpctlClient:
    def __init__(self, timeout_seconds: int) -> None:
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()

    def _headers(self, worker: WorkerRef) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if worker.basic_auth:
            token = base64.b64encode(worker.basic_auth.encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {token}"
        return headers

    def _post_run(self, worker: WorkerRef, argv: list[str]) -> Any:
        payload = {"argv": argv, "output": "json"}
        url = worker.endpoint.rstrip("/") + "/run"

        try:
            response = self.session.post(
                url,
                headers=self._headers(worker),
                data=json.dumps(payload),
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise PhpctlError(f"{worker.name}: request failed: {exc}") from exc

        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            raise PhpctlError(f"{worker.name}: http error: {exc}") from exc

        try:
            envelope = response.json()
        except ValueError as exc:
            raise PhpctlError(f"{worker.name}: invalid json response") from exc

        if not isinstance(envelope, dict):
            raise PhpctlError(f"{worker.name}: invalid phpctl envelope")

        if int(envelope.get("exit_code", 1)) != 0:
            stderr = str(envelope.get("stderr", "")).strip()
            raise PhpctlError(f"{worker.name}: phpctl command failed: {stderr or 'unknown error'}")

        stdout = str(envelope.get("stdout", "")).strip()
        if not stdout:
            return None

        try:
            return json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise PhpctlError(f"{worker.name}: invalid phpctl stdout json") from exc

    def health(self, worker: WorkerRef) -> dict[str, Any]:
        return self._post_run(worker, ["worker", "health"]) or {}

    def worker_info(self, worker: WorkerRef) -> dict[str, Any]:
        return self._post_run(worker, ["worker", "info"]) or {}

    def worker_capacity(self, worker: WorkerRef) -> dict[str, Any]:
        return self._post_run(worker, ["worker", "capacity"]) or {}

    def fpm_capacity(self, worker: WorkerRef) -> dict[str, Any]:
        return self._post_run(worker, ["fpm", "capacity"]) or {}

    def pool_list(self, worker: WorkerRef) -> list[PoolInfo]:
        payload = self._post_run(worker, ["fpm", "pool", "list"]) or []
        if not isinstance(payload, list):
            raise PhpctlError(f"{worker.name}: invalid pool list payload")

        result: list[PoolInfo] = []
        for item in payload:
            if not isinstance(item, dict):
                continue

            metadata_raw = item.get("metadata_json", {})
            metadata: dict[str, str]
            if isinstance(metadata_raw, str) and metadata_raw.strip():
                try:
                    parsed = json.loads(metadata_raw)
                    metadata = {str(k): str(v) for k, v in parsed.items()} if isinstance(parsed, dict) else {}
                except json.JSONDecodeError:
                    metadata = {}
            elif isinstance(metadata_raw, dict):
                metadata = {str(k): str(v) for k, v in metadata_raw.items()}
            else:
                metadata = {}

            result.append(
                PoolInfo(
                    name=str(item.get("name", "")),
                    available=bool(item.get("available", False)),
                    active=bool(item.get("active", False)),
                    listen=str(item.get("listen", "")),
                    pm=str(item.get("pm", "")),
                    pm_max_children=as_int(item.get("pm_max_children")),
                    managed_by=metadata.get("managed-by") or (str(item.get("managed_by", "")).strip() or None),
                    allocation_id=metadata.get("allocation-id") or (str(item.get("allocation_id", "")).strip() or None),
                    replica=as_int(metadata.get("replica") or item.get("replica")),
                    available_path=str(item.get("available_path", "")),
                    active_path=str(item.get("active_path", "")),
                    metadata=metadata,
                )
            )
        return result

    def pool_upsert(
        self,
        worker: WorkerRef,
        pool_name: str,
        params: dict[str, str],
        metadata: dict[str, str],
        template: str | None,
    ) -> dict[str, Any]:
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as handle:
            for key, value in params.items():
                handle.write(f"{key}={value}\n")
            params_path = handle.name

        argv = ["fpm", "pool", "upsert", pool_name, "--params-file", params_path, "--enable"]
        if template:
            argv.extend(["--template", template])

        for key, value in metadata.items():
            argv.extend(["--meta", f"{key}={value}"])

        try:
            return self._post_run(worker, argv) or {}
        finally:
            Path(params_path).unlink(missing_ok=True)

    def pool_delete(self, worker: WorkerRef, pool_name: str) -> Any:
        return self._post_run(worker, ["fpm", "pool", "delete", pool_name])

    def fpm_reload(self, worker: WorkerRef) -> dict[str, Any]:
        return self._post_run(worker, ["fpm", "reload"]) or {}