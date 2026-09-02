"""Single deterministic turn-plan compiler for generalized Agent routing.

SemanticTask describes meaning. TurnPlan combines that meaning with the current
ActiveObjective and RoutingEnvironment exactly once, producing the final lane,
continuity disposition, effective user-authored request, and coarse authority
requirements consumed by both Chat and durable steering.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .active_objective import (
    ActiveObjective,
    RoutingEnvironment,
    normalize_objective_relation,
    objective_resume_replays_prior_request,
)
from .semantic_normalizer import normalize_semantic_task
from .semantic_task import SemanticTask, SemanticTaskCompilation, compile_semantic_task


ContinuityDisposition = Literal[
    "new_objective",
    "continue_objective",
    "revise_objective",
    "replay_objective",
    "response_only_continuation",
]
TurnRunAction = Literal["chat", "start_agent", "steer_agent", "start_task_graph", "steer_task_graph", "clarify"]


class TurnPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    latest_request: str = Field(min_length=1)
    effective_request: str = Field(min_length=1)
    relation: Literal["none", "continue", "resume", "revise"] = "none"
    disposition: ContinuityDisposition = "new_objective"
    lane: Literal["chat", "agent"]
    profile_id: str | None = None
    run_action: TurnRunAction
    active_run_id: str | None = None
    authority_delta: list[str] = Field(default_factory=list)
    semantic_task: SemanticTask
    compilation: SemanticTaskCompilation


def derive_effective_objective(
    previous_objective: str,
    plan: TurnPlan,
) -> str:
    """Derive durable objective text from an already compiled TurnPlan.

    Response-only and replay turns do not change executable objective authority.
    Revisions replace it; continuations append only the effective user-authored
    instruction selected by the TurnPlan.
    """

    previous = str(previous_objective or "").strip()
    current = str(plan.effective_request or "").strip()
    if not previous or plan.disposition == "new_objective":
        return current
    if plan.disposition == "revise_objective":
        return current
    if plan.disposition in {
        "replay_objective",
        "response_only_continuation",
    }:
        return previous
    if plan.disposition == "continue_objective":
        return f"{previous}\nLater steering: {current}"
    return current


def compile_turn_plan(
    latest_user_message: str,
    semantic_task: SemanticTask,
    *,
    active_objective: ActiveObjective | None = None,
    routing_environment: RoutingEnvironment | dict | None = None,
    force_agent: bool = False,
) -> TurnPlan:
    """Compile final turn behavior without granting tool/capability authority."""

    latest = str(latest_user_message or "").strip()
    if not latest:
        raise ValueError("latest user message is required")

    task = normalize_semantic_task(semantic_task)
    compilation = compile_semantic_task(
        latest,
        task,
        routing_environment=routing_environment,
    )
    graph_composite = bool(
        task.ambiguity != "clarification_required"
        and compilation.anomalies
        and all(
            anomaly.code == "unsupported_composite_profiles"
            for anomaly in compilation.anomalies
        )
    )
    if graph_composite:
        # Phase 16 owns this previously fail-closed boundary. The profile-less
        # Agent lane is not executable as a normal Agent run; run_action below
        # forces the dedicated per-node TaskGraph compiler/runtime path.
        compilation = compilation.model_copy(
            update={
                "lane": "agent",
                "requires_clarification": False,
                "reason_code": f"{compilation.reason_code}:task_graph"[:96],
            }
        )
    relation = normalize_objective_relation(latest, task.objective_relation)

    active = (
        active_objective is not None
        and active_objective.status in {"active", "awaiting_user", "blocked"}
    )
    if not active:
        relation = "none"

    active_profile = (
        str(active_objective.profile or "").strip()
        if active_objective is not None
        else ""
    ) or None
    active_task_graph = bool(
        active
        and active_profile == "task-graph"
        and active_objective is not None
        and active_objective.run_id
    )
    profile_compatible = bool(
        active
        and (
            compilation.profile_id is None
            or active_profile is None
            or compilation.profile_id == active_profile
        )
    )

    effective_request = latest
    disposition: ContinuityDisposition = "new_objective"

    if relation == "continue" and active:
        disposition = "continue_objective"
    elif relation == "revise" and active:
        disposition = "revise_objective"
    elif relation == "resume" and active:
        # Replay requires both semantic context-dependence and a strict
        # deterministic confirmation that the latest text delegates its action
        # to prior context. This prevents a parser mislabel such as
        # "Run the focused test again" from discarding a complete latest
        # command, while still allowing opaque requests such as
        # "Try that exact request again" to replay user-authored authority.
        delegates_to_prior = bool(
            task.request_completeness == "context_dependent"
            and objective_resume_replays_prior_request(latest)
        )
        if delegates_to_prior:
            disposition = "replay_objective"
            if task.replay_target == "base_objective":
                effective_request = str(
                    active_objective.base_request
                    or active_objective.canonical_request
                ).strip()
            else:
                effective_request = active_objective.latest_user_request()
        else:
            # A complete retry command remains authoritative as written.
            disposition = "continue_objective"

    final_compilation = compilation
    if (
        active
        and profile_compatible
        and relation != "none"
        and compilation.lane == "chat"
        and not compilation.action_intents
        # A bounded lookup/verify/filter with required governed evidence is a
        # real Chat execution plan, not a response-only continuation.  Do not
        # pull it back onto an active Agent merely because the discourse
        # relation is "continue".
        and compilation.evidence_decision.policy.requirement != "required"
        and not compilation.requires_clarification
        and active_objective is not None
        and active_objective.run_id
        and active_profile is not None
    ):
        disposition = "response_only_continuation"
        final_compilation = compilation.model_copy(
            update={
                "lane": "agent",
                "profile_id": active_profile,
                "reason_code": (
                    f"{compilation.reason_code}:response_only_continuation"
                )[:96],
            }
        )

    if (
        force_agent
        and not final_compilation.requires_clarification
        and final_compilation.lane == "chat"
    ):
        forced_profile = (
            final_compilation.profile_id
            or (
                active_profile
                if active and relation != "none" and active_profile is not None
                else None
            )
            or "research"
        )
        final_compilation = final_compilation.model_copy(
            update={
                "lane": "agent",
                "profile_id": forced_profile,
                "reason_code": (
                    f"{final_compilation.reason_code}:forced_agent_mode"
                )[:96],
            }
        )

    graph_steering = bool(
        active_task_graph
        and relation != "none"
        and (
            graph_composite
            or final_compilation.profile_id is not None
            or bool(final_compilation.action_intents)
            or final_compilation.evidence_decision.policy.requirement == "required"
        )
    )
    if graph_steering and final_compilation.lane != "agent":
        final_compilation = final_compilation.model_copy(
            update={
                "lane": "agent",
                "reason_code": f"{final_compilation.reason_code}:task_graph_steering"[:96],
            }
        )
    if final_compilation.requires_clarification and not graph_composite:
        run_action: TurnRunAction = "clarify"
    elif graph_steering:
        run_action = "steer_task_graph"
    elif graph_composite:
        run_action = "start_task_graph"
    elif final_compilation.lane == "chat":
        run_action = "chat"
    elif active_objective is not None and active_objective.run_id and active:
        run_action = "steer_agent"
    else:
        run_action = "start_agent"

    return TurnPlan(
        latest_request=latest,
        effective_request=effective_request,
        relation=relation,
        disposition=disposition,
        lane=final_compilation.lane,
        profile_id=final_compilation.profile_id,
        run_action=run_action,
        active_run_id=(
            active_objective.run_id
            if active_objective is not None and active
            else None
        ),
        authority_delta=list(final_compilation.action_intents),
        semantic_task=task,
        compilation=final_compilation,
    )


__all__ = [
    "ContinuityDisposition",
    "TurnPlan",
    "TurnRunAction",
    "compile_turn_plan",
    "derive_effective_objective",
]
