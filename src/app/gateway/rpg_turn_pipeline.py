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
from app.rpg.response_trace_headers import finalize_rpg_trace_headers


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

        with rpg_pipeline_span("turn.campaign_genesis_gate") as span:
            from app.rpg.session.genesis.launch_readiness import (
                CampaignLaunchBlockedError,
                require_campaign_launch_ready,
            )
            from app.rpg.session.service import load_session

            launch_session = load_session(session_id)
            if not launch_session:
                raise HTTPException(
                    status_code=404,
                    detail={"ok": False, "error": "session_not_found", "session_id": session_id},
                )
            try:
                gate = require_campaign_launch_ready(launch_session)
            except CampaignLaunchBlockedError as exc:
                span["ready"] = False
                span["error"] = str(exc)
                raise HTTPException(
                    status_code=409,
                    detail={
                        "ok": False,
                        "error": "campaign_genesis_incomplete",
                        "session_id": session_id,
                        "message": str(exc),
                    },
                ) from exc
            span["enabled"] = gate.get("enabled")
            span["ready"] = gate.get("ready")

        from app.rpg.session import interactive_first_call_runtime

        with rpg_pipeline_span("turn.apply") as span:
            result = await asyncio.to_thread(
                lambda: interactive_first_call_runtime.apply_turn(
                    session_id,
                    command,
                    performance_override={
                        "enable_live_narration_llm": True,
                        "narration_mode": "blocking",
                    },
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

        with rpg_pipeline_span("turn.narrative_present") as span:
            from app.rpg.session.turn_presenter import (
                TurnPresentationInvariantError,
                present_authoritative_turn,
            )

            try:
                result = present_authoritative_turn(
                    result,
                    session_id=session_id,
                    player_input=command,
                )
            except TurnPresentationInvariantError as exc:
                span["published"] = False
                span["error"] = str(exc)
                raise HTTPException(
                    status_code=500,
                    detail={
                        "error": "rpg_turn_presentation_invariant_failed",
                        "message": str(exc),
                    },
                ) from exc
            canonical = result.get("canonical_narrative_response") if isinstance(result.get("canonical_narrative_response"), dict) else {}
            span["published"] = bool(canonical)
            span["response_id"] = canonical.get("response_id")
            span["block_count"] = len(canonical.get("blocks") or [])
            span["source"] = result.get("canonical_narrative_source")
            span["request_count"] = result.get("turn_presentation_request_count")

        with rpg_pipeline_span("turn.narrative_consumer_projection") as span:
            from app.rpg.narrative_engine.consumer_publish import attach_canonical_consumer_bundle

            result = attach_canonical_consumer_bundle(result)
            bundle = result.get("narrative_projections") if isinstance(result.get("narrative_projections"), dict) else {}
            publisher = result.get("narrative_publisher_telemetry") if isinstance(result.get("narrative_publisher_telemetry"), dict) else {}
            span["attached"] = bool(bundle)
            span["response_id"] = bundle.get("response_id")
            span["content_hash"] = bundle.get("content_hash")
            span["session_patched"] = result.get("narrative_session_projection_patched") is True
            span["publisher"] = result.get("narrative_publisher")
            span["alternate_publish_count"] = publisher.get("alternate_publish_count")
            span["zero_alternate_publishers"] = publisher.get("zero_alternate_publishers")

        with rpg_pipeline_span("turn.narrative_production_certification") as span:
            from app.rpg.narrative_engine.production_path import (
                NarrativeProductionPathError,
                enforce_production_narrative_result,
            )

            try:
                result = enforce_production_narrative_result(result)
            except NarrativeProductionPathError as exc:
                span["passed"] = False
                span["error"] = str(exc)
                raise HTTPException(
                    status_code=500,
                    detail={
                        "error": "rpg_narrative_production_certification_failed",
                        "message": str(exc),
                    },
                ) from exc
            certification = result.get("narrative_production_certification") if isinstance(result.get("narrative_production_certification"), dict) else {}
            span["passed"] = certification.get("passed") is True
            span["response_id"] = certification.get("response_id")
            span["content_hash"] = certification.get("content_hash")
            span["legacy_ownership_retired"] = result.get("legacy_presentation_ownership_retired") is True

        with rpg_pipeline_span("turn.narrative_shadow") as span:
            from app.rpg.narrative_engine.shadow import attach_shadow_report

            result = attach_shadow_report(result, session_id=session_id, player_input=command)
            shadow = result.get("narrative_engine_shadow") if isinstance(result.get("narrative_engine_shadow"), dict) else {}
            span["selected"] = shadow.get("selected") is True
            span["ok"] = shadow.get("ok") is True
            span["latency_ms"] = shadow.get("latency_ms")
            span["beat_count"] = len(shadow.get("beat_purposes") or [])

        with rpg_pipeline_span("turn.session_persist") as span:
            session = _persisted_turn_session(result, session_id)
            span["interaction_persisted"] = result.get("interaction_persisted") is True
            span["state_revision"] = result.get("state_revision")
            persistence = result.get("interaction_persistence") if isinstance(result.get("interaction_persistence"), dict) else {}
            span["persistence_mode"] = persistence.get("mode")
            span["snapshot_written"] = persistence.get("snapshot_written") is True
            span["canonical_projection_saved"] = result.get("narrative_session_projection_patched") is True

        with rpg_pipeline_span("turn.response_contract_build") as span:
            payload = build_turn_response_v2(
                result,
                session_id=session_id,
                command=command,
                session=session,
                trace_id=trace.trace_id,
            )
            payload["narrative_engine_shadow"] = dict(result.get("narrative_engine_shadow") or {})
            if isinstance(result.get("canonical_narrative_response"), dict):
                payload["canonical_narrative_response"] = dict(result["canonical_narrative_response"])
            if isinstance(result.get("narrative_projections"), dict):
                payload["narrative_projections"] = dict(result["narrative_projections"])
            if isinstance(result.get("narrative_publisher_telemetry"), dict):
                payload["narrative_publisher"] = result.get("narrative_publisher")
                payload["narrative_publisher_telemetry"] = dict(result["narrative_publisher_telemetry"])
            if isinstance(result.get("narrative_production_certification"), dict):
                payload["narrative_production_certification"] = dict(result["narrative_production_certification"])
                payload["legacy_presentation_ownership_retired"] = True
                payload["legacy_compatibility_fields_source"] = "canonical_projection_only"
            payload["turn_presentation_request_count"] = result.get("turn_presentation_request_count")
            payload["turn_presentation_response_id"] = result.get("turn_presentation_response_id")
            payload_timing = payload.get("timing") if isinstance(payload.get("timing"), dict) else {}
            payload_timing["pipeline_before_encode_ms"] = trace.elapsed_ms
            payload["timing"] = payload_timing
            payload["performance"] = trace.public_summary()
            span["contract_version"] = payload.get("contract_version")
            span["changed_domains"] = (payload.get("state") or {}).get("changed_domains")

        with rpg_pipeline_span("turn.response_send_prepare"):
            response = build_traced_json_response(payload)
        return finalize_rpg_trace_headers(response, trace)


def _persisted_turn_session(result: dict[str, Any], session_id: str) -> dict[str, Any] | None:
    result_session = result.get("session")
    canonical_patch = result.get("narrative_session_projection_patched") is True
    if isinstance(result_session, dict) and (
        canonical_patch or result.get("interaction_persisted") is not True
    ):
        from app.rpg.session.service import save_session

        return save_session(result_session, compact=True)
    if result.get("interaction_persisted") is True and isinstance(result_session, dict):
        return result_session
    from app.rpg.session.service import load_session

    return load_session(session_id)
