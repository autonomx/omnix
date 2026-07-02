from __future__ import annotations

from app.assist_core.hermes_rpg_approved_config import (
    FEATURE_FLAG,
    hermes_rpg_approved_flow_config_payload,
    hermes_rpg_approved_flow_feature_enabled,
)


def test_hermes_rpg_approved_flow_feature_flag_defaults_off() -> None:
    assert hermes_rpg_approved_flow_feature_enabled({}) is False
    assert hermes_rpg_approved_flow_config_payload({}) == {
        "ok": True,
        "source": "hermes_rpg_approved_flow_config",
        "feature_flag": FEATURE_FLAG,
        "default_enabled": False,
        "enabled": False,
        "requires_payload_enabled": True,
        "simulation_owned": True,
    }


def test_hermes_rpg_approved_flow_feature_flag_accepts_truthy_values() -> None:
    assert hermes_rpg_approved_flow_feature_enabled({FEATURE_FLAG: "1"}) is True
    assert hermes_rpg_approved_flow_feature_enabled({FEATURE_FLAG: "true"}) is True
    assert hermes_rpg_approved_flow_feature_enabled({FEATURE_FLAG: "ON"}) is True
    assert hermes_rpg_approved_flow_config_payload({FEATURE_FLAG: "yes"})["enabled"] is True
