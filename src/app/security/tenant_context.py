"""Process/request tenant context.

Phase 2 installs one process default for local mode. Phase 4 will replace the
request context with authenticated principals without changing service APIs.
"""
from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass

from app.persistence.tenant import TenantContext

_CURRENT_TENANT: ContextVar[TenantContext | None] = ContextVar("omnix_current_tenant", default=None)
_PROCESS_DEFAULT: TenantContext | None = None


def install_process_tenant(context: TenantContext) -> None:
    global _PROCESS_DEFAULT
    if _PROCESS_DEFAULT is not None and _PROCESS_DEFAULT != context:
        raise RuntimeError("process tenant is already installed")
    _PROCESS_DEFAULT = context


def reset_process_tenant_for_tests() -> None:
    global _PROCESS_DEFAULT
    _PROCESS_DEFAULT = None


def current_tenant() -> TenantContext:
    context = _CURRENT_TENANT.get()
    if context is not None:
        return context
    if _PROCESS_DEFAULT is None:
        raise RuntimeError("tenant context is not installed")
    return _PROCESS_DEFAULT


def push_tenant(context: TenantContext) -> Token:
    return _CURRENT_TENANT.set(context)


def pop_tenant(token: Token) -> None:
    _CURRENT_TENANT.reset(token)


@dataclass(frozen=True, slots=True)
class TenantProvider:
    def current(self) -> TenantContext:
        return current_tenant()
