"""Phase 18.0 — Unified GM tooling payload."""
from __future__ import annotations

from typing import Any, Dict

from app.rpg.presentation.memory_inspector import build_memory_inspector_payload
from app.rpg.presentation.visual_inspector import build_visual_inspector_payload


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def build_gm_tooling_payload(
    simulation_state: Dict[str, Any],
    *,
    queue_jobs: list | None = None,
    asset_manifest: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    return {
        "visuals": build_visual_inspector_payload(
            simulation_state,
            queue_jobs=queue_jobs or [],
            asset_manifest=asset_manifest or {"assets": {}},
        ),
        "memory": build_memory_inspector_payload(simulation_state),
        "operations": {
            "visual_inspector_route": "/api/rpg/visual/inspector",
            "memory_reinforce_route": "/api/rpg/memory/reinforce",
            "memory_decay_route": "/api/rpg/memory/decay",
            "queue_normalize_route": "/api/rpg/visual/queue/normalize",
            "queue_run_one_route": "/api/rpg/visual/queue/run_one",
            "queue_prune_route": "/api/rpg/visual/queue/prune",
            "asset_cleanup_route": "/api/rpg/visual/assets/cleanup",
            "session_export_route": "/api/rpg/session/export_package",
            "session_import_route": "/api/rpg/session/import_package",
        },
    }
