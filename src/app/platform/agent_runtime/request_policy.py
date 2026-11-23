"""Validate public run requests against operator and profile authority ceilings."""
from __future__ import annotations
from app.config.env import env_str as _env_str

import os
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Iterable

from app.capabilities.approval_policy import is_approval_policy, only_tightens

from .profiles import AgentProfile

_ISOLATION_STRENGTH = {
    "supervised_worktree": 0, "immutable_review_snapshot": 0,
    "docker_strong": 1, "unattended": 1,
}


def validate_request_policy(
    profile: AgentProfile, *, approval_policy: str,
    isolation_policy: str, allowed_paths: Iterable[str],
) -> None:
    ceiling = profile.approval_policy
    if not is_approval_policy(approval_policy) or not is_approval_policy(ceiling):
        raise ValueError("unknown approval policy")
    if not only_tightens(approval_policy, ceiling):
        raise ValueError("approval policy may only tighten the profile default")
    if isolation_policy not in _ISOLATION_STRENGTH:
        raise ValueError("unknown isolation policy")
    if isolation_policy == "immutable_review_snapshot" and profile.id != "coding-reviewer":
        raise ValueError("immutable review isolation requires the reviewer profile")
    if profile.id == "coding-reviewer" and isolation_policy != "immutable_review_snapshot":
        raise ValueError("reviewer requests require immutable review isolation")
    if _ISOLATION_STRENGTH[isolation_policy] < _ISOLATION_STRENGTH[profile.isolation_policy]:
        raise ValueError("isolation policy may only raise the profile default")
    path_ceiling = tuple(value.replace("\\", "/") for value in profile.allowed_paths)
    requested_paths = tuple(allowed_paths)
    if not requested_paths:
        raise ValueError("allowed paths must not be empty")
    for raw in requested_paths:
        path = raw.replace("\\", "/")
        if (not path or PurePosixPath(path).is_absolute()
                or PureWindowsPath(raw).drive or ".." in path.split("/")
                or "\x00" in path):
            raise ValueError("allowed paths must be relative workspace patterns")
        # Comparing a wildcard request with fnmatch can incorrectly authorize a
        # broader pattern. Accept exact ceiling patterns or a subtree of a
        # recursive ceiling; fail closed on other unverifiable relationships.
        if not any(
            limit == "**" or path == limit
            or (limit.endswith("/**") and path.startswith(limit[:-2]))
            for limit in path_ceiling
        ):
            raise ValueError("allowed paths exceed the profile ceiling")


def allowed_workspace_root(value: str) -> str:
    """Resolve symlinks before testing containment in operator-owned roots.

    OMNIX_AGENT_WORKSPACE_ROOTS uses the platform path-list separator. Relative
    configured roots are anchored to the repository, never the process cwd.
    """
    repository = Path(__file__).resolve().parents[4]
    configured = _env_str("OMNIX_AGENT_WORKSPACE_ROOTS")
    if configured is None:
        roots = [repository, repository / "resources/agent_workspaces"]
    else:
        roots = [Path(item.strip()) for item in configured.split(os.pathsep) if item.strip()]
    requested = Path(value).expanduser()
    if not value.strip() or not requested.is_absolute():
        raise ValueError("workspace root must be an absolute path")
    requested = requested.resolve()
    for root in roots:
        resolved = (root if root.is_absolute() else repository / root).expanduser().resolve()
        if requested.is_relative_to(resolved):
            return str(requested)
    raise ValueError("workspace root is outside OMNIX_AGENT_WORKSPACE_ROOTS")
