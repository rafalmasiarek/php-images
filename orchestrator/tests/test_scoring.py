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
