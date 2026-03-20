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
