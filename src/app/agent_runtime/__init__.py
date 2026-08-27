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
    ModelRef,
    ResourceScope,
    SuccessCriterion,
    WorkerLease,
)
from .interfaces import AgentRuntime, WorkflowRuntime

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
    "ModelRef",
    "ResourceScope",
    "SuccessCriterion",
    "WorkerLease",
    "WorkflowRuntime",
    "default_capability_registry",
]
