from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import FastAPI

from app.persistence.blob_store import BlobIntegrityError, LocalBlobStore
from app.persistence.tenant import local_tenant_context
from app.trading.alerts_api import create_trading_alert_router
from app.trading.api import create_trading_router
from app.trading.backtest import BacktestLogEntry, BacktestRunResult
from app.trading.paper_api import create_trading_paper_router
from app.trading.replay_api import create_trading_replay_router
from app.trading.replay_repository import TradingReplayRepository
from app.trading.replay_runtime_repository import TradingReplayRuntimeRepository
from app.trading.research_api import create_trading_research_router
from app.trading.scanner_api import create_trading_scanner_router


NOW = datetime(2026, 8, 6, tzinfo=timezone.utc)


class FakeConnection:
    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, statement: str, parameters=()):
        self.statements.append((statement, tuple(parameters)))
        return self


class FakeUnitOfWork:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def commit(self) -> None:
        self.committed = True


def minimal_backtest() -> BacktestRunResult:
    return BacktestRunResult(
        run_id="release-artifact-run",
        dataset_id="dataset-1",
        dataset_fingerprint="f" * 64,
        strategy_id="sma_cross",
        strategy_parameters={"fast_period": 2, "slow_period": 3},
        execution_policy={"fill_timing": "next_bar_open"},
        formula_version="omnix-indicators-v2",
        status="completed",
        initial_cash=Decimal("10000"),
        final_equity=Decimal("10100"),
        total_return_percent=Decimal("1"),
        max_drawdown_percent=Decimal("0.5"),
        win_rate_percent=Decimal("50"),
        exposure_percent=Decimal("25"),
        trade_count=0,
        started_at=NOW,
        finished_at=NOW,
        trades=(),
        equity_curve=(),
        logs=(BacktestLogEntry(log_index=0, message="release fixture"),),
    )


def test_all_trading_product_routes_are_registered_in_openapi() -> None:
    app = FastAPI()
    for router in (
        create_trading_router(),
        create_trading_alert_router(),
        create_trading_scanner_router(),
        create_trading_replay_router(),
        create_trading_paper_router(),
        create_trading_research_router(),
    ):
        app.include_router(router)
    paths = set(app.openapi()["paths"])
    required = {
        "/api/trading/instruments/search",
        "/api/trading/providers/status",
        "/api/trading/alerts",
        "/api/trading/scanners",
        "/api/trading/replay/datasets",
        "/api/trading/replay/backtests",
        "/api/trading/paper/accounts",
        "/api/trading/research",
    }
    assert required <= paths

    gateway = Path("src/app/gateway/trading_routes.py").read_text()
    for registration in (
        "create_trading_router",
        "create_trading_alert_router",
        "create_trading_scanner_router",
        "create_trading_replay_router",
        "create_trading_paper_router",
        "create_trading_research_router",
        "register_trading_alert_monitor",
        "register_trading_paper_monitor",
    ):
        assert registration in gateway


def test_backtest_artifact_is_checksummed_and_corruption_is_detected(
    monkeypatch,
    tmp_path,
) -> None:
    connection = FakeConnection()
    store = LocalBlobStore(tmp_path / "blobs")

    def relational_save(_repository, result):
        return result

    monkeypatch.setattr(TradingReplayRepository, "save_backtest", relational_save)
    repository = TradingReplayRuntimeRepository(
        context=local_tenant_context(),
        uow_factory=lambda: FakeUnitOfWork(connection),
        blob_store=store,
    )
    saved = repository.save_backtest(minimal_backtest())
    assert saved.artifact is not None
    assert saved.artifact.storage_provider == "local-filesystem"
    assert len(saved.artifact.checksum_sha256) == 64
    payload = store.read_bytes(
        saved.artifact.storage_key,
        expected_checksum=saved.artifact.checksum_sha256,
    )
    decoded = json.loads(payload)
    assert decoded["run_id"] == saved.run_id
    assert decoded["win_rate_percent"] == "50"
    assert decoded["exposure_percent"] == "25"
    assert any("artifact_checksum_sha256" in statement for statement, _ in connection.statements)

    artifact_path = store.root.joinpath(*saved.artifact.storage_key.split("/"))
    artifact_path.write_bytes(b"corrupt")
    with pytest.raises(BlobIntegrityError):
        store.read_bytes(
            saved.artifact.storage_key,
            expected_checksum=saved.artifact.checksum_sha256,
        )


def test_no_live_broker_or_ai_mutation_surface_exists() -> None:
    trading_source = "\n".join(
        path.read_text()
        for path in Path("src/app/trading").glob("*.py")
    ).lower()
    for forbidden in (
        "submit_live_order",
        "broker_credentials",
        "interactive_brokers",
        "alpaca_trade_api",
        "/api/trading/live",
    ):
        assert forbidden not in trading_source

    research = Path("src/app/trading/research.py").read_text().lower()
    for forbidden in (
        "place_order",
        "create_alert",
        "process_observation",
        "run_backtest",
        "lmstudio",
        "openrouter",
        "cerebras",
    ):
        assert forbidden not in research


def test_ui_controls_accessibility_and_attribution_are_structural_invariants() -> None:
    side_panel = Path(
        "apps/web/src/features/trading/TradingSidePanel.tsx"
    ).read_text()
    assert 'role="tablist"' in side_panel
    assert 'role="tab"' in side_panel
    assert 'aria-selected=' in side_panel
    assert "onClick={() => setActiveTab" in side_panel

    workspace = Path(
        "apps/web/src/features/trading/TradingWorkspace.tsx"
    ).read_text()
    assert "TradingComplianceFooter" in workspace
    assert "TradingScannerPanel" in workspace
    assert "TradingReplayPanel" in workspace
    assert "TradingPaperPanel" in workspace
    assert "TradingResearchPanel" in workspace

    styles = "\n".join(
        path.read_text()
        for path in Path("apps/web/src/features/trading").glob("*.css")
    )
    assert "prefers-reduced-motion" in styles
    assert ":focus-visible" in styles

    footer = Path(
        "apps/web/src/features/trading/TradingComplianceFooter.tsx"
    ).read_text()
    assert "Charts powered by TradingView Lightweight Charts™" in footer
    assert "Provider terms" in footer
    assert "No live brokerage execution" in footer


def test_legal_operator_and_roadmap_review_records_are_present() -> None:
    notices = Path("THIRD_PARTY_NOTICES.md").read_text()
    assert "TradingView Lightweight Charts" in notices
    assert "Apache License 2.0" in notices
    assert "tradingview-mcp" in notices
    assert "Copyright (c) 2025 Ahmet Taner Atila" in notices

    review = Path(
        "docs/plans/omnix_trading_terminal_roadmap_review.md"
    ).read_text()
    assert "Code-complete" in review
    assert "Release-certified" in review
    assert "environment certification pending" in review
    assert "fill_bar_index = signal_bar_index + 1" in review

    certification = Path(
        "docs/architecture/OMNIX_TRADING_RELEASE_CERTIFICATION.md"
    ).read_text()
    assert "Pending environment run" in certification
    assert "PR #1488 remains draft" in certification

    operations = Path(
        "docs/architecture/OMNIX_TRADING_OPERATIONS.md"
    ).read_text()
    assert "Provider outage procedure" in operations
    assert "Corrupt or missing artifact" in operations
    assert "Rollback" in operations

    security = Path(
        "docs/architecture/OMNIX_TRADING_SECURITY_LEGAL.md"
    ).read_text()
    assert "does not provide live brokerage execution" in security
    assert "Market-data rights" in security


def test_release_migrations_preserve_integrity_evidence() -> None:
    sequencing = Path(
        "src/app/persistence/migrations/0024_trading_backtest_bar_indices.sql"
    ).read_text()
    assert "signal_bar_index IS NULL AND fill_bar_index IS NULL" in sequencing
    assert "fill_bar_index = signal_bar_index + 1" in sequencing
    assert "trade_index * 2" not in sequencing

    artifacts = Path(
        "src/app/persistence/migrations/0025_trading_backtest_artifacts.sql"
    ).read_text()
    for column in (
        "win_rate_percent",
        "exposure_percent",
        "artifact_storage_provider",
        "artifact_storage_key",
        "artifact_checksum_sha256",
        "artifact_byte_size",
    ):
        assert column in artifacts
    assert "length(artifact_checksum_sha256) = 64" in artifacts
