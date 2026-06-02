from copy import deepcopy
import inspect
from pathlib import Path


def test_ci_phase4_season_weather_initial_state_is_deterministic():
    from app.rpg.locations import RUSTY_FLAGON, ensure_weather_state

    state = {"travel_state": {"current_location_id": RUSTY_FLAGON}, "time_state": {"day_count": 1}}
    weather = ensure_weather_state(state, location_id=RUSTY_FLAGON)

    assert weather["source"] == "deterministic_phase4_season_weather_expansion"
    assert weather["season"] == "early_autumn"
    assert weather["weather_id"] != "weather:unset"
    assert weather["label"]
    assert state["time_state"]["weather_label"] == weather["label"]
    assert state["time_state"]["weather_source"] == "deterministic_phase4_season_weather_expansion"


def test_ci_phase4_season_weather_progression_is_source_backed():
    from app.rpg.locations import derive_season_for_day_count, refresh_weather_state

    assert derive_season_for_day_count(1) == "early_autumn"
    assert derive_season_for_day_count(31) == "late_autumn"

    state = {"time_state": {"day_count": 1}}
    refreshed = refresh_weather_state(state, day_count=31, reason="season_boundary", turn_index=9)

    assert refreshed["ok"] is True
    assert refreshed["source"] == "deterministic_phase4_season_weather_expansion"
    assert refreshed["after"]["season"] == "late_autumn"
    assert refreshed["weather_log_entry"]["after_season"] == "late_autumn"
    assert refreshed["weather_log_entry"]["source"] == "deterministic_phase4_season_weather_expansion"
    assert state["time_state"]["season"] == "late_autumn"
    assert state["time_state"]["weather_id"] != "weather:unset"


def test_ci_phase4_time_state_carries_deterministic_weather_and_contract():
    from app.rpg.locations import MINUTES_PER_DAY, advance_time, build_time_narration_contract, ensure_time_state

    state = {}
    initial = ensure_time_state(state)
    crossed = advance_time(state, MINUTES_PER_DAY * 30, reason="season_boundary", turn_index=3)
    contract = build_time_narration_contract(crossed)

    assert initial["weather_id"] != "weather:unset"
    assert initial["weather_label"]
    assert crossed["after"]["season"] == "late_autumn"
    assert crossed["after"]["weather_source"] == "deterministic_phase4_season_weather_expansion"
    assert crossed["weather_refresh"]["weather_log_entry"]["changed"] is True
    assert "Weather: " + crossed["after"]["weather_label"] in contract["allowed_time_claims"]
    assert "Only claim weather and season details present in the deterministic after time_state." in contract[
        "forbidden_time_claims"
    ]
    assert "Do not claim weather effects; Phase 4.7 only exposes a deterministic weather_id placeholder." not in contract[
        "forbidden_time_claims"
    ]


def test_ci_phase4_weather_narration_contract_forbids_invention_and_provider_use():
    from app.rpg.locations import build_weather_narration_contract, select_weather_for_day
    from app.rpg.locations import weather as weather_module

    selected = select_weather_for_day(1)
    contract = build_weather_narration_contract({"after": selected})

    assert "Weather: " + selected["label"] in contract["allowed_weather_claims"]
    assert "Season: early_autumn" in contract["allowed_weather_claims"]
    assert "Do not invent weather, seasons, forecasts, storms, visibility, or survival effects." in contract[
        "forbidden_weather_claims"
    ]
    assert "Do not call providers or LLMs for deterministic weather selection." in contract["forbidden_weather_claims"]
    source = inspect.getsource(weather_module)
    assert "provider" not in source.replace("providers", "").lower()
    assert "openai" not in source.lower()


def test_ci_phase4_map_report_weather_payload_is_non_mutating_and_escaped():
    from app.rpg.locations import build_map_location_panel_payload, render_map_location_report_html

    state = {"time_state": {"elapsed_minutes": 0}}
    before = deepcopy(state)
    panel = build_map_location_panel_payload(state)
    html = render_map_location_report_html(
        {**panel, "weather_state": {**panel["weather_state"], "weather_label": "Rain <script>bad()</script>"}}
    )

    assert state == before
    assert panel["time_state"]["weather_id"] != "weather:unset"
    assert panel["weather_state"]["weather_label"] == panel["time_state"]["weather_label"]
    assert "Season:" in html
    assert "Weather:" in html
    assert "&lt;script&gt;bad()&lt;/script&gt;" in html
    assert "<script>bad()</script>" not in html


def test_ci_phase4_frontend_renderer_consumes_weather_payload_without_inference():
    renderer = Path("src/static/rpg/rpgMapLocationPanel.js").read_text(encoding="utf-8")

    assert "weatherLabelFromPayload" in renderer
    assert "weather_state" in renderer
    assert "weather_label" in renderer
    assert "weather_visibility" in renderer
    assert "rpg-map-location-weather" in renderer
    assert "passable" not in renderer.casefold()
    assert "Math.random" not in renderer


def test_ci_phase4_season_weather_readiness_and_exports():
    from app.rpg import locations

    readiness = locations.assert_phase4_season_weather_expansion_ready()

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase4_season_weather_expansion_ready"
    assert readiness["blockers"] == []
    assert readiness["source"] == "deterministic_phase4_season_weather_expansion"
    assert locations.DAYS_PER_SEASON == 30
    assert locations.SEASON_ORDER
    assert locations.WEATHER_PROFILES
    assert locations.SEASON_WEATHER_TABLE
    assert locations.ensure_weather_state
    assert locations.refresh_weather_state
    assert locations.build_weather_narration_contract
