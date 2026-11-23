"""Measured foreground RPG turn pipeline shared by all gateway routes."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from typing import Any, cast

from fastapi import HTTPException, Request
from fastapi.responses import Response

from app.apps.rpg.edge.api.traced_response import build_traced_json_response
from app.apps.rpg.foundation import turn_stream
from app.apps.rpg.foundation.performance_trace import (
    attach_rpg_result_timing,
    rpg_pipeline_span,
    rpg_pipeline_trace,
)
from app.apps.rpg.narration.presentation.turn_response import build_turn_response_v2
from app.apps.rpg.foundation.response_trace_headers import finalize_rpg_trace_headers
from app.apps.rpg.foundation.state import access as _sections
from app.apps.rpg.session.jobs.foreground_context import new_submission_id
from app.apps.rpg.session.turn.request import TurnKind, TurnRequest

logger = logging.getLogger(__name__)


def _foreground_delivery_mode(request: Request):
    from app.apps.rpg.narration.narrative_engine import DeliveryMode

    value = str(
        request.headers.get("x-omnix-rpg-delivery-mode") or "blocking"
    ).strip().casefold()
    try:
        return DeliveryMode(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "error": "invalid_rpg_narrative_delivery_mode",
                "allowed": [mode.value for mode in DeliveryMode],
                "received": value,
            },
        ) from exc


@dataclass(frozen=True)
class TurnDelivery:
    """How a turn's answer goes back: the narrative delivery mode, the pipeline trace that times the turn, and
    whether the narration follows the commit on the turn's stream instead of the response (RQ-6.2)."""

    mode: Any
    trace: Any
    narrate_after_commit: bool = False


def turn_request(*, session_id: str, command: str, submission_id: str = "",
                 action: dict[str, Any] | None = None) -> TurnRequest:
    """The turn a caller asks for, built once: its kind is the action's ``turn_kind`` (the player's text when there
    is none), and a turn its caller did not name gets a submission of its own."""
    named = dict(action or {})
    kind = cast(TurnKind, str(named.get("turn_kind") or "player_text"))  # TurnRequest refuses an unknown kind
    return TurnRequest(kind=kind, session_id=session_id,
                       submission_id=submission_id.strip() or new_submission_id(), text=command, action=named)


@contextmanager
def turn_scope(name: str, request: TurnRequest, *, fields: Mapping[str, Any], trace_id: str | None = None,
               drafts: bool = True) -> Iterator[Any]:
    """The scopes a turn runs in, yielding its pipeline trace: one authority snapshot, every model call counted for
    its outcome (RQ-1.3), and with ``drafts`` the narration's draft open under the submission, so the client can
    read it while the turn runs."""
    from app.apps.rpg.foundation.model_calls import counting_model_calls
    from app.apps.rpg.narration.narration_drafts import narration_draft_context
    from app.persistence.authority import authority_snapshot_scope

    with (
        authority_snapshot_scope(),
        narration_draft_context(request.session_id, request.submission_id) if drafts else nullcontext(),
        counting_model_calls(),
        rpg_pipeline_trace(name, session_id=request.session_id, trace_id=trace_id, fields=dict(fields)) as trace,
    ):
        yield trace


async def execute_foreground_rpg_turn(
    *,
    session_id: str,
    command: str,
    request: Request,
    action: dict[str, Any] | None = None,
) -> Response:
    """Run the whole turn on a worker thread.

    Every stage loads or saves the session in PostgreSQL or may call a model,
    so none of it may run on the gateway's event loop (PERF1).
    """
    from app.persistence.errors import RevisionConflict

    try:
        return await asyncio.to_thread(
            _execute_foreground_rpg_turn,
            session_id=session_id,
            command=command,
            request=request,
            action=action,
        )
    except RevisionConflict as exc:
        # Another write won the campaign revision, or the turn would rewrite
        # what it committed (WP-5.6): the client reloads and resubmits.
        raise HTTPException(
            status_code=409,
            detail={
                "ok": False,
                "error": "rpg_state_revision_conflict",
                "session_id": session_id,
                "message": str(exc),
            },
        ) from exc


STORYTELLER_UNAVAILABLE = ("The storyteller is unavailable right now, so the game tells what happens plainly. "
                           "Plain commands still work: look around, go somewhere, talk to someone, buy, attack.")


def submit_rpg_turn(
    *,
    session_id: str,
    command: str,
    submission_id: str,
    source: str,
    action: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A turn submitted from inside Omnix (Hermes, RQ-1.6): the turn route's steps without HTTP, keyed by
    ``submission_id`` like the play screen's. A refused turn returns its detail, with ``status_code``."""
    from app.apps.rpg.narration.narrative_engine import DeliveryMode
    from app.persistence.errors import RevisionConflict

    turn = turn_request(session_id=session_id, command=command, submission_id=submission_id, action=action)
    fields = {"command_chars": len(command), "source": source, "submission_id": turn.submission_id}
    with turn_scope("turn.pipeline", turn, fields=fields, drafts=False) as trace:
        try:
            return run_rpg_turn(turn, TurnDelivery(mode=DeliveryMode.BLOCKING, trace=trace))
        except HTTPException as exc:
            detail = dict(exc.detail) if isinstance(exc.detail, dict) else {"error": str(exc.detail)}
            return {**detail, "ok": False, "status_code": exc.status_code}
        except RevisionConflict as exc:
            return {"ok": False, "error": "rpg_state_revision_conflict", "message": str(exc), "status_code": 409}


def _launch_gate_session(session_id: str) -> dict[str, Any] | None:
    """What the launch gate reads; on PostgreSQL without loading the saved game (WP-5.6)."""
    from app.persistence.runtime import uses_postgresql_runtime

    if uses_postgresql_runtime():
        from app.apps.rpg.session.persistence.session_records import load_launch_gate_source_from_postgres

        return load_launch_gate_source_from_postgres(session_id)
    from app.apps.rpg.session.service import load_session

    return load_session(session_id)


def _execute_foreground_rpg_turn(
    *,
    session_id: str,
    command: str,
    request: Request,
    action: dict[str, Any] | None = None,
) -> Response:
    # The client names its submission, so it can read the narration's draft while the turn runs.
    named_submission = str(request.headers.get("x-omnix-rpg-submission-id") or "").strip()
    turn = turn_request(session_id=session_id, command=command, submission_id=named_submission, action=action)
    delivery_mode = _foreground_delivery_mode(request)
    fields = {
        "command_chars": len(command),
        "method": request.method,
        "path": request.url.path,
        "delivery_mode": delivery_mode.value,
        "submission_id": turn.submission_id,
    }
    with turn_scope("turn.pipeline", turn, fields=fields, trace_id=getattr(request.state, "rpg_trace_id", None),
                    drafts=bool(named_submission)) as trace:
        with rpg_pipeline_span("turn.request_received") as span:
            span["content_length"] = request.headers.get("content-length")
            span["submission_id"] = named_submission or turn.submission_id
            span["client_request_started"] = request.headers.get("x-omnix-rpg-client-started")
            span["delivery_mode"] = delivery_mode.value

        # The play screen follows the turn on its stream: the outcome now, the narration after (RQ-6.2).
        follows_stream = str(request.headers.get("x-omnix-rpg-turn-stream") or "").strip() == "1"
        payload = run_rpg_turn(turn, TurnDelivery(mode=delivery_mode, trace=trace,
                                                  narrate_after_commit=follows_stream))
        with rpg_pipeline_span("turn.response_send_prepare"):
            response = build_traced_json_response(payload)
        finalized_response = finalize_rpg_trace_headers(response, trace)
        finalized_response.headers["X-Omnix-Rpg-Submission-Id"] = turn.submission_id
        return finalized_response


def run_rpg_turn(turn: TurnRequest, delivery: TurnDelivery) -> dict[str, Any]:
    """One player turn (``_run_rpg_turn``), recorded for the operations view (RQ-8.4): a turn the game refuses (a
    4xx) is no failure; one that breaks is recorded as failed and raised."""
    from app.apps.rpg.foundation.model_calls import current_model_failures
    from app.apps.rpg.session.persistence.turn_metrics import record_turn_metric
    from app.persistence.errors import RevisionConflict

    session_id, submission_id, trace = turn.session_id, turn.submission_id, delivery.trace
    try:
        payload = _run_rpg_turn(turn, delivery)
    except HTTPException as exc:
        if exc.status_code >= 500:
            detail: dict[str, Any] = exc.detail if isinstance(exc.detail, dict) else {}
            record_turn_metric(campaign_id=session_id, submission_id=submission_id, turn_class=turn.kind, ok=False,
                               error=str(detail.get("error") or exc.status_code), complete_ms=trace.elapsed_ms,
                               model_failures=current_model_failures())
        raise
    except RevisionConflict:
        raise
    except Exception as exc:
        record_turn_metric(campaign_id=session_id, submission_id=submission_id, turn_class=turn.kind, ok=False,
                           error=type(exc).__name__, complete_ms=trace.elapsed_ms,
                           model_failures=current_model_failures())
        raise
    outcome = raw_outcome if isinstance(raw_outcome := payload.get("outcome"), Mapping) else {}
    calls = raw_model_calls if isinstance(raw_model_calls := outcome.get("model_calls"), Mapping) else {}
    record_turn_metric(campaign_id=session_id, submission_id=submission_id,
                       turn_class=str(outcome.get("planned_action") or outcome.get("kind") or turn.kind), ok=True,
                       degraded_stages=int(payload.get("degraded_stage_count") or 0), complete_ms=trace.elapsed_ms,
                       model_calls=int(calls.get("total") or 0), model_failures=current_model_failures())
    return payload


def _run_rpg_turn(turn: TurnRequest, delivery: TurnDelivery) -> dict[str, Any]:
    """One player turn, from its gates to its response payload: what the turn route and Hermes both run (RQ-1.6).

    The caller holds the turn's scopes (``turn_scope``) and turns the payload into its own response; a refused turn
    raises ``HTTPException`` with the detail the play screen reads. ``turn.action`` names a turn that is not the
    player's text, such as a ``world_tick`` (RQ-2.7). With ``delivery.narrate_after_commit`` a turn the narrative
    writer must narrate returns at its commit, its narration pending, and is narrated beside the request: its
    events reach ``foundation/turn_stream.py`` (RQ-6.2).
    """
    session_id, command, submission_id = turn.session_id, turn.text, turn.submission_id
    from app.apps.rpg.narration.lore_links import taken, taken_quotes

    taken()  # no lore mark of an earlier response in this context links this one (EV-12)
    taken_quotes()  # nor voices its quotes (EV-13)
    with rpg_pipeline_span("turn.campaign_genesis_gate") as span:
        from app.apps.rpg.genesis.forge.launch_readiness import (
            CampaignLaunchBlockedError,
            require_campaign_launch_ready,
        )
        launch_session = _launch_gate_session(session_id)
        if not launch_session:
            raise HTTPException(
                status_code=404,
                detail={
                    "ok": False,
                    "error": "session_not_found",
                    "session_id": session_id,
                },
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

    with rpg_pipeline_span("turn.campaign_ended_gate") as span:
        # A hardcore campaign ends when the hero falls; it plays no more turns (RQ-5.1).
        from app.apps.rpg.rules.combat.stakes import campaign_ended

        ended = campaign_ended(_sections.simulation_state_of(launch_session) or {})
        span["ended"] = bool(ended)
        if ended:
            raise HTTPException(
                status_code=409,
                detail={
                    "ok": False,
                    "error": "rpg_campaign_ended",
                    "session_id": session_id,
                    "reason": str(ended.get("reason") or "ended"),
                    "message": "This hero's story has ended: they fell in a hardcore campaign. "
                               "Start a new campaign to play on.",
                },
            )

    with rpg_pipeline_span("turn.budget_gate") as span:
        from app.apps.rpg.session.turn_budget import TurnBudgetExceeded, require_turn_budget

        try:
            require_turn_budget()
        except TurnBudgetExceeded as exc:
            span["exceeded"] = True
            raise HTTPException(
                status_code=429,
                detail={
                    "ok": False,
                    "error": "rpg_turn_budget_exceeded",
                    "session_id": session_id,
                    "message": str(exc),
                    "limit": exc.limit,
                    "retry_after_seconds": exc.retry_after_seconds,
                },
                headers={"Retry-After": str(exc.retry_after_seconds)},
            ) from exc

    from app.apps.rpg.session import pipeline
    from app.apps.rpg.foundation.llm_priority import foreground_rpg_llm_priority
    from app.apps.rpg.session.jobs.foreground_turn import execute_foreground_turn
    from app.apps.rpg.session.deferred_narration_guard import canonical_presentation_follows_context
    from app.apps.rpg.session.turn.narration_timing import narrating_after_commit
    from app.apps.rpg.session.turn.run import keeping_turn_start

    # One turn of the campaign at a time, in arrival order (RQ-1.4): a second tab's turn waits for this one
    # and then runs on the state it left, instead of being refused.
    turn_stream.publish(turn_stream.stream_key(session_id, submission_id), "accepted", {"submission_id": submission_id})
    with _wait_for_campaign_turn(session_id):
        with rpg_pipeline_span("turn.apply") as span, keeping_turn_start() as turn_start:
            def apply_foreground_turn() -> dict[str, Any]:
                # The narrative engine presents this turn below (``present_authoritative_turn``).
                with foreground_rpg_llm_priority(), canonical_presentation_follows_context(), \
                        narrating_after_commit(delivery.narrate_after_commit):
                    return execute_foreground_turn(pipeline.apply_turn, session_id, command,
                                                   submission_id=submission_id, action=turn.action or None)

            result = apply_foreground_turn()
            attach_rpg_result_timing(result)
            span["ok"] = (
                result.get("ok") is True if isinstance(result, dict) else False
            )
            span["turn_id"] = (
                result.get("turn_id") if isinstance(result, dict) else None
            )
            span["interaction_id"] = (
                result.get("interaction_id") if isinstance(result, dict) else None
            )
            span["idempotent_replay"] = (
                result.get("idempotent_replay") is True
                if isinstance(result, dict)
                else False
            )

        with rpg_pipeline_span("turn.outcome_baseline"):
            # The document the turn started from: TurnOutcome reports what the turn changed against it (RQ-1.3).
            # The pipeline loaded it (upgraded first if stored at an older version, RQ-1.1); else it is read here.
            before_document = turn_start.get("document") or _turn_start_document(session_id)

        if not isinstance(result, dict) or result.get("ok") is not True:
            status_code = (
                404
                if isinstance(result, dict)
                and result.get("error") == "session_not_found"
                else int(result.get("status_code") or 400) if isinstance(result, dict) else 400
            )
            raise HTTPException(status_code=status_code, detail=result)

        stream = turn_stream.stream_key(session_id, submission_id)
        turn_stream.publish(stream, "committed", {"turn_id": result.get("turn_id"),
                                                  "interaction_id": result.get("interaction_id"),
                                                  "revision": result.get("state_revision")})
        if result.get("narration_after_commit") is True:
            # The outcome now; the narration on the stream when the writer is done (RQ-6.2).
            payload = _respond(result, turn, delivery, before_document=before_document)
            payload["visible_response"] = {"plain_text": "", "status": "pending"}
            payload["narration"] = {"status": "pending",
                                    "stream_path": f"/api/rpg/sessions/{session_id}/submissions/{submission_id}/stream"}
            turn_stream.publish(stream, "outcome", {"outcome": payload.get("outcome")})
            _narrate_after_commit(result, turn)
            return payload
        from app.apps.rpg.session.committed_narration import NarrationRefused, narrate_committed_turn

        try:
            result = narrate_committed_turn(result, session_id=session_id, command=command,
                                            delivery_mode=delivery.mode)
        except NarrationRefused as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        payload = _respond(result, turn, delivery, before_document=before_document)
        turn_stream.publish(stream, "outcome", {"outcome": payload.get("outcome")})
        turn_stream.publish(stream, "narration.final", _final(payload))

    return payload


def _respond(result: dict[str, Any], turn: TurnRequest, delivery: TurnDelivery, *,
             before_document: dict[str, Any] | None) -> dict[str, Any]:
    """The turn's response: its contract, with the TurnOutcome against the document it started from."""
    session_id, command, submission_id = turn.session_id, turn.text, turn.submission_id
    delivery_mode, trace = delivery.mode, delivery.trace
    with rpg_pipeline_span("turn.session_persist") as span:
        session = _persisted_turn_session(result, session_id)
        span["interaction_persisted"] = result.get("interaction_persisted") is True
        span["state_revision"] = result.get("state_revision")
        persistence = (
            raw_interaction_persistence if isinstance(raw_interaction_persistence := result.get("interaction_persistence"), dict) else {}
        )
        span["persistence_mode"] = persistence.get("mode")
        span["snapshot_written"] = persistence.get("snapshot_written") is True
        span["canonical_projection_saved"] = (
            result.get("narrative_session_projection_patched") is True
        )

    with rpg_pipeline_span("turn.response_contract_build") as span:
        payload = build_turn_response_v2(
            result,
            session_id=session_id,
            command=command,
            session=session,
            trace_id=trace.trace_id,
        )
        payload["narrative_engine_shadow"] = dict(
            result.get("narrative_engine_shadow") or {}
        )
        if isinstance(result.get("canonical_narrative_response"), dict):
            payload["canonical_narrative_response"] = dict(
                result["canonical_narrative_response"]
            )
        if isinstance(result.get("narrative_projections"), dict):
            payload["narrative_projections"] = dict(
                result["narrative_projections"]
            )
        if isinstance(result.get("narrative_delivery_state"), dict):
            payload["narrative_delivery_state"] = dict(
                result["narrative_delivery_state"]
            )
            payload["narrative_delivery_mode"] = delivery_mode.value
        if isinstance(result.get("narrative_publisher_telemetry"), dict):
            payload["narrative_publisher"] = result.get("narrative_publisher")
            payload["narrative_publisher_telemetry"] = dict(
                result["narrative_publisher_telemetry"]
            )
        if isinstance(result.get("narrative_production_certification"), dict):
            payload["narrative_production_certification"] = dict(
                result["narrative_production_certification"]
            )
            payload["legacy_presentation_ownership_retired"] = True
            payload["legacy_compatibility_fields_source"] = (
                "canonical_projection_only"
            )
        if isinstance(result.get("canonical_narrative_replay"), dict):
            payload["canonical_narrative_replay"] = dict(
                result["canonical_narrative_replay"]
            )
        payload["turn_presentation_request_count"] = result.get(
            "turn_presentation_request_count"
        )
        payload["turn_presentation_response_id"] = result.get(
            "turn_presentation_response_id"
        )
        from app.apps.rpg.narration.narrative_delivery import deferred_public_turn_payload

        payload = deferred_public_turn_payload(payload)
        payload["degraded_stage_count"] = len(result.get("degraded_stages") or ())
        from app.apps.rpg.foundation.model_calls import current_model_calls
        from app.apps.rpg.narration.presentation.turn_outcome import build_turn_outcome
        from app.apps.rpg.narration.presentation.turn_response import attach_turn_outcome

        outcome = build_turn_outcome(
            result,
            before=before_document,
            after=session,
            submission_id=submission_id,
            model_calls=current_model_calls(),
            timings={**(payload.get("timing") or {}), "pipeline_before_encode_ms": trace.elapsed_ms},
        )
        payload = attach_turn_outcome(payload, outcome)
        # Its names that open their lore (EV-12); a turn narrated after its commit is linked when its narration is.
        if isinstance(payload.get("visible_response"), dict) and result.get("narration_after_commit") is not True:
            payload["visible_response"] = _linked(payload["visible_response"], session_id, session,
                                                  revision=result.get("state_revision"))
        from app.apps.rpg.foundation.model_calls import current_model_failures

        if current_model_failures():
            # The provider was down or too slow: the game told the turn plainly, and the player is told why.
            payload["notices"] = [{"kind": "storyteller_unavailable", "message": STORYTELLER_UNAVAILABLE}]
            span["model_failures"] = current_model_failures()
        span["model_calls"] = outcome.model_calls.total
        span["applied_changes"] = len(outcome.applied_changes)
        payload_timing = (
            raw_timing if isinstance(raw_timing := payload.get("timing"), dict) else {}
        )
        payload_timing["pipeline_before_encode_ms"] = trace.elapsed_ms
        payload["timing"] = payload_timing
        payload["performance"] = trace.public_summary()
        span["contract_version"] = payload.get("contract_version")
        span["changed_domains"] = (payload.get("state") or {}).get(
            "changed_domains"
        )
        span["delivery_mode"] = delivery_mode.value
        span["prose_deferred"] = bool(
            payload.get("deferred_narrative_delivery")
        )

    return payload


def _linked(visible: dict[str, Any], session_id: str, document: Any, *, revision: Any) -> dict[str, Any]:
    """The visible response with its lore links, worked out on its final text (EV-12); and the entries it named that
    the hero did not know, proposed as heard of for the next turn (EV-11). Never fails the turn."""
    from app.apps.rpg.narration.lore_links import propose_heard_of, taken, with_links

    try:
        if not (visible.get("narration") or visible.get("messages")):
            return visible
        linked = with_links(visible, document)
        propose_heard_of(session_id, document, linked.get("links") or {}, revision=int(revision or 0))
        return linked
    except Exception:
        logger.warning("rpg_lore_links_failed session=%s", session_id, exc_info=True)
        return visible
    finally:
        taken()  # the response's marks are used up, whatever came of them
        from app.apps.rpg.narration.lore_links import taken_quotes

        taken_quotes()


def _final(payload: Mapping[str, Any]) -> dict[str, Any]:
    canonical = payload.get("canonical_narrative_response")
    return {"visible_response": dict(payload.get("visible_response") or {}),
            "response_id": canonical.get("response_id") if isinstance(canonical, Mapping) else None}


def _narrate_after_commit(result: dict[str, Any], turn: TurnRequest) -> None:
    """Narrate a committed turn beside the request: the writer's drafts reach the stream, and the response is
    inserted with no campaign save; if it fails, the turn stands and the stream says so."""
    import contextvars
    import threading

    session_id, submission_id = turn.session_id, turn.submission_id
    stream = turn_stream.stream_key(session_id, submission_id)

    def narrate() -> None:
        from app.apps.rpg.foundation.persistence.rpg_session_save_policy import rpg_session_save_policy
        from app.apps.rpg.session.committed_narration import narrate_turn_after_commit

        try:
            # The campaign is never saved here (roadmap §4.1 step 10): a session save the narration's grounding
            # asks for is staged, as inside a turn, and nothing commits it.
            with rpg_session_save_policy(defer=True), \
                    turn_scope("turn.narration", turn, fields={"submission_id": submission_id}):
                narrated = narrate_turn_after_commit(result, session_id=session_id, command=turn.text)
            from app.apps.rpg.narration.presentation.turn_response import build_visible_response

            visible = _linked(dict(narrated.result.get("visible_response")
                                   or build_visible_response(narrated.result, turn.text)),
                              session_id, narrated.session, revision=result.get("state_revision"))
            canonical = narrated.result.get("canonical_narrative_response")
            turn_stream.publish(stream, "narration.final", {
                "visible_response": visible,
                "response_id": canonical.get("response_id") if isinstance(canonical, Mapping) else None})
        except Exception as exc:  # the turn has committed: its narration failing is told, not raised
            logger.warning("rpg_turn_narration_after_commit_failed session=%s", session_id, exc_info=True)
            from app.apps.rpg.session.persistence.turn_metrics import record_turn_metric

            record_turn_metric(campaign_id=session_id, submission_id=submission_id, turn_class="narration",
                               ok=False, error=type(exc).__name__)
            turn_stream.publish(stream, "error", {"stage": "narration", "error": type(exc).__name__,
                                                  "message": STORYTELLER_UNAVAILABLE})

    context = contextvars.copy_context()
    threading.Thread(target=context.run, args=(narrate,), name=f"rpg-narration:{session_id}", daemon=True).start()


@contextmanager
def _wait_for_campaign_turn(session_id: str) -> Iterator[None]:
    from app.apps.rpg.session.persistence.turn_order import TurnInProgress, campaign_turn

    try:
        with campaign_turn(session_id):
            yield
    except TurnInProgress as exc:  # only waiting for the turn raises it
        raise HTTPException(
            status_code=409,
            detail={
                "ok": False,
                "error": "rpg_turn_in_progress",
                "session_id": session_id,
                "message": str(exc),
                "retry_after_seconds": 5,
            },
            headers={"Retry-After": "5"},
        ) from exc


def _turn_start_document(session_id: str) -> dict[str, Any] | None:
    from app.persistence.runtime import uses_postgresql_runtime

    if uses_postgresql_runtime():
        from app.apps.rpg.session.persistence.session_records import load_session_from_postgres

        return load_session_from_postgres(session_id)
    from app.apps.rpg.session.service import load_session

    return load_session(session_id)


def _persisted_turn_session(
    result: dict[str, Any],
    session_id: str,
) -> dict[str, Any] | None:
    """The campaign as the turn left it, for the response. The turn's commit step saved it (one save per turn,
    roadmap §4.1); the route saves nothing."""
    result_session = result.get("session")
    if isinstance(result_session, dict):
        return result_session
    from app.apps.rpg.session.service import load_session

    return load_session(session_id)
