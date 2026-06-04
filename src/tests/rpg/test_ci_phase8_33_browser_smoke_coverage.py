from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SMOKE = ROOT / "docs" / "plans" / "rpg_phase8_33_browser_smoke_coverage.md"

PANEL_FILES = {
    "conversation-settings": ROOT / "src" / "static" / "rpg-conversation-settings.js",
    "map-location": ROOT / "src" / "static" / "rpg" / "rpgMapLocationPanel.js",
    "player-hud": ROOT / "src" / "static" / "rpg" / "rpgPlayerHud.js",
    "objective-journal": ROOT / "src" / "static" / "rpg" / "rpgObjectiveJournalPanel.js",
    "combat-action": ROOT / "src" / "static" / "rpg" / "rpgCombatActionPanel.js",
    "inventory-party": ROOT / "src" / "static" / "rpg" / "rpgInventoryPartyPanel.js",
    "recent-activity": ROOT / "src" / "static" / "rpg" / "rpgRecentActivityPanel.js",
    "suggested-actions": ROOT / "src" / "static" / "rpg" / "rpgSuggestedActionsPanel.js",
    "survival-inspector": ROOT / "src" / "static" / "rpg" / "rpg-survival-inspector.js",
}


def test_phase8_33_smoke_plan_records_all_registered_panels():
    smoke = SMOKE.read_text(encoding="utf-8")
    for panel_id, path in PANEL_FILES.items():
        assert panel_id in smoke
        assert str(path.relative_to(ROOT)).replace("\\", "/") in smoke
    for expected in (
        "shared chrome, source badge",
        "runtime notice",
        "decorated panel",
        "runtime-validated command bridge only",
        "Phase 8.34 — UI runtime-authority boundary audit.",
        "Phase 8.35 — Phase 8 final closeout note and Phase 9 handoff.",
    ):
        assert expected in smoke


def test_phase8_33_registered_panels_keep_shared_chrome_smoke_contracts():
    for panel_id, path in PANEL_FILES.items():
        source = path.read_text(encoding="utf-8")
        assert "window.RpgPanelChrome" in source
        assert "panelSourceBadge" in source
        assert "runtimeValidationNotice" in source
        assert "decoratePanel" in source
        assert f'"{panel_id}"' in source
        if panel_id != "conversation-settings":
            assert "panelEmptyState" in source


def test_phase8_33_registered_panels_escape_visible_payload_values():
    for panel_id, path in PANEL_FILES.items():
        source = path.read_text(encoding="utf-8")
        assert "escapeHtml" in source, panel_id
        assert "innerHTML" in source or "insertAdjacentHTML" in source or "textContent" in source
        if "innerHTML" in source or "insertAdjacentHTML" in source:
            assert "${escapeHtml(" in source or "chrome.escapeHtml" in source, panel_id


def test_phase8_33_smoke_plan_preserves_runtime_authority_boundary():
    smoke = SMOKE.read_text(encoding="utf-8")
    for expected in (
        "source-backed smoke coverage slice",
        "not a new browser test harness installation",
        "Suggested actions remain hints until runtime validates a command.",
        "Survival inspector may submit command intents only through the existing runtime validation path.",
        "No registered panel may add provider/LLM calls.",
        "No registered panel may mutate gameplay truth.",
        "Runtime and simulation remain authoritative.",
    ):
        assert expected in smoke


def test_phase8_33_registered_panels_remain_provider_free_and_runtime_safe():
    for panel_id, path in PANEL_FILES.items():
        source = path.read_text(encoding="utf-8")
        lower = source.lower()
        for forbidden in (
            "fetch(",
            "xmlhttprequest",
            "provider",
            "llm",
            "apply_turn",
            "math.random",
            "mutateworld",
            "acceptaction",
        ):
            assert forbidden not in lower, panel_id
        if panel_id != "survival-inspector":
            assert "sendcommand" not in lower, panel_id
            assert "executecommand" not in lower, panel_id
