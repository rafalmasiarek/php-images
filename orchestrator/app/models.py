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