from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
ADR = ROOT / "docs" / "architecture" / "ADR-0003-rpg-world-scenario-map-architecture.md"


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
        "Lifecycle, archival, and deletion",
        "never destructively deleted through normal product APIs",
        "Existing campaigns pinned to archived projects remain readable and playable",
    )
    for phrase in required:
        assert phrase in text
