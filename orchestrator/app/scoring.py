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
