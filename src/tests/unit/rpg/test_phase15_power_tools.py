"""Comprehensive tests for Phase 1.5 — Power Tools Extensions.

Covers:
- PATCH 1: Tone presets, default constraints, constraint/tone injection, bulk regen helper
- PATCH 2: Service layer — tone/constraints in regenerate_setup_section,
           regenerate_multiple_items_service, compute_creator_health, health in responses
- PATCH 3: Routes — regenerate with tone/constraints, /regenerate-multiple endpoint
"""

from __future__ import annotations

import json
import os
import sys
import unittest

# Ensure the src directory is on the import path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.rpg.creator.regeneration import (
    DEFAULT_CONSTRAINTS,
    TONE_PRESETS,
    apply_constraints_to_setup,
    apply_tone_to_setup,
    regenerate_multiple_items,
)
from app.rpg.services import adventure_builder_service as builder

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _minimal_setup(**overrides):
    """Return a minimal valid adventure setup dict."""
    base = {
        "setup_id": "test_setup",
        "title": "Test Adventure",
        "genre": "fantasy",
        "setting": "A test world",
        "premise": "Testing the adventure builder system",
    }
    base.update(overrides)
    return base


def _rich_setup(**overrides):
    """Return a setup with factions, locations, and NPCs."""
    base = _minimal_setup(
        factions=[
            {"faction_id": "fac_guild", "name": "Thieves Guild", "description": "A shadowy guild", "goals": ["steal"]},
            {"faction_id": "fac_crown", "name": "The Crown", "description": "Royal authority", "goals": ["order"]},
        ],
        locations=[
            {"location_id": "loc_tavern", "name": "Rusty Mug", "description": "A rough tavern", "tags": ["social"]},
            {"location_id": "loc_castle", "name": "Castle Keep", "description": "The royal castle", "tags": ["royal"]},
        ],
        npc_seeds=[
            {"npc_id": "npc_fixer", "name": "The Fixer", "role": "fence", "description": "A well-connected fence"},
            {"npc_id": "npc_guard", "name": "Captain Ward", "role": "guard", "description": "Stern city guard"},
            {"npc_id": "npc_merchant", "name": "Elara", "role": "merchant", "description": "Traveling merchant"},
        ],
        starting_location_id="loc_tavern",
    )
    base.update(overrides)
    return base


# ===========================================================================
# PATCH 1 — regeneration.py constants and helpers
# ===========================================================================


class TestTonePresets(unittest.TestCase):
    """Test TONE_PRESETS constant."""

    def test_tone_presets_is_set(self):
        self.assertIsInstance(TONE_PRESETS, set)

    def test_tone_presets_contains_expected_values(self):
        for tone in ("neutral", "grim", "heroic", "chaotic"):
            self.assertIn(tone, TONE_PRESETS)

    def test_tone_presets_count(self):
        self.assertEqual(len(TONE_PRESETS), 4)


class TestDefaultConstraints(unittest.TestCase):
    """Test DEFAULT_CONSTRAINTS constant."""

    def test_default_constraints_is_dict(self):
        self.assertIsInstance(DEFAULT_CONSTRAINTS, dict)

    def test_default_constraints_keys(self):
        self.assertIn("require_factions", DEFAULT_CONSTRAINTS)
        self.assertIn("require_conflict", DEFAULT_CONSTRAINTS)
        self.assertIn("npc_density", DEFAULT_CONSTRAINTS)

    def test_default_constraints_values(self):
        self.assertFalse(DEFAULT_CONSTRAINTS["require_factions"])
        self.assertTrue(DEFAULT_CONSTRAINTS["require_conflict"])
        self.assertEqual(DEFAULT_CONSTRAINTS["npc_density"], "medium")


class TestApplyConstraintsToSetup(unittest.TestCase):
    """Test apply_constraints_to_setup helper."""

    def test_injects_constraints_into_metadata(self):
        setup = _minimal_setup()
        constraints = {"require_factions": True, "npc_density": "high"}
        result = apply_constraints_to_setup(setup, constraints)
        self.assertEqual(result["metadata"]["constraints"], constraints)

    def test_preserves_existing_metadata(self):
        setup = _minimal_setup(metadata={"template_name": "test"})
        result = apply_constraints_to_setup(setup, {"require_conflict": True})
        self.assertEqual(result["metadata"]["template_name"], "test")
        self.assertEqual(result["metadata"]["constraints"], {"require_conflict": True})

    def test_none_constraints_results_in_empty_dict(self):
        setup = _minimal_setup()
        result = apply_constraints_to_setup(setup, None)
        self.assertEqual(result["metadata"]["constraints"], {})

    def test_empty_constraints(self):
        setup = _minimal_setup()
        result = apply_constraints_to_setup(setup, {})
        self.assertEqual(result["metadata"]["constraints"], {})

    def test_does_not_mutate_original(self):
        setup = _minimal_setup()
        original_id = id(setup)
        result = apply_constraints_to_setup(setup, {"x": 1})
        self.assertNotEqual(id(result), original_id)

    def test_none_setup(self):
        result = apply_constraints_to_setup(None, {"x": 1})
        self.assertIn("metadata", result)
        self.assertEqual(result["metadata"]["constraints"], {"x": 1})


class TestApplyToneToSetup(unittest.TestCase):
    """Test apply_tone_to_setup helper."""

    def test_injects_valid_tone(self):
        setup = _minimal_setup()
        result = apply_tone_to_setup(setup, "grim")
        self.assertEqual(result["metadata"]["tone"], "grim")

    def test_rejects_invalid_tone(self):
        setup = _minimal_setup()
        result = apply_tone_to_setup(setup, "silly")
        self.assertNotIn("tone", (result.get("metadata") or {}))

    def test_none_tone_returns_unchanged(self):
        setup = _minimal_setup()
        result = apply_tone_to_setup(setup, None)
        self.assertEqual(result, setup)

    def test_empty_tone_returns_unchanged(self):
        setup = _minimal_setup()
        result = apply_tone_to_setup(setup, "")
        self.assertEqual(result, setup)

    def test_preserves_existing_metadata(self):
        setup = _minimal_setup(metadata={"template_name": "test"})
        result = apply_tone_to_setup(setup, "heroic")
        self.assertEqual(result["metadata"]["template_name"], "test")
        self.assertEqual(result["metadata"]["tone"], "heroic")

    def test_all_valid_tones(self):
        for tone in TONE_PRESETS:
            result = apply_tone_to_setup(_minimal_setup(), tone)
            self.assertEqual(result["metadata"]["tone"], tone)


class TestRegenerateMultipleItems(unittest.TestCase):
    """Test regenerate_multiple_items helper."""

    def test_calls_fn_for_each_item(self):
        calls = []

        def mock_fn(setup, target, item_id):
            calls.append(item_id)
            return {"item_id": item_id, "regenerated": True}

        results = regenerate_multiple_items({}, "npc_seeds", ["a", "b", "c"], mock_fn)
        self.assertEqual(len(results), 3)
        self.assertEqual(calls, ["a", "b", "c"])

    def test_skips_failed_items(self):
        def mock_fn(setup, target, item_id):
            if item_id == "fail":
                raise ValueError("boom")
            return {"item_id": item_id}

        results = regenerate_multiple_items({}, "npc_seeds", ["ok", "fail", "ok2"], mock_fn)
        self.assertEqual(len(results), 2)

    def test_empty_item_ids(self):
        results = regenerate_multiple_items({}, "npc_seeds", [], lambda s, t, i: None)
        self.assertEqual(results, [])

    def test_none_result_skipped(self):
        def mock_fn(setup, target, item_id):
            return None

        results = regenerate_multiple_items({}, "npc_seeds", ["a"], mock_fn)
        self.assertEqual(results, [])


# ===========================================================================
# PATCH 2 — Service layer
# ===========================================================================


class TestRegenerateSetupSectionWithToneConstraints(unittest.TestCase):
    """Test that regenerate_setup_section accepts and applies tone/constraints."""

    def test_accepts_tone_parameter(self):
        """Function signature accepts tone without error."""
        result = builder.regenerate_setup_section(
            _rich_setup(),
            "npc_seeds",
            mode="preview",
            tone="grim",
        )
        # Should succeed (preview mode)
        self.assertTrue(result.get("success"), result)

    def test_accepts_constraints_parameter(self):
        """Function signature accepts constraints without error."""
        result = builder.regenerate_setup_section(
            _rich_setup(),
            "factions",
            mode="preview",
            constraints={"require_factions": True},
        )
        self.assertTrue(result.get("success"), result)

    def test_tone_and_constraints_together(self):
        """Both tone and constraints can be passed simultaneously."""
        result = builder.regenerate_setup_section(
            _rich_setup(),
            "locations",
            mode="preview",
            tone="heroic",
            constraints={"npc_density": "high"},
        )
        self.assertTrue(result.get("success"), result)

    def test_none_tone_works(self):
        """None tone doesn't break anything."""
        result = builder.regenerate_setup_section(
            _rich_setup(),
            "npc_seeds",
            mode="preview",
            tone=None,
        )
        self.assertTrue(result.get("success"), result)

    def test_none_constraints_works(self):
        """None constraints doesn't break anything."""
        result = builder.regenerate_setup_section(
            _rich_setup(),
            "factions",
            mode="preview",
            constraints=None,
        )
        self.assertTrue(result.get("success"), result)


class TestComputeCreatorHealth(unittest.TestCase):
    """Test compute_creator_health function."""

    def test_healthy_setup(self):
        result = builder.compute_creator_health(_rich_setup())
        # Has factions, 3 NPCs, starting_location_id set
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["score"], 100)

    def test_no_npcs_warning(self):
        result = builder.compute_creator_health(_minimal_setup())
        warnings = result["warnings"]
        self.assertTrue(any("NPCs" in w for w in warnings))

    def test_no_factions_warning(self):
        result = builder.compute_creator_health(_minimal_setup())
        warnings = result["warnings"]
        self.assertTrue(any("factions" in w.lower() for w in warnings))

    def test_no_starting_location_warning(self):
        result = builder.compute_creator_health(_minimal_setup())
        warnings = result["warnings"]
        self.assertTrue(any("starting location" in w.lower() for w in warnings))

    def test_score_decreases_with_warnings(self):
        result = builder.compute_creator_health(_minimal_setup())
        self.assertLess(result["score"], 100)

    def test_score_minimum_zero(self):
        result = builder.compute_creator_health({})
        self.assertGreaterEqual(result["score"], 0)

    def test_one_npc_triggers_warning(self):
        result = builder.compute_creator_health(_minimal_setup(npc_seeds=[{"npc_id": "a"}]))
        self.assertTrue(any("NPCs" in w for w in result["warnings"]))

    def test_two_npcs_no_warning(self):
        result = builder.compute_creator_health(_minimal_setup(
            npc_seeds=[{"npc_id": "a"}, {"npc_id": "b"}],
            factions=[{"faction_id": "f"}],
            starting_location_id="loc",
        ))
        self.assertEqual(result["warnings"], [])

    def test_returns_dict_shape(self):
        result = builder.compute_creator_health({})
        self.assertIn("warnings", result)
        self.assertIn("score", result)
        self.assertIsInstance(result["warnings"], list)
        self.assertIsInstance(result["score"], int)


class TestHealthInResponses(unittest.TestCase):
    """Test that health is included in regeneration responses."""

    def test_single_item_response_has_health(self):
        result = builder.regenerate_single_item(
            _rich_setup(),
            "npc_seeds",
            "npc_fixer",
        )
        self.assertTrue(result.get("success"), result)
        self.assertIn("health", result)
        self.assertIn("warnings", result["health"])
        self.assertIn("score", result["health"])


class TestRegenerateMultipleItemsService(unittest.TestCase):
    """Test regenerate_multiple_items_service function."""

    def test_empty_item_ids(self):
        result = builder.regenerate_multiple_items_service(
            _rich_setup(), "npc_seeds", []
        )
        self.assertFalse(result["success"])
        self.assertIn("error", result)

    def test_bulk_regen_returns_correct_shape(self):
        result = builder.regenerate_multiple_items_service(
            _rich_setup(), "npc_seeds", ["npc_fixer", "npc_guard"]
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["target"], "npc_seeds")
        self.assertIn("count", result)
        self.assertIn("items", result)
        self.assertIsInstance(result["items"], list)

    def test_bulk_regen_count_matches_items(self):
        result = builder.regenerate_multiple_items_service(
            _rich_setup(), "npc_seeds", ["npc_fixer"]
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["count"], len(result["items"]))

    def test_bulk_regen_with_nonexistent_item(self):
        result = builder.regenerate_multiple_items_service(
            _rich_setup(), "npc_seeds", ["nonexistent_npc"]
        )
        # Should succeed overall but with 0 items
        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 0)

    def test_bulk_regen_factions(self):
        result = builder.regenerate_multiple_items_service(
            _rich_setup(), "factions", ["fac_guild"]
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["target"], "factions")

    def test_bulk_regen_locations(self):
        result = builder.regenerate_multiple_items_service(
            _rich_setup(), "locations", ["loc_tavern"]
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["target"], "locations")


# ===========================================================================
# PATCH 3 — Routes
# ===========================================================================


def _create_test_app():
    """Create a Flask test app with the creator blueprint."""
    from flask import Flask

    from app.rpg.creator_routes import creator_bp

    app = Flask(__name__)
    app.register_blueprint(creator_bp)
    app.config["TESTING"] = True
    return app


class TestRegenerateRouteExtended(unittest.TestCase):
    """Test that the regenerate route accepts tone/constraints."""

    def setUp(self):
        self.app = _create_test_app()
        self.client = self.app.test_client()

    def test_regenerate_accepts_tone(self):
        resp = self.client.post(
            "/api/rpg/adventure/regenerate",
            json={
                "target": "npc_seeds",
                "setup": _rich_setup(),
                "mode": "preview",
                "tone": "grim",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))

    def test_regenerate_accepts_constraints(self):
        resp = self.client.post(
            "/api/rpg/adventure/regenerate",
            json={
                "target": "factions",
                "setup": _rich_setup(),
                "mode": "preview",
                "constraints": {"require_factions": True},
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))


class TestRegenerateMultipleRoute(unittest.TestCase):
    """Test the /api/rpg/adventure/regenerate-multiple endpoint."""

    def setUp(self):
        self.app = _create_test_app()
        self.client = self.app.test_client()

    def test_missing_json(self):
        resp = self.client.post(
            "/api/rpg/adventure/regenerate-multiple",
            content_type="text/plain",
            data="not json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_missing_target(self):
        resp = self.client.post(
            "/api/rpg/adventure/regenerate-multiple",
            json={"setup": _rich_setup(), "item_ids": ["npc_fixer"]},
        )
        self.assertEqual(resp.status_code, 400)

    def test_empty_item_ids(self):
        resp = self.client.post(
            "/api/rpg/adventure/regenerate-multiple",
            json={"target": "npc_seeds", "setup": _rich_setup(), "item_ids": []},
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data["success"])

    def test_successful_bulk_regen(self):
        resp = self.client.post(
            "/api/rpg/adventure/regenerate-multiple",
            json={
                "target": "npc_seeds",
                "setup": _rich_setup(),
                "item_ids": ["npc_fixer", "npc_guard"],
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["target"], "npc_seeds")
        self.assertIn("count", data)
        self.assertIn("items", data)

    def test_response_shape(self):
        resp = self.client.post(
            "/api/rpg/adventure/regenerate-multiple",
            json={
                "target": "factions",
                "setup": _rich_setup(),
                "item_ids": ["fac_guild"],
            },
        )
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertIn("target", data)
        self.assertIn("count", data)
        self.assertIn("items", data)


# ===========================================================================
# Backward compatibility
# ===========================================================================


class TestPhase15BackwardCompatibility(unittest.TestCase):
    """Ensure Phase 1.4 behavior is preserved."""

    def test_regenerate_without_tone_constraints_still_works(self):
        """Calling without tone/constraints should behave as before."""
        result = builder.regenerate_setup_section(
            _rich_setup(),
            "npc_seeds",
            mode="preview",
        )
        self.assertTrue(result.get("success"), result)
        self.assertEqual(result["mode"], "preview")

    def test_single_item_regen_still_works(self):
        result = builder.regenerate_single_item(
            _rich_setup(),
            "npc_seeds",
            "npc_fixer",
        )
        self.assertTrue(result.get("success"), result)
        self.assertEqual(result["target"], "npc_seeds")
        self.assertEqual(result["item_id"], "npc_fixer")

    def test_preview_mode_still_returns_diff(self):
        result = builder.regenerate_setup_section(
            _rich_setup(),
            "factions",
            mode="preview",
        )
        self.assertTrue(result.get("success"))
        self.assertIn("diff", result)
        self.assertIn("apply_token", result)

    def test_existing_route_still_works(self):
        app = _create_test_app()
        client = app.test_client()
        resp = client.post(
            "/api/rpg/adventure/regenerate",
            json={
                "target": "npc_seeds",
                "setup": _rich_setup(),
                "mode": "preview",
            },
        )
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
