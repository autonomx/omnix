"""Unit tests for Phase 13.2 — Creator Pack Authoring."""
from app.rpg.creator.pack_authoring import (
    build_pack_draft_export,
    build_pack_draft_preview,
    validate_pack_draft,
)


def test_validate_pack_draft_requires_manifest_id_and_title():
    result = validate_pack_draft({"manifest": {}})
    assert result["ok"] is False
    assert "manifest.id_required" in result["errors"]
    assert "manifest.title_required" in result["errors"]


def test_build_pack_draft_export_includes_validation():
    result = build_pack_draft_export({
        "manifest": {"id": "pack:test", "title": "Test Pack"},
        "characters": [],
    })
    assert "validation" in result
    assert result["manifest"]["id"] == "pack:test"


def test_build_pack_draft_preview_contains_preview():
    result = build_pack_draft_preview({
        "manifest": {"id": "pack:test", "title": "Test Pack"},
        "characters": [{"name": "Captain Elira"}],
    })
    assert "validation" in result
    assert "preview" in result