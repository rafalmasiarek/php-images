# phpctl Orchestrator

A lightweight production-oriented orchestrator for managing PHP-FPM pools across distributed `phpctl` workers.

This component continuously reconciles a **desired state** against the **actual cluster state** reported by workers exposing the `phpctl` HTTP API.

It is designed to be:

- simple to operate
- easy to audit
- compatible with your existing `phpctl`
- safe for failure/recovery scenarios
- capable of healing lost replicas
- capable of discovering new workers dynamically
- capable of controlled rebalancing

---

## Table of Contents

1. Overview
2. Goals
3. Non-goals
4. Architecture
5. Repository Layout
6. Runtime Model
7. Worker Contract
8. Discovery Model
9. Desired State Model
10. Replica Management
11. Scheduling Model
12. Rebalancing Model
13. Failure Handling
14. Drain Handling
15. Returning Worker Handling
16. Generation and Ownership Model
17. Reconcile Loop
18. State File
19. Lock File
20. Configuration Reference
21. File-Based Worker Discovery
22. Static Worker Discovery
23. Config Reload Behavior
24. Rebalance Cooldown
25. Safe Migration Sequence
26. Logging
27. Docker Image
28. Running Locally
29. Running in Production
30. Example Config
31. Example Dynamic Worker File
32. Operational Playbooks
33. Limitations
34. Security Notes
35. phpctl Compatibility Notes

---

## 1. Overview

The orchestrator manages PHP-FPM pool placement on remote workers.

Each worker is expected to run your existing `phpctl` server and expose commands over HTTP. The orchestrator does not SSH into nodes, does not mutate containers directly, and does not require PHP locally. It is a standalone Python control-plane process.

The orchestrator is responsible for:

- discovering workers
- checking worker health
- reading worker identity and capacity
- reading existing PHP-FPM pools
- computing desired placement for allocations and replicas
- creating or updating required pools
- deleting stale pools managed by the orchestrator
- reloading PHP-FPM on workers after changes
- healing lost replicas after worker failure
- gradually rebalancing healthy replicas to better nodes when enabled

---

## 2. Goals

Primary goals:

- work with your current `phpctl` protocol
- keep implementation understandable
- avoid hidden state outside the state file
- allow replicas to be restored automatically after worker loss
- allow adding a new worker without restarting the orchestrator
- avoid aggressive reshuffling unless explicitly enabled
- ensure pool ownership is explicit through metadata
- make stale pool cleanup deterministic after node recovery

---

## 3. Non-goals

This orchestrator does **not** aim to be:

- a full Kubernetes replacement
- a service mesh
- a distributed consensus system
- an HA multi-leader scheduler
- a global load balancer
- a metrics backend
- a secret manager

This is intentionally a **single-controller reconcile loop**.

---

## 4. Architecture

The architecture is split into two parts:

### Workers

Workers are machines or containers running:

- your PHP image
- `phpctl`
- `php-fpm`

Each worker exposes a `phpctl server`.

### Orchestrator

The orchestrator is a separate Python application that:

- reads desired state
- discovers workers
- probes workers
- computes actual state
- computes desired placement
- reconciles the differences

This gives a clear separation:

- **worker** = execution node
- **orchestrator** = control plane

---

## 5. Repository Layout

Expected generated layout:

```text
orchestrator/
├── Dockerfile
├── requirements.txt
├── entrypoint.py
├── app
│   ├── __init__.py
│   ├── config.py
│   ├── discovery.py
│   ├── filters.py
│   ├── locking.py
│   ├── logging_utils.py
│   ├── main.py
│   ├── models.py
│   ├── phpctl_client.py
│   ├── reconcile.py
│   ├── scheduler.py
│   ├── scoring.py
│   └── state.py
├── examples
│   ├── desired-state.json
│   ├── docker-compose.yml
│   └── workers.json
└── tests
    ├── test_filters.py
    ├── test_reconcile.py
    ├── test_scoring.py
    └── test_scheduler.py
```

---

## 6. Runtime Model

The orchestrator supports two modes:

### Once mode

Runs a single reconcile and exits.

Use this for:

- debugging
- CI validation
- manual reconciliation
- smoke testing

Example:

```bash
python -m app.main --config /config/desired-state.json --once
```

### Loop mode

Runs forever and periodically reloads config and worker discovery sources.

Use this for:

- production
- automatic healing
- ongoing balancing
- dynamic worker additions

Example:

```bash
python -m app.main --config /config/desired-state.json --loop
```

---

## 7. Worker Contract

The orchestrator assumes the worker supports these `phpctl` commands:

```text
worker health
worker info
worker capacity
fpm capacity
fpm pool list
fpm pool upsert <name> --params-file <file> --meta ... --enable
fpm pool delete <name>
fpm reload
```

The orchestrator expects `phpctl server` to expose:

```text
POST /run
```

With a request body like:

```json
{
  "argv": ["worker", "info"],
  "output": "json"
}
```

The response envelope is expected to be:

```json
{
  "ok": true,
  "exit_code": 0,
  "stdout": "{\"worker_id\":\"worker-a\"}",
  "stderr": ""
}
```

The orchestrator parses `stdout` as JSON.

---

## 8. Discovery Model

Worker discovery is no longer limited to a static list.

The orchestrator supports a **merged discovery model** where workers can come from multiple sources.

### Discovery sources

Supported sources:

- static workers in config
- file-based workers in a separate JSON file

This allows dynamic cluster changes without restarting the orchestrator.

### Merge behavior

Workers are merged by endpoint.

If the same endpoint appears in multiple discovery sources, the last loaded definition wins.

This lets you combine:

- a baseline static list
- a dynamic file managed by automation

---

## 9. Desired State Model

Desired state is defined in a config file, usually JSON or YAML.

The config contains:

- controller settings
- reconcile interval
- discovery sources
- rebalance settings
- allocations

Each allocation defines:

- allocation id
- replica count
- matching rules
- fallback policy
- pool template/params
- scheduling strategy

---

## 10. Replica Management

Yes — the orchestrator supports **replica count management**.

If an allocation says:

```json
{
  "allocation_id": "api-main",
  "replicas": 3
}
```

then the orchestrator attempts to ensure the cluster has exactly:

```text
api-main-r1
api-main-r2
api-main-r3
```

subject to worker availability and capacity constraints.

### Important

Replica count enforcement is **best effort under capacity constraints**.

If only 2 replicas can fit, the orchestrator will schedule 2 and emit a warning.

It will try again in the next reconcile loop.

---

## 11. Scheduling Model

Scheduling happens per allocation.

### High-level flow

For each allocation:

1. filter eligible workers
2. apply fallback rules if needed
3. check capacity constraints
4. score eligible workers
5. place replicas one by one
6. prefer spreading replicas across workers
7. emit a desired placement plan

### Worker filtering

A worker may be filtered by:

- `worker_id`
- `worker_group`
- labels

### Fallback behavior

If strict matching finds no candidates and:

```json
"fallback_to_free_workers": true
```

then the orchestrator may use any healthy schedulable worker.

### Capacity guards

The scheduler respects:

- `max_pools`
- `max_children_total`
- `max_replicas`

as reported by `phpctl worker capacity` and `phpctl fpm capacity`.

---

## 12. Rebalancing Model

Rebalancing is separate from healing.

This is critical.

### Healing

Healing means:

- a worker disappears
- replicas are lost
- missing replicas are recreated elsewhere

### Rebalancing

Rebalancing means:

- the cluster is healthy
- a better worker becomes available
- some healthy replicas are moved gradually

These must not be conflated.

### Rebalance settings

Rebalancing is controlled by a dedicated config section:

```json
"rebalance": {
  "enabled": true,
  "max_moves_per_reconcile": 1,
  "min_score_improvement": 15,
  "cooldown_seconds": 120
}
```

### Why this matters

Without these controls, the orchestrator could move pools around too aggressively every loop.

The safeguards ensure:

- only a few migrations happen at once
- only meaningful improvements are accepted
- replicas are not moved repeatedly in short intervals

---

## 13. Failure Handling

There are two main failure classes.

### 13.1 Worker disappears unexpectedly

Example causes:

- crash
- network loss
- host failure
- container restart loop
- service stop

When a worker is unreachable or unhealthy:

- it is marked effectively unavailable
- it is excluded from new scheduling in that iteration
- its pools are treated as lost for desired-state purposes
- missing replicas are rescheduled elsewhere if capacity allows

The orchestrator does **not** try to delete anything on the down worker during outage.

That node is not a trusted live source anymore.

### 13.2 Worker is intentionally drained

Example causes:

- maintenance
- node rotation
- migration
- planned decommission

A drained worker remains reachable, but is marked:

```text
status = drain
```

That means:

- no new replicas are scheduled there
- existing replicas may be moved away gradually
- the worker is still readable
- cleanup is still possible

---

## 14. Drain Handling

Worker states:

- `ready`
- `drain`
- `down`

### ready

- worker can receive new replicas

### drain

- worker should not receive new replicas
- existing replicas may be migrated away

### down

- worker is not usable
- worker actual state is ignored for live scheduling

A drained worker is useful for zero-downtime maintenance.

---

## 15. Returning Worker Handling

A very important scenario:

1. worker goes down
2. orchestrator recreates lost replicas elsewhere
3. original worker comes back
4. old pool files still exist on that worker

If not handled properly, this can create stale duplicate state.

The orchestrator solves this using:

- metadata ownership
- allocation id
- replica number
- generation tracking
- desired worker identity metadata

When the old worker returns, the orchestrator compares:

- what is currently desired
- what is currently present on the recovered worker

If the recovered worker still has an old managed pool that is no longer desired there, it is deleted as stale state.

This prevents old replicas from being implicitly reactivated after recovery.

---

## 16. Generation and Ownership Model

Every managed pool should carry metadata.

Example metadata:

```text
managed-by=phpctl-orchestrator
allocation-id=api-main
replica=2
generation=17
worker-id=worker-a
worker-group=blue
desired-worker-id=worker-c
desired-worker-group=blue
strategy=balanced
```

### Meaning

- `managed-by` identifies ownership
- `allocation-id` groups related replicas
- `replica` identifies replica number
- `generation` increments when allocation shape changes
- `worker-id` indicates current target worker identity
- `desired-worker-id` indicates intended placement
- `strategy` records placement mode

### Why generations matter

If allocation configuration changes, the generation increases.

That means old pools can be distinguished from newly desired pools.

This is essential for:

- stale cleanup
- safe migration
- post-recovery reconciliation

---

## 17. Reconcile Loop

Each iteration follows this general sequence:

1. load config
2. load discovery sources
3. merge workers
4. probe worker health
5. read worker identity/capacity
6. read pool lists
7. compute actual cluster state
8. compute desired replicas
9. upsert missing or outdated replicas
10. reload changed target workers
11. delete stale replicas
12. reload cleanup workers
13. persist updated state

### Important ordering

The orchestrator uses a **create-first, delete-later** approach for safe migration:

1. create/update pool on destination worker
2. reload destination worker
3. optionally verify worker is still healthy
4. delete stale pool on source worker
5. reload source worker

This helps reduce service interruption risk.

---

## 18. State File

The orchestrator uses a state file, typically:

```text
/var/lib/php-orchestrator/state.json
```

It stores persistent controller state such as:

- allocation generations
- allocation fingerprints
- last successful reconcile time
- rebalance timestamps per replica
- last seen workers

Example structure:

```json
{
  "generations": {
    "api-main": 3
  },
  "allocation_fingerprints": {
    "api-main": "sha256..."
  },
  "last_successful_reconcile_at": "2026-03-16T10:00:00+00:00",
  "last_rebalance_at": {
    "api-main-r2": "2026-03-16T10:02:00+00:00"
  },
  "last_seen_workers": {
    "worker-a": "2026-03-16T10:00:00+00:00",
    "worker-b": "2026-03-16T10:00:00+00:00"
  }
}
```

### Purpose

The state file enables:

- generation persistence
- config change detection
- rebalance cooldown tracking
- worker observation history

---

## 19. Lock File

The orchestrator uses a lock file to avoid overlapping reconcile runs.

Typical location:

```text
/var/lib/php-orchestrator/reconcile.lock
```

This prevents multiple loops or accidental duplicate invocations from mutating cluster state simultaneously.

---

## 20. Configuration Reference

A full config may look like this:

```json
{
  "controller_id": "phpctl-orchestrator",
  "reconcile_interval_seconds": 15,
  "request_timeout_seconds": 5,
  "state_file": "/var/lib/php-orchestrator/state.json",
  "lock_file": "/var/lib/php-orchestrator/reconcile.lock",
  "discovery": {
    "static_workers": [
      {
        "name": "worker-a",
        "endpoint": "http://worker-a:8080",
        "status": "ready"
      }
    ],
    "file_workers_path": "/config/workers.json"
  },
  "rebalance": {
    "enabled": true,
    "max_moves_per_reconcile": 1,
    "min_score_improvement": 15,
    "cooldown_seconds": 120
  },
  "allocations": [
    {
      "allocation_id": "api-main",
      "replicas": 3,
      "match": {
        "worker_group": "blue",
        "labels": {
          "region": "eu",
          "tier": "prod"
        }
      },
      "fallback_to_free_workers": true,
      "strategy": "balanced",
      "pool": {
        "params": {
          "PM": "dynamic",
          "PM_MAX_CHILDREN": "16",
          "PM_START_SERVERS": "4",
          "PM_MIN_SPARE_SERVERS": "2",
          "PM_MAX_SPARE_SERVERS": "6",
          "ENABLE_PING": "true",
          "ENABLE_METRICS": "true",
          "STATUS_PATH": "/fpm-status",
          "PING_PATH": "/fpm-ping",
          "PING_RESPONSE": "pong"
        }
      }
    }
  ]
}
```

---

## 21. File-Based Worker Discovery

Dynamic worker discovery is supported via a separate JSON file.

Example:

```json
[
  {
    "name": "worker-a",
    "endpoint": "http://worker-a:8080",
    "status": "ready"
  },
  {
    "name": "worker-b",
    "endpoint": "http://worker-b:8080",
    "status": "ready"
  },
  {
    "name": "worker-c",
    "endpoint": "http://worker-c:8080",
    "status": "drain"
  }
]
```

### Operational benefit

This lets you:

- add new workers during runtime
- mark workers as drained
- remove workers from active discovery
- let external automation rewrite worker membership

No orchestrator restart is required.

At the next reconcile loop, the new workers are considered.

---

## 22. Static Worker Discovery

Static workers are defined directly in the main config file.

This is useful for:

- simple deployments
- lab environments
- bootstrap setups
- fallback definitions

Static and file workers are merged together.

---

## 23. Config Reload Behavior

The orchestrator does not rely on an OS file watcher to be useful.

Instead, the simplest and safest behavior is:

- reload the main config file at the beginning of every loop
- reload discovery sources at the beginning of every loop

This means configuration changes become effective automatically on the next iteration.

### Why this is enough in most cases

Because the reconcile interval is usually short, for example:

```json
"reconcile_interval_seconds": 15
```

This gives near-real-time adaptation without extra watcher complexity.

### Optional watcher behavior

A true mtime watcher can be added later, but it is not required for production usefulness.

---

## 24. Rebalance Cooldown

Cooldown prevents constant migrations of the same replica.

If a replica was moved recently, it should not be moved again until the cooldown has passed.

Example:

```json
"cooldown_seconds": 120
```

This means a replica moved now is protected from another move for 120 seconds.

### Why this matters

Without cooldown:

- node additions could cause oscillation
- score changes could trigger repeated movement
- replicas might churn excessively

Cooldown keeps the cluster stable.

---

## 25. Safe Migration Sequence

A healthy replica should not be aggressively torn down before its replacement exists.

Safe migration sequence:

1. upsert replica on destination worker
2. reload destination worker FPM
3. confirm destination worker remains healthy
4. delete stale source replica
5. reload source worker FPM

This is the correct production approach for minimizing service gaps.

---

## 26. Logging

The orchestrator uses structured logging.

By default logs are emitted in JSON format.

Environment variables:

```text
ORCH_LOG_LEVEL=INFO
ORCH_LOG_FORMAT=json
```

Possible formats:

- `json`
- `text`

### Why structured logs are useful

They help with:

- production diagnostics
- central log ingestion
- searching by allocation id
- filtering by worker
- tracing reconcile outcomes

---

## 27. Docker Image

The generated Docker image is Python-based and intentionally small.

Typical base:

```dockerfile
FROM python:3.13-alpine3.23
```

Main runtime features:

- `tini` for signal handling
- Python entrypoint
- no PHP dependency
- no shell wrapper required

---

## 28. Running Locally

Example build:

```bash
docker build -f orchestrator/Dockerfile -t phpctl-orchestrator .
```

Example run:

```bash
docker run --rm \
  -v "$(pwd)/orchestrator/examples/desired-state.json:/config/desired-state.json:ro" \
  phpctl-orchestrator \
  python -m app.main --config /config/desired-state.json --once
```

---

## 29. Running in Production

Recommended production pattern:

- run orchestrator as a separate deployment/service/container
- mount main config read-only
- mount workers discovery file read-only or managed by automation
- persist state directory
- persist lock directory if needed
- run in loop mode

Example:

```bash
python -m app.main --config /config/desired-state.json --loop
```

### Recommended persisted paths

```text
/var/lib/php-orchestrator/state.json
/var/lib/php-orchestrator/reconcile.lock
```

---

## 30. Example Config

Minimal example:

```json
{
  "controller_id": "phpctl-orchestrator",
  "reconcile_interval_seconds": 15,
  "discovery": {
    "static_workers": [
      {
        "name": "worker-a",
        "endpoint": "http://worker-a:8080",
        "status": "ready"
      }
    ]
  },
  "allocations": [
    {
      "allocation_id": "api-main",
      "replicas": 1,
      "pool": {
        "params": {
          "PM_MAX_CHILDREN": "8"
        }
      }
    }
  ]
}
```

---

## 31. Example Dynamic Worker File

Example dynamic file:

```json
[
  {
    "name": "worker-a",
    "endpoint": "http://worker-a:8080",
    "status": "ready"
  },
  {
    "name": "worker-b",
    "endpoint": "http://worker-b:8080",
    "status": "ready"
  }
]
```

To add a new worker at runtime, update the file:

```json
[
  {
    "name": "worker-a",
    "endpoint": "http://worker-a:8080",
    "status": "ready"
  },
  {
    "name": "worker-b",
    "endpoint": "http://worker-b:8080",
    "status": "ready"
  },
  {
    "name": "worker-c",
    "endpoint": "http://worker-c:8080",
    "status": "ready"
  }
]
```

At the next loop, the new worker is eligible for scheduling.

---

## 32. Operational Playbooks

### Add a worker

1. start worker with `phpctl server`
2. add it to `workers.json`
3. wait for next reconcile loop
4. if rebalance is enabled, replicas may gradually move there
5. if rebalance is disabled, it will be used for new healing/placement only

### Drain a worker

1. set worker status to `drain`
2. wait for rebalance/migration loops
3. once pools are gone, stop the worker

### Remove a worker permanently

1. mark it `drain`
2. let replicas migrate
3. remove from discovery source
4. stop the worker

### Recover from worker crash

1. let orchestrator heal replicas elsewhere
2. when worker returns, stale pools are cleaned up automatically if still managed and no longer desired

---

## 33. Limitations

Current limitations include:

- single-controller design
- no built-in leader election
- no native Kubernetes API discovery in the basic version
- no Consul discovery in the basic version
- no DNS-SRV discovery in the basic version
- no advanced rollout policies
- no per-replica live readiness probe beyond worker-level health unless extended
- no external metrics-based autoscaling

These are acceptable tradeoffs for a compact, auditable first production version.

---

## 34. Security Notes

The orchestrator talks to remote `phpctl` servers and can mutate FPM pools.

Because of that:

- workers should not expose `phpctl server` publicly
- network access should be restricted
- Basic Auth should be used if supported in front of the worker
- transport should be protected at network layer or reverse proxy layer
- discovery inputs should be controlled and trusted

This is a control-plane component and should be treated accordingly.

---

## 35. phpctl Compatibility Notes

This orchestrator assumes compatibility with your `phpctl` command surface, especially:

- `worker info`
- `worker health`
- `worker capacity`
- `fpm capacity`
- `fpm pool list`
- `fpm pool upsert`
- `fpm pool delete`
- `fpm reload`

It also assumes pool metadata is preserved using:

```text
; phpctl.meta.<key>=<value>
```

This is essential because the orchestrator relies on those metadata fields for:

- ownership
- stale cleanup
- generation tracking
- replica identification
- migration correctness

If the worker-side `phpctl` behavior changes, the orchestrator may need matching updates.

---

## Summary

This orchestrator is intended to be a practical, production-usable control plane for `phpctl`-managed PHP-FPM workers.

It already covers the core operational needs:

- replica count enforcement
- healing after worker loss
- dynamic worker discovery through merged sources
- controlled rebalance
- safe migration ordering
- stale cleanup after returning nodes
- periodic config reload without restart
- explicit ownership and generation tracking

It is intentionally conservative and predictable, which is exactly what you want from infrastructure that mutates running PHP-FPM topology.