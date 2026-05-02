from __future__ import annotations

import threading
from copy import deepcopy
from typing import Any, Dict

from tests.rpg.manual.safe import _safe_dict

# From manual_llm_transcript_old.py


def _thread_label() -> str:
    current = threading.current_thread()
    return f"{current.name}:{current.ident}"


def _manual_service_session_id(scenario_name: str, run_id: str, *, stable: bool = False) -> str:
    base = f"manual_service_{scenario_name}"
    if stable:
        return base
    return f"{base}_{run_id}"


def _reset_manual_session_artifacts(session_id: str) -> None:
    """Best-effort delete of saved session artifacts before a manual scenario.

    The normal/default path uses unique run-scoped IDs, so this is mostly for
    --stable-session-ids runs and for local cleanup safety.
    """
    session_id = str(session_id or "").strip()
    if not session_id:
        return

    candidate_names = {
        f"{session_id}.json",
        f"{session_id}.rpg.json",
        f"{session_id}.session.json",
    }

    from pathlib import Path

    REPO_ROOT = Path(__file__).resolve().parents[3]
    RPG_SESSION_DIRS = [
        REPO_ROOT / "resources" / "data" / "rpg_sessions",
        REPO_ROOT / "data" / "rpg_sessions",
    ]

    for root in RPG_SESSION_DIRS:
        if not root.exists():
            continue
        for name in candidate_names:
            candidate = root / name
            if candidate.exists() and candidate.is_file():
                try:
                    candidate.unlink()
                    print(f"[manual][session] reset saved session artifact: {candidate}", flush=True)
                except Exception as exc:
                    print(
                        f"[manual][session] failed to delete {candidate}: {type(exc).__name__}: {exc}",
                        flush=True,
                    )


def _ensure_manual_session(session_id: str) -> Dict[str, Any]:
    """Ensure a manual scenario session exists before running turns.

    Several focused manual scenarios use unique session IDs. apply_turn(...)
    expects the session to exist, so this helper clones/creates one from the
    manual test template when needed.
    """
    session = _clone_or_create_manual_session(session_id)
    if session:
        return session

    try:
        from app.rpg.session.runtime import apply_turn

        warmup = apply_turn(
            session_id="manual_test_session",
            player_input="I wait",
        )
        template_session = _extract_session(warmup)
        if not template_session:
            return {}

        from app.rpg.session.service import save_session

        cloned = deepcopy(template_session)
        manifest = _safe_dict(cloned.get("manifest"))
        manifest["session_id"] = session_id
        manifest["id"] = f"session:{session_id}"
        manifest["title"] = f"Manual Service Scenario: {session_id}"
        cloned["manifest"] = manifest

        cloned = _sanitize_manual_session_for_test(cloned)
        save_session(cloned)
        return cloned
    except Exception:
        return {}


def _seed_session_currency(session_id: str, currency: Dict[str, Any]) -> bool:
    session = _ensure_manual_session(session_id)
    if not session:
        return False

    session = _sanitize_manual_session_for_test(
        session,
        currency=currency,
        reset_player_items=True,
    )

    try:
        from app.rpg.session.service import save_session
        save_session(session)
    except Exception:
        return False
    return True


def _clone_or_create_manual_session(session_id: str) -> Dict[str, Any]:
    """Create or load a manual scenario session."""
    try:
        from app.rpg.session.service import load_session
        session = _safe_dict(load_session(session_id))
        if session:
            return session
    except Exception:
        pass
    return {}


def _extract_session(result: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(
        result.get("session")
        or _safe_dict(result.get("result")).get("session")
    )


def _sanitize_manual_session_for_test(session: Dict[str, Any], *, currency: Dict[str, Any] = None, reset_player_items: bool = False) -> Dict[str, Any]:
    # Placeholder - need to implement or import from old file
    return session


def _sync_manual_simulation_state(session: Dict[str, Any], simulation_state: Dict[str, Any]) -> None:
    # Placeholder - need to implement or import from old file
    pass


def _save_manual_session_for_test(session: Dict[str, Any], reason: str) -> None:
    # Placeholder - need to implement or import from old file
    pass


def _manual_apply_interaction_seed_fields(session: Dict[str, Any], setup_interaction_state: Dict[str, Any]) -> Dict[str, Any]:
    # Placeholder - need to implement or import from old file
    return session


def _manual_apply_social_seed_fields(session: Dict[str, Any], setup_interaction_state: Dict[str, Any]) -> Dict[str, Any]:
    # Placeholder - need to implement or import from old file
    return session


# Helper functions that might be needed
def _ensure_manual_simulation_roots(session: Dict[str, Any]) -> Dict[str, Any]:
    # Placeholder implementation
    return _safe_dict(session.get("simulation_state")) or {}


def _default_manual_currency() -> Dict[str, int]:
    return {"gold": 0, "silver": 0, "copper": 0}