"""Generalized Omnix agent/workflow runtime foundations."""

from .capabilities import (
    Capability,
    CapabilityEffect,
    CapabilityExecutionZone,
    CapabilityRegistry,
    CapabilityRisk,
    default_capability_registry,
)
from .contracts import (
    AcceptancePlan,
    AgentApproval,
    AgentArtifact,
    AgentEvent,
    AgentRunCommand,
    AgentRunSnapshot,
    AgentRunSpec,
    EvidenceCoverage,
    ModelRef,
    ResourceScope,
    SuccessCriterion,
    WorkerLease,
)
from .interfaces import AgentRuntime, WorkflowRuntime
from .task_graph import (
    TaskEdge,
    TaskGraph,
    TaskGraphCompilation,
    TaskGraphRunSnapshot,
    TaskNode,
    compile_task_graph,
)
from .task_graph_optimizer import TaskGraphOptimizationPlan, optimize_task_graph
from .task_graph_runtime import PostgresTaskGraphRuntime, default_task_graph_runtime

__all__ = [
    "AcceptancePlan",
    "AgentApproval",
    "AgentArtifact",
    "AgentEvent",
    "AgentRunCommand",
    "AgentRunSnapshot",
    "AgentRunSpec",
    "AgentRuntime",
    "Capability",
    "CapabilityEffect",
    "CapabilityExecutionZone",
    "CapabilityRegistry",
    "CapabilityRisk",
    "EvidenceCoverage",
    "ModelRef",
    "ResourceScope",
    "SuccessCriterion",
    "TaskEdge",
    "TaskGraph",
    "TaskGraphCompilation",
    "TaskGraphOptimizationPlan",
    "TaskGraphRunSnapshot",
    "TaskNode",
    "WorkerLease",
    "WorkflowRuntime",
    "PostgresTaskGraphRuntime",
    "compile_task_graph",
    "default_capability_registry",
    "default_task_graph_runtime",
    "optimize_task_graph",
]
