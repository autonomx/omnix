from __future__ import annotations

import os
from collections.abc import Mapping

_TRUE_VALUES = {"1", "true", "yes", "on"}
FEATURE_FLAG = "HERMES_RPG_APPROVED_FLOW_ENABLED"


def hermes_rpg_approved_flow_feature_enabled(environ: Mapping[str, str] | None = None) -> bool:
    source = os.environ if environ is None else environ
    return str(source.get(FEATURE_FLAG, "")).strip().lower() in _TRUE_VALUES


def hermes_rpg_approved_flow_config_payload(environ: Mapping[str, str] | None = None) -> dict[str, object]:
    enabled = hermes_rpg_approved_flow_feature_enabled(environ)
    return {
        "ok": True,
        "source": "hermes_rpg_approved_flow_config",
        "feature_flag": FEATURE_FLAG,
        "default_enabled": False,
        "enabled": enabled,
        "requires_payload_enabled": True,
        "simulation_owned": True,
    }
