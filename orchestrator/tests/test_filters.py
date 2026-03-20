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
