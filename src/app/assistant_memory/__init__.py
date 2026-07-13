"""Backend-owned curated memory contracts, persistence, and policy."""

from .lifecycle import MemorySnapshotView, MemorySnapshotViewItem, resolve_snapshot_view
from .models import (
    SYSTEM_MEMORY_OWNER_ID,
    MemoryCandidate,
    MemoryCategory,
    MemoryOwnerType,
    MemoryPolicyDecision,
    MemoryRecord,
    MemoryScope,
    MemoryScopeContext,
    MemorySnapshot,
    MemorySnapshotItem,
)
from .owner_defaults import default_memory_service
from .owner_repository import OwnerAwareInMemoryMemoryRepository
from .owner_service import OwnerAwareMemoryService
from .policy import (
    candidate_acceptance,
    explicit_save_decision,
    is_expired,
    is_visible_in_scope,
    move_scope_decision,
    prompt_eligibility,
    source_requires_approval,
)
from .repository import (
    InMemoryMemoryRepository,
    MemoryConflictError,
    MemoryNotFoundError,
    default_memory_db_path,
)
from .scope import (
    DEFAULT_PROFILE_ID,
    DEFAULT_WORKSPACE_ID,
    resolve_chat_scope,
    resolve_session_memory_scope,
    scope_id_for,
)
from .selection import MemorySelection, MemorySelectionDiagnostics, select_memory_records
from .service import MemoryPolicyError, MemoryService, normalize_memory_content

__all__ = [
    "DEFAULT_PROFILE_ID",
    "DEFAULT_WORKSPACE_ID",
    "InMemoryMemoryRepository",
    "MemoryCandidate",
    "MemoryCategory",
    "MemoryConflictError",
    "MemoryNotFoundError",
    "MemoryOwnerType",
    "MemoryPolicyDecision",
    "MemoryPolicyError",
    "MemoryRecord",
    "MemoryScope",
    "MemoryScopeContext",
    "MemorySelection",
    "MemorySelectionDiagnostics",
    "MemoryService",
    "MemorySnapshot",
    "MemorySnapshotItem",
    "MemorySnapshotView",
    "MemorySnapshotViewItem",
    "OwnerAwareInMemoryMemoryRepository",
    "OwnerAwareMemoryService",
    "SYSTEM_MEMORY_OWNER_ID",
    "candidate_acceptance",
    "default_memory_db_path",
    "default_memory_service",
    "explicit_save_decision",
    "is_expired",
    "is_visible_in_scope",
    "move_scope_decision",
    "normalize_memory_content",
    "prompt_eligibility",
    "resolve_chat_scope",
    "resolve_session_memory_scope",
    "resolve_snapshot_view",
    "scope_id_for",
    "select_memory_records",
    "source_requires_approval",
]
