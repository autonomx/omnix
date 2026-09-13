from __future__ import annotations

from app.rpg.session.item_signals import apply_item_signal, is_signal_item, normalize_item_signals


def test_signal_item_detection_accepts_special_types_and_tags() -> None:
    assert is_signal_item({"item_id": "old_marker", "name": "Old Marker", "item_type": "relic"}) is True
    assert is_signal_item({"item_id": "special_record", "name": "Special Record", "tags": ["signal"]}) is True
    assert is_signal_item({"item_id": "ration", "name": "Ration", "item_type": "consumable"}) is False


def test_normalize_item_signals_repairs_unsupported_ops_and_buckets() -> None:
    item = {
        "item_id": "sealed_record",
        "name": "Sealed Record",
        "item_type": "relic",
        "item_signals": [
            {"id": "show_record", "op": "add_affordance", "bucket": "unknown", "tag": "present_record"},
            {"id": "bad", "op": "rewrite_world"},
        ],
    }

    result = normalize_item_signals(item)

    assert result["ok"] is True
    assert result["signals"][0]["bucket"] == "dialogue"
    assert "repaired_affordance_bucket:unknown" in result["repairs"]
    assert "ignored_unsupported_item_signal_op:rewrite_world" in result["repairs"]


def test_apply_item_signal_adds_affordance_and_trace() -> None:
    state: dict = {}
    item = {
        "item_id": "sealed_record",
        "name": "Sealed Record",
        "item_type": "relic",
        "item_signals": [
            {"signal_id": "show_record", "op": "add_affordance", "bucket": "evidence", "tag": "present_record"}
        ],
    }

    result = apply_item_signal(state, item, "show_record")

    assert result["ok"] is True
    assert state["narrative_affordances"]["evidence"][0]["tag"] == "present_record"
    assert result["trace"]["event"] == "item_signal_applied"
    assert result["trace"]["mechanics_source"] == "engine_item_signal_v1"


def test_apply_item_signal_sets_world_flag_and_scene_status() -> None:
    state: dict = {}
    item = {
        "item_id": "access_mark",
        "name": "Access Mark",
        "item_type": "relic",
        "item_signals": [
            {"signal_id": "mark_access", "op": "set_world_flag", "flag": "north_path_authorized", "value": True},
            {"signal_id": "mark_glow", "op": "add_scene_status", "status": "access_mark_glowing", "dimension": "access"},
        ],
    }

    result = apply_item_signal(state, item)

    assert result["ok"] is True
    assert state["world_flags"]["north_path_authorized"] is True
    assert state["scene_state"]["statuses"][0]["status"] == "access_mark_glowing"
    assert {effect["op"] for effect in result["effects"]} == {"set_world_flag", "add_scene_status"}


def test_apply_item_signal_restores_resource_with_cap() -> None:
    state = {"player": {"resources": {"mana": {"current": 3, "max": 10}}}}
    item = {
        "item_id": "calm_focus",
        "name": "Calm Focus",
        "item_type": "relic",
        "item_signals": [{"signal_id": "steady", "op": "restore_resource", "resource": "mana", "amount": 20}],
    }

    result = apply_item_signal(state, item, "steady")

    assert result["ok"] is True
    assert state["player"]["resources"]["mana"]["current"] == 10
    assert result["effects"][0]["max"] == 10


def test_apply_item_signal_rejects_missing_signal() -> None:
    item = {
        "item_id": "access_mark",
        "name": "Access Mark",
        "item_type": "relic",
        "item_signals": [{"signal_id": "known", "op": "set_world_flag", "flag": "known_flag"}],
    }

    result = apply_item_signal({}, item, "unknown")

    assert result["ok"] is False
    assert result["error"] == "item_signal_not_found"
