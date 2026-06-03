from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-pr-deterministic.yml"
RENDERER = ROOT / "src" / "static" / "rpg" / "rpgRecentActivityPanel.js"
SETTINGS = ROOT / "src" / "static" / "rpg-conversation-settings.js"

GATE_NAME = "RPG CI Phase 8 recent activity panel gate"
GATE_COMMAND = "python -m pytest src/tests/rpg/test_ci_phase8_recent_activity_panel.py -q --tb=short"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_ci_phase8_recent_activity_panel_renderer_exports_read_only_helpers():
    renderer = _read(RENDERER)

    for expected in (
        "window.RpgRecentActivityPanel",
        "recentActivityPayloadFromTurnPayload",
        "renderRecentActivityPanel",
        "normalizeActivityEntries",
        "renderActivityEntry",
        "rpg-recent-activity-panel",
        "rpg-recent-activity-entry",
        "data-activity-kind",
        "data-source",
        "journal_entries",
        "world_events",
        "major_warnings",
        "recent_action_state",
    ):
        assert expected in renderer

    assert "innerHTML" in renderer
    assert "escapeHtml" in renderer


def test_ci_phase8_recent_activity_panel_is_provider_free_and_read_only():
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
        "sendActivity",
        "mutateWorld",
        "acceptAction",
    )
    for token in forbidden_tokens:
        assert token.lower() not in lower_renderer

    assert "Read-only world, journal, warning, and action signals from deterministic payloads." in renderer
    assert "commands still go through runtime validation" in renderer


def test_ci_phase8_recent_activity_panel_escapes_visible_values():
    renderer = _read(RENDERER)

    for expected in (
        "${escapeHtml(source)}",
        "${escapeHtml(kind)}",
        "${escapeHtml(label)}",
        "${escapeHtml(detail)}",
        "${escapeHtml(severity)}",
    ):
        assert expected in renderer


def test_ci_phase8_recent_activity_panel_is_loaded_by_frontend_settings():
    settings = _read(SETTINGS)

    assert "rpgRecentActivityPanel.js" in settings
    assert "rpgInventoryPartyPanel.js" in settings
    assert settings.index("rpgInventoryPartyPanel.js") < settings.index("rpgRecentActivityPanel.js")


def test_ci_phase8_recent_activity_panel_workflow_gate_is_ordered_before_manifest():
    workflow = _read(WORKFLOW)

    assert GATE_NAME in workflow
    assert GATE_COMMAND in workflow
    previous_gate = "RPG CI Phase 8 inventory party detail panel gate"
    next_gate = "RPG CI runtime facade manifest gate"
    assert workflow.index(previous_gate) < workflow.index(GATE_NAME) < workflow.index(next_gate)


def test_ci_phase8_recent_activity_panel_runtime_manifest_stays_authoritative():
    from app.rpg.session import runtime

    manifest = runtime.get_runtime_wrapper_manifest()

    assert manifest["final_apply_turn_authoritative_module"] == "app.rpg.session.runtime_part27"
    assert manifest["final_apply_attack_combat_action_module"] == "app.rpg.session.runtime_part23"
