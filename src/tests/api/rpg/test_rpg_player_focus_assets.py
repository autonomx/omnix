from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
STATIC = ROOT / "static"


def test_player_focus_assets_exist_and_are_loaded_by_conversation_settings():
    css = STATIC / "rpg" / "rpg-player-focus.css"
    js = STATIC / "rpg" / "rpg-player-focus.js"
    loader = STATIC / "rpg-conversation-settings.js"

    assert css.exists()
    assert js.exists()
    assert loader.exists()

    loader_text = loader.read_text(encoding="utf-8")
    assert "/static/rpg/rpg-player-focus.css" in loader_text
    assert "/static/rpg/rpg-player-focus.js" in loader_text
    assert "ensurePlayerFocusAssets" in loader_text


def test_player_focus_script_exposes_focus_controller_and_watchdog_copy():
    script = (STATIC / "rpg" / "rpg-player-focus.js").read_text(encoding="utf-8")

    assert "window.RpgPlayerFocus" in script
    assert "rpg-player-focus" in script
    assert "rpg-dev-panels-open" in script
    assert "Response is taking longer than expected" in script
    assert "markTurnActive" in script
    assert "markTurnDone" in script


def test_player_focus_css_hides_developer_chrome_by_default():
    css = (STATIC / "rpg" / "rpg-player-focus.css").read_text(encoding="utf-8")

    assert "body.rpg-player-focus #rpgTopPanels" in css
    assert "body.rpg-player-focus #rpg-player-journal-panel" in css
    assert "body.rpg-player-focus #rpg-inspector-tabs" in css
    assert "body.rpg-player-focus .rpg-conversation-settings-panel" in css
    assert "body.rpg-player-focus.rpg-dev-panels-open" in css
    assert ".rpg-turn-status-chip" in css
