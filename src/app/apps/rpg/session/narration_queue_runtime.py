from __future__ import annotations

# RPG session runtime responsibility module.
from app.apps.rpg.session.state_normalization import (
    _normalize_performance_settings as _normalize_performance_settings,
)
import hashlib as hashlib
from typing import (
    Any as Any, Dict as Dict, List as List, Tuple as Tuple,
)


# Backward compatibility wrapper
# ── Fast-turn performance helpers ─────────────────────────────────────────


def _runtime_compact_save_enabled(runtime_state: dict[str, Any]) -> bool:
    return _normalize_performance_settings(runtime_state)["compact_save"]


__all__ = ["_runtime_compact_save_enabled"]
