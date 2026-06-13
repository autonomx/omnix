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


def test_runtime_promotion_normalizes_missing_turn_ids_before_rpg_js():
    script = (STATIC / "rpg" / "runtime-promotion-panel.js").read_text(encoding="utf-8")

    assert "normalizeTurnStreamEvent" in script
    assert "event.turn_id = 'client_turn_' + Date.now()" in script
    assert "event.fallback_narration" in script
    assert "/api/rpg/session/turn/stream" in script
    assert "wrapTurnStreamIdentifiers" in script


def test_runtime_promotion_exports_turn_stream_normalizer_for_debugging():
    script = (STATIC / "rpg" / "runtime-promotion-panel.js").read_text(encoding="utf-8")

    assert "window.RpgRuntimePromotionPanel" in script
    assert "normalizeTurnStreamEvent: normalizeTurnStreamEvent" in script
