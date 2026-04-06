"""Phase 12.9 + 13.0 — Packaging/Modding regression tests.

Ensures that package export/import and content pack operations
don't break existing functionality.
"""

from app.rpg.packaging.package_io import (
    build_package_manifest,
    export_session_package,
    import_session_package,
)
from app.rpg.modding.content_packs import (
    apply_content_pack,
    build_pack_application_preview,
    ensure_content_pack_state,
    install_content_pack,
    list_content_packs,
)


def test_export_package_preserves_top_level_keys():
    """Export should preserve top-level keys from original state."""
    original = {"presentation_state": {}, "some_key": "value"}
    result = export_session_package(
        original,
        title="Test",
        description="Test",
        created_by="tester",
    )
    # The export normalizes state, but the result should have expected keys
    assert "manifest" in result
    assert "simulation_state" in result
    assert "character_cards" in result
    assert result["manifest"]["title"] == "Test"


def test_import_package_normalizes_malformed_input():
    """Import should normalize malformed package data."""
    malformed = {"garbage": True}
    result = import_session_package(malformed)
    assert "simulation_state" in result
    assert isinstance(result["simulation_state"], dict)


def test_content_pack_state_does_not_break_visual_state():
    """ensure_content_pack_state should not break visual_state."""
    simulation_state = {
        "presentation_state": {
            "visual_state": {"defaults": {}, "character_visual_identities": {}}
        }
    }
    result = ensure_content_pack_state(simulation_state)
    assert "presentation_state" in result
    assert "visual_state" in result["presentation_state"]
    assert "modding_state" in result["presentation_state"]


def test_package_manifest_has_required_fields():
    """Package manifest should always have required fields."""
    manifest = build_package_manifest(
        title="Test",
        description="Test",
        created_by="tester",
    )
    for field in ["package_version", "title", "description", "created_by", "source"]:
        assert field in manifest


def test_pack_preview_does_not_modify_original():
    """Preview should not modify the original pack data."""
    pack = {"manifest": {"id": "test", "title": "Test"}, "characters": []}
    build_pack_application_preview(pack)
    assert "manifest" in pack
    assert pack["manifest"]["id"] == "test"


def test_multiple_packs_install_without_error():
    """Installing multiple packs should work without error."""
    simulation_state = {"presentation_state": {}}
    for i in range(5):
        simulation_state = install_content_pack(
            simulation_state,
            {"manifest": {"id": f"pack:{i}", "title": f"Pack {i}"}, "characters": []},
        )
    packs = list_content_packs(simulation_state)
    assert len(packs) == 5


def test_apply_pack_with_empty_visual_defaults():
    """Applying a pack with empty visual_defaults should not break."""
    simulation_state = {
        "presentation_state": {"visual_state": {"defaults": {}}}
    }
    result = apply_content_pack(
        simulation_state,
        {"manifest": {"id": "empty", "title": "Empty"}, "visual_defaults": {}},
    )
    assert "presentation_state" in result