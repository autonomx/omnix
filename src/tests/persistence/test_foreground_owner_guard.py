"""The record-only job fence is composed from module declarations without changing its SQL (PA-2.2)."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.persistence import execution_repositories
from app.persistence.declarations import RecordOnlyJobGuard, record_only_job_guards

FIXTURE = Path(__file__).parent / "fixtures" / "foreground_owner_guard.sql"


def test_the_composed_guard_is_the_guard_the_kernel_wrote_before() -> None:
    assert execution_repositories.foreground_owner_guard() == FIXTURE.read_text(encoding="utf-8")
    assert execution_repositories.foreground_owner_guard("jobs") == FIXTURE.read_text(encoding="utf-8").replace("omnix_jobs.", "jobs.")


def test_each_declared_guard_binds_the_submission_claim_token_once() -> None:
    assert [guard.job_type for guard in record_only_job_guards()] == ["rpg.turn.foreground_record"]
    assert execution_repositories.foreground_guard_credentials("node", "token") == ("node", "token")
    assert execution_repositories.foreground_owner_guard().count("%s") == 2


def test_a_guard_must_take_exactly_one_claim_token() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        RecordOnlyJobGuard("module.record", "AND module = 'module'")
