"""The narrative adapters are built once a process, so they must ask whose request this is each time.

Each used to keep the first caller's tenant: with accounts, a second workspace's narrated turn ran as the first's.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.apps.rpg.narration.narrative_delivery import PostgresNarrativeDeliveryRepositoryAdapter
from app.apps.rpg.narration.narrative_repository import PostgresNarrativeResponseRepositoryAdapter
from app.apps.rpg.narration.narrative_retirement import PostgresNarrativeRetirementRepositoryAdapter
from app.runtime.tenant_context import TenantContext, pop_tenant, push_tenant


def _tenant(name: str) -> TenantContext:
    return TenantContext(user_id=f"user:{name}", workspace_id=f"workspace:{name}", membership_id=f"membership:{name}",
                         roles=frozenset({"member"}))


@pytest.mark.parametrize("adapter_type", [
    PostgresNarrativeDeliveryRepositoryAdapter,
    PostgresNarrativeResponseRepositoryAdapter,
    PostgresNarrativeRetirementRepositoryAdapter,
])
def test_each_call_runs_as_the_tenant_of_its_request(adapter_type) -> None:
    adapter = adapter_type(database=SimpleNamespace(), unit_of_work_factory=MagicMock())
    seen = []
    for name in ("first", "second", "first"):
        token = push_tenant(_tenant(name))
        try:
            seen.append(adapter._context().workspace_id)
        finally:
            pop_tenant(token)
    assert seen == ["workspace:first", "workspace:second", "workspace:first"]
