from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "static"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_next_action_buttons_ui_module_exists_and_exports_contract() -> None:
    source = _read(STATIC / "rpg" / "rpgNextActionButtons.js")

    assert "window.RpgNextActionButtons" in source
    assert "normalizeButtons" in source
    assert "submitCommand" in source
    assert "rpg:next_action_buttons" in source
    assert "phase14_24_next_action_buttons_ui" in source


def test_next_action_buttons_ui_submits_preserved_submit_command_not_label() -> None:
    source = _read(STATIC / "rpg" / "rpgNextActionButtons.js")

    assert "data-submit-command" in source
    assert "button.submit_command || button.command" in source
    assert "submitCommand(command)" in source
    assert "button.label" in source
    assert "Buttons submit the preserved command" in source
    assert "You can still type anything" in source


def test_next_action_buttons_ui_filters_malformed_buttons() -> None:
    source = _read(STATIC / "rpg" / "rpgNextActionButtons.js")

    assert "const seen = new Set()" in source
    assert "!id || !command || seen.has(id)" in source
    assert ".slice(0, 8)" in source
    assert "validation_required: button.validation_required !== false" in source
    assert "presentation_only: button.presentation_only !== false" in source


def test_next_action_buttons_ui_watches_rpg_turn_responses() -> None:
    source = _read(STATIC / "rpg" / "rpgNextActionButtons.js")

    assert "installFetchWatcher" in source
    assert "/api/rpg/session/turn" in source
    assert "response.clone().json()" in source
    assert "render(payload)" in source


def test_conversation_settings_bootstrap_loads_next_action_buttons_module() -> None:
    source = _read(STATIC / "rpg-conversation-settings.js")

    assert "ensureNextActionButtonsScript" in source
    assert "/static/rpg/rpgNextActionButtons.js" in source
    assert "rpg-next-action-buttons-script" in source
    assert "ensureNextActionButtonsScript," in source
    assert source.count("ensureNextActionButtonsScript();") >= 2
