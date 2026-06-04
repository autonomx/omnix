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


def assert_contains(text, expected_values):
    for expected in expected_values:
        assert expected in text


def test_panel_layout_registry_exports_ordered_accessible_slots():
    registry = REGISTRY.read_text(encoding="utf-8")
    assert_contains(
        registry,
        (
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
            "PANEL_LABELS",
            "panelLabels",
            "panelLabel",
            "panelIndex",
            "RPG status panels",
            "Conversation settings panel",
            "Map and location panel",
            "Player HUD panel",
            "Survival inspector panel",
            "role",
            "region",
            "aria-label",
            "data-panel-order",
        ),
    )


def test_panel_layout_registry_is_provider_free():
    registry = REGISTRY.read_text(encoding="utf-8").lower()
    for forbidden in ("fetch(", "xmlhttprequest", "provider", "llm", "apply_turn", "math.random"):
        assert forbidden not in registry


def test_panel_layout_registry_and_chrome_load_before_panels():
    settings = SETTINGS.read_text(encoding="utf-8")
    assert "rpgPanelLayoutRegistry.js" in settings
    assert "rpgPanelChrome.js" in settings
    assert "ensurePanelChromeScript" in settings
    assert settings.index("rpgPanelLayoutRegistry.js") < settings.index("rpgPanelChrome.js")
    assert settings.index("rpgPanelLayoutRegistry.js") < settings.index("rpgPlayerHud.js")
    assert settings.index("rpgPanelChrome.js") < settings.index("rpgRecentActivityPanel.js")
    assert settings.index("rpgPanelChrome.js") < settings.index("rpgSuggestedActionsPanel.js")


def test_panel_chrome_exports_read_only_visibility_and_accessibility_helpers():
    chrome = CHROME.read_text(encoding="utf-8")
    assert_contains(
        chrome,
        (
            "deterministic_phase8_panel_chrome",
            "panelSourceBadge",
            "panelEmptyState",
            "runtimeValidationNotice",
            "attachPanelToLayout",
            "decoratePanel",
            "window.RpgPanelChrome",
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
        ),
    )


def test_panel_chrome_exports_state_readonly_focus_and_section_metadata():
    chrome = CHROME.read_text(encoding="utf-8")
    assert_contains(
        chrome,
        (
            "PANEL_STATES",
            "panelChromeState",
            "panelStateAttrs",
            "applyPanelState",
            "data-panel-state",
            "source_backed",
            "advisory",
            "empty",
            "ready",
            "READ_ONLY_AUTHORITY",
            "runtime_validated_commands_only",
            "readOnlyAttrs",
            "applyReadOnlyMetadata",
            "data-panel-read-only",
            "data-panel-authority",
            "aria-readonly",
            "FOCUS_TARGET",
            "panel_region",
            "focusAttrs",
            "applyFocusMetadata",
            "data-panel-focus-target",
            "data-panel-focus-source",
            "data-panel-focus-label",
            "PANEL_DENSITIES",
            "PANEL_SECTIONS",
            "densityAttrs",
            "applyDensityMetadata",
            "panelChromeSection",
            "sectionAttrs",
            "applySectionMetadata",
            "header",
            "body",
            "footer",
            "root",
            "applySectionMetadata(attached, \"root\")",
        ),
    )


def test_panel_chrome_exports_freshness_priority_render_provenance_tone_schema_metadata():
    chrome = CHROME.read_text(encoding="utf-8")
    assert_contains(
        chrome,
        (
            "PANEL_FRESHNESS",
            "panelChromeFreshness",
            "freshnessAttrs",
            "applyFreshnessMetadata",
            "data-panel-freshness",
            "live",
            "missing",
            "snapshot",
            "stale",
            "PANEL_PRIORITIES",
            "panelChromePriority",
            "priorityAttrs",
            "applyPriorityMetadata",
            "data-panel-priority",
            "critical",
            "high",
            "low",
            "normal",
            "PANEL_RENDER_KINDS",
            "panelChromeRenderKind",
            "renderKindAttrs",
            "applyRenderKindMetadata",
            "data-panel-render-kind",
            "badge",
            "empty_state",
            "notice",
            "panel",
            "PANEL_PROVENANCE",
            "panelChromeProvenance",
            "provenanceAttrs",
            "applyProvenanceMetadata",
            "data-panel-provenance",
            "chrome",
            "layout_registry",
            "payload",
            "runtime_contract",
            "PANEL_TONES",
            "panelChromeTone",
            "toneAttrs",
            "applyToneMetadata",
            "data-panel-tone",
            "info",
            "muted",
            "neutral",
            "warning",
            "PANEL_SCHEMA_VERSION",
            "phase8_panel_chrome_v1",
            "panelChromeSchemaVersion",
            "schemaAttrs",
            "applySchemaMetadata",
            "data-panel-schema-version",
            "data-panel-schema-source",
            "applySchemaMetadata(attached)",
        ),
    )


def test_panel_chrome_exports_surface_metadata_helpers():
    chrome = CHROME.read_text(encoding="utf-8")
    assert_contains(
        chrome,
        (
            "PANEL_SURFACES",
            "panelChromeSurface",
            "surfaceAttrs",
            "applySurfaceMetadata",
            "data-panel-surface",
            "data-panel-surface-source",
            "badge",
            "empty",
            "notice",
            "panel",
            "surfaceAttrs(\"badge\")",
            "surfaceAttrs(\"empty\")",
            "surfaceAttrs(\"notice\")",
            "applySurfaceMetadata(attached, surface || \"panel\")",
        ),
    )


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
    assert ".focus(" not in chrome
    assert "addeventlistener" not in chrome


def assert_panel_uses_chrome(panel_path, decorate_call, authority_text, allows_command_bridge=False):
    panel = panel_path.read_text(encoding="utf-8")
    assert_contains(
        panel,
        (
            "window.RpgPanelChrome",
            "panelSourceBadge",
            "panelEmptyState",
            "runtimeValidationNotice",
            decorate_call,
            "data-panel-chrome=\"deterministic_phase8_panel_chrome\"",
        ),
    )
    assert authority_text in panel
    if allows_command_bridge:
        assert "RpgCommandBridge.submitCommand" in panel
        assert "window.rpgSendMessage" in panel
    else:
        assert "sendCommand" not in panel
        assert "executeCommand" not in panel
    assert "provider" not in panel.lower()
    assert "llm" not in panel.lower()


def test_conversation_settings_uses_panel_chrome_without_runtime_authority():
    settings = SETTINGS.read_text(encoding="utf-8")
    assert_contains(
        settings,
        (
            "window.RpgPanelChrome",
            "panelSourceBadge",
            "runtimeValidationNotice",
            "decoratePanel(panel, \"conversation-settings\", SOURCE)",
            "data-panel-chrome=\"deterministic_phase8_panel_chrome\"",
            "deterministic_conversation_settings",
        ),
    )
    assert "Conversation settings only affect presentation/audit preferences" in settings
    assert "gameplay state changes still go through runtime validation" in settings
    assert "apply_turn" not in settings
    assert "provider" not in settings.lower()
    assert "llm" not in settings.lower()


def test_registered_panels_use_panel_chrome_without_runtime_authority():
    for panel_path, decorate_call, authority_text in (
        (RECENT_ACTIVITY, "decoratePanel(target, \"recent-activity\", source)", "commands still go through runtime validation"),
        (SUGGESTED_ACTIONS, "decoratePanel(target, \"suggested-actions\", source)", "Suggestions are not accepted actions until runtime validates the command"),
        (INVENTORY_PARTY, "decoratePanel(target, \"inventory-party\", source)", "Inventory and party details are read-only"),
        (COMBAT_ACTION, "decoratePanel(target, \"combat-action\", source)", "Combat action affordances are read-only"),
        (OBJECTIVE_JOURNAL, "decoratePanel(target, \"objective-journal\", source)", "Objectives and journal entries are read-only"),
        (PLAYER_HUD, "decoratePanel(target, \"player-hud\", source)", "Player HUD details are read-only"),
        (MAP_LOCATION, "decoratePanel(target, \"map-location\", source)", "Map and location details are read-only"),
    ):
        assert_panel_uses_chrome(panel_path, decorate_call, authority_text)


def test_survival_inspector_uses_panel_chrome_with_runtime_validation():
    assert_panel_uses_chrome(
        SURVIVAL_INSPECTOR,
        "decoratePanel(panel, \"survival-inspector\", SOURCE)",
        "Survival inspector actions still submit commands through runtime validation",
        allows_command_bridge=True,
    )
