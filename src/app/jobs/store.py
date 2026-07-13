"""Shared job-store compatibility boundary.

PostgreSQL is the production authority and is installed by the explicit Omnix
startup bootstrap. Provider-free tests use ``InMemoryJobStore``; no SQLite
runtime or schema remains in this module.
"""

from __future__ import annotations

from app.testing.in_memory_job_store import InMemoryJobStore


def default_job_store() -> InMemoryJobStore:
    return InMemoryJobStore()


__all__ = ["InMemoryJobStore", "default_job_store"]
