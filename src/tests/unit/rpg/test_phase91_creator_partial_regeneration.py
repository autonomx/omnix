"""Backend tests for Phase 1.3 — Creator UX Partial Regeneration.

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
    """Two-step preview → apply using the new strict token contract."""
    from app.rpg.services.adventure_builder_service import regenerate_setup_section

    # Step 1: Preview to get a valid token
    preview = regenerate_setup_section(payload, target, mode="preview")
    assert preview["success"] is True
    token = preview["apply_token"]

    # Step 2: Apply using the token — use mode="apply" explicitly
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


# ─────────────────────────────────────────────────────────────
# Service-level tests
# ─────────────────────────────────────────────────────────────


class TestRegenerateSetupSection:
    """Tests for the ``regenerate_setup_section`` service function."""

    def test_regenerate_factions_replaces_only_factions(self):
        from app.rpg.services.adventure_builder_service import regenerate_setup_section

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
        from app.rpg.services.adventure_builder_service import regenerate_setup_section

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
        from app.rpg.services.adventure_builder_service import regenerate_setup_section

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

        # Missing title which is required — should cause blocking validation
        payload = _minimal_setup(title="")
        result = regenerate_setup_section(payload, "factions")

        assert result["success"] is False
        assert result["error"] == "Setup has blocking validation issues"
        assert result["validation"]["blocking"] is True

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

        # Try to apply it for locations — should fail
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


# ─────────────────────────────────────────────────────────────
# Endpoint-level tests
# ─────────────────────────────────────────────────────────────


class TestRegenerateEndpoint:
    """Tests for the ``POST /api/rpg/adventure/regenerate`` endpoint."""

    @pytest.fixture
    def client(self):
        """Return a minimal Flask test client for the regenerate endpoint."""
        from flask import Flask, jsonify, request

        from app.rpg.services.adventure_builder_service import regenerate_setup_section

        app = Flask(__name__)
        app.config["TESTING"] = True

        @app.route("/api/rpg/adventure/regenerate", methods=["POST"])
        def regenerate():
            data = request.get_json()
            if data is None:
                return jsonify({"success": False, "error": "Request must be JSON"}), 400
            target = data.get("target")
            if not target:
                return jsonify({"success": False, "error": "Missing target", "validation": {"blocking": False}}), 400
            setup = data.get("setup", {})
            # Support preview → apply flow
            mode = data.get("mode", "apply")
            apply_token = data.get("apply_token")
            result = regenerate_setup_section(setup, target, mode=mode, apply_token=apply_token)
            http_status = 200 if result["success"] else 400
            return jsonify(result), http_status

        with app.test_client() as client:
            yield client

    def _preview_then_apply(self, client, target, setup=None):
        """Helper to perform the two-step preview => apply contract via endpoint.

        Uses the same setup payload for both calls so setup_id matches.
        """
        setup = setup or _minimal_setup()
        # Step 1: Preview
        preview_resp = client.post("/api/rpg/adventure/regenerate", json={
            "target": target,
            "setup": setup,
            "mode": "preview",
        })
        assert preview_resp.status_code == 200, preview_resp.get_data(as_text=True)
        preview_data = preview_resp.get_json()
        assert "apply_token" in preview_data

        # Step 2: Apply with token — reuse same setup object
        apply_resp = client.post("/api/rpg/adventure/regenerate", json={
            "target": target,
            "setup": setup,
            "mode": "apply",
            "apply_token": preview_data["apply_token"],
        })
        assert apply_resp.status_code == 200, apply_resp.get_data(as_text=True)
        return apply_resp.get_json()

    def test_regenerate_factions_via_endpoint(self, client):
        data = self._preview_then_apply(client, "factions")
        _assert_success_contract(data, "factions")
        assert isinstance(data["updated_setup"].get("factions"), list)

    def test_regenerate_locations_via_endpoint(self, client):
        data = self._preview_then_apply(client, "locations")
        _assert_success_contract(data, "locations")
        assert isinstance(data["updated_setup"].get("locations"), list)

    def test_regenerate_npc_seeds_via_endpoint(self, client):
        data = self._preview_then_apply(client, "npc_seeds")
        _assert_success_contract(data, "npc_seeds")
        assert isinstance(data["updated_setup"].get("npc_seeds"), list)

    def test_regenerate_opening_via_endpoint(self, client):
        data = self._preview_then_apply(client, "opening")
        _assert_success_contract(data, "opening")
        metadata = data["updated_setup"].get("metadata", {})
        assert "regenerated_opening" in metadata

    def test_regenerate_threads_via_endpoint(self, client):
        data = self._preview_then_apply(client, "threads")
        _assert_success_contract(data, "threads")
        assert data["updated_setup"]["metadata"]["regenerated_threads"] == data["regenerated"]

    def test_invalid_target_returns_400(self, client):
        payload = {
            "target": "bogus",
            "setup": _minimal_setup(),
        }
        resp = client.post("/api/rpg/adventure/regenerate", json=payload)
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False

    def test_missing_target_returns_400(self, client):
        payload = {
            "setup": _minimal_setup(),
        }
        resp = client.post("/api/rpg/adventure/regenerate", json=payload)
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False

    def test_missing_json_body_returns_400(self, client):
        resp = client.post(
            "/api/rpg/adventure/regenerate",
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_preview_mode_returns_token(self, client):
        payload = {
            "target": "factions",
            "setup": _minimal_setup(),
            "mode": "preview",
        }
        resp = client.post("/api/rpg/adventure/regenerate", json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "apply_token" in data
        assert "before" in data
        assert "after" in data
        assert "diff" in data

    def test_apply_with_invalid_token_returns_400(self, client):
        payload = {
            "target": "factions",
            "setup": _minimal_setup(),
            "mode": "apply",
            "apply_token": "invalid",
        }
        resp = client.post("/api/rpg/adventure/regenerate", json=payload)
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False
        assert "Invalid or expired apply_token" in data["error"]


# ─────────────────────────────────────────────────────────────
# Merge semantics tests
# ─────────────────────────────────────────────────────────────


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