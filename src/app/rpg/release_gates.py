"""Provider-free structural release gates for the interactive RPG pipeline."""
from __future__ import annotations

import json
from typing import Any, Iterable

from app.rpg.presentation.turn_response import TURN_RESPONSE_MAX_BYTES
from app.rpg.session.interaction_lifecycle import INTERACTION_LIFECYCLE_STATUSES

RELEASE_GATE_VERSION = "rpg_interactive_release_gates_v1"
_FORBIDDEN_FOREGROUND_KEYS = {
    "session",
    "game",
    "simulation_state",
    "runtime_state",
    "foreground_job",
    "first_call_grounding_diagnostics",
    "narration_context",
}


def evaluate_turn_response_release_gates(payload: dict[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    visible = payload.get("visible_response") if isinstance(payload.get("visible_response"), dict) else {}
    messages = visible.get("messages") if isinstance(visible.get("messages"), list) else []
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    failures: list[str] = []

    if payload.get("contract_version") != "rpg_turn_response_v2":
        failures.append("wrong_contract_version")
    if len(encoded) > TURN_RESPONSE_MAX_BYTES:
        failures.append("response_exceeds_50kb")
    leaked_keys = sorted(_FORBIDDEN_FOREGROUND_KEYS & set(payload))
    if leaked_keys:
        failures.append(f"foreground_graph_leak:{','.join(leaked_keys)}")
    if not payload.get("interaction_id"):
        failures.append("missing_interaction_id")
    if not str(visible.get("plain_text") or "").strip():
        failures.append("missing_visible_text")
    if "conversation" in (state.get("changed_domains") or []) and not messages and not visible.get("narration"):
        failures.append("conversation_without_visible_response")

    return {
        "format_version": RELEASE_GATE_VERSION,
        "ok": not failures,
        "failures": failures,
        "response_bytes": len(encoded),
        "max_response_bytes": TURN_RESPONSE_MAX_BYTES,
        "interaction_id": payload.get("interaction_id"),
        "changed_domains": list(state.get("changed_domains") or []),
    }


def evaluate_session_release_gates(session: dict[str, Any]) -> dict[str, Any]:
    runtime = session.get("runtime_state") if isinstance(session.get("runtime_state"), dict) else {}
    timeline = runtime.get("interaction_timeline") if isinstance(runtime.get("interaction_timeline"), dict) else {}
    events = [item for item in timeline.get("events", []) if isinstance(item, dict)]
    lifecycles = runtime.get("interaction_lifecycles") if isinstance(runtime.get("interaction_lifecycles"), dict) else {}
    failures: list[str] = []

    sequences = [int(item.get("sequence") or 0) for item in events]
    if sequences != sorted(set(sequences)):
        failures.append("interaction_sequence_not_strictly_monotonic")
    if sequences and int(runtime.get("interaction_seq") or 0) < sequences[-1]:
        failures.append("interaction_seq_behind_timeline")
    if len(events) > 50:
        failures.append("interaction_timeline_unbounded")
    invalid_lifecycles = sorted(
        interaction_id
        for interaction_id, lifecycle in lifecycles.items()
        if not isinstance(lifecycle, dict)
        or lifecycle.get("status") not in INTERACTION_LIFECYCLE_STATUSES
    )
    if invalid_lifecycles:
        failures.append(f"invalid_lifecycle_status:{','.join(invalid_lifecycles)}")

    return {
        "format_version": RELEASE_GATE_VERSION,
        "ok": not failures,
        "failures": failures,
        "interaction_count": len(events),
        "last_interaction_seq": sequences[-1] if sequences else 0,
        "state_revision": int(runtime.get("state_revision") or 0),
        "lifecycle_count": len(lifecycles),
    }


def evaluate_job_transition_release_gates(transitions: Iterable[str]) -> dict[str, Any]:
    values = [str(value) for value in transitions]
    failures: list[str] = []
    terminal_index = next(
        (index for index, value in enumerate(values) if value in {"completed", "failed", "canceled"}),
        None,
    )
    if terminal_index is not None and any(
        value in {"queued", "leased", "running", "waiting", "retrying"}
        for value in values[terminal_index + 1:]
    ):
        failures.append("terminal_job_reopened")
    if values.count("completed") > 1:
        failures.append("job_completed_more_than_once")
    return {
        "format_version": RELEASE_GATE_VERSION,
        "ok": not failures,
        "failures": failures,
        "transitions": values,
    }


def assert_release_gate(report: dict[str, Any]) -> None:
    if report.get("ok") is not True:
        raise AssertionError(";".join(str(value) for value in report.get("failures") or ["release_gate_failed"]))
