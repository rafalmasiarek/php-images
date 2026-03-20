#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-.}"
TARGET_DIR="${ROOT_DIR%/}/orchestrator"

mkdir -p \
  "${TARGET_DIR}/app" \
  "${TARGET_DIR}/examples" \
  "${TARGET_DIR}/tests"

cat > "${TARGET_DIR}/Dockerfile" <<'EOF'
FROM python:3.13-alpine3.23

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ORCH_LOG_LEVEL=INFO \
    ORCH_LOG_FORMAT=json \
    ORCH_STATE_FILE=/var/lib/php-orchestrator/state.json \
    ORCH_LOCK_FILE=/var/lib/php-orchestrator/reconcile.lock

WORKDIR /app

RUN apk add --no-cache ca-certificates tini

COPY orchestrator/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY orchestrator/entrypoint.py /app/entrypoint.py
COPY orchestrator/app /app/app

RUN mkdir -p /var/lib/php-orchestrator /config

ENTRYPOINT ["/sbin/tini", "--", "python", "/app/entrypoint.py"]
CMD ["python", "-m", "app.main"]
EOF

cat > "${TARGET_DIR}/requirements.txt" <<'EOF'
requests==2.32.3
PyYAML==6.0.2
EOF

cat > "${TARGET_DIR}/entrypoint.py" <<'EOF'
#!/usr/bin/env python3
from __future__ import annotations

import signal
import subprocess
import sys
from typing import Sequence


def _default_command(cmd: Sequence[str]) -> list[str]:
    if not cmd:
        return ["python", "-m", "app.main"]
    return list(cmd)


def main() -> int:
    argv = _default_command(sys.argv[1:])
    child = subprocess.Popen(argv)

    def _forward(signum: int, _frame: object) -> None:
        if child.poll() is None:
            child.send_signal(signum)

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, _forward)

    return child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
EOF
chmod +x "${TARGET_DIR}/entrypoint.py"

cat > "${TARGET_DIR}/app/__init__.py" <<'EOF'
__all__ = []
EOF

cat > "${TARGET_DIR}/app/logging_utils.py" <<'EOF'
from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def configure_logging() -> None:
    level_name = os.getenv("ORCH_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    if os.getenv("ORCH_LOG_FORMAT", "json").lower() == "text":
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        )
    else:
        handler.setFormatter(JsonFormatter())

    root.addHandler(handler)
EOF

cat > "${TARGET_DIR}/app/models.py" <<'EOF'
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class WorkerRef:
    name: str
    endpoint: str
    status: str = "ready"
    basic_auth: str | None = None
    expected_worker_id: str | None = None
    expected_worker_group: str | None = None
    labels: dict[str, str] = field(default_factory=dict)
    source: str = "static"


@dataclass(slots=True)
class DiscoveryConfig:
    static_workers: list[WorkerRef] = field(default_factory=list)
    file_workers_path: str | None = None
    dns_endpoints: list[WorkerRef] = field(default_factory=list)


@dataclass(slots=True)
class RebalancePolicy:
    enabled: bool = False
    max_moves_per_reconcile: int = 1
    min_score_improvement: int = 15
    cooldown_seconds: int = 120


@dataclass(slots=True)
class WorkerRuntime:
    ref: WorkerRef
    reachable: bool
    healthy: bool
    worker_id: str
    worker_group: str
    labels: dict[str, str]
    max_pools: int | None
    max_children_total: int | None
    max_replicas: int | None
    max_memory_mb: int | None
    pool_count: int
    active_pool_count: int
    sum_pm_max_children: int
    replicas: int
    free_pools: int | None
    free_children: int | None
    free_replicas: int | None
    pools: list["PoolInfo"] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def schedulable(self) -> bool:
        return self.reachable and self.healthy and self.ref.status == "ready"

    @property
    def draining(self) -> bool:
        return self.reachable and self.healthy and self.ref.status == "drain"

    @property
    def down(self) -> bool:
        return not self.reachable or not self.healthy or self.ref.status == "down"


@dataclass(slots=True)
class AllocationMatch:
    worker_id: str | None = None
    worker_group: str | None = None
    labels: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class AllocationPool:
    template: str | None = None
    params: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class Allocation:
    allocation_id: str
    replicas: int
    match: AllocationMatch = field(default_factory=AllocationMatch)
    fallback_to_free_workers: bool = False
    pool: AllocationPool = field(default_factory=AllocationPool)
    strategy: str = "balanced"


@dataclass(slots=True)
class PoolInfo:
    name: str
    available: bool
    active: bool
    listen: str
    pm: str
    pm_max_children: int | None
    managed_by: str | None
    allocation_id: str | None
    replica: int | None
    available_path: str
    active_path: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class DesiredReplica:
    allocation_id: str
    replica: int
    pool_name: str
    target_worker_name: str
    target_worker_id: str
    target_worker_group: str
    generation: int
    params: dict[str, str]
    template: str | None
    metadata: dict[str, str]


@dataclass(slots=True)
class RebalanceMove:
    allocation_id: str
    replica: int
    pool_name: str
    from_worker_name: str
    to_worker_name: str
    improvement: int


@dataclass(slots=True)
class ReconcileActions:
    create_or_update: list[DesiredReplica] = field(default_factory=list)
    delete: list[tuple[str, str]] = field(default_factory=list)
    reload_workers_phase_one: set[str] = field(default_factory=set)
    reload_workers_phase_two: set[str] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)
    rebalance_moves: list[RebalanceMove] = field(default_factory=list)


@dataclass(slots=True)
class Config:
    controller_id: str
    reconcile_interval_seconds: int
    request_timeout_seconds: int
    state_file: str
    lock_file: str
    discovery: DiscoveryConfig
    rebalance: RebalancePolicy
    allocations: list[Allocation]


def normalize_status(status: str | None) -> str:
    value = (status or "ready").strip().lower()
    if value not in {"ready", "drain", "down"}:
        return "ready"
    return value


def as_int(value: Any, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default
EOF

cat > "${TARGET_DIR}/app/config.py" <<'EOF'
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

from .models import (
    Allocation,
    AllocationMatch,
    AllocationPool,
    Config,
    DiscoveryConfig,
    RebalancePolicy,
    WorkerRef,
    normalize_status,
)


def _read_config_file(path: str) -> dict[str, Any]:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    if file_path.suffix.lower() in {".yaml", ".yml"}:
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Configuration root must be an object")
    return data


def _read_worker_item(item: dict[str, Any], *, source: str) -> WorkerRef:
    name = str(item.get("name", "")).strip()
    endpoint = str(item.get("endpoint", "")).strip()

    if not endpoint:
        raise ValueError("worker endpoint is required")
    if not name:
        name = _derive_worker_name_from_endpoint(endpoint)

    labels = item.get("labels", {})
    if labels is None:
        labels = {}
    if not isinstance(labels, dict):
        raise ValueError("worker labels must be an object")

    return WorkerRef(
        name=name,
        endpoint=endpoint,
        status=normalize_status(item.get("status")),
        basic_auth=str(item["basic_auth"]).strip() if item.get("basic_auth") else None,
        expected_worker_id=str(item["expected_worker_id"]).strip() if item.get("expected_worker_id") else None,
        expected_worker_group=str(item["expected_worker_group"]).strip() if item.get("expected_worker_group") else None,
        labels={str(k): str(v) for k, v in labels.items()},
        source=source,
    )


def _derive_worker_name_from_endpoint(endpoint: str) -> str:
    value = endpoint.strip()
    for prefix in ("http://", "https://"):
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    value = value.split("/", 1)[0]
    value = value.replace(":", "-")
    return value or "worker"


def _read_worker_list(data: Any, *, source: str) -> list[WorkerRef]:
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError(f"{source} workers must be a list")

    workers: list[WorkerRef] = []
    for item in data:
        if isinstance(item, str):
            workers.append(
                WorkerRef(
                    name=_derive_worker_name_from_endpoint(item),
                    endpoint=item.strip(),
                    source=source,
                )
            )
            continue
        if not isinstance(item, dict):
            raise ValueError(f"{source} worker entry must be an object or string")
        workers.append(_read_worker_item(item, source=source))
    return workers


def _read_discovery(data: dict[str, Any]) -> DiscoveryConfig:
    discovery_data = data.get("discovery", {})
    if discovery_data is None:
        discovery_data = {}
    if not isinstance(discovery_data, dict):
        raise ValueError("discovery must be an object")

    static_workers = _read_worker_list(discovery_data.get("static_workers", []), source="static")
    legacy_workers = _read_worker_list(data.get("workers", []), source="static")
    dns_endpoints = _read_worker_list(discovery_data.get("dns_endpoints", []), source="dns")

    combined_static = static_workers + legacy_workers

    file_workers_path = discovery_data.get("file_workers_path")
    if file_workers_path is not None:
        file_workers_path = str(file_workers_path)

    return DiscoveryConfig(
        static_workers=combined_static,
        file_workers_path=file_workers_path,
        dns_endpoints=dns_endpoints,
    )


def _read_rebalance(data: dict[str, Any]) -> RebalancePolicy:
    rebalance_data = data.get("rebalance", {})
    if rebalance_data is None:
        rebalance_data = {}
    if not isinstance(rebalance_data, dict):
        raise ValueError("rebalance must be an object")

    return RebalancePolicy(
        enabled=bool(rebalance_data.get("enabled", False)),
        max_moves_per_reconcile=max(0, int(rebalance_data.get("max_moves_per_reconcile", 1))),
        min_score_improvement=max(0, int(rebalance_data.get("min_score_improvement", 15))),
        cooldown_seconds=max(0, int(rebalance_data.get("cooldown_seconds", 120))),
    )


def _read_allocations(data: Any) -> list[Allocation]:
    if not isinstance(data, list):
        raise ValueError("allocations must be a list")

    allocations: list[Allocation] = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("allocation entry must be an object")

        allocation_id = str(item["allocation_id"]).strip()
        replicas = int(item["replicas"])
        if not allocation_id:
            raise ValueError("allocation_id is required")
        if replicas < 0:
            raise ValueError("replicas must be >= 0")

        match_data = item.get("match", {})
        if match_data is None:
            match_data = {}
        if not isinstance(match_data, dict):
            raise ValueError(f"allocation {allocation_id}: match must be an object")

        labels = match_data.get("labels", {})
        if labels is None:
            labels = {}
        if not isinstance(labels, dict):
            raise ValueError(f"allocation {allocation_id}: match.labels must be an object")

        pool_data = item.get("pool", {})
        if pool_data is None:
            pool_data = {}
        if not isinstance(pool_data, dict):
            raise ValueError(f"allocation {allocation_id}: pool must be an object")

        params = pool_data.get("params", {})
        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise ValueError(f"allocation {allocation_id}: pool.params must be an object")

        allocations.append(
            Allocation(
                allocation_id=allocation_id,
                replicas=replicas,
                match=AllocationMatch(
                    worker_id=str(match_data["worker_id"]).strip() if match_data.get("worker_id") else None,
                    worker_group=str(match_data["worker_group"]).strip() if match_data.get("worker_group") else None,
                    labels={str(k): str(v) for k, v in labels.items()},
                ),
                fallback_to_free_workers=bool(item.get("fallback_to_free_workers", False)),
                pool=AllocationPool(
                    template=str(pool_data["template"]).strip() if pool_data.get("template") else None,
                    params={str(k): str(v) for k, v in params.items()},
                ),
                strategy=str(item.get("strategy", "balanced")).strip().lower() or "balanced",
            )
        )
    return allocations


def load_config(path: str) -> Config:
    data = _read_config_file(path)

    controller_id = str(data.get("controller_id", "phpctl-orchestrator")).strip() or "phpctl-orchestrator"
    reconcile_interval_seconds = int(data.get("reconcile_interval_seconds", int(os.getenv("ORCH_RECONCILE_INTERVAL", "15"))))
    request_timeout_seconds = int(data.get("request_timeout_seconds", int(os.getenv("ORCH_REQUEST_TIMEOUT", "5"))))
    state_file = str(data.get("state_file", os.getenv("ORCH_STATE_FILE", "/var/lib/php-orchestrator/state.json")))
    lock_file = str(data.get("lock_file", os.getenv("ORCH_LOCK_FILE", "/var/lib/php-orchestrator/reconcile.lock")))

    discovery = _read_discovery(data)
    rebalance = _read_rebalance(data)
    allocations = _read_allocations(data.get("allocations", []))

    return Config(
        controller_id=controller_id,
        reconcile_interval_seconds=max(1, reconcile_interval_seconds),
        request_timeout_seconds=max(1, request_timeout_seconds),
        state_file=state_file,
        lock_file=lock_file,
        discovery=discovery,
        rebalance=rebalance,
        allocations=allocations,
    )
EOF

cat > "${TARGET_DIR}/app/state.py" <<'EOF'
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_STATE: dict[str, Any] = {
    "generations": {},
    "allocation_fingerprints": {},
    "last_successful_reconcile_at": None,
    "last_rebalance_at": {},
}


class StateStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return json.loads(json.dumps(DEFAULT_STATE))
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return json.loads(json.dumps(DEFAULT_STATE))
        if not isinstance(data, dict):
            return json.loads(json.dumps(DEFAULT_STATE))
        merged = json.loads(json.dumps(DEFAULT_STATE))
        merged.update(data)
        if not isinstance(merged.get("generations"), dict):
            merged["generations"] = {}
        if not isinstance(merged.get("allocation_fingerprints"), dict):
            merged["allocation_fingerprints"] = {}
        if not isinstance(merged.get("last_rebalance_at"), dict):
            merged["last_rebalance_at"] = {}
        return merged

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def ensure_generation(self, state: dict[str, Any], allocation_id: str, fingerprint: str) -> int:
        generations = state.setdefault("generations", {})
        fingerprints = state.setdefault("allocation_fingerprints", {})

        current_generation = int(generations.get(allocation_id, 0))
        current_fingerprint = str(fingerprints.get(allocation_id, ""))

        if current_generation <= 0:
            current_generation = 1

        if current_fingerprint != fingerprint:
            if current_fingerprint:
                current_generation += 1
            fingerprints[allocation_id] = fingerprint

        generations[allocation_id] = current_generation
        return current_generation
EOF

cat > "${TARGET_DIR}/app/locking.py" <<'EOF'
from __future__ import annotations

import fcntl
from pathlib import Path
from typing import TextIO


class FileLock:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.handle: TextIO | None = None

    def __enter__(self) -> "FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+", encoding="utf-8")
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.handle is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()
            self.handle = None
EOF

cat > "${TARGET_DIR}/app/phpctl_client.py" <<'EOF'
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
EOF

cat > "${TARGET_DIR}/app/discovery.py" <<'EOF'
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Iterable, List

from .models import DiscoveryConfig, WorkerRef, WorkerRuntime
from .phpctl_client import PhpctlClient, PhpctlError

logger = logging.getLogger(__name__)


def _merge_workers(items: List[WorkerRef]) -> List[WorkerRef]:
    merged: Dict[str, WorkerRef] = {}
    for item in items:
        key = item.endpoint.strip()
        if not key:
            continue
        merged[key] = item
    return list(merged.values())


def _load_static(discovery: DiscoveryConfig) -> List[WorkerRef]:
    return list(discovery.static_workers)


def _load_file_workers(discovery: DiscoveryConfig) -> List[WorkerRef]:
    if not discovery.file_workers_path:
        return []

    path = Path(discovery.file_workers_path)
    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.warning(
            "file worker discovery failed to parse",
            extra={"extra_fields": {"path": str(path), "error": str(exc)}},
        )
        return []

    if not isinstance(data, list):
        logger.warning(
            "file worker discovery ignored invalid payload",
            extra={"extra_fields": {"path": str(path), "reason": "root must be a list"}},
        )
        return []

    result: List[WorkerRef] = []
    for item in data:
        if isinstance(item, str):
            endpoint = item.strip()
            if not endpoint:
                continue
            result.append(
                WorkerRef(
                    name=_name_from_endpoint(endpoint),
                    endpoint=endpoint,
                    source="file",
                )
            )
            continue

        if not isinstance(item, dict):
            continue

        endpoint = str(item.get("endpoint", "")).strip()
        if not endpoint:
            continue

        result.append(
            WorkerRef(
                name=str(item.get("name") or _name_from_endpoint(endpoint)),
                endpoint=endpoint,
                status=str(item.get("status") or "ready").strip().lower() or "ready",
                basic_auth=str(item["basic_auth"]).strip() if item.get("basic_auth") else None,
                expected_worker_id=str(item["expected_worker_id"]).strip() if item.get("expected_worker_id") else None,
                expected_worker_group=str(item["expected_worker_group"]).strip() if item.get("expected_worker_group") else None,
                labels={str(k): str(v) for k, v in dict(item.get("labels", {})).items()} if isinstance(item.get("labels", {}), dict) else {},
                source="file",
            )
        )
    return result


def _load_dns_workers(discovery: DiscoveryConfig) -> List[WorkerRef]:
    result: List[WorkerRef] = []
    for item in discovery.dns_endpoints:
        result.append(
            WorkerRef(
                name=item.name or _name_from_endpoint(item.endpoint),
                endpoint=item.endpoint,
                status=item.status,
                basic_auth=item.basic_auth,
                expected_worker_id=item.expected_worker_id,
                expected_worker_group=item.expected_worker_group,
                labels=dict(item.labels),
                source="dns",
            )
        )
    return result


def discover_worker_refs(discovery: DiscoveryConfig) -> List[WorkerRef]:
    workers: List[WorkerRef] = []
    workers.extend(_load_static(discovery))
    workers.extend(_load_file_workers(discovery))
    workers.extend(_load_dns_workers(discovery))
    return _merge_workers(workers)


def probe_workers(client: PhpctlClient, workers: Iterable[WorkerRef]) -> list[WorkerRuntime]:
    runtime_workers: list[WorkerRuntime] = []

    for worker in workers:
        try:
            health = client.health(worker)
            info = client.worker_info(worker)
            capacity = client.worker_capacity(worker)
            usage = client.fpm_capacity(worker)
            pools = client.pool_list(worker)

            labels_raw = info.get("labels", {})
            if isinstance(labels_raw, str) and labels_raw.strip():
                labels = json.loads(labels_raw)
                if not isinstance(labels, dict):
                    labels = {}
                labels = {str(k): str(v) for k, v in labels.items()}
            elif isinstance(labels_raw, dict):
                labels = {str(k): str(v) for k, v in labels_raw.items()}
            else:
                labels = {}

            runtime_workers.append(
                WorkerRuntime(
                    ref=worker,
                    reachable=True,
                    healthy=bool(health.get("healthy", False)),
                    worker_id=str(info.get("worker_id", worker.expected_worker_id or worker.name)),
                    worker_group=str(info.get("worker_group", worker.expected_worker_group or "-")),
                    labels=labels,
                    max_pools=_as_optional_int(capacity.get("max_pools")),
                    max_children_total=_as_optional_int(capacity.get("max_children_total")),
                    max_replicas=_as_optional_int(capacity.get("max_replicas")),
                    max_memory_mb=_as_optional_int(capacity.get("max_memory_mb")),
                    pool_count=int(usage.get("pool_count", 0) or 0),
                    active_pool_count=int(usage.get("active_pool_count", 0) or 0),
                    sum_pm_max_children=int(usage.get("sum_pm_max_children", 0) or 0),
                    replicas=int(usage.get("replicas", 0) or 0),
                    free_pools=_as_optional_int(usage.get("free_pools")),
                    free_children=_as_optional_int(usage.get("free_children")),
                    free_replicas=_as_optional_int(usage.get("free_replicas")),
                    pools=pools,
                )
            )
        except (PhpctlError, OSError, ValueError, KeyError, RuntimeError) as exc:
            logger.warning(
                "worker probe failed",
                extra={"extra_fields": {"worker": worker.name, "endpoint": worker.endpoint, "error": str(exc)}},
            )
            runtime_workers.append(
                WorkerRuntime(
                    ref=worker,
                    reachable=False,
                    healthy=False,
                    worker_id=worker.expected_worker_id or worker.name,
                    worker_group=worker.expected_worker_group or "-",
                    labels={},
                    max_pools=None,
                    max_children_total=None,
                    max_replicas=None,
                    max_memory_mb=None,
                    pool_count=0,
                    active_pool_count=0,
                    sum_pm_max_children=0,
                    replicas=0,
                    free_pools=None,
                    free_children=None,
                    free_replicas=None,
                    pools=[],
                    errors=[str(exc)],
                )
            )

    return runtime_workers


def _as_optional_int(value: object) -> int | None:
    if value in (None, "", "-"):
        return None
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return None
    if parsed == 0:
        return None
    return parsed


def _name_from_endpoint(endpoint: str) -> str:
    value = endpoint.strip()
    for prefix in ("http://", "https://"):
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    value = value.split("/", 1)[0]
    value = value.replace(":", "-")
    return value or "worker"
EOF

cat > "${TARGET_DIR}/app/filters.py" <<'EOF'
from __future__ import annotations

from .models import Allocation, WorkerRuntime


def worker_matches(worker: WorkerRuntime, allocation: Allocation) -> bool:
    match = allocation.match

    if match.worker_id and worker.worker_id != match.worker_id:
        return False

    if match.worker_group and worker.worker_group != match.worker_group:
        return False

    for key, value in match.labels.items():
        if worker.labels.get(key) != value:
            return False

    return True


def candidate_workers(workers: list[WorkerRuntime], allocation: Allocation) -> list[WorkerRuntime]:
    matched = [worker for worker in workers if worker.schedulable and worker_matches(worker, allocation)]
    if matched:
        return matched

    if allocation.fallback_to_free_workers:
        return [worker for worker in workers if worker.schedulable]

    return []
EOF

cat > "${TARGET_DIR}/app/scoring.py" <<'EOF'
from __future__ import annotations

from .models import Allocation, WorkerRuntime


def allocation_replica_count(worker: WorkerRuntime, allocation_id: str) -> int:
    count = 0
    for pool in worker.pools:
        if pool.metadata.get("managed-by") == "phpctl-orchestrator" and pool.metadata.get("allocation-id") == allocation_id:
            count += 1
    return count


def can_fit(worker: WorkerRuntime, requested_pm_max_children: int) -> bool:
    if not worker.schedulable:
        return False

    if worker.max_pools is not None and worker.active_pool_count + 1 > worker.max_pools:
        return False

    if worker.max_replicas is not None and worker.replicas + 1 > worker.max_replicas:
        return False

    if worker.max_children_total is not None and worker.sum_pm_max_children + requested_pm_max_children > worker.max_children_total:
        return False

    return True


def placement_score(worker: WorkerRuntime, allocation: Allocation, requested_pm_max_children: int) -> int:
    score = 0

    same_allocation = allocation_replica_count(worker, allocation.allocation_id)
    score -= same_allocation * 1000

    score -= worker.active_pool_count * 15
    score -= worker.replicas * 10
    score -= worker.sum_pm_max_children // max(1, requested_pm_max_children)

    if worker.max_pools is not None:
        free_pools = worker.max_pools - worker.active_pool_count
        score += free_pools * 10

    if worker.max_replicas is not None:
        free_replicas = worker.max_replicas - worker.replicas
        score += free_replicas * 10

    if worker.max_children_total is not None:
        free_children = worker.max_children_total - worker.sum_pm_max_children
        score += free_children // max(1, requested_pm_max_children)

    return score
EOF

cat > "${TARGET_DIR}/app/scheduler.py" <<'EOF'
from __future__ import annotations

import copy
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone

from .filters import candidate_workers
from .models import Allocation, RebalanceMove, RebalancePolicy, WorkerRuntime
from .scoring import can_fit, placement_score


def allocation_fingerprint(allocation: Allocation) -> str:
    payload = {
        "allocation_id": allocation.allocation_id,
        "replicas": allocation.replicas,
        "match": {
            "worker_id": allocation.match.worker_id,
            "worker_group": allocation.match.worker_group,
            "labels": allocation.match.labels,
        },
        "fallback_to_free_workers": allocation.fallback_to_free_workers,
        "pool": {
            "template": allocation.pool.template,
            "params": allocation.pool.params,
        },
        "strategy": allocation.strategy,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def requested_pm_max_children(allocation: Allocation) -> int:
    return int(allocation.pool.params.get("PM_MAX_CHILDREN", "8"))


def schedule_missing_replicas(
    workers: list[WorkerRuntime],
    allocation: Allocation,
    existing_assignments: dict[int, str],
) -> dict[int, str]:
    candidates = candidate_workers(workers, allocation)
    if not candidates:
        return {}

    requested_children = requested_pm_max_children(allocation)
    shadow_workers = {worker.ref.name: copy.deepcopy(worker) for worker in candidates}
    planned: dict[int, str] = {}

    for replica in range(1, allocation.replicas + 1):
        if replica in existing_assignments:
            worker_name = existing_assignments[replica]
            if worker_name in shadow_workers:
                _reserve_on_shadow(shadow_workers[worker_name], allocation, requested_children, replica)
            continue

        fit_workers = [worker for worker in shadow_workers.values() if can_fit(worker, requested_children)]
        if not fit_workers:
            break

        fit_workers.sort(
            key=lambda worker: (
                _same_allocation_count(worker, allocation.allocation_id),
                worker.ref.name in existing_assignments.values(),
                -placement_score(worker, allocation, requested_children),
                worker.ref.name,
            )
        )

        selected = fit_workers[0]
        planned[replica] = selected.ref.name
        _reserve_on_shadow(selected, allocation, requested_children, replica)

    return planned


def plan_rebalance(
    workers: list[WorkerRuntime],
    allocation: Allocation,
    current_assignments: dict[int, str],
    policy: RebalancePolicy,
    state: dict[str, object],
) -> list[RebalanceMove]:
    if not policy.enabled or policy.max_moves_per_reconcile <= 0:
        return []

    candidates = candidate_workers(workers, allocation)
    if not candidates:
        return []

    requested_children = requested_pm_max_children(allocation)
    worker_map = {worker.ref.name: copy.deepcopy(worker) for worker in candidates}
    if not worker_map:
        return []

    last_rebalance_at = state.get("last_rebalance_at", {})
    if not isinstance(last_rebalance_at, dict):
        last_rebalance_at = {}

    now = datetime.now(timezone.utc)
    moves: list[RebalanceMove] = []

    for replica, current_worker_name in sorted(current_assignments.items()):
        if current_worker_name not in worker_map:
            continue

        pool_name = f"{allocation.allocation_id}-r{replica}"
        cooldown_key = f"{allocation.allocation_id}:{replica}"
        raw_ts = str(last_rebalance_at.get(cooldown_key, "")).strip()
        if raw_ts:
            try:
                last_ts = datetime.fromisoformat(raw_ts)
                if last_ts.tzinfo is None:
                    last_ts = last_ts.replace(tzinfo=timezone.utc)
                delta = (now - last_ts).total_seconds()
                if delta < policy.cooldown_seconds:
                    continue
            except ValueError:
                pass

        current_worker = worker_map[current_worker_name]
        current_score = placement_score(current_worker, allocation, requested_children)

        better_options: list[tuple[int, WorkerRuntime]] = []
        for candidate in worker_map.values():
            if candidate.ref.name == current_worker_name:
                continue
            if not can_fit(candidate, requested_children):
                continue
            candidate_score = placement_score(candidate, allocation, requested_children)
            improvement = candidate_score - current_score
            if improvement >= policy.min_score_improvement:
                better_options.append((improvement, candidate))

        if not better_options:
            continue

        better_options.sort(key=lambda item: (-item[0], item[1].ref.name))
        improvement, best_worker = better_options[0]

        moves.append(
            RebalanceMove(
                allocation_id=allocation.allocation_id,
                replica=replica,
                pool_name=pool_name,
                from_worker_name=current_worker_name,
                to_worker_name=best_worker.ref.name,
                improvement=improvement,
            )
        )

        _remove_from_shadow(current_worker, allocation, requested_children, replica)
        _reserve_on_shadow(best_worker, allocation, requested_children, replica)

        if len(moves) >= policy.max_moves_per_reconcile:
            break

    return moves


def _same_allocation_count(worker: WorkerRuntime, allocation_id: str) -> int:
    count = 0
    for pool in worker.pools:
        if pool.metadata.get("managed-by") == "phpctl-orchestrator" and pool.metadata.get("allocation-id") == allocation_id:
            count += 1
    return count


def _reserve_on_shadow(worker: WorkerRuntime, allocation: Allocation, requested_children: int, replica: int) -> None:
    from .models import PoolInfo

    worker.active_pool_count += 1
    worker.replicas += 1
    worker.sum_pm_max_children += requested_children
    worker.pools.append(
        PoolInfo(
            name=f"{allocation.allocation_id}-r{replica}",
            available=True,
            active=True,
            listen="",
            pm=allocation.pool.params.get("PM", "dynamic"),
            pm_max_children=requested_children,
            managed_by="phpctl-orchestrator",
            allocation_id=allocation.allocation_id,
            replica=replica,
            available_path="-",
            active_path="-",
            metadata={
                "managed-by": "phpctl-orchestrator",
                "allocation-id": allocation.allocation_id,
                "replica": str(replica),
            },
        )
    )


def _remove_from_shadow(worker: WorkerRuntime, allocation: Allocation, requested_children: int, replica: int) -> None:
    worker.active_pool_count = max(0, worker.active_pool_count - 1)
    worker.replicas = max(0, worker.replicas - 1)
    worker.sum_pm_max_children = max(0, worker.sum_pm_max_children - requested_children)

    kept = []
    removed = False
    for pool in worker.pools:
        if not removed and pool.metadata.get("allocation-id") == allocation.allocation_id and str(pool.metadata.get("replica", "")) == str(replica):
            removed = True
            continue
        kept.append(pool)
    worker.pools = kept
EOF

cat > "${TARGET_DIR}/app/reconcile.py" <<'EOF'
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, Tuple

from .discovery import discover_worker_refs, probe_workers
from .models import Config, DesiredReplica, PoolInfo, ReconcileActions, RebalanceMove, WorkerRuntime
from .phpctl_client import PhpctlClient, PhpctlError
from .scheduler import allocation_fingerprint, plan_rebalance, requested_pm_max_children, schedule_missing_replicas
from .state import StateStore

logger = logging.getLogger(__name__)


def reconcile(config: Config) -> dict[str, object]:
    client = PhpctlClient(timeout_seconds=config.request_timeout_seconds)
    store = StateStore(config.state_file)
    state = store.load()

    worker_refs = discover_worker_refs(config.discovery)
    workers = probe_workers(client, worker_refs)
    worker_by_name = {worker.ref.name: worker for worker in workers}

    desired: dict[str, DesiredReplica] = {}
    actions = ReconcileActions()

    existing_managed = _existing_managed_pools(workers, config.controller_id)

    for allocation in config.allocations:
        fingerprint = allocation_fingerprint(allocation)
        generation = store.ensure_generation(state, allocation.allocation_id, fingerprint)

        existing_for_allocation = _healthy_existing_assignments(
            workers=workers,
            allocation_id=allocation.allocation_id,
            max_replicas=allocation.replicas,
        )

        planned_missing = schedule_missing_replicas(
            workers=workers,
            allocation=allocation,
            existing_assignments=existing_for_allocation,
        )

        combined_assignments = dict(existing_for_allocation)
        combined_assignments.update(planned_missing)

        moves = plan_rebalance(
            workers=workers,
            allocation=allocation,
            current_assignments=combined_assignments,
            policy=config.rebalance,
            state=state,
        )
        for move in moves:
            combined_assignments[move.replica] = move.to_worker_name
            actions.rebalance_moves.append(move)

        for replica in range(1, allocation.replicas + 1):
            worker_name = combined_assignments.get(replica)
            if not worker_name:
                continue

            worker = worker_by_name.get(worker_name)
            if worker is None:
                continue

            pool_name = f"{allocation.allocation_id}-r{replica}"
            desired[pool_name] = _build_desired_replica(
                controller_id=config.controller_id,
                generation=generation,
                allocation=allocation,
                replica=replica,
                pool_name=pool_name,
                worker=worker,
            )

        scheduled_count = sum(1 for pool_name in desired if pool_name.startswith(f"{allocation.allocation_id}-r"))
        if scheduled_count < allocation.replicas:
            actions.warnings.append(
                f"allocation {allocation.allocation_id}: requested {allocation.replicas} replicas but only {scheduled_count} could be scheduled"
            )

    _plan_actions(
        config=config,
        workers=workers,
        existing_managed=existing_managed,
        desired=desired,
        actions=actions,
    )

    _apply_upserts(client, worker_by_name, actions)
    _apply_reload_and_health_phase(client, worker_by_name, sorted(actions.reload_workers_phase_one))
    _apply_deletes(client, worker_by_name, actions)
    _apply_reload_and_health_phase(client, worker_by_name, sorted(actions.reload_workers_phase_two))

    _update_rebalance_state(state, actions.rebalance_moves)

    state["last_successful_reconcile_at"] = datetime.now(timezone.utc).isoformat()
    store.save(state)

    summary = {
        "workers_total": len(workers),
        "workers_ready": len([worker for worker in workers if worker.schedulable]),
        "workers_drain": len([worker for worker in workers if worker.draining]),
        "workers_down": len([worker for worker in workers if worker.down]),
        "desired_replicas": len(desired),
        "upserts": len(actions.create_or_update),
        "deletes": len(actions.delete),
        "rebalance_moves": len(actions.rebalance_moves),
        "warnings": actions.warnings,
    }

    logger.info("reconcile finished", extra={"extra_fields": summary})
    return summary


def _existing_managed_pools(
    workers: list[WorkerRuntime],
    controller_id: str,
) -> dict[str, list[tuple[str, PoolInfo]]]:
    managed: dict[str, list[tuple[str, PoolInfo]]] = {}
    for worker in workers:
        if worker.down:
            continue
        for pool in worker.pools:
            if pool.metadata.get("managed-by") == controller_id:
                managed.setdefault(pool.name, []).append((worker.ref.name, pool))
    return managed


def _healthy_existing_assignments(
    workers: list[WorkerRuntime],
    allocation_id: str,
    max_replicas: int,
) -> dict[int, str]:
    assignments: dict[int, str] = {}
    for worker in workers:
        if not worker.schedulable:
            continue
        for pool in worker.pools:
            if pool.metadata.get("managed-by") != "phpctl-orchestrator":
                continue
            if pool.metadata.get("allocation-id") != allocation_id:
                continue
            replica = _pool_replica(pool)
            if replica is None or replica < 1 or replica > max_replicas:
                continue
            assignments.setdefault(replica, worker.ref.name)
    return assignments


def _build_desired_replica(
    controller_id: str,
    generation: int,
    allocation,
    replica: int,
    pool_name: str,
    worker: WorkerRuntime,
) -> DesiredReplica:
    params = {
        "POOL_NAME": pool_name,
        "USER": "www-data",
        "GROUP": "www-data",
        "LISTEN": f"/var/run/php-fpm-{pool_name}.sock",
        "LISTEN_OWNER": "www-data",
        "LISTEN_GROUP": "www-data",
        "PM": allocation.pool.params.get("PM", "dynamic"),
        "PM_MAX_CHILDREN": allocation.pool.params.get("PM_MAX_CHILDREN", "8"),
        "PM_START_SERVERS": allocation.pool.params.get("PM_START_SERVERS", "2"),
        "PM_MIN_SPARE_SERVERS": allocation.pool.params.get("PM_MIN_SPARE_SERVERS", "1"),
        "PM_MAX_SPARE_SERVERS": allocation.pool.params.get("PM_MAX_SPARE_SERVERS", "3"),
        "CATCH_WORKERS_OUTPUT": allocation.pool.params.get("CATCH_WORKERS_OUTPUT", "yes"),
        "CLEAR_ENV": allocation.pool.params.get("CLEAR_ENV", "no"),
        "ENABLE_METRICS": allocation.pool.params.get("ENABLE_METRICS", "false"),
        "STATUS_PATH": allocation.pool.params.get("STATUS_PATH", ""),
        "ENABLE_PING": allocation.pool.params.get("ENABLE_PING", "false"),
        "PING_PATH": allocation.pool.params.get("PING_PATH", ""),
        "PING_RESPONSE": allocation.pool.params.get("PING_RESPONSE", ""),
    }
    for key, value in allocation.pool.params.items():
        params[str(key)] = str(value)

    metadata = {
        "managed-by": controller_id,
        "allocation-id": allocation.allocation_id,
        "replica": str(replica),
        "generation": str(generation),
        "worker-id": worker.worker_id,
        "worker-group": worker.worker_group,
        "desired-worker-id": worker.worker_id,
        "desired-worker-group": worker.worker_group,
        "strategy": allocation.strategy,
    }

    return DesiredReplica(
        allocation_id=allocation.allocation_id,
        replica=replica,
        pool_name=pool_name,
        target_worker_name=worker.ref.name,
        target_worker_id=worker.worker_id,
        target_worker_group=worker.worker_group,
        generation=generation,
        params=params,
        template=allocation.pool.template,
        metadata=metadata,
    )


def _plan_actions(
    config: Config,
    workers: list[WorkerRuntime],
    existing_managed: dict[str, list[tuple[str, PoolInfo]]],
    desired: dict[str, DesiredReplica],
    actions: ReconcileActions,
) -> None:
    worker_by_name = {worker.ref.name: worker for worker in workers}

    for pool_name, desired_replica in desired.items():
        locations = existing_managed.get(pool_name, [])
        target_ok = False

        for worker_name, pool in locations:
            if worker_name == desired_replica.target_worker_name:
                generation = str(pool.metadata.get("generation", ""))
                desired_worker_id = str(pool.metadata.get("desired-worker-id", ""))
                if generation == str(desired_replica.generation) and desired_worker_id == desired_replica.target_worker_id:
                    target_ok = True

        if not target_ok:
            actions.create_or_update.append(desired_replica)
            actions.reload_workers_phase_one.add(desired_replica.target_worker_name)

        for worker_name, _pool in locations:
            if worker_name != desired_replica.target_worker_name:
                worker = worker_by_name.get(worker_name)
                if worker is not None and not worker.down:
                    actions.delete.append((worker_name, pool_name))
                    actions.reload_workers_phase_two.add(worker_name)

    for pool_name, locations in existing_managed.items():
        if pool_name in desired:
            continue
        for worker_name, _pool in locations:
            worker = worker_by_name.get(worker_name)
            if worker is not None and not worker.down:
                actions.delete.append((worker_name, pool_name))
                actions.reload_workers_phase_two.add(worker_name)

    for move in actions.rebalance_moves:
        actions.reload_workers_phase_one.add(move.to_worker_name)
        actions.reload_workers_phase_two.add(move.from_worker_name)


def _apply_upserts(
    client: PhpctlClient,
    workers: dict[str, WorkerRuntime],
    actions: ReconcileActions,
) -> None:
    for replica in actions.create_or_update:
        worker = workers[replica.target_worker_name]
        logger.info(
            "upserting pool",
            extra={
                "extra_fields": {
                    "worker": worker.ref.name,
                    "pool": replica.pool_name,
                    "allocation_id": replica.allocation_id,
                    "replica": replica.replica,
                    "generation": replica.generation,
                }
            },
        )
        client.pool_upsert(
            worker.ref,
            pool_name=replica.pool_name,
            params=replica.params,
            metadata=replica.metadata,
            template=replica.template,
        )


def _apply_deletes(
    client: PhpctlClient,
    workers: dict[str, WorkerRuntime],
    actions: ReconcileActions,
) -> None:
    seen: set[tuple[str, str]] = set()
    for worker_name, pool_name in actions.delete:
        key = (worker_name, pool_name)
        if key in seen:
            continue
        seen.add(key)

        worker = workers[worker_name]
        logger.info(
            "deleting stale pool",
            extra={"extra_fields": {"worker": worker_name, "pool": pool_name}},
        )
        client.pool_delete(worker.ref, pool_name)


def _apply_reload_and_health_phase(
    client: PhpctlClient,
    workers: dict[str, WorkerRuntime],
    worker_names: list[str],
) -> None:
    for worker_name in worker_names:
        worker = workers.get(worker_name)
        if worker is None or worker.down:
            continue

        logger.info("reloading worker fpm", extra={"extra_fields": {"worker": worker_name}})
        client.fpm_reload(worker.ref)

        health = client.health(worker.ref)
        if not bool(health.get("healthy", False)):
            raise PhpctlError(f"{worker_name}: worker health check failed after reload")


def _update_rebalance_state(state: dict[str, object], moves: list[RebalanceMove]) -> None:
    if not moves:
        return
    store = state.setdefault("last_rebalance_at", {})
    if not isinstance(store, dict):
        store = {}
        state["last_rebalance_at"] = store

    now = datetime.now(timezone.utc).isoformat()
    for move in moves:
        key = f"{move.allocation_id}:{move.replica}"
        store[key] = now


def _pool_replica(pool: PoolInfo) -> int | None:
    if pool.replica is not None:
        return pool.replica
    raw = str(pool.metadata.get("replica", "")).strip()
    if raw.isdigit():
        return int(raw)
    return None
EOF

cat > "${TARGET_DIR}/app/main.py" <<'EOF'
from __future__ import annotations

import argparse
import logging
import time

from .config import load_config
from .locking import FileLock
from .logging_utils import configure_logging
from .reconcile import reconcile

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="phpctl orchestrator")
    parser.add_argument("--config", required=True, help="Path to desired state file")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Run one reconcile loop and exit")
    mode.add_argument("--loop", action="store_true", help="Run forever")
    return parser


def main() -> int:
    configure_logging()
    args = build_parser().parse_args()

    initial_config = load_config(args.config)
    run_forever = bool(args.loop or not args.once)

    if not run_forever:
        with FileLock(initial_config.lock_file):
            reconcile(initial_config)
        return 0

    while True:
        try:
            config = load_config(args.config)
            with FileLock(config.lock_file):
                reconcile(config)
            sleep_for = config.reconcile_interval_seconds
        except Exception as exc:  # noqa: BLE001
            logger.exception("reconcile failed", extra={"extra_fields": {"error": str(exc)}})
            sleep_for = max(1, initial_config.reconcile_interval_seconds)

        time.sleep(sleep_for)


if __name__ == "__main__":
    raise SystemExit(main())
EOF

cat > "${TARGET_DIR}/examples/desired-state.json" <<'EOF'
{
  "controller_id": "phpctl-orchestrator",
  "reconcile_interval_seconds": 15,
  "request_timeout_seconds": 5,
  "state_file": "/var/lib/php-orchestrator/state.json",
  "lock_file": "/var/lib/php-orchestrator/reconcile.lock",
  "discovery": {
    "static_workers": [
      {
        "name": "worker-a",
        "endpoint": "http://worker-a:8080",
        "status": "ready"
      },
      {
        "name": "worker-b",
        "endpoint": "http://worker-b:8080",
        "status": "ready"
      }
    ],
    "file_workers_path": "/config/workers.json",
    "dns_endpoints": [
      "http://worker-c:8080"
    ]
  },
  "rebalance": {
    "enabled": true,
    "max_moves_per_reconcile": 1,
    "min_score_improvement": 15,
    "cooldown_seconds": 120
  },
  "allocations": [
    {
      "allocation_id": "api-main",
      "replicas": 3,
      "match": {
        "worker_group": "blue",
        "labels": {
          "region": "eu",
          "tier": "prod"
        }
      },
      "fallback_to_free_workers": true,
      "strategy": "balanced",
      "pool": {
        "params": {
          "PM": "dynamic",
          "PM_MAX_CHILDREN": "16",
          "PM_START_SERVERS": "4",
          "PM_MIN_SPARE_SERVERS": "2",
          "PM_MAX_SPARE_SERVERS": "6",
          "ENABLE_PING": "true",
          "ENABLE_METRICS": "true",
          "STATUS_PATH": "/fpm-status",
          "PING_PATH": "/fpm-ping",
          "PING_RESPONSE": "pong"
        }
      }
    }
  ]
}
EOF

cat > "${TARGET_DIR}/examples/workers.json" <<'EOF'
[
  {
    "name": "worker-d",
    "endpoint": "http://worker-d:8080",
    "status": "ready"
  }
]
EOF

cat > "${TARGET_DIR}/examples/docker-compose.yml" <<'EOF'
services:
  worker-a:
    image: ghcr.io/rafalmasiarek/php:8.5-fpm
    environment:
      PHPCTL_WORKER_ID: worker-a
      PHPCTL_WORKER_GROUP: blue
      PHPCTL_WORKER_LABEL_REGION: eu
      PHPCTL_WORKER_LABEL_TIER: prod
      PHPCTL_WORKER_MAX_POOLS: "20"
      PHPCTL_WORKER_MAX_CHILDREN_TOTAL: "128"
      PHPCTL_WORKER_MAX_REPLICAS: "20"
    command: ["phpctl", "server", "--listen", "0.0.0.0:8080"]

  worker-b:
    image: ghcr.io/rafalmasiarek/php:8.5-fpm
    environment:
      PHPCTL_WORKER_ID: worker-b
      PHPCTL_WORKER_GROUP: blue
      PHPCTL_WORKER_LABEL_REGION: eu
      PHPCTL_WORKER_LABEL_TIER: prod
      PHPCTL_WORKER_MAX_POOLS: "20"
      PHPCTL_WORKER_MAX_CHILDREN_TOTAL: "128"
      PHPCTL_WORKER_MAX_REPLICAS: "20"
    command: ["phpctl", "server", "--listen", "0.0.0.0:8080"]

  worker-c:
    image: ghcr.io/rafalmasiarek/php:8.5-fpm
    environment:
      PHPCTL_WORKER_ID: worker-c
      PHPCTL_WORKER_GROUP: blue
      PHPCTL_WORKER_LABEL_REGION: eu
      PHPCTL_WORKER_LABEL_TIER: prod
      PHPCTL_WORKER_MAX_POOLS: "20"
      PHPCTL_WORKER_MAX_CHILDREN_TOTAL: "128"
      PHPCTL_WORKER_MAX_REPLICAS: "20"
    command: ["phpctl", "server", "--listen", "0.0.0.0:8080"]

  orchestrator:
    build:
      context: ..
      dockerfile: orchestrator/Dockerfile
    volumes:
      - ./desired-state.json:/config/desired-state.json:ro
      - ./workers.json:/config/workers.json:ro
    command: ["python", "-m", "app.main", "--config", "/config/desired-state.json", "--loop"]
    depends_on:
      - worker-a
      - worker-b
      - worker-c
EOF

cat > "${TARGET_DIR}/tests/test_filters.py" <<'EOF'
from app.filters import worker_matches
from app.models import Allocation, AllocationMatch, AllocationPool, WorkerRef, WorkerRuntime


def test_worker_matches() -> None:
    worker = WorkerRuntime(
        ref=WorkerRef(name="worker-a", endpoint="http://worker-a:8080"),
        reachable=True,
        healthy=True,
        worker_id="worker-a",
        worker_group="blue",
        labels={"region": "eu", "tier": "prod"},
        max_pools=10,
        max_children_total=100,
        max_replicas=10,
        max_memory_mb=None,
        pool_count=0,
        active_pool_count=0,
        sum_pm_max_children=0,
        replicas=0,
        free_pools=10,
        free_children=100,
        free_replicas=10,
        pools=[],
    )
    allocation = Allocation(
        allocation_id="api-main",
        replicas=1,
        match=AllocationMatch(worker_group="blue", labels={"region": "eu"}),
        pool=AllocationPool(params={"PM_MAX_CHILDREN": "8"}),
    )
    assert worker_matches(worker, allocation) is True
EOF

cat > "${TARGET_DIR}/tests/test_discovery.py" <<'EOF'
import json
from pathlib import Path

from app.discovery import discover_worker_refs
from app.models import DiscoveryConfig, WorkerRef


def test_discovery_merges_static_and_file(tmp_path: Path) -> None:
    file_path = tmp_path / "workers.json"
    file_path.write_text(
        json.dumps(
            [
                {"name": "worker-b", "endpoint": "http://worker-b:8080"},
                {"name": "worker-c", "endpoint": "http://worker-c:8080"}
            ]
        ),
        encoding="utf-8",
    )

    discovery = DiscoveryConfig(
        static_workers=[WorkerRef(name="worker-a", endpoint="http://worker-a:8080")],
        file_workers_path=str(file_path),
        dns_endpoints=[WorkerRef(name="worker-c", endpoint="http://worker-c:8080", source="dns")],
    )

    workers = discover_worker_refs(discovery)
    endpoints = sorted(worker.endpoint for worker in workers)
    assert endpoints == [
        "http://worker-a:8080",
        "http://worker-b:8080",
        "http://worker-c:8080",
    ]
EOF

cat > "${TARGET_DIR}/tests/test_scoring.py" <<'EOF'
from app.models import Allocation, AllocationMatch, AllocationPool, PoolInfo, WorkerRef, WorkerRuntime
from app.scoring import allocation_replica_count, can_fit, placement_score


def test_scoring_and_capacity() -> None:
    worker = WorkerRuntime(
        ref=WorkerRef(name="worker-a", endpoint="http://worker-a:8080"),
        reachable=True,
        healthy=True,
        worker_id="worker-a",
        worker_group="blue",
        labels={},
        max_pools=10,
        max_children_total=100,
        max_replicas=10,
        max_memory_mb=None,
        pool_count=0,
        active_pool_count=1,
        sum_pm_max_children=8,
        replicas=1,
        free_pools=9,
        free_children=92,
        free_replicas=9,
        pools=[
            PoolInfo(
                name="api-main-r1",
                available=True,
                active=True,
                listen="",
                pm="dynamic",
                pm_max_children=8,
                managed_by="phpctl-orchestrator",
                allocation_id="api-main",
                replica=1,
                available_path="-",
                active_path="-",
                metadata={"managed-by": "phpctl-orchestrator", "allocation-id": "api-main", "replica": "1"},
            )
        ],
    )
    allocation = Allocation(
        allocation_id="api-main",
        replicas=2,
        match=AllocationMatch(),
        pool=AllocationPool(params={"PM_MAX_CHILDREN": "8"}),
    )
    assert allocation_replica_count(worker, "api-main") == 1
    assert can_fit(worker, 8) is True
    assert isinstance(placement_score(worker, allocation, 8), int)
EOF

cat > "${TARGET_DIR}/tests/test_scheduler.py" <<'EOF'
from app.models import Allocation, AllocationMatch, AllocationPool, RebalancePolicy, WorkerRef, WorkerRuntime
from app.scheduler import plan_rebalance, schedule_missing_replicas


def _worker(name: str, pools: int = 0, children: int = 0, replicas: int = 0) -> WorkerRuntime:
    return WorkerRuntime(
        ref=WorkerRef(name=name, endpoint=f"http://{name}:8080"),
        reachable=True,
        healthy=True,
        worker_id=name,
        worker_group="blue",
        labels={"region": "eu"},
        max_pools=10,
        max_children_total=100,
        max_replicas=10,
        max_memory_mb=None,
        pool_count=pools,
        active_pool_count=pools,
        sum_pm_max_children=children,
        replicas=replicas,
        free_pools=10 - pools,
        free_children=100 - children,
        free_replicas=10 - replicas,
        pools=[],
    )


def test_scheduler_spreads_missing_replicas() -> None:
    workers = [_worker("worker-a"), _worker("worker-b")]
    allocation = Allocation(
        allocation_id="api-main",
        replicas=2,
        match=AllocationMatch(worker_group="blue", labels={"region": "eu"}),
        fallback_to_free_workers=False,
        pool=AllocationPool(params={"PM_MAX_CHILDREN": "8"}),
    )
    planned = schedule_missing_replicas(workers, allocation, {})
    assert len(planned) == 2
    assert planned[1] != planned[2]


def test_rebalance_can_plan_move() -> None:
    workers = [
        _worker("worker-a", pools=5, children=40, replicas=5),
        _worker("worker-b", pools=0, children=0, replicas=0),
    ]
    allocation = Allocation(
        allocation_id="api-main",
        replicas=1,
        match=AllocationMatch(worker_group="blue", labels={"region": "eu"}),
        fallback_to_free_workers=True,
        pool=AllocationPool(params={"PM_MAX_CHILDREN": "8"}),
    )
    moves = plan_rebalance(
        workers=workers,
        allocation=allocation,
        current_assignments={1: "worker-a"},
        policy=RebalancePolicy(enabled=True, max_moves_per_reconcile=1, min_score_improvement=1, cooldown_seconds=0),
        state={},
    )
    assert len(moves) == 1
    assert moves[0].to_worker_name == "worker-b"
EOF

cat > "${TARGET_DIR}/tests/test_reconcile.py" <<'EOF'
def test_placeholder() -> None:
    assert True
EOF

echo "Created ${TARGET_DIR}"
echo
echo "Next steps:"
echo "1. Review orchestrator/examples/desired-state.json"
echo "2. Optionally update orchestrator/examples/workers.json for dynamic worker additions"
echo "3. Build image with: docker build -f orchestrator/Dockerfile -t phpctl-orchestrator ."
echo "4. Run once with: python -m app.main --config orchestrator/examples/desired-state.json --once"
echo "5. Run loop with: python -m app.main --config orchestrator/examples/desired-state.json --loop"