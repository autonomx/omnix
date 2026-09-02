"""Deterministic multi-profile TaskGraph contracts and compiler.

The semantic parser may describe meaning. This module compiles that meaning into
per-node authority envelopes. The graph coordinator itself has no capability
union and cannot execute user actions outside a node envelope.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts import (
    AcceptancePlan,
    AgentApprovalPolicy,
    EvidencePolicy,
    ModelRef,
    ResourceScope,
    RunLimits,
    SuccessCriterion,
    WorkspaceSpec,
)
from .evidence import EvidenceCompilationError, capability_for_requirement, compile_task_authority
from .profiles import get_agent_profile, resolve_profile_capabilities
from .semantic_task import (
    SemanticDataDependency,
    SemanticOperation,
    SemanticSubject,
    SemanticTask,
    compile_semantic_task,
)


TaskNodeKind = Literal[
    "evidence_read",
    "agent",
    "capability",
    "condition",
    "approval",
    "join",
]
TaskEdgeKind = Literal["data", "control", "condition", "approval"]
TaskNodeRunStatus = Literal[
    "pending",
    "ready",
    "running",
    "waiting_for_approval",
    "completed",
    "failed",
    "cancelled",
    "skipped",
]
TaskGraphRunStatus = Literal[
    "queued",
    "running",
    "waiting_for_approval",
    "completed",
    "failed",
    "cancelled",
]


_TARGET_PROFILE: dict[str, str] = {
    "workspace": "coding",
    "repository": "coding",
    "repository_ci": "coding",
    "operations": "ops",
    "home": "house",
    "home_energy": "house",
    "email": "personal-assistant",
    "calendar": "personal-assistant",
    "contacts": "personal-assistant",
    "market": "trading-research",
    "market_quote": "trading-research",
    "market_filing": "trading-research",
    "market_status": "trading-research",
    "weather": "research",
    "software_release": "research",
    "public_web": "research",
}

_MUTATING_ACTIONS = {
    "workspace_mutate",
    "workspace_execute",
    "ops_execute",
    "home_mutate",
    "email_send",
    "email_draft",
    "calendar_create",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TaskNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=120)
    kind: TaskNodeKind = "agent"
    profile_id: str | None = None
    objective: str = ""
    semantic_targets: list[str] = Field(default_factory=list)
    semantic_action_intents: list[str] = Field(default_factory=list)
    required_local_capabilities: list[str] = Field(default_factory=list)
    required_external_capabilities: list[str] = Field(default_factory=list)
    resource_scopes: list[ResourceScope] = Field(default_factory=list)
    evidence_policy: EvidencePolicy = Field(default_factory=EvidencePolicy)
    success_criteria: list[SuccessCriterion] = Field(default_factory=list)
    acceptance_plan: AcceptancePlan | None = None
    approval_policy: AgentApprovalPolicy = "ask_sensitive"
    workspace: WorkspaceSpec | None = None
    model: ModelRef | None = None
    limits: RunLimits = Field(default_factory=RunLimits)
    capability_id: str | None = None
    input_template: dict[str, Any] = Field(default_factory=dict)
    condition: str | None = None
    output_keys: list[str] = Field(default_factory=lambda: ["result"])
    optional: bool = False
    estimated_cost: float = Field(default=1.0, ge=0.0)
    cacheable: bool = False

    @model_validator(mode="after")
    def validate_node_authority(self) -> "TaskNode":
        if self.kind in {"agent", "evidence_read"}:
            if not self.profile_id or self.model is None:
                raise ValueError("agent/evidence_read node requires profile_id and model")
            profile = get_agent_profile(self.profile_id)
            resolve_profile_capabilities(
                profile,
                requested=list(self.required_local_capabilities),
                requested_external=list(self.required_external_capabilities),
            )
            if profile.requires_workspace and self.workspace is None:
                raise ValueError(f"node profile {profile.id} requires workspace")
            if not profile.requires_workspace and self.workspace is not None:
                raise ValueError(f"node profile {profile.id} cannot receive workspace")
        if self.kind == "capability" and not self.capability_id:
            raise ValueError("capability node requires capability_id")
        if self.kind == "condition" and not self.condition:
            raise ValueError("condition node requires condition")
        if self.kind in {"join", "approval"} and (
            self.required_local_capabilities or self.required_external_capabilities
        ):
            raise ValueError(f"{self.kind} node cannot carry action authority")
        return self


class TaskEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str
    target: str
    kind: TaskEdgeKind = "control"
    source_output: str | None = None
    target_input: str | None = None
    expected_value: Any | None = None


class TaskGraph(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    graph_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    revision: int = Field(default=1, ge=1)
    user_request_digest: str
    nodes: list[TaskNode]
    edges: list[TaskEdge] = Field(default_factory=list)
    output_contract: dict[str, Any] = Field(default_factory=dict)
    max_parallel_nodes: int = Field(default=4, ge=1, le=32)
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_graph(self) -> "TaskGraph":
        node_ids = [node.id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("task graph node ids must be unique")
        known = set(node_ids)
        for edge in self.edges:
            if edge.source not in known or edge.target not in known:
                raise ValueError("task graph edge references unknown node")
            if edge.source == edge.target:
                raise ValueError("task graph self-edge is not allowed")

        incoming: dict[str, set[str]] = {node_id: set() for node_id in known}
        outgoing: dict[str, set[str]] = {node_id: set() for node_id in known}
        for edge in self.edges:
            incoming[edge.target].add(edge.source)
            outgoing[edge.source].add(edge.target)
        ready = [node_id for node_id, sources in incoming.items() if not sources]
        visited: list[str] = []
        while ready:
            current = ready.pop()
            visited.append(current)
            for target in outgoing[current]:
                incoming[target].discard(current)
                if not incoming[target]:
                    ready.append(target)
        if len(set(visited)) != len(known):
            raise ValueError("task graph must be acyclic")
        return self


class TaskGraphCompilerAnomaly(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    detail: str


class TaskGraphCompilation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    graph: TaskGraph | None = None
    anomalies: list[TaskGraphCompilerAnomaly] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.graph is not None and not self.anomalies


class TaskNodeRunState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str
    status: TaskNodeRunStatus = "pending"
    attempts: int = Field(default=0, ge=0)
    child_run_id: str | None = None
    output: dict[str, Any] = Field(default_factory=dict)
    last_error: str | None = None
    fingerprint: str
    started_at: datetime | None = None
    completed_at: datetime | None = None


class TaskGraphRunSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    graph: TaskGraph
    status: TaskGraphRunStatus = "queued"
    revision: int = Field(default=1, ge=1)
    node_states: list[TaskNodeRunState] = Field(default_factory=list)
    last_error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None


class TaskGraphEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    run_id: str
    sequence: int | None = None
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


def task_node_fingerprint(node: TaskNode) -> str:
    """Hash all semantics that make a completed node safe to reuse."""

    payload = node.model_dump(mode="json", exclude={"id"})
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _request_digest(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _profile_for_target(target: str) -> str | None:
    return _TARGET_PROFILE.get(target)


def _effective_profile_map(task: SemanticTask) -> dict[str, str]:
    profiles = {
        profile
        for target in [
            *[item.target for item in task.subjects],
            *[item.target for item in task.operations],
            *[item.target for item in task.data_dependencies],
        ]
        if (profile := _profile_for_target(target)) is not None
    }
    # Trading research includes governed public-web research. Keep market+web
    # work in one least-privilege trading node rather than creating a redundant
    # research node with overlapping web authority.
    collapse_research = "trading-research" in profiles and "research" in profiles
    result: dict[str, str] = {}
    for target, profile in _TARGET_PROFILE.items():
        result[target] = (
            "trading-research"
            if collapse_research and profile == "research"
            else profile
        )
    return result


def _subtask_for_profile(
    task: SemanticTask,
    profile_id: str,
    profile_map: dict[str, str],
) -> SemanticTask:
    subjects = [
        item for item in task.subjects
        if profile_map.get(item.target) == profile_id
    ]
    operations = [
        item for item in task.operations
        if profile_map.get(item.target) == profile_id
    ]
    dependencies = [
        item for item in task.data_dependencies
        if profile_map.get(item.target) == profile_id
    ]
    return task.model_copy(
        update={
            "subjects": subjects,
            "operations": operations,
            "data_dependencies": dependencies,
            "ambiguity": "none",
            "candidate_interpretations": [],
        }
    )


def _node_objective(
    latest_user_message: str,
    profile_id: str,
    subtask: SemanticTask,
) -> str:
    targets = sorted({
        item.target
        for item in [*subtask.subjects, *subtask.operations, *subtask.data_dependencies]
    })
    scope = ", ".join(targets) or profile_id
    return (
        f"Complete only the {profile_id} portion of the user's request. "
        f"Authority scope: {scope}.\n\nUser request:\n{latest_user_message}"
    )



def _resource_scopes_for_policy(
    policy: EvidencePolicy,
    required_external: tuple[str, ...],
) -> list[ResourceScope]:
    """Bind only resource identities that map safely to broker input fields."""

    allowed = set(required_external)
    scopes: list[ResourceScope] = []
    seen: set[tuple[str, str, str]] = set()
    for requirement in policy.requirements:
        subject = requirement.subject
        if subject is None:
            continue
        try:
            capability, _trust = capability_for_requirement(requirement)
        except EvidenceCompilationError:
            continue
        if capability not in allowed:
            continue

        resource_type: str | None = None
        resource_id: str | None = None
        if subject.type == "security":
            ticker = str(subject.qualifiers.get("ticker") or "").strip()
            if ticker:
                resource_type = "ticker"
                resource_id = ticker
        elif subject.type == "location":
            location = str(subject.display_name or subject.canonical_id or "").strip()
            if location:
                resource_type = "location"
                resource_id = location

        if not resource_type or not resource_id:
            continue
        key = (capability, resource_type, resource_id.casefold())
        if key in seen:
            continue
        seen.add(key)
        scopes.append(
            ResourceScope(
                capability=capability,
                resource_type=resource_type,
                resource_id=resource_id,
            )
        )
    return scopes

def compile_task_graph(
    latest_user_message: str,
    task: SemanticTask,
    *,
    model: ModelRef,
    workspace: WorkspaceSpec | None = None,
    routing_environment: Any | None = None,
    max_parallel_nodes: int = 4,
) -> TaskGraphCompilation:
    """Compile a SemanticTask into independent per-profile authority nodes."""

    if task.ambiguity == "clarification_required":
        return TaskGraphCompilation(
            anomalies=[
                TaskGraphCompilerAnomaly(
                    code="clarification_required",
                    detail="ambiguous semantic task cannot compile into execution graph",
                )
            ]
        )

    profile_map = _effective_profile_map(task)
    ordered_profiles: list[str] = []
    operation_profile_order: list[str] = []
    for operation in task.operations:
        profile = profile_map.get(operation.target)
        if profile is not None:
            operation_profile_order.append(profile)
            if profile not in ordered_profiles:
                ordered_profiles.append(profile)
    for dependency in task.data_dependencies:
        profile = profile_map.get(dependency.target)
        if dependency.required and profile is not None and profile not in ordered_profiles:
            ordered_profiles.append(profile)
    for subject in task.subjects:
        profile = profile_map.get(subject.target)
        if profile is not None and profile not in ordered_profiles:
            ordered_profiles.append(profile)

    if not ordered_profiles:
        return TaskGraphCompilation(
            anomalies=[
                TaskGraphCompilerAnomaly(
                    code="no_executable_graph_nodes",
                    detail="semantic task contains no profile-bound work",
                )
            ]
        )

    anomalies: list[TaskGraphCompilerAnomaly] = []
    nodes: list[TaskNode] = []
    profile_node: dict[str, TaskNode] = {}
    for index, profile_id in enumerate(ordered_profiles, start=1):
        subtask = _subtask_for_profile(task, profile_id, profile_map)
        compilation = compile_semantic_task(
            latest_user_message,
            subtask,
            routing_environment=routing_environment,
        )
        unsafe = [
            row for row in compilation.anomalies
            if row.code != "unsupported_composite_profiles"
        ]
        if compilation.requires_clarification or unsafe:
            anomalies.extend(
                TaskGraphCompilerAnomaly(code=row.code, detail=row.detail)
                for row in unsafe
            )
            if compilation.requires_clarification and not unsafe:
                anomalies.append(
                    TaskGraphCompilerAnomaly(
                        code="node_compilation_requires_clarification",
                        detail=f"profile {profile_id} could not compile safely",
                    )
                )
            continue

        profile = get_agent_profile(profile_id)
        node_workspace = workspace if profile.requires_workspace else None
        if profile.requires_workspace and node_workspace is None:
            anomalies.append(
                TaskGraphCompilerAnomaly(
                    code="required_workspace_unavailable",
                    detail=f"profile {profile_id} requires a workspace",
                )
            )
            continue

        try:
            authority = compile_task_authority(
                profile,
                latest_user_message,
                compilation.evidence_decision,
                semantic_action_intents=compilation.action_intents,
                allow_text_semantic_fallback=False,
            )
        except EvidenceCompilationError as exc:
            anomalies.append(
                TaskGraphCompilerAnomaly(code=exc.code, detail=str(exc))
            )
            continue

        read_only = (
            bool(compilation.action_intents)
            and not set(compilation.action_intents).intersection(_MUTATING_ACTIONS)
        )
        node_kind: TaskNodeKind = (
            "evidence_read"
            if read_only and compilation.evidence_decision.policy.requirement == "required"
            else "agent"
        )
        node = TaskNode(
            id=f"{profile_id}-{index}",
            kind=node_kind,
            profile_id=profile_id,
            objective=_node_objective(latest_user_message, profile_id, subtask),
            semantic_targets=sorted({
                item.target
                for item in [*subtask.subjects, *subtask.operations, *subtask.data_dependencies]
            }),
            semantic_action_intents=list(compilation.action_intents),
            required_local_capabilities=list(authority.required_local),
            required_external_capabilities=list(authority.required_external),
            resource_scopes=_resource_scopes_for_policy(
                compilation.evidence_decision.policy,
                authority.required_external,
            ),
            evidence_policy=compilation.evidence_decision.policy,
            success_criteria=[
                SuccessCriterion(
                    id=f"{profile_id}-complete",
                    description=f"Complete the {profile_id} scoped portion of the user request.",
                )
            ],
            approval_policy="ask_sensitive",
            workspace=node_workspace,
            model=model,
            cacheable=read_only,
            estimated_cost=(
                0.5 if node_kind == "evidence_read" else 1.0
            ),
        )
        nodes.append(node)
        profile_node[profile_id] = node

    if anomalies:
        return TaskGraphCompilation(anomalies=anomalies)

    edges: list[TaskEdge] = []
    if task.multi_step:
        first_position: dict[str, int] = {}
        for position, profile_id in enumerate(operation_profile_order):
            first_position.setdefault(profile_id, position)
        for target_profile, target_node in profile_node.items():
            if not set(target_node.semantic_action_intents).intersection(_MUTATING_ACTIONS):
                continue
            target_position = first_position.get(target_profile, 10_000)
            for source_profile, source_node in profile_node.items():
                if source_profile == target_profile:
                    continue
                source_position = first_position.get(source_profile, 10_000)
                if source_position < target_position:
                    edges.append(
                        TaskEdge(
                            source=source_node.id,
                            target=target_node.id,
                            kind="data",
                            target_input=f"{source_node.id}.result",
                        )
                    )

    if len(nodes) > 1:
        join = TaskNode(
            id="join-results",
            kind="join",
            objective="Aggregate completed node outputs without acquiring new authority.",
            output_keys=["result"],
        )
        nodes.append(join)
        for node in nodes:
            if node.id == join.id:
                continue
            edges.append(TaskEdge(source=node.id, target=join.id, kind="data"))

    graph = TaskGraph(
        user_request_digest=_request_digest(latest_user_message),
        nodes=nodes,
        edges=edges,
        output_contract={"result_node": "join-results" if len(nodes) > 1 else nodes[0].id},
        max_parallel_nodes=max_parallel_nodes,
    )
    return TaskGraphCompilation(graph=graph)
