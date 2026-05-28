from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "static"


def _read(path: str) -> str:
    return (STATIC / path).read_text(encoding="utf-8")


def test_bundle_bk_survival_inspector_module_projects_runtime_payload_keys() -> None:
    js = _read("rpg/rpg-survival-inspector.js")

    assert "window.RpgSurvivalInspector" in js
    assert "survival_action_context" in js
    assert "survival_pressure" in js
    assert "survival_tick_result" in js
    assert "suggested_actions" in js
    assert "next_actions" in js
    assert "recentSurvivalEvents" in js
    assert "rpg-survival-inspector-panel" in js
    assert "data-rpg-survival-command" in js


def test_bundle_bk_survival_inspector_fetch_and_event_hooks_are_present() -> None:
    js = _read("rpg/rpg-survival-inspector.js")

    assert "installFetchObserver" in js
    assert "response.clone().json().then(maybeRenderPayload)" in js
    assert "rpg:survival_payload" in js
    assert "rpg:turn_payload" in js
    assert "rpg:inspector_payload" in js
    assert "/api/rpg" in js


def test_bundle_bk_conversation_settings_loads_survival_inspector_without_touching_rpg_js() -> None:
    settings_js = _read("rpg-conversation-settings.js")
    rpg_js = _read("rpg/rpg.js")

    assert "ensureSurvivalInspectorScript" in settings_js
    assert "/static/rpg/rpg-survival-inspector.js" in settings_js
    assert "rpg-survival-inspector-script" in settings_js
    assert "RpgSurvivalInspector" not in rpg_js


def test_bundle_bk_survival_inspector_styles_exist_for_needs_actions_and_events() -> None:
    css = _read("rpg/rpg-survival-inspector.css")

    assert ".rpg-survival-inspector-panel" in css
    assert ".rpg-survival-needs" in css
    assert ".rpg-survival-need--critical" in css
    assert ".rpg-survival-action" in css
    assert ".rpg-survival-event" in css
