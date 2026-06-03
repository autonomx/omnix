from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-pr-deterministic.yml"
RENDERER = ROOT / "src" / "static" / "rpg" / "rpgSuggestedActionsPanel.js"
SETTINGS = ROOT / "src" / "static" / "rpg-conversation-settings.js"

GATE_NAME = "RPG CI Phase 8 suggested actions panel gate"
GATE_COMMAND = "python -m pytest src/tests/rpg/test_ci_phase8_suggested_actions_panel.py -q --tb=short"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_ci_phase8_suggested_actions_panel_renderer_exports_read_only_helpers():
    renderer = _read(RENDERER)

    for expected in (
        "window.RpgSuggestedActionsPanel",
        "suggestedActionsPayloadFromTurnPayload",
        "renderSuggestedActionsPanel",
        "normalizeSuggestedActions",
        "renderSuggestedAction",
        "rpg-suggested-actions-panel",
        "rpg-suggested-action",
        "data-action-kind",
        "data-source",
        "suggested_actions",
        "legal_actions",
        "active_objectives",
    ):
        assert expected in renderer

    assert "innerHTML" in renderer
    assert "escapeHtml" in renderer


def test_ci_phase8_suggested_actions_panel_is_provider_free_and_read_only():
    renderer = _read(RENDERER)
    lower_renderer = renderer.lower()

    forbidden_tokens = (
        "fetch(",
        "XMLHttpRequest",
        "localStorage.setItem",
        "sessionStorage.setItem",
        "Math.random",
        "provider",
        "llm",
        "apply_turn",
        "sendAction",
        "acceptAction",
        "mutate",
    )
    for token in forbidden_tokens:
        assert token.lower() not in lower_renderer

    assert "Read-only command hints from deterministic payloads." in renderer
    assert "not accepted actions until runtime validates the command" in renderer


def test_ci_phase8_suggested_actions_panel_escapes_visible_values():
    renderer = _read(RENDERER)

    for expected in (
        "${escapeHtml(source)}",
        "${escapeHtml(kind)}",
        "${escapeHtml(label)}",
        "${escapeHtml(command)}",
        "${escapeHtml(reason)}",
    ):
        assert expected in renderer


def test_ci_phase8_suggested_actions_panel_is_loaded_by_frontend_settings():
    settings = _read(SETTINGS)

    assert "rpgSuggestedActionsPanel.js" in settings
    assert "rpgRecentActivityPanel.js" in settings
    assert settings.index("rpgRecentActivityPanel.js") < settings.index("rpgSuggestedActionsPanel.js")


def test_ci_phase8_suggested_actions_panel_workflow_gate_is_ordered_before_manifest():
    workflow = _read(WORKFLOW)

    assert GATE_NAME in workflow
    assert GATE_COMMAND in workflow
    previous_gate = "RPG CI Phase 8 recent activity panel gate"
    next_gate = "RPG CI runtime facade manifest gate"
    assert workflow.index(previous_gate) < workflow.index(GATE_NAME) < workflow.index(next_gate)


def test_ci_phase8_suggested_actions_panel_runtime_manifest_stays_authoritative():
    from app.rpg.session import runtime

    manifest = runtime.get_runtime_wrapper_manifest()

    assert manifest["final_apply_turn_authoritative_module"] == "app.rpg.session.runtime_part27"
    assert manifest["final_apply_attack_combat_action_module"] == "app.rpg.session.runtime_part23"
