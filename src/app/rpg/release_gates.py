"""Provider-free structural release gates for the interactive RPG pipeline."""
from __future__ import annotations

import json
from typing import Any, Iterable

from app.rpg.presentation.turn_response import TURN_RESPONSE_MAX_BYTES
from app.rpg.session.interaction_lifecycle import INTERACTION_LIFECYCLE_STATUSES

RELEASE_GATE_VERSION = "rpg_interactive_release_gates_v2"
_FORBIDDEN_FOREGROUND_KEYS = {
    "session",
    "game",
    "simulation_state",
    "runtime_state",
    "foreground_job",
    "first_call_grounding_diagnostics",
    "narration_context",
}
_LEGACY_TRANSCRIPT_KEYS = {
    "transcript",
    "dialogue_history",
    "conversation_history",
    "dialogue_log",
}
_DIALOGUE_MINIMUMS = {
    "direct_answer_rate": 0.95,
    "correct_speaker_rate": 0.99,
    "grounded_specificity_rate": 0.90,
    "continuity_rate": 0.95,
    "candidate_rejection_rate": 1.0,
}
_DIALOGUE_MAXIMUMS = {
    "near_duplicate_rate": 0.05,
    "private_leak_rate": 0.0,
    "empty_line_rate": 0.0,
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
    if sequences != sorted(set(sequences)) or any(sequence <= 0 for sequence in sequences):
        failures.append("interaction_sequence_not_strictly_monotonic")
    if sequences and int(runtime.get("interaction_seq") or 0) < sequences[-1]:
        failures.append("interaction_seq_behind_timeline")
    if sequences and int(runtime.get("state_revision") or 0) < max(int(item.get("state_revision") or 0) for item in events):
        failures.append("state_revision_behind_timeline")
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


def evaluate_migration_release_gates(session: dict[str, Any]) -> dict[str, Any]:
    manifest = session.get("manifest") if isinstance(session.get("manifest"), dict) else {}
    runtime = session.get("runtime_state") if isinstance(session.get("runtime_state"), dict) else {}
    timeline = runtime.get("interaction_timeline") if isinstance(runtime.get("interaction_timeline"), dict) else {}
    failures: list[str] = []

    if int(manifest.get("schema_version") or 0) < 5:
        failures.append("session_schema_before_interaction_migration")
    if timeline.get("format_version") != "rpg_interaction_timeline_v1":
        failures.append("missing_interaction_timeline")
    for container_name, container in (
        ("session", session),
        ("runtime_state", runtime),
        ("simulation_state", session.get("simulation_state")),
        ("state", session.get("state")),
    ):
        if not isinstance(container, dict):
            continue
        leaked = sorted(_LEGACY_TRANSCRIPT_KEYS & set(container))
        if leaked:
            failures.append(f"legacy_transcript_present:{container_name}:{','.join(leaked)}")
    session_report = evaluate_session_release_gates(session)
    failures.extend(item for item in session_report["failures"] if item not in failures)

    return {
        "format_version": RELEASE_GATE_VERSION,
        "ok": not failures,
        "failures": failures,
        "schema_version": int(manifest.get("schema_version") or 0),
        "interaction_count": session_report["interaction_count"],
        "interaction_seq": int(runtime.get("interaction_seq") or 0),
        "state_revision": int(runtime.get("state_revision") or 0),
    }


def evaluate_performance_release_gates(summary: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    attribution = _float(summary.get("attribution_percent"))
    total_ms = _float(summary.get("total_ms"))
    unattributed_ms = _float(summary.get("unattributed_ms"))
    cpu_ms = _float(summary.get("cpu_ms"))
    response_bytes = _int_or_none(summary.get("response_bytes"))

    if attribution < 95.0:
        failures.append("foreground_attribution_below_95_percent")
    if total_ms < 0 or unattributed_ms < 0 or cpu_ms < 0:
        failures.append("negative_performance_measurement")
    if unattributed_ms > total_ms + 0.001:
        failures.append("unattributed_time_exceeds_total")
    if response_bytes is not None and response_bytes > TURN_RESPONSE_MAX_BYTES:
        failures.append("response_exceeds_50kb")

    return {
        "format_version": RELEASE_GATE_VERSION,
        "ok": not failures,
        "failures": failures,
        "attribution_percent": attribution,
        "minimum_attribution_percent": 95.0,
        "total_ms": total_ms,
        "unattributed_ms": unattributed_ms,
        "cpu_ms": cpu_ms,
        "response_bytes": response_bytes,
    }


def evaluate_dialogue_quality_release_gates(report: dict[str, Any]) -> dict[str, Any]:
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    failures: list[str] = []
    for key, minimum in _DIALOGUE_MINIMUMS.items():
        if _float(metrics.get(key)) < minimum:
            failures.append(f"{key}_below_target")
    for key, maximum in _DIALOGUE_MAXIMUMS.items():
        if _float(metrics.get(key)) > maximum:
            failures.append(f"{key}_above_target")
    if int(report.get("accepted_case_count") or 0) < 30:
        failures.append("dialogue_matrix_too_small")
    if report.get("failures"):
        failures.append("dialogue_benchmark_reported_failures")

    return {
        "format_version": RELEASE_GATE_VERSION,
        "ok": not failures,
        "failures": failures,
        "metrics": dict(metrics),
        "minimums": dict(_DIALOGUE_MINIMUMS),
        "maximums": dict(_DIALOGUE_MAXIMUMS),
        "accepted_case_count": int(report.get("accepted_case_count") or 0),
    }


def evaluate_ui_timing_release_gates(snapshot: dict[str, Any]) -> dict[str, Any]:
    client = snapshot.get("client") if isinstance(snapshot.get("client"), dict) else snapshot
    failures: list[str] = []
    interaction_id = str(snapshot.get("interactionId") or snapshot.get("interaction_id") or "").strip()
    commit_to_visible = _optional_float(client.get("commitToVisibleMs") or client.get("commit_to_visible_ms"))
    request_to_visible = _optional_float(client.get("requestToVisibleMs") or client.get("request_to_visible_ms"))

    if not interaction_id:
        failures.append("missing_ui_interaction_identity")
    if commit_to_visible is None:
        failures.append("missing_commit_to_visible_timing")
    elif commit_to_visible > 50.0:
        failures.append("react_commit_to_visible_above_50ms")
    if request_to_visible is not None and request_to_visible < 0:
        failures.append("negative_request_to_visible_timing")

    return {
        "format_version": RELEASE_GATE_VERSION,
        "ok": not failures,
        "failures": failures,
        "interaction_id": interaction_id or None,
        "commit_to_visible_ms": commit_to_visible,
        "maximum_commit_to_visible_ms": 50.0,
        "request_to_visible_ms": request_to_visible,
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


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
