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
