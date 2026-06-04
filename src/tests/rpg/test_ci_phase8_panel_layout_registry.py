from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = ROOT / "src" / "static" / "rpg" / "rpgPanelLayoutRegistry.js"
CHROME = ROOT / "src" / "static" / "rpg" / "rpgPanelChrome.js"
SETTINGS = ROOT / "src" / "static" / "rpg-conversation-settings.js"
RECENT_ACTIVITY = ROOT / "src" / "static" / "rpg" / "rpgRecentActivityPanel.js"
SUGGESTED_ACTIONS = ROOT / "src" / "static" / "rpg" / "rpgSuggestedActionsPanel.js"
INVENTORY_PARTY = ROOT / "src" / "static" / "rpg" / "rpgInventoryPartyPanel.js"
COMBAT_ACTION = ROOT / "src" / "static" / "rpg" / "rpgCombatActionPanel.js"
OBJECTIVE_JOURNAL = ROOT / "src" / "static" / "rpg" / "rpgObjectiveJournalPanel.js"
PLAYER_HUD = ROOT / "src" / "static" / "rpg" / "rpgPlayerHud.js"
MAP_LOCATION = ROOT / "src" / "static" / "rpg" / "rpgMapLocationPanel.js"
SURVIVAL_INSPECTOR = ROOT / "src" / "static" / "rpg" / "rpg-survival-inspector.js"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-pr-deterministic.yml"


def test_panel_layout_registry_exports_ordered_slots():
    registry = REGISTRY.read_text(encoding="utf-8")
    for expected in (
        "deterministic_phase8_panel_layout_registry",
        "PANEL_ORDER",
        "conversation-settings",
        "map-location",
        "player-hud",
        "objective-journal",
        "combat-action",
        "inventory-party",
        "recent-activity",
        "suggested-actions",
        "survival-inspector",
        "window.RpgPanelLayoutRegistry",
    ):
        assert expected in registry


def test_panel_layout_registry_exports_accessibility_metadata():
    registry = REGISTRY.read_text(encoding="utf-8")
    for expected in (
        "PANEL_LABELS",
        "panelLabels",
        "panelLabel",
        "panelIndex",
        "RPG status panels",
        "Conversation settings panel",
        "Map and location panel",
        "Player HUD panel",
        "Survival inspector panel",
        "role", "region",
        "aria-label",
        "data-panel-order",
    ):
        assert expected in registry


def test_panel_layout_registry_is_provider_free():
    registry = REGISTRY.read_text(encoding="utf-8").lower()
    for forbidden in ("fetch(", "xmlhttprequest", "provider", "llm", "apply_turn", "math.random"):
        assert forbidden not in registry


def test_panel_layout_registry_is_loaded_before_panels():
    settings = SETTINGS.read_text(encoding="utf-8")
    assert "rpgPanelLayoutRegistry.js" in settings
    assert settings.index("rpgPanelLayoutRegistry.js") < settings.index("rpgPlayerHud.js")
    assert settings.index("rpgPanelLayoutRegistry.js") < settings.index("rpgSuggestedActionsPanel.js")


def test_conversation_settings_uses_panel_chrome_without_runtime_authority():
    settings = SETTINGS.read_text(encoding="utf-8")
    for expected in (
        "window.RpgPanelChrome",
        "panelSourceBadge",
        "runtimeValidationNotice",
        "decoratePanel(panel, \"conversation-settings\", SOURCE)",
        "data-panel-chrome=\"deterministic_phase8_panel_chrome\"",
        "deterministic_conversation_settings",
    ):
        assert expected in settings
    assert "Conversation settings only affect presentation/audit preferences" in settings
    assert "gameplay state changes still go through runtime validation" in settings
    assert "apply_turn" not in settings
    assert "provider" not in settings.lower()
    assert "llm" not in settings.lower()


def test_panel_chrome_exports_read_only_visibility_helpers():
    chrome = CHROME.read_text(encoding="utf-8")
    for expected in (
        "deterministic_phase8_panel_chrome",
        "panelSourceBadge",
        "panelEmptyState",
        "runtimeValidationNotice",
        "attachPanelToLayout",
        "decoratePanel",
        "window.RpgPanelChrome",
    ):
        assert expected in chrome


def test_panel_chrome_exports_accessibility_metadata_helpers():
    chrome = CHROME.read_text(encoding="utf-8")
    for expected in (
        "panelChromeLabel",
        "panelChromeA11yAttrs",
        "data-panel-a11y-source",
        "role=\"region\"",
        "aria-label",
        "role=\"note\"",
        "Runtime validation notice",
        "role=\"status\"",
        "aria-live=\"polite\"",
        "tabindex",
        "window.RpgPanelLayoutRegistry",
    ):
        assert expected in chrome


def test_panel_chrome_exports_state_metadata_helpers():
    chrome = CHROME.read_text(encoding="utf-8")
    for expected in (
        "PANEL_STATES",
        "panelChromeState",
        "panelStateAttrs",
        "applyPanelState",
        "data-panel-state",
        "data-panel-state-source",
        "source_backed",
        "advisory",
        "empty",
        "ready",
        "panelStateAttrs(\"source_backed\")",
        "panelStateAttrs(\"empty\")",
        "panelStateAttrs(\"advisory\")",
        "applyPanelState(attached, state || \"ready\")",
    ):
        assert expected in chrome


def test_panel_chrome_exports_read_only_metadata_helpers():
    chrome = CHROME.read_text(encoding="utf-8")
    for expected in (
        "READ_ONLY_AUTHORITY",
        "runtime_validated_commands_only",
        "readOnlyAttrs",
        "applyReadOnlyMetadata",
        "data-panel-read-only",
        "data-panel-authority",
        "data-panel-read-only-source",
        "data-panel-read-only-reason",
        "aria-readonly",
        "Panel is presentation-only; gameplay authority stays with runtime validation.",
        "Runtime validation remains authoritative for gameplay commands.",
        "applyReadOnlyMetadata(attached)",
    ):
        assert expected in chrome


def test_panel_chrome_is_provider_free_and_non_mutating():
    chrome = CHROME.read_text(encoding="utf-8").lower()
    for forbidden in (
        "fetch(",
        "xmlhttprequest",
        "provider",
        "llm",
        "apply_turn",
        "sendcommand",
        "executecommand",
        "math.random",
    ):
        assert forbidden not in chrome


def test_panel_chrome_loads_after_layout_registry_before_panels():
    settings = SETTINGS.read_text(encoding="utf-8")
    assert "rpgPanelChrome.js" in settings
    assert "ensurePanelChromeScript" in settings
    assert settings.index("rpgPanelLayoutRegistry.js") < settings.index("rpgPanelChrome.js")
    assert settings.index("rpgPanelChrome.js") < settings.index("rpgRecentActivityPanel.js")
    assert settings.index("rpgPanelChrome.js") < settings.index("rpgSuggestedActionsPanel.js")


def test_recent_activity_uses_panel_chrome_without_runtime_authority():
    recent = RECENT_ACTIVITY.read_text(encoding="utf-8")
    for expected in (
        "window.RpgPanelChrome",
        "panelSourceBadge",
        "panelEmptyState",
        "runtimeValidationNotice",
        "decoratePanel(target, \"recent-activity\", source)",
        "data-panel-chrome=\"deterministic_phase8_panel_chrome\"",
    ):
        assert expected in recent
    assert "commands still go through runtime validation" in recent


def test_suggested_actions_uses_panel_chrome_without_runtime_authority():
    suggested = SUGGESTED_ACTIONS.read_text(encoding="utf-8")
    for expected in (
        "window.RpgPanelChrome",
        "panelSourceBadge",
        "panelEmptyState",
        "runtimeValidationNotice",
        "decoratePanel(target, \"suggested-actions\", source)",
        "data-panel-chrome=\"deterministic_phase8_panel_chrome\"",
    ):
        assert expected in suggested
    assert "Suggestions are not accepted actions until runtime validates the command" in suggested


def test_inventory_party_uses_panel_chrome_without_runtime_authority():
    inventory = INVENTORY_PARTY.read_text(encoding="utf-8")
    for expected in (
        "window.RpgPanelChrome",
        "panelSourceBadge",
        "panelEmptyState",
        "runtimeValidationNotice",
        "decoratePanel(target, \"inventory-party\", source)",
        "data-panel-chrome=\"deterministic_phase8_panel_chrome\"",
    ):
        assert expected in inventory
    assert "Inventory and party details are read-only" in inventory
    assert "commands still go through runtime validation" in inventory


def test_combat_action_uses_panel_chrome_without_runtime_authority():
    combat = COMBAT_ACTION.read_text(encoding="utf-8")
    for expected in (
        "window.RpgPanelChrome",
        "panelSourceBadge",
        "panelEmptyState",
        "runtimeValidationNotice",
        "decoratePanel(target, \"combat-action\", source)",
        "data-panel-chrome=\"deterministic_phase8_panel_chrome\"",
    ):
        assert expected in combat
    assert "Combat action affordances are read-only" in combat
    assert "commands still go through runtime validation" in combat
    assert "sendCommand" not in combat
    assert "executeCommand" not in combat


def test_objective_journal_uses_panel_chrome_without_runtime_authority():
    journal = OBJECTIVE_JOURNAL.read_text(encoding="utf-8")
    for expected in (
        "window.RpgPanelChrome",
        "panelSourceBadge",
        "panelEmptyState",
        "runtimeValidationNotice",
        "decoratePanel(target, \"objective-journal\", source)",
        "data-panel-chrome=\"deterministic_phase8_panel_chrome\"",
    ):
        assert expected in journal
    assert "Objectives and journal entries are read-only" in journal
    assert "commands still go through runtime validation" in journal
    assert "sendCommand" not in journal
    assert "executeCommand" not in journal


def test_player_hud_uses_panel_chrome_without_runtime_authority():
    hud = PLAYER_HUD.read_text(encoding="utf-8")
    for expected in (
        "window.RpgPanelChrome",
        "panelSourceBadge",
        "panelEmptyState",
        "runtimeValidationNotice",
        "decoratePanel(target, \"player-hud\", source)",
        "data-panel-chrome=\"deterministic_phase8_panel_chrome\"",
    ):
        assert expected in hud
    assert "Player HUD details are read-only" in hud
    assert "commands still go through runtime validation" in hud
    assert "sendCommand" not in hud
    assert "executeCommand" not in hud


def test_map_location_uses_panel_chrome_without_runtime_authority():
    map_location = MAP_LOCATION.read_text(encoding="utf-8")
    for expected in (
        "window.RpgPanelChrome",
        "panelSourceBadge",
        "panelEmptyState",
        "runtimeValidationNotice",
        "decoratePanel(target, \"map-location\", source)",
        "data-panel-chrome=\"deterministic_phase8_panel_chrome\"",
    ):
        assert expected in map_location
    assert "Map and location details are read-only" in map_location
    assert "commands still go through runtime validation" in map_location
    assert "sendCommand" not in map_location
    assert "executeCommand" not in map_location


def test_survival_inspector_uses_panel_chrome_with_runtime_validation():
    survival = SURVIVAL_INSPECTOR.read_text(encoding="utf-8")
    for expected in (
        "window.RpgPanelChrome",
        "panelSourceBadge",
        "panelEmptyState",
        "runtimeValidationNotice",
        "decoratePanel(panel, \"survival-inspector\", SOURCE)",
        "data-panel-chrome=\"deterministic_phase8_panel_chrome\"",
    ):
        assert expected in survival
    assert "Survival inspector actions still submit commands through runtime validation" in survival
    assert "RpgCommandBridge.submitCommand" in survival
    assert "window.rpgSendMessage" in survival
    assert "provider" not in survival.lower()
    assert "llm" not in survival.lower()


def test_panel_layout_registry_gate_is_ordered():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    gate = "RPG CI Phase 8 panel layout registry gate"
    assert gate in workflow
    assert "test_ci_phase8_panel_layout_registry.py" in workflow
    assert workflow.index("RPG CI Phase 8 suggested actions panel gate") < workflow.index(gate)
    assert workflow.index(gate) < workflow.index("RPG CI runtime facade manifest gate")
