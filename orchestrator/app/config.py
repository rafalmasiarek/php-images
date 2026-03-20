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