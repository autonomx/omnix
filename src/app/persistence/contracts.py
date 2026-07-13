from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .tenant import TenantContext


@runtime_checkable
class IdentityRepository(Protocol):
    def ensure_local_identity(self) -> TenantContext: ...

    def load_context(self, *, user_id: str, workspace_id: str) -> TenantContext: ...

    def get_workspace(self, context: TenantContext, workspace_id: str) -> dict[str, Any] | None: ...

    def update_workspace_name(
        self,
        context: TenantContext,
        *,
        workspace_id: str,
        name: str,
        expected_revision: int,
    ) -> dict[str, Any]: ...


@runtime_checkable
class AuditRepository(Protocol):
    def append(
        self,
        context: TenantContext,
        *,
        aggregate_type: str,
        aggregate_id: str,
        action: str,
        payload: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> int: ...


@runtime_checkable
class IdempotencyRepository(Protocol):
    def reserve(
        self,
        context: TenantContext,
        *,
        scope: str,
        key: str,
        request_hash: str,
    ) -> dict[str, Any]: ...

    def complete(
        self,
        context: TenantContext,
        *,
        scope: str,
        key: str,
        response: dict[str, Any],
    ) -> dict[str, Any]: ...


@runtime_checkable
class ChatRepository(Protocol):
    def create_session(self, context: TenantContext, payload: dict[str, Any]) -> dict[str, Any]: ...
    def get_session(self, context: TenantContext, session_id: str) -> dict[str, Any] | None: ...
    def append_message(self, context: TenantContext, session_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...


@runtime_checkable
class CharacterRepository(Protocol):
    def get_character(self, context: TenantContext, character_id: str) -> dict[str, Any] | None: ...


@runtime_checkable
class MemoryRepository(Protocol):
    def get_memory(self, context: TenantContext, memory_id: str) -> dict[str, Any] | None: ...


@runtime_checkable
class AssetRepository(Protocol):
    def get_asset(self, context: TenantContext, asset_id: str) -> dict[str, Any] | None: ...


@runtime_checkable
class JobRepository(Protocol):
    def get_job(self, context: TenantContext, job_id: str) -> dict[str, Any] | None: ...


@runtime_checkable
class CampaignRepository(Protocol):
    def get_campaign(self, context: TenantContext, campaign_id: str) -> dict[str, Any] | None: ...


@runtime_checkable
class TurnRepository(Protocol):
    def get_by_submission(
        self,
        context: TenantContext,
        campaign_id: str,
        submission_id: str,
    ) -> dict[str, Any] | None: ...


@runtime_checkable
class OutboxRepository(Protocol):
    def append(
        self,
        context: TenantContext,
        *,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> int: ...


@runtime_checkable
class BlobStore(Protocol):
    def put_bytes(self, storage_key: str, content: bytes) -> dict[str, Any]: ...
    def read_bytes(self, storage_key: str) -> bytes: ...
    def delete(self, storage_key: str) -> bool: ...


@runtime_checkable
class SecretStore(Protocol):
    def put_secret(self, reference: str, value: str) -> None: ...
    def get_secret(self, reference: str) -> str | None: ...
    def delete_secret(self, reference: str) -> bool: ...
