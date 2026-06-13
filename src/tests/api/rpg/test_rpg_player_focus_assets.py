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


def test_rpg_start_menu_clears_saved_session_before_new_adventure():
    script = (STATIC / "rpg" / "rpg-player-focus.js").read_text(encoding="utf-8")
    css = (STATIC / "rpg" / "rpg-player-focus.css").read_text(encoding="utf-8")

    assert "Choose your adventure" in script
    assert "Continue Previous Adventure" in script
    assert "New Quick Adventure" in script
    assert "New Custom Adventure" in script
    assert "clearSavedRpgSession" in script
    assert "omnix_rpg_session_id" in script
    assert "omnix_rpg_state" in script
    assert "omnix:rpg:start_action" in script
    assert "rpgQuickAdventureBtn" in script
    assert "rpgSetupBtn" in script
    assert ".rpg-start-menu-overlay" in css
    assert ".rpg-start-secondary" in css


def test_player_focus_provides_legacy_combat_controls_helper():
    script = (STATIC / "rpg" / "rpg-player-focus.js").read_text(encoding="utf-8")

    assert "ensureCombatControlHelper" in script
    assert "window.rpgUpdateCombatControls" in script
    assert "data-combat-action" in script
    assert "resolve_current" in script


def test_player_focus_skips_preview_session_resume_requests():
    script = (STATIC / "rpg" / "rpg-player-focus.js").read_text(encoding="utf-8")

    assert "/api\\/rpg\\/session\\/resume" in script
    assert "preview_session_resume_skipped" in script
    assert "indexOf('preview_') === 0" in script
    assert "previewResumeResponse" in script


def test_player_focus_filters_generic_ambient_filler():
    script = (STATIC / "rpg" / "rpg-player-focus.js").read_text(encoding="utf-8")

    assert "murmurs a quick thought under their breath" in script
    assert "cleanAmbientNode" in script
    assert "isGenericAmbientFiller" in script


def test_player_focus_does_not_clear_pending_state_on_player_message():
    script = (STATIC / "rpg" / "rpg-player-focus.js").read_text(encoding="utf-8")

    assert "isPlayerMessageNode" in script
    assert "rpg-msg--player" in script
    assert "if (isPlayerMessageNode(node)) return false" in script
    assert "Still waiting for the GM/NPC response" in script


def test_player_focus_does_not_short_circuit_turn_stream_llm_calls():
    script = (STATIC / "rpg" / "rpg-player-focus.js").read_text(encoding="utf-8")

    assert "previewTurnStreamResponse" not in script
    assert "preview_fast_response" not in script
    assert "preview_session_fast_path" not in script
    assert "A room is available. Five silver for the night" not in script
    assert "/api\\/rpg\\/session\\/turn" in script


def test_turn_submit_watchdog_asset_is_loaded_and_recovers_missing_stream_submit():
    loader = (STATIC / "rpg-conversation-settings.js").read_text(encoding="utf-8")
    script = (STATIC / "rpg" / "rpg-turn-submit-watchdog.js").read_text(encoding="utf-8")

    assert "/static/rpg/rpg-turn-submit-watchdog.js" in loader
    assert "ensureTurnSubmitWatchdogScript" in loader
    assert "no_turn_stream_fetch_detected" in script
    assert "watchdog_recovery" in script
    assert "/api/rpg/session/turn/stream" in script
    assert "ambient_ignored" in script
    assert "rpg-ambient" in script
