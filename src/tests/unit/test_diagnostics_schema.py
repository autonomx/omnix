"""The consolidated diagnostics sections (WP-10.9)."""
from __future__ import annotations

from types import SimpleNamespace

from app.events.event_reader import EventReaders
from app.runtime.config import GatewayRole, RuntimeConfig
from app.runtime.capabilities import RuntimeCapabilities
from app.security.permissions import kernel_defaults_for


def _state(**extra):
    config = RuntimeConfig(gateway_role=GatewayRole.API)
    return SimpleNamespace(
        runtime_config=config, runtime_capabilities=RuntimeCapabilities.from_config(config),
        runtime_started=False, runtime_services=None, started_monotonic=0.0, **extra,
    )


def test_version_features_and_events_are_reported_per_process() -> None:
    from app.persistence.migrations import SCHEMA_KNOWN
    from app.gateway.runtime_diagnostics import runtime_diagnostics

    payload = runtime_diagnostics(_state()).model_dump()

    assert payload["schema_version"] == 2
    assert payload["version"]["application_schema"] == SCHEMA_KNOWN
    assert payload["features"] == sorted(payload["features"]) and "chat" in payload["features"]
    assert payload["events"] == {"readers": 0, "subscribers": 0, "queries": 0, "listeners_alive": 0}
    assert payload["retention"] is None


def test_event_readers_report_an_aggregate_without_workspace_ids() -> None:
    import asyncio

    from app.runtime.tenant_context import local_tenant_context

    readers = EventReaders(database=None)
    reader = readers.for_tenant(local_tenant_context())
    reader._ensure_running = lambda: None  # no database in this test
    loop = asyncio.new_event_loop()
    try:
        reader.subscribe(loop)
        reader.subscribe(loop)
    finally:
        loop.close()

    summary = readers.diagnostics()

    assert summary == {"readers": 1, "subscribers": 2, "queries": 0, "listeners_alive": 0}
    assert local_tenant_context().workspace_id not in str(summary)


def test_diagnostics_need_the_diagnostics_permission() -> None:
    for path in ("/api/diagnostics", "/api/runtime/status", "/api/workers/health"):
        assert kernel_defaults_for(path) == ("admin:diagnostics", "admin:diagnostics")
