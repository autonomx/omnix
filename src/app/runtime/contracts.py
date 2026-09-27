"""Small process-service contracts used by gateway composition.

Transactions remain in the persistence unit of work. These interfaces describe
the process-owned services exposed to routes, rather than transaction objects.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from app.assets.models import AssetRecord, AssetListResponse
    from app.chat.models import ChatSession, ChatSessionListResponse, CreateChatSessionRequest
    from app.jobs.models import CreateJobRequest, JobRecord
    from app.jobs.residency import ModelResidencyRecord
    from app.persistence.database import PostgresDatabase
    from app.persistence.tenant import TenantContext


class JobService(Protocol):
    database: PostgresDatabase
    context: TenantContext

    def create_job(self, request: CreateJobRequest) -> JobRecord: ...
    def get_job(self, job_id: str) -> JobRecord | None: ...


class AssetService(Protocol):
    def list_assets(self) -> AssetListResponse: ...
    def get_asset(self, asset_id: str) -> AssetRecord | None: ...
    def upsert_asset(self, asset: AssetRecord) -> AssetRecord: ...
    def delete_asset(self, asset_id: str, *, delete_file: bool = True) -> dict[str, Any]: ...


class ChatService(Protocol):
    def list_sessions(self) -> ChatSessionListResponse: ...
    def create_session(self, request: CreateChatSessionRequest) -> ChatSession: ...
    def get_session(self, session_id: str) -> ChatSession | None: ...


class ModelResidencyService(Protocol):
    def list_records(self) -> list[ModelResidencyRecord]: ...
    def upsert_record(self, record: ModelResidencyRecord) -> ModelResidencyRecord: ...
    def delete_record(self, model_id: str) -> bool: ...
