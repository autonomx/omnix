"""Where Hermes code lives (WP-8.2)."""
from __future__ import annotations

from pathlib import Path

from app.providers.hermes_client import HermesSidecarClient
from app.runtime.feature_catalog import FEATURE_CATALOG, load_feature

APP = Path(__file__).parents[2] / "app"


def test_the_sidecar_client_is_transport_only() -> None:
    # Prompts and output models belong to the feature asking; the shared client
    # would otherwise import research, trading or assist types.
    public = {name for name in vars(HermesSidecarClient) if not name.startswith("_")}

    assert public == {"health", "capabilities", "rpg_plan", "structured"}


def test_rpg_hermes_modules_live_under_rpg() -> None:
    # assist_core is gone (WP-8.2): assist mode lives in app/chat/assist.
    assert not (APP / "assist_core").exists()
    assert FEATURE_CATALOG["hermes"] == "app.rpg.hermes.feature:FEATURE"
    assert load_feature("hermes").depends_on == ("rpg",)
