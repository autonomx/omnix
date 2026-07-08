"""Canonical owner-aware memory service factory."""
from .owner_service import OwnerAwareMemoryService


def default_memory_service() -> OwnerAwareMemoryService:
    return OwnerAwareMemoryService()


__all__ = ["default_memory_service"]
