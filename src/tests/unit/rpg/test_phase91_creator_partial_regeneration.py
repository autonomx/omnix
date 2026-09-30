"""Backend tests for Phase 1.3 â€” Creator UX Partial Regeneration.

Tests the new regeneration endpoint and service logic for targeted
section regeneration (factions, locations, NPCs, opening, threads).
"""

from __future__ import annotations

import pytest


def _minimal_setup(**overrides):
    """Build a minimal valid setup payload for testing."""
    payload = {
        "setup_id": "test_setup_regen",
        "title": "Test Adventure",
        "genre": "fantasy",
        "setting": "A test world",
        "premise": "A test premise",
        "factions": overrides.pop("factions", []),
        "locations": overrides.pop("locations", []),
        "npc_seeds": overrides.pop("npc_seeds", []),
        "hard_rules": [],
        "soft_tone_rules": [],
        "forbidden_content": [],
        "canon_notes": [],
        "metadata": {},
        "starting_location_id": None,
        "starting_npc_ids": [],
    }
    payload.update(overrides)
    return payload


def _preview_and_apply(payload, target):
    """Two-step preview â†’ apply using the new strict token contract."""
    from app.rpg.services.adventure_builder_service import regenerate_setup_section

    # Step 1: Preview to get a valid token
    preview = regenerate_setup_section(payload, target, mode="preview")
    assert preview["success"] is True
    token = preview["apply_token"]

    # Step 2: Apply using the token â€” use mode="apply" explicitly
    return regenerate_setup_section(
        payload, target, mode="apply", apply_token=token,
    )


def _assert_success_contract(result, target):
    assert result["success"] is True
    assert result["target"] == target
    assert set(result.keys()) >= {
        "success",
        "target",
        "updated_setup",
        "regenerated",
        "validation",
        "preview",
        "resolved_context",
    }
    assert isinstance(result["updated_setup"], dict)


def _assert_core_fields_preserved(before, after):
    assert after["setup_id"] == before["setup_id"]
    assert after["title"] == before["title"]
    assert after["genre"] == before["genre"]
    assert after["setting"] == before["setting"]
    assert after["premise"] == before["premise"]


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Service-level tests
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestRegenerateSetupSection:
    """Tests for the ``regenerate_setup_section`` service function."""

    def test_regenerate_factions_replaces_only_factions(self):

        payload = _minimal_setup(
            factions=[{
                "faction_id": "old_faction",
                "name": "Old Faction",
                "description": "old",
                "goals": [],
            }],
            locations=[{
                "location_id": "loc_alpha",
                "name": "Alpha",
                "description": "desc",
                "tags": [],
            }],
        )
        result = _preview_and_apply(payload, "factions")

        _assert_success_contract(result, "factions")
        updated = result["updated_setup"]
        _assert_core_fields_preserved(payload, updated)
        assert isinstance(updated["factions"], list)
        assert updated["factions"] == result["regenerated"]
        # Original location should remain intact
        assert any(loc["location_id"] == "loc_alpha" for loc in updated["locations"])

    def test_regenerate_locations_replaces_only_locations(self):

        payload = _minimal_setup(
            locations=[{
                "location_id": "old_loc",
                "name": "Old Location",
                "description": "old desc",
                "tags": [],
            }],
            factions=[{
                "faction_id": "fac_beta",
                "name": "Beta Faction",
                "description": "faction desc",
                "goals": [],
            }],
        )
        result = _preview_and_apply(payload, "locations")

        _assert_success_contract(result, "locations")
        # Original faction should remain intact
        updated = result["updated_setup"]
        _assert_core_fields_preserved(payload, updated)
        assert isinstance(updated["locations"], list)
        assert updated["locations"] == result["regenerated"]
        assert any(f["faction_id"] == "fac_beta" for f in updated["factions"])

    def test_regenerate_npc_seeds_replaces_only_npcs(self):

        payload = _minimal_setup(
            npc_seeds=[{
                "npc_id": "npc_old",
                "name": "Old NPC",
                "role": "guard",
                "description": "old",
                "goals": [],
                "faction_id": "",
                "location_id": "",
                "must_survive": False,
            }],
        )
        result = _preview_and_apply(payload, "npc_seeds")

        _assert_success_contract(result, "npc_seeds")
        # Other sections should remain intact
        updated = result["updated_setup"]
        _assert_core_fields_preserved(payload, updated)
        assert isinstance(updated["npc_seeds"], list)
        assert updated["npc_seeds"] == result["regenerated"]

    def test_regenerate_opening_updates_start_state(self):
        payload = _minimal_setup()
        result = _preview_and_apply(payload, "opening")

        _assert_success_contract(result, "opening")
        updated = result["updated_setup"]
        _assert_core_fields_preserved(payload, updated)
        regenerated = result["regenerated"]
        assert isinstance(regenerated, dict)
        assert "resolved_context" in regenerated
        metadata = updated.get("metadata", {})
        assert "regenerated_opening" in metadata
        resolved = regenerated.get("resolved_context", {})
        if resolved.get("location_id"):
            assert updated["starting_location_id"] == resolved["location_id"]
        if resolved.get("npc_ids"):
            assert updated["starting_npc_ids"] == resolved["npc_ids"]

    def test_regenerate_threads_returns_threads(self):
        payload = _minimal_setup()
        result = _preview_and_apply(payload, "threads")

        _assert_success_contract(result, "threads")
        # Threads should be stored in metadata for preview
        updated = result["updated_setup"]
        _assert_core_fields_preserved(payload, updated)
        metadata = updated.get("metadata", {})
        assert "regenerated_threads" in metadata
        assert metadata["regenerated_threads"] == result["regenerated"]

    def test_unsupported_target_returns_error(self):
        from app.rpg.services.adventure_builder_service import regenerate_setup_section

        result = regenerate_setup_section(_minimal_setup(), "invalid_target")

        assert result["success"] is False
        assert "Unsupported regeneration target" in result["error"]

    def test_blocking_validation_returns_error(self):
        from app.rpg.services.adventure_builder_service import regenerate_setup_section

        # Missing title which is required â€” should cause blocking validation
        payload = _minimal_setup(
            factions=[
                {"faction_id": "faction-duplicate", "name": "One", "description": "d"},
                {"faction_id": "faction-duplicate", "name": "Two", "description": "d"},
            ]
        )
        result = regenerate_setup_section(payload, "factions", mode="preview")

        assert result["success"] is False
        assert result["error"] == "Setup has blocking validation issues"
        assert result["validation"]["blocking"] is True
        assert any(issue["code"] == "duplicate_id" for issue in result["validation"]["issues"])

    def test_invalid_preview_token_returns_error(self):
        from app.rpg.services.adventure_builder_service import regenerate_setup_section

        result = regenerate_setup_section(
            _minimal_setup(), "factions", mode="apply", apply_token="bogus_token"
        )

        assert result["success"] is False
        assert "Invalid or expired apply_token" in result["error"]

    def test_mismatched_target_returns_error(self):
        from app.rpg.services.adventure_builder_service import regenerate_setup_section

        # Get a preview for factions
        preview = regenerate_setup_section(_minimal_setup(), "factions", mode="preview")
        token = preview["apply_token"]

        # Try to apply it for locations â€” should fail
        result = regenerate_setup_section(
            _minimal_setup(), "locations", mode="apply", apply_token=token
        )

        assert result["success"] is False
        assert "Mismatched regeneration target" in result["error"]

    def test_preview_response_includes_rationale(self):
        from app.rpg.services.adventure_builder_service import regenerate_setup_section

        result = regenerate_setup_section(_minimal_setup(), "factions", mode="preview")
        assert result["success"] is True
        assert "rationale" in result
        assert isinstance(result["rationale"], str)
        assert len(result["rationale"]) > 0


class TestApplyRegeneratedSection:
    """Direct tests for the merge helper to lock exact apply semantics."""

    def test_apply_factions_replaces_only_factions(self):
        from app.rpg.services.adventure_builder_service import (
            _apply_regenerated_section,
        )

        payload = _minimal_setup(
            factions=[{"faction_id": "old", "name": "Old", "description": "x", "goals": []}],
            locations=[{"location_id": "loc_a", "name": "Alpha", "description": "desc", "tags": []}],
        )
        regenerated = [{"faction_id": "new", "name": "New", "description": "y", "goals": []}]

        updated = _apply_regenerated_section(payload, "factions", regenerated)

        assert updated["factions"] == regenerated
        assert updated["locations"] == payload["locations"]
        _assert_core_fields_preserved(payload, updated)

    def test_apply_opening_updates_metadata_and_start_state(self):
        from app.rpg.services.adventure_builder_service import (
            _apply_regenerated_section,
        )

        payload = _minimal_setup()
        regenerated = {
            "opening_situation": "The bells toll at dusk.",
            "resolved_context": {
                "location_id": "loc_night_market",
                "npc_ids": ["npc_mara_voss"],
            },
        }

        updated = _apply_regenerated_section(payload, "opening", regenerated)

        assert updated["metadata"]["regenerated_opening"] == regenerated
        assert updated["starting_location_id"] == "loc_night_market"
        assert updated["starting_npc_ids"] == ["npc_mara_voss"]
        _assert_core_fields_preserved(payload, updated)

    def test_apply_threads_stores_in_metadata(self):
        from app.rpg.services.adventure_builder_service import (
            _apply_regenerated_section,
        )

        payload = _minimal_setup(metadata={"existing_key": "keep_me"})
        regenerated = [{"thread_id": "thr_1", "title": "A dark rumor spreads"}]

        updated = _apply_regenerated_section(payload, "threads", regenerated)

        assert updated["metadata"]["regenerated_threads"] == regenerated
        assert updated["metadata"]["existing_key"] == "keep_me"
        _assert_core_fields_preserved(payload, updated)

    def test_apply_invalid_target_raises(self):
        from app.rpg.services.adventure_builder_service import (
            _apply_regenerated_section,
        )

        with pytest.raises(ValueError):
            _apply_regenerated_section(_minimal_setup(), "bogus", [])


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Endpoint route retirement check
# The current setup-generation service has no Flask endpoint; active and retired
# RPG route contracts are checked through the composed gateway.

class TestRegenerateEndpointRetirement:
    def test_legacy_endpoint_is_absent_from_gateway(self):
        from app.gateway.main import create_gateway_app

        app = create_gateway_app()
        routes = {
            (method, route.path)
            for route in app.routes
            if hasattr(route, "path")
            for method in getattr(route, "methods", ())
        }
        assert ("POST", "/api/rpg/adventure/regenerate") not in routes

# Merge semantics tests
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestMergeSemantics:
    """Verify that regeneration only touches the requested section."""

    def test_factions_replace_preserves_other_sections(self):
        payload = _minimal_setup(
            factions=[{"faction_id": "old", "name": "Old", "description": "x", "goals": []}],
            locations=[{"location_id": "loc_a", "name": "Alpha", "description": "desc", "tags": []}],
        )
        result = _preview_and_apply(payload, "factions")
        _assert_success_contract(result, "factions")

        updated = result["updated_setup"]
        # Locations untouched
        assert len(updated["locations"]) == 1
        assert updated["locations"][0]["location_id"] == "loc_a"
        assert updated["factions"] == result["regenerated"]
        _assert_core_fields_preserved(payload, updated)

    def test_opening_updates_start_state_fields(self):
        payload = _minimal_setup()
        result = _preview_and_apply(payload, "opening")
        _assert_success_contract(result, "opening")

        updated = result["updated_setup"]
        # Opening should update metadata and possibly starting_location_id
        metadata = updated.get("metadata", {})
        assert "regenerated_opening" in metadata
        regenerated = result["regenerated"]
        resolved = regenerated.get("resolved_context", {})
        if resolved.get("location_id"):
            assert updated["starting_location_id"] == resolved["location_id"]
        if resolved.get("npc_ids"):
            assert updated["starting_npc_ids"] == resolved["npc_ids"]
        _assert_core_fields_preserved(payload, updated)

    def test_threads_land_in_metadata(self):
        payload = _minimal_setup()
        result = _preview_and_apply(payload, "threads")
        _assert_success_contract(result, "threads")

        updated = result["updated_setup"]
        metadata = updated.get("metadata", {})
        assert "regenerated_threads" in metadata
        assert isinstance(metadata["regenerated_threads"], list)
        assert metadata["regenerated_threads"] == result["regenerated"]
        _assert_core_fields_preserved(payload, updated)
