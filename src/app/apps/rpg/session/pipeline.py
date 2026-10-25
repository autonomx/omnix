"""The ordered stages of a turn (RQ-1.4, RQ-2.10): the turn on the pipeline, its commit, and what follows it.

``apply_turn`` is the one way in: the turn route, Hermes and queued turns all reach it through the turn route's
steps (``edge/api/turn_pipeline.py``). The planned-turn stage resolves the turn or refuses it; the commit stage
writes it; the lifecycle stage records its narration after the commit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Protocol

from app.apps.rpg.foundation.performance_trace import current_rpg_pipeline_trace, rpg_pipeline_span
from app.apps.rpg.foundation.debug_logging import log_rpg_event, new_rpg_trace_id, summarize_turn_result


@dataclass(slots=True)
class TurnContext:
    """Mutable data passed through one turn's stages."""

    session_id: str
    player_input: str
    action: dict[str, Any] | None
    session_override: dict[str, Any] | None = None
    result: Any = None
    resolved: bool = False
    trace_id: str = field(default_factory=lambda: new_rpg_trace_id("turn"))
    degraded_stages: list[str] = field(default_factory=list)


class TurnStage(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def optional(self) -> bool: ...

    def run(self, ctx: TurnContext) -> TurnContext: ...


@dataclass(frozen=True, slots=True)
class PlannedTurnStage:
    """Run the turn on the one turn pipeline, or refuse it (RQ-1.4)."""

    name: str = "planned_turn"
    optional: bool = False

    def run(self, ctx: TurnContext) -> TurnContext:
        from app.apps.rpg.session.turn.run import apply_planned_turn_stage

        return apply_planned_turn_stage(ctx)


@dataclass(frozen=True, slots=True)
class InteractionCommitStage:
    """Persist the interaction before any post-commit lifecycle side effects."""

    name: str = "interaction_commit"
    optional: bool = False
    commit_boundary: bool = True

    def run(self, ctx: TurnContext) -> TurnContext:
        from app.apps.rpg.session.interaction_stages import commit_interaction

        return commit_interaction(ctx)


@dataclass(frozen=True, slots=True)
class InteractionLifecycleStage:
    """Record post-commit narration lifecycle and queue optional enrichment."""

    name: str = "interaction_lifecycle"
    optional: bool = True

    def run(self, ctx: TurnContext) -> TurnContext:
        from app.apps.rpg.session.interaction_stages import initialize_lifecycle

        return initialize_lifecycle(ctx)


TURN_PIPELINE: tuple[TurnStage, ...] = (
    PlannedTurnStage(),
    InteractionCommitStage(),
    InteractionLifecycleStage(),
)


def apply_turn(
    session_id: str,
    player_input: str,
    action: dict[str, Any] | None = None,
    *,
    session_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One turn of the campaign through its stages: the result the turn route presents, or a refusal."""
    context = TurnContext(session_id=session_id, player_input=player_input, action=action,
                          session_override=session_override)
    return run_turn_pipeline(context).result


def run_turn_pipeline(
    ctx: TurnContext,
    *,
    stages: tuple[TurnStage, ...] = TURN_PIPELINE,
) -> TurnContext:
    """Run stages in their declared order and report optional degradation."""

    commit_boundary = next(
        (index for index, stage in enumerate(stages) if getattr(stage, "commit_boundary", False)),
        None,
    )
    started_at = perf_counter()
    log_rpg_event(
        "turn.started",
        category="performance",
        session_id=ctx.session_id,
        trace_id=ctx.trace_id,
        fields={
            "player_input": ctx.player_input,
            "player_input_chars": len(str(ctx.player_input or "")),
            "action": ctx.action or {},
            "session_override_present": isinstance(ctx.session_override, dict),
        },
    )
    try:
        if commit_boundary is None:
            ctx = _run_stage_sequence(ctx, stages)
        else:
            from app.persistence.runtime import uses_postgresql_runtime
            from app.apps.rpg.narration.narrative_engine.persistence_policy import (
                narrative_repository_save_policy,
            )
            from app.apps.rpg.foundation.persistence.rpg_session_save_policy import (
                rpg_session_save_policy,
            )

            defer_session_writes = uses_postgresql_runtime()
            with (
                narrative_repository_save_policy(defer=defer_session_writes),
                rpg_session_save_policy(defer=defer_session_writes),
            ):
                ctx = _run_stage_sequence(ctx, stages[: commit_boundary + 1])
            ctx = _run_stage_sequence(ctx, stages[commit_boundary + 1 :])
    except Exception as exc:
        log_rpg_event(
            "turn.exception",
            category="performance",
            level="error",
            session_id=ctx.session_id,
            trace_id=ctx.trace_id,
            duration_ms=(perf_counter() - started_at) * 1000.0,
            fields={"player_input": ctx.player_input, "action": ctx.action or {}},
            error=exc,
            include_traceback=True,
        )
        raise

    summary = summarize_turn_result(ctx.result)
    turn_id = str(summary.get("turn_id") or "") or None
    ok = ctx.result.get("ok") is True if isinstance(ctx.result, dict) else False
    log_rpg_event(
        "turn.completed" if ok else "turn.failed",
        category="performance",
        level="info" if ok else "error",
        session_id=ctx.session_id,
        turn_id=turn_id,
        trace_id=ctx.trace_id,
        duration_ms=(perf_counter() - started_at) * 1000.0,
        fields={"player_input": ctx.player_input, "result": summary},
        error=(
            str(ctx.result.get("error"))
            if isinstance(ctx.result, dict) and ctx.result.get("error")
            else None
        ),
    )
    return ctx


def _run_stage_sequence(
    ctx: TurnContext,
    stages: tuple[TurnStage, ...],
) -> TurnContext:
    for stage in stages:
        try:
            with rpg_pipeline_span(
                f"turn.stage.{stage.name}",
                fields={"stage": stage.name, "optional": stage.optional},
            ):
                next_context = stage.run(ctx)
            if not isinstance(next_context, TurnContext):
                raise TypeError(f"turn stage {stage.name!r} returned a non-context value")
            ctx = next_context
        except Exception as exc:
            if not stage.optional:
                raise
            ctx.degraded_stages.append(stage.name)
            trace = current_rpg_pipeline_trace()
            if trace is not None:
                trace.fields["degraded_stages"] = list(ctx.degraded_stages)
            log_rpg_event(
                "turn.stage.degraded",
                category="performance",
                level="warning",
                session_id=ctx.session_id,
                trace_id=ctx.trace_id,
                fields={
                    "metric": "rpg_turn_stage_degraded",
                    "stage": stage.name,
                    "degraded_stage_count": len(ctx.degraded_stages),
                },
                error=exc,
                include_traceback=True,
            )
    return ctx


__all__ = [
    "TURN_PIPELINE",
    "InteractionCommitStage",
    "InteractionLifecycleStage",
    "PlannedTurnStage",
    "TurnContext",
    "TurnStage",
    "apply_turn",
    "run_turn_pipeline",
]
