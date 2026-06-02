def test_ci_phase2_starter_loadout_grants_currency_items_and_is_idempotent():
    from app.rpg.economy.currency import get_player_currency
    from app.rpg.economy.starter_loadout import (
        SOURCE,
        build_starter_loadout,
        ensure_player_starter_loadout,
    )

    loadout = build_starter_loadout()
    assert loadout["source"] == SOURCE
    assert loadout["currency"] == {"gold": 0, "silver": 15, "copper": 0}

    state = {"player_state": {}}
    updated = ensure_player_starter_loadout(state)
    player_state = updated["player_state"]
    inventory_state = player_state["inventory_state"]
    item_ids = {item["item_id"]: item["qty"] for item in inventory_state["items"]}

    assert get_player_currency(updated) == {"gold": 0, "silver": 15, "copper": 0}
    assert item_ids == {
        "combat_knife": 1,
        "healing_potion": 1,
        "bandit_token": 1,
    }
    assert player_state["starter_loadout_source"] == SOURCE

    second = ensure_player_starter_loadout(updated)
    second_items = second["player_state"]["inventory_state"]["items"]
    assert second_items == inventory_state["items"]
    assert get_player_currency(second) == {"gold": 0, "silver": 15, "copper": 0}


def test_ci_phase2_starter_loadout_preserves_existing_inventory_and_currency():
    from app.rpg.economy.currency import get_player_currency
    from app.rpg.economy.starter_loadout import ensure_player_starter_loadout

    state = {
        "player_state": {
            "inventory_state": {
                "items": [{"item_id": "rusty_sword", "qty": 1}],
                "currency": {"gold": 1, "silver": 2, "copper": 3},
            }
        }
    }

    updated = ensure_player_starter_loadout(state)
    inventory_state = updated["player_state"]["inventory_state"]

    assert get_player_currency(updated) == {"gold": 1, "silver": 2, "copper": 3}
    assert [item["item_id"] for item in inventory_state["items"]] == ["rusty_sword"]
    assert updated["player_state"]["starter_loadout_source"] == "deterministic_starter_loadout"


def test_ci_phase2_merchant_stock_initializes_with_prices_and_quantities():
    from app.rpg.economy.merchant_transactions import get_merchant_state

    state = {"player_state": {"inventory_state": {"currency": {"silver": 15}}}}
    merchant = get_merchant_state(state)
    stock = {row["item_id"]: row for row in merchant["stock"]}

    assert merchant["source"] == "deterministic_merchant_transactions"
    assert stock["healing_potion"]["qty"] == 3
    assert stock["healing_potion"]["price"] == {"gold": 0, "silver": 10, "copper": 0}
    assert stock["combat_knife"]["qty"] == 2
    assert stock["wooden_shield"]["qty"] == 1


def test_ci_phase2_buy_from_merchant_moves_currency_item_and_stock():
    from app.rpg.economy.currency import get_player_currency
    from app.rpg.economy.merchant_transactions import buy_from_merchant, get_merchant_state

    state = {"player_state": {"inventory_state": {"items": [], "currency": {"silver": 15}}}}
    result = buy_from_merchant(state, item_id="healing_potion", qty=1, tick=4)
    inventory = state["player_state"]["inventory_state"]
    merchant = get_merchant_state(state)
    stock = {row["item_id"]: row for row in merchant["stock"]}

    assert result["resolved"] is True
    assert result["reason"] == "transaction_completed"
    assert result["price"] == {"gold": 0, "silver": 10, "copper": 0}
    assert get_player_currency(state) == {"gold": 0, "silver": 5, "copper": 0}
    assert {item["item_id"]: item["qty"] for item in inventory["items"]}["healing_potion"] == 1
    assert stock["healing_potion"]["qty"] == 2
    assert merchant["transaction_log"][-1]["kind"] == "buy"
    assert merchant["transaction_log"][-1]["source"] == "deterministic_merchant_transactions"


def test_ci_phase2_buy_from_merchant_rejects_insufficient_funds_and_stock():
    from app.rpg.economy.currency import get_player_currency
    from app.rpg.economy.merchant_transactions import buy_from_merchant, get_merchant_state

    state = {"player_state": {"inventory_state": {"items": [], "currency": {"silver": 5}}}}
    poor = buy_from_merchant(state, item_id="healing_potion", qty=1, tick=5)
    assert poor["resolved"] is False
    assert poor["reason"] == "insufficient_funds"
    assert get_player_currency(state) == {"gold": 0, "silver": 5, "copper": 0}

    state = {"player_state": {"inventory_state": {"items": [], "currency": {"gold": 5}}}}
    too_many = buy_from_merchant(state, item_id="wooden_shield", qty=2, tick=6)
    merchant = get_merchant_state(state)
    stock = {row["item_id"]: row for row in merchant["stock"]}
    assert too_many["resolved"] is False
    assert too_many["reason"] == "insufficient_stock"
    assert stock["wooden_shield"]["qty"] == 1


def test_ci_phase2_sell_to_merchant_moves_item_and_logs_transaction():
    from app.rpg.economy.currency import get_player_currency
    from app.rpg.economy.merchant_transactions import get_merchant_state, sell_to_merchant

    state = {
        "player_state": {
            "inventory_state": {
                "items": [{"item_id": "combat_knife", "qty": 1}],
                "currency": {"silver": 0},
            }
        }
    }
    result = sell_to_merchant(state, item_id="combat_knife", qty=1, tick=7)
    merchant = get_merchant_state(state)
    stock = {row["item_id"]: row for row in merchant["stock"]}

    assert result["resolved"] is True
    assert result["reason"] == "transaction_completed"
    assert result["price"] == {"gold": 0, "silver": 5, "copper": 0}
    assert get_player_currency(state) == {"gold": 0, "silver": 5, "copper": 0}
    assert state["player_state"]["inventory_state"]["items"] == []
    assert stock["combat_knife"]["qty"] == 3
    assert merchant["transaction_log"][-1]["kind"] == "sell"
    assert merchant["transaction_log"][-1]["item_id"] == "combat_knife"


def test_ci_phase2_economy_report_collects_transactions_and_guardrails():
    from app.rpg.economy.reporting import build_economy_transaction_report

    data = {
        "turns": [
            {
                "turn": 4,
                "result": {
                    "transaction_log_entry": {
                        "kind": "buy",
                        "item_id": "healing_potion",
                        "qty": 1,
                        "price": {"silver": 10},
                        "reason": "transaction_completed",
                        "source": "deterministic_merchant_transactions",
                    }
                },
            }
        ]
    }
    report = build_economy_transaction_report(data)
    transaction = report["transactions"][0]
    contract = report["presentation_contract"]

    assert report["source"] == "deterministic_economy_report"
    assert report["transaction_count"] == 1
    assert transaction["turn"] == 4
    assert transaction["kind"] == "buy"
    assert transaction["item_id"] == "healing_potion"
    assert transaction["price"] == {"gold": 0, "silver": 10, "copper": 0}
    assert contract["source"] == "deterministic_economy_presentation_contract"
    assert contract["allowed_transaction_claims"] == ["buy 1 x healing_potion for 10 silver"]
    assert any("Do not invent merchant stock" in item for item in contract["forbidden_economy_claims"])
    assert any("Do not invent prices" in item for item in contract["forbidden_economy_claims"])


def test_ci_phase2_campaign_report_displays_economy_transactions():
    from tests.rpg.autoplay.campaign_report import render_campaign_report_html

    html = render_campaign_report_html(
        {
            "scenario_seed": "ci_phase2_economy_report",
            "turns": [
                {
                    "turn": 4,
                    "result": {
                        "transaction_log_entry": {
                            "kind": "buy",
                            "item_id": "healing_potion",
                            "qty": 1,
                            "price": {"silver": 10},
                            "reason": "transaction_completed",
                            "source": "deterministic_merchant_transactions",
                        }
                    },
                }
            ],
        }
    )

    assert "Economy Transactions" in html
    assert "healing_potion" in html
    assert "10 silver" in html
    assert "transaction_completed" in html
    assert "deterministic_merchant_transactions" in html
    assert "Economy Presentation Guardrails" in html
    assert "deterministic_economy_presentation_contract" in html
    assert "Do not invent merchant stock" in html
    assert "Do not invent prices" in html
