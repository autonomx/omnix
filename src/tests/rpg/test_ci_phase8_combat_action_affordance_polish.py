from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-pr-deterministic.yml"
RENDERER = ROOT / "src" / "static" / "rpg" / "rpgCombatActionPanel.js"
SOURCE = "deterministic_phase8_combat_state_action_affordance_gate"
GATE_NAME = "RPG CI Phase 8 combat action affordance polish gate"
GATE_COMMAND = "python -m pytest src/tests/rpg/test_ci_phase8_combat_action_affordance_polish.py -q --tb=short"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_ci_phase8_combat_polish_renderer_exports_read_only_helpers():
    renderer = _read(RENDERER)

    for expected in (
        "healthPercent",
        "participantStateLabel",
        "targetThreatLabel",
        "actionCommand",
        "turnGuidance",
        "renderTarget",
        "rpg-combat-turn-guidance",
        "rpg-combat-health-bar",
        "rpg-combat-action-command",
        "rpg-combat-targets",
        "data-active",
        "data-action-type",
        "data-target-id",
    ):
        assert expected in renderer

    assert "window.RpgCombatActionPanel" in renderer
    assert "combatActionPayloadFromTurnPayload" in renderer
    assert "innerHTML" in renderer
    assert "escapeHtml" in renderer
    assert SOURCE in _read(ROOT / "src" / "app" / "rpg" / "session" / "runtime_part27.py")


def test_ci_phase8_combat_polish_preserves_runtime_authority_and_provider_free_ui():
    renderer = _read(RENDERER)

    forbidden_tokens = (
        "fetch(",
        "XMLHttpRequest",
        "localStorage.setItem",
        "sessionStorage.setItem",
        "Math.random",
        "provider",
        "llm",
        "applyAttack",
        "apply_turn",
        "sendCombat",
    )
    lower_renderer = renderer.lower()
    for token in forbidden_tokens:
        assert token.lower() not in lower_renderer

    assert "Choose a listed combat action; the runtime still validates the command." in renderer
    assert "player combat commands should not be treated as accepted yet" in renderer
    assert "No active combat. Continue exploring or pursue your current objective." in renderer


def test_ci_phase8_combat_polish_escapes_new_visible_values():
    renderer = _read(RENDERER)

    for expected in (
        "${escapeHtml(guidance)}",
        "${escapeHtml(command)}",
        "${escapeHtml(percent)}%",
        "${escapeHtml(actorId)}",
        "${escapeHtml(action.action_type || \"action\")}",
    ):
        assert expected in renderer

    assert 'style="width: ${escapeHtml(percent)}%"' in renderer
    assert 'aria-label="${escapeHtml(name)} health ${escapeHtml(percent)} percent"' in renderer


def test_ci_phase8_combat_polish_workflow_gate_is_ordered_before_manifest():
    workflow = _read(WORKFLOW)

    assert GATE_NAME in workflow
    assert GATE_COMMAND in workflow
    previous_gate = "RPG CI Phase 8 combat state action affordance gate"
    next_gate = "RPG CI runtime facade manifest gate"
    assert workflow.index(previous_gate) < workflow.index(GATE_NAME) < workflow.index(next_gate)


def test_ci_phase8_combat_polish_runtime_manifest_stays_authoritative():
    from app.rpg.session import runtime

    manifest = runtime.get_runtime_wrapper_manifest()

    assert manifest["final_apply_turn_authoritative_module"] == "app.rpg.session.runtime_part27"
    assert manifest["final_apply_attack_combat_action_module"] == "app.rpg.session.runtime_part23"
