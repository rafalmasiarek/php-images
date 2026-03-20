import json
from pathlib import Path

from app.discovery import discover_worker_refs
from app.models import DiscoveryConfig, WorkerRef


def test_discovery_merges_static_and_file(tmp_path: Path) -> None:
    file_path = tmp_path / "workers.json"
    file_path.write_text(
        json.dumps(
            [
                {"name": "worker-b", "endpoint": "http://worker-b:8080"},
                {"name": "worker-c", "endpoint": "http://worker-c:8080"}
            ]
        ),
        encoding="utf-8",
    )

    discovery = DiscoveryConfig(
        static_workers=[WorkerRef(name="worker-a", endpoint="http://worker-a:8080")],
        file_workers_path=str(file_path),
        dns_endpoints=[WorkerRef(name="worker-c", endpoint="http://worker-c:8080", source="dns")],
    )

    workers = discover_worker_refs(discovery)
    endpoints = sorted(worker.endpoint for worker in workers)
    assert endpoints == [
        "http://worker-a:8080",
        "http://worker-b:8080",
        "http://worker-c:8080",
    ]
