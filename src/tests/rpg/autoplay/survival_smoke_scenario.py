"""Bundle BJ — deterministic survival autoplay smoke scenario.

This helper runs a tiny end-to-end survival sequence through the real runtime
surfaces added in BA-BI: passive ticks, economy purchase, inventory consumption,
report row generation, and BI artifact enrichment.
"""
from __future__ import annotations

import json
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from app.rpg.interactions.interaction_runtime import resolve_general_interaction
from app.rpg.session.response_builder import build_apply_turn_response
from tests.rpg.autoplay.survival_report_writer_hook import run_autoplay_survival_report_writer_hook

SURVIVAL_SMOKE_SOURCE = "autoplay_survival_smoke_scenario"
DEFAULT_SURVIVAL_SMOKE_ACTIONS = (
    "check my satchel straps",
    "buy water",
    "drink water",
    "travel to the ruined mill",
    "buy rations",
    "eat rations",
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _base_session() -> Dict[str, Any]:
    return {
        "manifest": {
            "id": "session:survival-smoke",
            "title": "Survival Smoke",
            "schema_version": 2,
        },
        "installed_packs": [],
        "simulation_state": {
            "session_id": "session:survival-smoke",
            "survival": {
                "enabled": True,
                "hunger": 55,
                "thirst": 70,
                "fatigue": 20,
                "events": [],
            },
            "player_state": {
                "currency": {"gold": 0, "silver": 1, "copper": 0},
                "inventory": {
                    "items": [],
                    "equipment": {},
                    "carry_capacity": 50,
                },
            },
        },
        "runtime_state": {
            "tick": 0,
            "survival_tick_history": [],
        },
    }


def _authoritative_result(
    *,
    session: Mapping[str, Any],
    player_input: str,
    turn_index: int,
    resolved_result: Mapping[str, Any],
) -> Dict[str, Any]:
    turn_id = f"survival-smoke:{turn_index}"
    return {
        "ok": True,
        "player_input": player_input,
        "authoritative": {
            "turn_id": turn_id,
            "tick": turn_index,
            "resolved_result": dict(_safe_dict(resolved_result)),
            "deterministic_fallback_narration": "The survival smoke turn resolves deterministically.",
        },
        "result": {
            "turn_id": turn_id,
            "tick": turn_index,
            "player_input": player_input,
        },
        "turn_contract": {
            "ok": True,
            "turn_id": turn_id,
            "tick": turn_index,
            "player_input": player_input,
            "resolved_result": dict(_safe_dict(resolved_result)),
        },
        "session": dict(_safe_dict(session)),
    }


def _passive_resolved_result(player_input: str) -> Dict[str, Any]:
    return {
        "ok": True,
        "player_input": player_input,
        "summary": "Passive survival smoke turn.",
        "source": SURVIVAL_SMOKE_SOURCE,
    }


def _resolve_smoke_action(session: Dict[str, Any], player_input: str, turn_index: int) -> Dict[str, Any]:
    lowered = player_input.strip().lower()
    if any(token in lowered for token in ("buy ", "drink", "eat", "rest", "sleep", "make camp")):
        interaction = resolve_general_interaction(
            session["simulation_state"],
            player_input=player_input,
            tick=turn_index,
        )
        return {
            "ok": True,
            "player_input": player_input,
            "general_interaction_result": interaction,
            "interaction_result": _safe_dict(interaction.get("interaction_result")),
            "survival_result": _safe_dict(interaction.get("survival_result")),
            "source": SURVIVAL_SMOKE_SOURCE,
        }
    return _passive_resolved_result(player_input)


def run_survival_smoke_turn(
    session: Dict[str, Any],
    *,
    player_input: str,
    turn_index: int,
) -> Dict[str, Any]:
    session = deepcopy(_safe_dict(session))
    session.setdefault("runtime_state", {})
    session["runtime_state"]["tick"] = turn_index
    resolved = _resolve_smoke_action(session, player_input, turn_index)
    response = build_apply_turn_response(
        _authoritative_result(
            session=session,
            player_input=player_input,
            turn_index=turn_index,
            resolved_result=resolved,
        )
    )
    return response


def run_survival_smoke_sequence(actions: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    session = _base_session()
    rows: List[Dict[str, Any]] = []
    for index, action in enumerate(list(actions or DEFAULT_SURVIVAL_SMOKE_ACTIONS), start=1):
        response = run_survival_smoke_turn(session, player_input=action, turn_index=index)
        session = response["session"]
        rows.append(
            {
                "turn": index,
                "player_input": action,
                "turn_contract": deepcopy(response.get("turn_contract") or {}),
                "result": deepcopy(response.get("result") or {}),
                "survival": deepcopy(
                    _safe_dict(_safe_dict(session.get("simulation_state")).get("survival"))
                ),
                "source": SURVIVAL_SMOKE_SOURCE,
            }
        )
    return {
        "ok": True,
        "session": session,
        "rows": rows,
        "source": SURVIVAL_SMOKE_SOURCE,
    }


def write_survival_smoke_autoplay_artifacts(output_dir: str | Path) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    sequence = run_survival_smoke_sequence()
    transcript_path = output_dir / "survival-smoke-transcript.json"
    transcript_path.write_text(
        json.dumps({"rows": sequence["rows"], "source": SURVIVAL_SMOKE_SOURCE}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    zip_path = output_dir / "autoplay-campaign-results.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "survival-smoke-transcript.json",
            json.dumps({"rows": sequence["rows"], "source": SURVIVAL_SMOKE_SOURCE}, indent=2, sort_keys=True),
        )
    hook_result = run_autoplay_survival_report_writer_hook(
        script_path=Path(__file__),
        argv=["--survival-smoke"],
        exit_code=0,
        results_dir=output_dir,
    )
    return {
        "ok": True,
        "sequence": sequence,
        "transcript_path": str(transcript_path),
        "zip_path": str(zip_path),
        "hook_result": hook_result,
        "source": SURVIVAL_SMOKE_SOURCE,
    }
