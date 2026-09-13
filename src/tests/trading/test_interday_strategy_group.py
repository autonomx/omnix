from __future__ import annotations

from pathlib import Path

import pytest

from app.trading.strategy_managed_finviz_shadow import (
    INTERDAY_TRADING_STRATEGY_ID,
    INTERDAY_TRADING_SUBSTRATEGY_KEYS,
    managed_finviz_shadow_document,
)
from app.trading.strategy_repository import TradingStrategyConfigDocument


def test_interday_group_has_four_embedded_and_two_linked_substrategies() -> None:
    assert len(INTERDAY_TRADING_SUBSTRATEGY_KEYS) == 6
    assert INTERDAY_TRADING_SUBSTRATEGY_KEYS[-2:] == (
        "stoch-rsi-5min",
        "gap-pullback-v2-prospective-20260825",
    )
    assert managed_finviz_shadow_document("paper-test").strategy_id == INTERDAY_TRADING_STRATEGY_ID


def test_strategy_document_rejects_self_parent() -> None:
    payload = managed_finviz_shadow_document("paper-test").model_dump(mode="python")
    payload["parent_strategy_id"] = INTERDAY_TRADING_STRATEGY_ID
    with pytest.raises(ValueError, match="strategy_cannot_parent_itself"):
        TradingStrategyConfigDocument.model_validate(payload)


def test_interday_migration_renames_and_attaches_children() -> None:
    migration = Path(__file__).parents[2] / "app/persistence/migrations/0068_trading_interday_strategy_group.sql"
    sql = migration.read_text(encoding="utf-8")

    assert "finviz-learning-v2-shadow" in sql
    assert "interday-trading-strategy-shadow" in sql
    assert "stoch-rsi-5min" in sql
    assert "gap-pullback-v2-prospective-20260825" in sql
    assert "ON UPDATE CASCADE" in sql
    assert "parent_strategy_id" in sql
