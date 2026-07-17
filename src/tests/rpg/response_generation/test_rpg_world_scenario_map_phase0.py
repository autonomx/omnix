from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
ADR = ROOT / "docs" / "architecture" / "ADR-0003-rpg-world-scenario-map-architecture.md"
ROADMAP = ROOT / "docs" / "plans" / "rpg_world_scenario_map_roadmap.md"


def test_world_scenario_map_adr_locks_authority_boundaries() -> None:
    text = ADR.read_text(encoding="utf-8")
    required = (
        "World Project",
        "World Revision",
        "World Release",
        "Scenario Revision",
        "Campaign Map Instance",
        "Events are authoritative",
        "Observer-safe projection",
        "generation fingerprint",
        "Campaigns never auto-upgrade",
    )
    for phrase in required:
        assert phrase in text


def test_world_scenario_map_roadmap_requires_golden_slice() -> None:
    text = ROADMAP.read_text(encoding="utf-8")
    assert "Phase 2A" in text
    assert "Phase 2B" in text
    assert "Move Xylvanna only in Campaign A" in text
    assert "Confirm Campaign B is unchanged" in text
    assert "no World Forge calls during normal launch" in text
