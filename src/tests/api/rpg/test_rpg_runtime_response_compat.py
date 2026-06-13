from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT
STATIC = ROOT / "static"


def test_sitecustomize_provides_opening_bonus_default():
    sitecustomize = SRC / "sitecustomize.py"
    text = sitecustomize.read_text(encoding="utf-8")

    assert "builtins.opening_bonus" in text
    assert "0.0" in text
    assert "resume/idle catch-up" in text


def test_sitecustomize_adapts_lmstudio_for_rpg_narrator_interface():
    sitecustomize = SRC / "sitecustomize.py"
    text = sitecustomize.read_text(encoding="utf-8")

    assert "_install_rpg_lmstudio_gateway_compat" in text
    assert "LMStudioProvider.generate" in text
    assert "LMStudioProvider.generate_stream" in text
    assert "LMStudioProvider.call" in text
    assert "chat_completion" in text


def test_runtime_promotion_normalizes_missing_turn_ids_before_rpg_js():
    script = (STATIC / "rpg" / "runtime-promotion-panel.js").read_text(encoding="utf-8")

    assert "normalizeTurnStreamEvent" in script
    assert "event.turn_id = 'client_turn_' + Date.now()" in script
    assert "event.fallback_narration" in script
    assert "/api/rpg/session/turn/stream" in script
    assert "wrapTurnStreamIdentifiers" in script


def test_runtime_promotion_improves_generic_bran_room_fallback():
    script = (STATIC / "rpg" / "runtime-promotion-panel.js").read_text(encoding="utf-8")

    assert "improveFallbackForCurrentCommand" in script
    assert "serviceFallbackForCommand" in script
    assert "mentionsRoom" in script
    assert "mentionsBran" in script
    assert "Five silver for the night" in script
    assert "A deliberate action is taken" in script


def test_runtime_promotion_exports_turn_stream_normalizer_for_debugging():
    script = (STATIC / "rpg" / "runtime-promotion-panel.js").read_text(encoding="utf-8")

    assert "window.RpgRuntimePromotionPanel" in script
    assert "normalizeTurnStreamEvent: normalizeTurnStreamEvent" in script
    assert "improveFallbackForCurrentCommand: improveFallbackForCurrentCommand" in script


def test_player_focus_logs_turn_stream_without_wrapping_or_canceling_it():
    script = (STATIC / "rpg" / "rpg-player-focus.js").read_text(encoding="utf-8")

    assert "[RPG][TurnDebug]" in script
    assert "fetch_start" in script
    assert "fetch_response" in script
    assert "watchdog_stalled" in script
    assert "feed_response_node" in script
    assert "Do not wrap/cancel turn streams here" in script
    assert "wrapTurnStreamResponseWithAuthoritativeFallback" not in script
    assert "reader.cancel('authoritative fallback delivered')" not in script
