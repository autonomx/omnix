from __future__ import annotations

from pathlib import Path

import pytest

from app.trading.strategy_managed_finviz_shadow import (
    INTERDAY_TRADING_STRATEGY_ID,
    INTERDAY_TRADING_SUBSTRATEGY_KEYS,
    STOCH_RSI_GUARDED_STRATEGY_ID,
    managed_finviz_shadow_document,
    managed_stoch_rsi_guarded_document,
)
from app.trading.strategy_repository import TradingStrategyConfigDocument


def test_interday_group_has_four_embedded_and_three_linked_substrategies() -> None:
    assert len(INTERDAY_TRADING_SUBSTRATEGY_KEYS) == 7
    assert INTERDAY_TRADING_SUBSTRATEGY_KEYS[-3:] == (
        "stoch-rsi-5min",
        STOCH_RSI_GUARDED_STRATEGY_ID,
        "gap-pullback-v2-prospective-20260825",
    )
    assert managed_finviz_shadow_document("paper-test").strategy_id == INTERDAY_TRADING_STRATEGY_ID


def test_guarded_stoch_rsi_child_is_linked_shadow_only_profile() -> None:
    document = managed_stoch_rsi_guarded_document("paper-test")

    assert document.strategy_id == STOCH_RSI_GUARDED_STRATEGY_ID
    assert document.parent_strategy_id == INTERDAY_TRADING_STRATEGY_ID
    assert document.strategy_kind == "stoch_rsi_5m_v1"
    assert document.mode == "shadow"
    assert document.enabled is True
    assert document.config.policy_profile == "guarded_v1"
    assert document.config.universe_discovery_source == "finviz"


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
