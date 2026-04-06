from app.rpg.packaging.package_io import (
    build_package_manifest,
    export_session_package,
    import_session_package,
)


def test_build_package_manifest():
    manifest = build_package_manifest(
        title="Test Package",
        description="Portable RPG session",
        created_by="tester",
    )
    assert manifest["package_version"] == "1.0"
    assert manifest["title"] == "Test Package"


def test_export_session_package_basic():
    result = export_session_package(
        {"presentation_state": {}},
        title="Export",
        description="Desc",
        created_by="tester",
    )
    assert "manifest" in result
    assert "simulation_state" in result
    assert "character_cards" in result


def test_import_session_package_basic():
    package_data = {
        "manifest": {"package_version": "1.0", "title": "Pkg"},
        "simulation_state": {"presentation_state": {}},
        "character_cards": [],
    }
    result = import_session_package(package_data)
    assert "simulation_state" in result
    assert "imported_cards" in result


def test_package_manifest_fields():
    manifest = build_package_manifest(
        title="My Adventure",
        description="Epic quest",
        created_by="admin",
        source="custom",
    )
    assert manifest["title"] == "My Adventure"
    assert manifest["description"] == "Epic quest"
    assert manifest["created_by"] == "admin"
    assert manifest["source"] == "custom"


def test_export_includes_visual_registry():
    result = export_session_package(
        {"presentation_state": {"visual_state": {}}},
        title="Test",
        description="",
        created_by="tester",
    )
    assert "visual_registry" in result
    assert "visual_assets" in result["visual_registry"]
    assert "scene_illustrations" in result["visual_registry"]
    assert "image_requests" in result["visual_registry"]
    assert "defaults" in result["visual_registry"]