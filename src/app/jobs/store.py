"""Production job-store composition boundary.

PostgreSQL is the only production authority. Provider-free tests must inject a
store from tests/support rather than importing a test double into app.jobs.
"""
from __future__ import annotations


def default_job_store():
    from app.persistence.runtime import uses_postgresql_runtime

    if not uses_postgresql_runtime():
        raise RuntimeError(
            "No production in-memory job store exists; inject a test store explicitly"
        )
    from app.runtime_composition import production_job_store

    return production_job_store()


__all__ = ["default_job_store"]
