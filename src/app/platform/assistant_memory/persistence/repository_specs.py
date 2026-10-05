"""Repository registrations owned by the assistant-memory feature."""

from app.persistence.repository_registry import RepositorySpec
from app.platform.assistant_memory.persistence.repository import PostgresMemoryRepository

ASSISTANT_MEMORY_REPOSITORY_SPECS = (
    RepositorySpec(
        PostgresMemoryRepository,
        PostgresMemoryRepository,
        "memories",
    ),
)
