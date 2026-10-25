from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict

from app.runtime.paths import rpg_npc_profiles_root
from app.apps.rpg.foundation.safe_values import safe_dict as _safe_dict, safe_str as _safe_str

DEFAULT_PROFILE_ROOT: Path | None = None


def _profile_root() -> Path:
    return DEFAULT_PROFILE_ROOT or rpg_npc_profiles_root()


def safe_npc_profile_filename(npc_id: str) -> str:
    npc_id = _safe_str(npc_id).strip() or "npc_unknown"
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", npc_id)
    safe = safe.strip("._") or "npc_unknown"
    return f"{safe}.json"


def npc_profile_path(npc_id: str) -> Path:
    return _profile_root() / safe_npc_profile_filename(npc_id)


def load_npc_profile(npc_id: str) -> Dict[str, Any]:
    path = npc_profile_path(npc_id)
    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    return _safe_dict(data)
