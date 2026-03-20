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
