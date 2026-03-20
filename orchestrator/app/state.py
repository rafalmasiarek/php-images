from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_STATE: dict[str, Any] = {
    "generations": {},
    "allocation_fingerprints": {},
    "last_successful_reconcile_at": None,
    "last_rebalance_at": {},
}


class StateStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return json.loads(json.dumps(DEFAULT_STATE))
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return json.loads(json.dumps(DEFAULT_STATE))
        if not isinstance(data, dict):
            return json.loads(json.dumps(DEFAULT_STATE))
        merged = json.loads(json.dumps(DEFAULT_STATE))
        merged.update(data)
        if not isinstance(merged.get("generations"), dict):
            merged["generations"] = {}
        if not isinstance(merged.get("allocation_fingerprints"), dict):
            merged["allocation_fingerprints"] = {}
        if not isinstance(merged.get("last_rebalance_at"), dict):
            merged["last_rebalance_at"] = {}
        return merged

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def ensure_generation(self, state: dict[str, Any], allocation_id: str, fingerprint: str) -> int:
        generations = state.setdefault("generations", {})
        fingerprints = state.setdefault("allocation_fingerprints", {})

        current_generation = int(generations.get(allocation_id, 0))
        current_fingerprint = str(fingerprints.get(allocation_id, ""))

        if current_generation <= 0:
            current_generation = 1

        if current_fingerprint != fingerprint:
            if current_fingerprint:
                current_generation += 1
            fingerprints[allocation_id] = fingerprint

        generations[allocation_id] = current_generation
        return current_generation
