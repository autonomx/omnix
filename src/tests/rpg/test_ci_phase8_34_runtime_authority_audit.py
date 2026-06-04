from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
AUDIT = ROOT / "docs" / "plans" / "rpg_phase8_34_runtime_authority_audit.md"
CHROME = ROOT / "src" / "static" / "rpg" / "rpgPanelChrome.js"
LAYOUT = ROOT / "src" / "static" / "rpg" / "rpgPanelLayoutRegistry.js"

READ_ONLY_PANELS = {
    "conversation-settings": ROOT / "src" / "static" / "rpg-conversation-settings.js",
    "map-location": ROOT / "src" / "static" / "rpg" / "rpgMapLocationPanel.js",
    "player-hud": ROOT / "src" / "static" / "rpg" / "rpgPlayerHud.js",
    "objective-journal": ROOT / "src" / "static" / "rpg" / "rpgObjectiveJournalPanel.js",
    "combat-action": ROOT / "src" / "static" / "rpg" / "rpgCombatActionPanel.js",
    "inventory-party": ROOT / "src" / "static" / "rpg" / "rpgInventoryPartyPanel.js",
    "recent-activity": ROOT / "src" / "static" / "rpg" / "rpgRecentActivityPanel.js",
    "suggested-actions": ROOT / "src" / "static" / "rpg" / "rpgSuggestedActionsPanel.js",
}

SURVIVAL = ROOT / "src" / "static" / "rpg" / "rpg-survival-inspector.js"

FORBIDDEN_READ_ONLY_TOKENS = (
    "fetch(",
    "xmlhttprequest",
    "provider",
    "llm",
    "apply_turn",
    "math.random",
    "sendcommand",
    "executecommand",
    "acceptaction",
    "mutateworld",
    "setgamestate",
)


def test_phase8_34_audit_records_runtime_authority_boundary():
    audit = AUDIT.read_text(encoding="utf-8")
    for expected in (
        "Phase 8.34 records the UI runtime-authority boundary audit",
        "Simulation/runtime is authoritative for gameplay truth.",
        "Shared panel chrome is presentation-only.",
        "Suggested actions are hints only and are not accepted gameplay actions.",
        "Survival inspector actions may use command bridge hooks",
        "Rejected/non-player-turn actions must not be treated as successful state changes.",
        "app.rpg.session.runtime_part27",
        "app.rpg.session.runtime_part23",
        "Phase 8.35 — Phase 8 final closeout note and Phase 9 handoff.",
    ):
        assert expected in audit


def test_phase8_34_read_only_panels_do_not_submit_or_mutate_runtime_state():
    for panel_id, path in READ_ONLY_PANELS.items():
        source = path.read_text(encoding="utf-8").lower()
        for forbidden in FORBIDDEN_READ_ONLY_TOKENS:
            assert forbidden not in source, panel_id
        assert "window.rpgpanelchrome" in source, panel_id
        assert "runtimevalidationnotice" in source, panel_id


def test_phase8_34_survival_inspector_is_only_registered_command_intent_panel():
    survival = SURVIVAL.read_text(encoding="utf-8")
    assert "RpgCommandBridge.submitCommand" in survival
    assert "window.rpgSendMessage" in survival
    assert "Survival inspector actions still submit commands through runtime validation" in survival
    for panel_id, path in READ_ONLY_PANELS.items():
        source = path.read_text(encoding="utf-8")
        assert "RpgCommandBridge.submitCommand" not in source, panel_id
        assert "window.rpgSendMessage" not in source, panel_id


def test_phase8_34_shared_chrome_and_layout_remain_provider_free_and_presentation_only():
    chrome = CHROME.read_text(encoding="utf-8")
    layout = LAYOUT.read_text(encoding="utf-8")
    assert 'READ_ONLY_AUTHORITY = "runtime_validated_commands_only"' in chrome
    assert "runtimeValidationNotice" in chrome
    assert "Panel is presentation-only; gameplay authority stays with runtime validation." in chrome
    for source_name, source in (("chrome", chrome.lower()), ("layout", layout.lower())):
        for forbidden in ("fetch(", "xmlhttprequest", "provider", "llm", "apply_turn", "math.random", "sendcommand", "executecommand"):
            assert forbidden not in source, source_name


def test_phase8_34_runtime_wrapper_manifest_remains_authoritative():
    from app.rpg.session import runtime

    manifest = runtime.get_runtime_wrapper_manifest()
    assert manifest["final_apply_turn_authoritative_module"] == "app.rpg.session.runtime_part27"
    assert manifest["final_apply_attack_combat_action_module"] == "app.rpg.session.runtime_part23"
