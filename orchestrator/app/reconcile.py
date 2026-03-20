from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

from .discovery import discover_worker_refs, probe_workers
from .loadbalancer_client import LoadBalancerClient
from .models import Config, DesiredReplica, PoolInfo, ReconcileActions, RebalanceMove, WorkerRuntime
from .phpctl_client import PhpctlClient, PhpctlError
from .scheduler import allocation_fingerprint, plan_rebalance, schedule_missing_replicas
from .state import StateStore

logger = logging.getLogger(__name__)


def reconcile(config: Config) -> dict[str, object]:
    client = PhpctlClient(timeout_seconds=config.request_timeout_seconds)
    store = StateStore(config.state_file)
    state = store.load()

    worker_refs = discover_worker_refs(config.discovery)
    workers = probe_workers(client, worker_refs)
    worker_by_name = {worker.ref.name: worker for worker in workers}
    allocation_by_id = {allocation.allocation_id: allocation for allocation in config.allocations}

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

    load_balancer_published = False
    load_balancer_routes = 0
    if config.load_balancer.enabled:
        snapshot = _build_load_balancer_snapshot(
            config=config,
            desired=desired,
            workers=workers,
            allocations=allocation_by_id,
        )
        load_balancer_routes = len(snapshot.get("routes", []))
        publisher = LoadBalancerClient(config.load_balancer)
        load_balancer_published = publisher.publish(snapshot, state)

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
        "load_balancer_routes": load_balancer_routes,
        "load_balancer_published": load_balancer_published,
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


def _build_load_balancer_snapshot(
    config: Config,
    desired: dict[str, DesiredReplica],
    workers: list[WorkerRuntime],
    allocations: dict[str, object],
) -> dict[str, object]:
    worker_by_name = {worker.ref.name: worker for worker in workers}
    grouped: dict[str, list[DesiredReplica]] = {}

    for replica in desired.values():
        grouped.setdefault(replica.allocation_id, []).append(replica)

    routes: list[dict[str, object]] = []

    for allocation_id, replicas in sorted(grouped.items()):
        allocation = allocations.get(allocation_id)
        if allocation is None:
            continue

        lb = allocation.load_balancer
        if not lb.enabled:
            continue

        upstreams: list[str] = []

        if lb.upstreams:
            upstreams.extend(lb.upstreams)
        else:
            for replica in sorted(replicas, key=lambda item: item.replica):
                worker = worker_by_name.get(replica.target_worker_name)
                if worker is None or worker.down:
                    continue

                host = _resolve_worker_upstream_host(worker)
                if not host:
                    continue
                if lb.upstream_port is None:
                    continue

                upstreams.append(f"{host}:{lb.upstream_port}")

        deduped_upstreams: list[str] = []
        seen_upstreams: set[str] = set()
        for upstream in upstreams:
            value = upstream.strip()
            if not value or value in seen_upstreams:
                continue
            seen_upstreams.add(value)
            deduped_upstreams.append(value)

        route_id = lb.route_id or allocation_id
        routes.append(
            {
                "route_id": route_id,
                "allocation_id": allocation_id,
                "hosts": list(lb.hosts),
                "path": lb.path,
                "tls": lb.tls,
                "health_uri": lb.health_uri,
                "upstreams": deduped_upstreams,
                "replicas": len(replicas),
            }
        )

    return {
        "controller_id": config.controller_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "routes": routes,
    }


def _resolve_worker_upstream_host(worker: WorkerRuntime) -> str | None:
    labels = worker.labels

    for key in ("lb-address", "loadbalancer-address", "public-host", "ingress-host"):
        value = str(labels.get(key, "")).strip()
        if value:
            return value

    endpoint = worker.ref.endpoint.strip()
    if not endpoint:
        return None

    parsed = urlparse(endpoint)
    if parsed.hostname:
        return parsed.hostname

    value = endpoint
    for prefix in ("http://", "https://"):
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    value = value.split("/", 1)[0]
    value = value.split(":", 1)[0]
    return value or None