from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INVENTORY = ROOT / "docs" / "plans" / "rpg_phase8_32_panel_contract_inventory.md"
REGISTRY = ROOT / "src" / "static" / "rpg" / "rpgPanelLayoutRegistry.js"
CHROME = ROOT / "src" / "static" / "rpg" / "rpgPanelChrome.js"

REGISTERED_PANELS = (
    "conversation-settings",
    "map-location",
    "player-hud",
    "objective-journal",
    "combat-action",
    "inventory-party",
    "recent-activity",
    "suggested-actions",
    "survival-inspector",
)

METADATA_FAMILIES = (
    "accessibility metadata",
    "state metadata",
    "read-only/runtime-authority metadata",
    "focus metadata",
    "section metadata",
    "density metadata",
    "freshness metadata",
    "priority metadata",
    "render-kind metadata",
    "provenance metadata",
    "tone metadata",
    "schema/version metadata",
    "surface metadata",
)


def test_phase8_32_inventory_records_registered_panel_contracts():
    inventory = INVENTORY.read_text(encoding="utf-8")
    registry = REGISTRY.read_text(encoding="utf-8")
    for panel_id in REGISTERED_PANELS:
        assert panel_id in inventory
        assert panel_id in registry
    for expected in (
        "PANEL_ORDER",
        "PANEL_LABELS",
        "panelOrder()",
        "panelLabels()",
        "panelLabel(panelId)",
        "panelIndex(panelId)",
        "ensurePanelRoot()",
        "ensurePanelSlot(panelId)",
        "ensureOrderedPanelSlots()",
        "attachPanelToSlot(panelElement, panelId)",
    ):
        assert expected in inventory


def test_phase8_32_inventory_records_chrome_contracts_and_metadata_families():
    inventory = INVENTORY.read_text(encoding="utf-8")
    chrome = CHROME.read_text(encoding="utf-8")
    for expected in (
        "deterministic_phase8_panel_chrome",
        "runtime_validated_commands_only",
        "phase8_panel_chrome_v1",
        "panelSourceBadge(...)" ,
        "panelEmptyState(...)" ,
        "runtimeValidationNotice(...)" ,
        "attachPanelToLayout(...)" ,
        "decoratePanel(...)" ,
    ):
        assert expected in inventory
    for expected in (
        "PANEL_DENSITIES",
        "PANEL_FRESHNESS",
        "PANEL_PRIORITIES",
        "PANEL_PROVENANCE",
        "PANEL_RENDER_KINDS",
        "PANEL_SECTIONS",
        "PANEL_STATES",
        "PANEL_SURFACES",
        "PANEL_TONES",
        "PANEL_SCHEMA_VERSION",
    ):
        assert expected in chrome
    for family in METADATA_FAMILIES:
        assert family in inventory
    assert "Do not add another metadata-only family in Phase 8" in inventory


def test_phase8_32_inventory_preserves_runtime_authority_boundaries():
    inventory = INVENTORY.read_text(encoding="utf-8")
    for expected in (
        "documentation and source-guard only",
        "No provider or LLM calls",
        "presentation-only unless they submit command intents through the existing runtime validation path",
        "Suggested actions remain hints, not accepted gameplay actions.",
        "Survival inspector actions remain command intents routed through runtime validation.",
        "Runtime and simulation remain authoritative for gameplay truth.",
        "Phase 8.33 — Browser smoke coverage for registered panels.",
        "Phase 8.34 — UI runtime-authority boundary audit.",
        "Phase 8.35 — Phase 8 final closeout note and Phase 9 handoff.",
    ):
        assert expected in inventory
