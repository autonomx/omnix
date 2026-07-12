"""Measured foreground RPG turn pipeline shared by all gateway routes."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import Response

from app.rpg.performance_trace import (
    attach_rpg_result_timing,
    build_traced_json_response,
    rpg_pipeline_span,
    rpg_pipeline_trace,
)
from app.rpg.presentation.turn_response import build_turn_response_v2


async def execute_foreground_rpg_turn(
    *,
    session_id: str,
    command: str,
    request: Request,
) -> Response:
    trace_id = getattr(request.state, "rpg_trace_id", None)
    with rpg_pipeline_trace(
        "turn.pipeline",
        session_id=session_id,
        trace_id=trace_id,
        fields={
            "command_chars": len(command),
            "method": request.method,
            "path": request.url.path,
        },
    ) as trace:
        with rpg_pipeline_span("turn.request_received") as span:
            span["content_length"] = request.headers.get("content-length")
            span["submission_id"] = request.headers.get("x-omnix-rpg-submission-id")
            span["client_request_started"] = request.headers.get("x-omnix-rpg-client-started")

        from app.rpg.session import interactive_first_call_runtime

        with rpg_pipeline_span("turn.apply") as span:
            result = await asyncio.to_thread(
                lambda: interactive_first_call_runtime.apply_turn(
                    session_id,
                    command,
                    performance_override={"enable_live_narration_llm": False},
                )
            )
            attach_rpg_result_timing(result)
            span["ok"] = result.get("ok") is True if isinstance(result, dict) else False
            span["turn_id"] = result.get("turn_id") if isinstance(result, dict) else None
            span["interaction_id"] = result.get("interaction_id") if isinstance(result, dict) else None
            span["idempotent_replay"] = result.get("idempotent_replay") is True if isinstance(result, dict) else False

        if not isinstance(result, dict) or result.get("ok") is not True:
            status_code = 404 if isinstance(result, dict) and result.get("error") == "session_not_found" else 400
            raise HTTPException(status_code=status_code, detail=result)

        with rpg_pipeline_span("turn.session_persist") as span:
            session = _persisted_turn_session(result, session_id)
            span["interaction_persisted"] = result.get("interaction_persisted") is True
            span["state_revision"] = result.get("state_revision")
            persistence = result.get("interaction_persistence") if isinstance(result.get("interaction_persistence"), dict) else {}
            span["persistence_mode"] = persistence.get("mode")
            span["snapshot_written"] = persistence.get("snapshot_written") is True

        with rpg_pipeline_span("turn.response_contract_build") as span:
            payload = build_turn_response_v2(
                result,
                session_id=session_id,
                command=command,
                session=session,
                trace_id=trace.trace_id,
            )
            payload_timing = payload.get("timing") if isinstance(payload.get("timing"), dict) else {}
            payload_timing["pipeline_before_encode_ms"] = trace.elapsed_ms
            payload["timing"] = payload_timing
            payload["performance"] = trace.public_summary()
            span["contract_version"] = payload.get("contract_version")
            span["changed_domains"] = (payload.get("state") or {}).get("changed_domains")

        with rpg_pipeline_span("turn.response_send_prepare"):
            return build_traced_json_response(payload)


def _persisted_turn_session(result: dict[str, Any], session_id: str) -> dict[str, Any] | None:
    result_session = result.get("session")
    if result.get("interaction_persisted") is True and isinstance(result_session, dict):
        return result_session
    if isinstance(result_session, dict):
        from app.rpg.session.service import save_session

        return save_session(result_session, compact=True)
    from app.rpg.session.service import load_session

    return load_session(session_id)
