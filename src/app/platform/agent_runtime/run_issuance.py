"""Issuing a run's authority: the one way a spec becomes something a run may be created with.

A run is created only with an ``IssuedRunSpec``. ``issue_run_spec`` issues a new top-level run (or a superseding
revision): the process's policy first (model fidelity, quality sizing), then the default limits, then the authority
checks. ``issue_child_spec`` issues a child from its request, narrowed to the parent (``subagents.derive_child_spec``)
and then checked the same way. ``bind_run_workspace`` binds the GitHub authority and prepares the workspace of an
issued spec. The checks are the service's, so a subclass's stricter check applies to every path.

Profiles are ceilings, and a child never holds what its parent does not: issuing only narrows.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .budget import apply_default_run_limits
from .contracts import AgentRunSnapshot, AgentRunSpec, IssuedRunSpec, WorkspaceSpec

if TYPE_CHECKING:
    from .service_core import AgentRunService
    from .subagents import ChildRunRequest


def issue_run_spec(service: AgentRunService, spec: AgentRunSpec) -> IssuedRunSpec:
    """The spec a new top-level run, or a superseding revision, is persisted with."""
    return _checked(service, apply_default_run_limits(service._prepare_start_spec(spec)))


def issue_child_spec(
    service: AgentRunService,
    parent: AgentRunSnapshot,
    request: ChildRunRequest,
    *,
    workspace_override: WorkspaceSpec | None = None,
    run_id: str | None = None,
) -> IssuedRunSpec:
    """The spec a child of ``parent`` is persisted with: narrowed to the parent and the child's profile, then
    checked. ``run_id`` names a child whose identity is decided by its caller (a reviewer's retry slot)."""
    from .subagents import derive_child_spec

    child = derive_child_spec(parent, request, workspace_override=workspace_override)
    if run_id is not None:
        child = child.model_copy(update={"run_id": run_id})
    return _checked(service, child)


def bind_run_workspace(service: AgentRunService, spec: IssuedRunSpec) -> IssuedRunSpec:
    """An issued spec with its GitHub authority bound and its workspace prepared."""
    return IssuedRunSpec(service._prepare_workspace(service._bind_github_repository_authority(spec)))


def _checked(service: AgentRunService, spec: AgentRunSpec) -> IssuedRunSpec:
    service._validate_run_spec_authority(spec)
    service._validate_evidence_authority(spec)
    return IssuedRunSpec(spec)


__all__ = ["bind_run_workspace", "issue_child_spec", "issue_run_spec"]
