from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


LOCAL_USER_ID = "user:local"
LOCAL_WORKSPACE_ID = "workspace:local"
LOCAL_MEMBERSHIP_ID = "membership:local-owner"


class TenantAccessDenied(PermissionError):
    """Raised when a trusted principal cannot access a workspace aggregate."""


@dataclass(frozen=True, slots=True)
class TenantContext:
    user_id: str
    workspace_id: str
    membership_id: str
    roles: frozenset[str]

    def __post_init__(self) -> None:
        for name, value in (
            ("user_id", self.user_id),
            ("workspace_id", self.workspace_id),
            ("membership_id", self.membership_id),
        ):
            if not str(value).strip():
                raise ValueError(f"{name} is required")
        if not self.roles:
            raise ValueError("at least one trusted role is required")

    def has_role(self, *roles: str) -> bool:
        return bool(self.roles.intersection(role for role in roles if role))

    def require_role(self, *roles: str) -> None:
        if not self.has_role(*roles):
            raise TenantAccessDenied(
                f"principal {self.user_id} lacks required role in {self.workspace_id}"
            )

    def require_workspace(self, workspace_id: str) -> None:
        if str(workspace_id) != self.workspace_id:
            raise TenantAccessDenied(
                f"workspace {workspace_id} is outside principal scope {self.workspace_id}"
            )


@dataclass(frozen=True, slots=True)
class TrustedPrincipal:
    user_id: str
    memberships: tuple[TenantContext, ...]

    def for_workspace(self, workspace_id: str) -> TenantContext:
        for context in self.memberships:
            if context.workspace_id == workspace_id:
                return context
        raise TenantAccessDenied(
            f"principal {self.user_id} has no active membership in {workspace_id}"
        )


def tenant_context(
    *,
    user_id: str,
    workspace_id: str,
    membership_id: str,
    roles: Iterable[str],
) -> TenantContext:
    return TenantContext(
        user_id=str(user_id).strip(),
        workspace_id=str(workspace_id).strip(),
        membership_id=str(membership_id).strip(),
        roles=frozenset(str(role).strip() for role in roles if str(role).strip()),
    )


def local_tenant_context() -> TenantContext:
    return TenantContext(
        user_id=LOCAL_USER_ID,
        workspace_id=LOCAL_WORKSPACE_ID,
        membership_id=LOCAL_MEMBERSHIP_ID,
        roles=frozenset({"owner", "admin", "member"}),
    )
