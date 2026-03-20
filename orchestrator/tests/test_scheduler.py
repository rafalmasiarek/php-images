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
