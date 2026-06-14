from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from app.rpg.session.turn_memory_common import d


def load_persisted_session(session_id: str) -> dict[str, Any]:
    if not session_id:
        return {}
    try:
        from app.rpg.session import runtime as canonical_runtime

        return d(canonical_runtime.load_runtime_session(session_id))
    except Exception:
        return {}


def save_persisted_session(session: Mapping[str, Any], *, session_id: str) -> bool:
    if not session_id or not isinstance(session, Mapping):
        return False
    try:
        from app.rpg.session import runtime as canonical_runtime

        session_to_save = deepcopy(d(session))
        manifest = d(session_to_save.get("manifest"))
        manifest.setdefault("session_id", session_id)
        manifest.setdefault("id", session_id)
        session_to_save["manifest"] = manifest
        canonical_runtime.save_runtime_session(session_to_save)
        return True
    except Exception:
        return False
