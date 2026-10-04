"""The premarket handoff import is explicit and off by default (WP-8.3)."""
from __future__ import annotations

from datetime import datetime, timezone

from app.trading import prospective_gap_inputs as inputs_module
from app.trading.prospective_gap_runtime import ProspectiveGapRuntime


def test_the_scheduled_github_import_is_off_by_default(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_TRADING_PROSPECTIVE_GAP_HANDOFF_IMPORT", raising=False)
    assert inputs_module.handoff_import_task(None) is None
    monkeypatch.setenv("OMNIX_TRADING_PROSPECTIVE_GAP_HANDOFF_IMPORT", "1")
    assert inputs_module.handoff_import_task(None).task_id == "trading.prospective_gap_handoff_import"


class _Inputs:
    def __init__(self, existing=None) -> None:
        self.existing = existing
        self.imported = []

    def handoff(self, session_date):
        return self.existing

    def import_handoff(self, content, *, source, imported_by=None):
        self.imported.append((content, source, imported_by))


def test_the_import_runs_only_in_the_premarket_window_and_only_once(monkeypatch) -> None:
    fetched = []
    monkeypatch.setattr(
        inputs_module,
        "fetch_handoff_from_github",
        lambda session_date: fetched.append(session_date) or ("{}", "github:test"),
    )
    after_open = datetime(2026, 10, 5, 14, 0, tzinfo=timezone.utc)  # 10:00 ET
    premarket = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)  # 08:00 ET

    assert inputs_module.import_todays_handoff_from_github(_Inputs(), now=lambda: after_open) is False
    assert inputs_module.import_todays_handoff_from_github(_Inputs(existing=object()), now=lambda: premarket) is False
    assert fetched == []

    store = _Inputs()
    assert inputs_module.import_todays_handoff_from_github(store, now=lambda: premarket) is True
    assert store.imported == [("{}", "github:test", "trading.prospective_gap_handoff_import")]


def test_the_runtime_no_longer_fetches_from_github_or_reads_input_files() -> None:
    assert not hasattr(ProspectiveGapRuntime, "_fetch_scheduler_handoff_from_github")
    assert not hasattr(ProspectiveGapRuntime, "_load_climatology_state")
