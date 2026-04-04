"""Comprehensive tests for Phase 1.4 — Regeneration UX polish.

Covers:
- Phase 1.4A: Preview / apply regeneration modes
- Phase 1.4B: Replace vs merge strategies
- Phase 1.4C: Single-item regeneration
- Phase 1.4D: Undo / rollback state helpers
- Diff computation helpers
- Merge helpers
- Route integration tests
"""

from __future__ import annotations

import json
import sys
import os
import unittest

# Ensure the src directory is on the import path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.rpg.creator.regeneration import (
    APPLY_STRATEGIES,
    ENTITY_TARGETS,
    REGENERATION_MODES,
    REGENERATION_TARGETS,
    TARGET_ID_FIELD,
    TARGET_STRATEGIES,
    RegenerationOptions,
    compute_item_diff,
    compute_section_diff,
    generate_apply_token,
    merge_entity_lists,
    merge_thread_lists,
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
            {
                "faction_id": "fac_guard",
                "name": "City Guard",
                "description": "The law",
                "goals": ["Keep order"],
            },
            {
                "faction_id": "fac_thieves",
                "name": "Thieves Guild",
                "description": "Underground",
                "goals": ["Profit"],
            },
        ],
        locations=[
            {
                "location_id": "loc_market",
                "name": "Night Market",
                "description": "Bustling market",
                "tags": ["urban"],
            },
            {
                "location_id": "loc_docks",
                "name": "Docks",
                "description": "Foggy waterfront",
                "tags": ["harbor"],
            },
        ],
        npc_seeds=[
            {
                "npc_id": "npc_fixer",
                "name": "Mara Voss",
                "role": "fixer",
                "description": "A resourceful broker",
                "goals": ["Survive"],
                "faction_id": "fac_thieves",
                "location_id": "loc_market",
                "must_survive": False,
            },
            {
                "npc_id": "npc_detective",
                "name": "Officer Hale",
                "role": "detective",
                "description": "A weary cop",
                "goals": ["Find truth"],
                "faction_id": "fac_guard",
                "location_id": "loc_docks",
                "must_survive": True,
            },
        ],
    )
    base.update(overrides)
    return base


# ===========================================================================
# Phase 1.4A — Preview / apply regeneration modes
# ===========================================================================


class TestRegenerationConstants(unittest.TestCase):
    """Verify regeneration module constants are properly defined."""

    def test_regeneration_modes(self):
        assert "preview" in REGENERATION_MODES
        assert "apply" in REGENERATION_MODES

    def test_apply_strategies(self):
        assert "replace" in APPLY_STRATEGIES
        assert "merge" in APPLY_STRATEGIES
        assert "append" in APPLY_STRATEGIES

    def test_target_strategies_coverage(self):
        """Every regeneration target has a strategy set."""
        for target in REGENERATION_TARGETS:
            assert target in TARGET_STRATEGIES, f"Missing strategy for {target}"
            assert "replace" in TARGET_STRATEGIES[target], f"Replace not in {target}"

    def test_entity_targets(self):
        assert ENTITY_TARGETS == {"factions", "locations", "npc_seeds"}

    def test_target_id_fields(self):
        assert TARGET_ID_FIELD["factions"] == "faction_id"
        assert TARGET_ID_FIELD["locations"] == "location_id"
        assert TARGET_ID_FIELD["npc_seeds"] == "npc_id"
        assert TARGET_ID_FIELD["threads"] == "thread_id"


class TestApplyToken(unittest.TestCase):
    """Verify apply token generation."""

    def test_token_starts_with_prefix(self):
        token = generate_apply_token("npc_seeds")
        assert token.startswith("regen_preview_")

    def test_tokens_are_unique(self):
        t1 = generate_apply_token("npc_seeds")
        t2 = generate_apply_token("npc_seeds")
        assert t1 != t2

    def test_token_with_payload(self):
        token = generate_apply_token("factions", {"some": "data"})
        assert token.startswith("regen_preview_")


class TestPreviewMode(unittest.TestCase):
    """Preview mode returns diff without applying changes."""

    def test_preview_returns_diff(self):
        result = builder.regenerate_setup_section(
            _rich_setup(), "npc_seeds", mode="preview"
        )
        assert result["success"] is True
        assert result["mode"] == "preview"
        assert "before" in result
        assert "after" in result
        assert "diff" in result
        assert "apply_token" in result

    def test_preview_diff_has_required_keys(self):
        result = builder.regenerate_setup_section(
            _rich_setup(), "factions", mode="preview"
        )
        diff = result["diff"]
        assert "added" in diff
        assert "removed" in diff
        assert "changed" in diff
        assert "summary" in diff

    def test_preview_does_not_return_updated_setup(self):
        result = builder.regenerate_setup_section(
            _rich_setup(), "locations", mode="preview"
        )
        assert "updated_setup" not in result

    def test_preview_for_opening(self):
        result = builder.regenerate_setup_section(
            _rich_setup(), "opening", mode="preview"
        )
        assert result["success"] is True
        assert result["mode"] == "preview"

    def test_preview_for_threads(self):
        result = builder.regenerate_setup_section(
            _rich_setup(), "threads", mode="preview"
        )
        assert result["success"] is True
        assert result["mode"] == "preview"

    def test_preview_token_is_string(self):
        result = builder.regenerate_setup_section(
            _rich_setup(), "npc_seeds", mode="preview"
        )
        assert isinstance(result["apply_token"], str)
        assert len(result["apply_token"]) > 10


class TestApplyMode(unittest.TestCase):
    """Apply mode returns updated setup and standard response."""

    def test_apply_returns_updated_setup(self):
        result = builder.regenerate_setup_section(
            _rich_setup(), "npc_seeds", mode="apply"
        )
        assert result["success"] is True
        assert result["mode"] == "apply"
        assert "updated_setup" in result
        assert "regenerated" in result
        assert "validation" in result
        assert "preview" in result
        assert "resolved_context" in result

    def test_apply_returns_strategy(self):
        result = builder.regenerate_setup_section(
            _rich_setup(), "factions", mode="apply", apply_strategy="replace"
        )
        assert result["apply_strategy"] == "replace"

    def test_apply_with_token(self):
        """Apply with a preview token should work (cache hit or regenerate)."""
        # First get a preview
        preview = builder.regenerate_setup_section(
            _rich_setup(), "npc_seeds", mode="preview"
        )
        token = preview["apply_token"]

        # Then apply with that token
        result = builder.regenerate_setup_section(
            _rich_setup(), "npc_seeds", mode="apply", apply_token=token
        )
        assert result["success"] is True
        assert result["mode"] == "apply"
        assert "updated_setup" in result

    def test_apply_with_invalid_token(self):
        """Apply with a bogus token should still work (regenerate fresh)."""
        result = builder.regenerate_setup_section(
            _rich_setup(), "npc_seeds", mode="apply", apply_token="bogus_token"
        )
        assert result["success"] is True

    def test_default_mode_is_apply(self):
        """When mode is not specified, should default to apply."""
        result = builder.regenerate_setup_section(
            _rich_setup(), "npc_seeds"
        )
        assert result["success"] is True
        assert result["mode"] == "apply"


class TestModeValidation(unittest.TestCase):
    """Validate mode and target parameters."""

    def test_invalid_mode(self):
        result = builder.regenerate_setup_section(
            _rich_setup(), "npc_seeds", mode="invalid"
        )
        assert result["success"] is False
        assert "mode" in result["error"].lower()

    def test_invalid_target(self):
        result = builder.regenerate_setup_section(
            _rich_setup(), "invalid_target", mode="preview"
        )
        assert result["success"] is False
        assert "target" in result["error"].lower()

    def test_blocking_validation(self):
        """Blocking validation issues prevent regeneration."""
        result = builder.regenerate_setup_section(
            {"setup_id": "x"}, "npc_seeds", mode="preview"
        )
        assert result["success"] is False


# ===========================================================================
# Phase 1.4B — Replace vs merge
# ===========================================================================


class TestReplaceStrategy(unittest.TestCase):
    """Replace strategy (Phase 1.3 behaviour)."""

    def test_replace_factions(self):
        payload = _rich_setup()
        new_factions = [{"faction_id": "fac_new", "name": "New Faction", "description": "", "goals": []}]
        result = builder._replace_regenerated_section(payload, "factions", new_factions)
        assert len(result["factions"]) == 1
        assert result["factions"][0]["faction_id"] == "fac_new"

    def test_replace_locations(self):
        payload = _rich_setup()
        new_locs = [{"location_id": "loc_new", "name": "New Place", "description": "", "tags": []}]
        result = builder._replace_regenerated_section(payload, "locations", new_locs)
        assert len(result["locations"]) == 1

    def test_replace_npcs(self):
        payload = _rich_setup()
        new_npcs = [{"npc_id": "npc_new", "name": "New NPC", "role": "hero", "description": "", "goals": []}]
        result = builder._replace_regenerated_section(payload, "npc_seeds", new_npcs)
        assert len(result["npc_seeds"]) == 1

    def test_replace_threads(self):
        payload = _rich_setup()
        threads = [{"thread_id": "t1", "title": "Thread 1"}]
        result = builder._replace_regenerated_section(payload, "threads", threads)
        assert result["metadata"]["regenerated_threads"] == threads

    def test_replace_opening(self):
        payload = _rich_setup()
        opening = {
            "opening_situation": {"location": "Test", "summary": "Opening"},
            "resolved_context": {"location_id": "loc_market", "npc_ids": ["npc_fixer"]},
        }
        result = builder._replace_regenerated_section(payload, "opening", opening)
        assert result["metadata"]["regenerated_opening"] == opening
        assert result["starting_location_id"] == "loc_market"


class TestMergeStrategy(unittest.TestCase):
    """Merge strategy with id-based merge for entities."""

    def test_merge_adds_new_entities(self):
        payload = _rich_setup()
        new_factions = [
            {"faction_id": "fac_new", "name": "New Faction", "description": "", "goals": []},
        ]
        result = builder._merge_regenerated_section(payload, "factions", new_factions)
        # Should keep both original + new
        assert len(result["factions"]) == 3
        ids = [f["faction_id"] for f in result["factions"]]
        assert "fac_guard" in ids
        assert "fac_thieves" in ids
        assert "fac_new" in ids

    def test_merge_overwrites_existing(self):
        payload = _rich_setup()
        updated_faction = {
            "faction_id": "fac_guard",
            "name": "Imperial Guard",
            "description": "Updated",
            "goals": ["Enforce law"],
        }
        result = builder._merge_regenerated_section(payload, "factions", [updated_faction])
        assert len(result["factions"]) == 2
        guard = next(f for f in result["factions"] if f["faction_id"] == "fac_guard")
        assert guard["name"] == "Imperial Guard"
        assert guard["description"] == "Updated"

    def test_merge_preserves_unmentioned(self):
        payload = _rich_setup()
        # Only regenerate one faction, other should stay
        new_factions = [
            {"faction_id": "fac_guard", "name": "Updated Guard", "description": "X", "goals": []},
        ]
        result = builder._merge_regenerated_section(payload, "factions", new_factions)
        assert len(result["factions"]) == 2
        thieves = next(f for f in result["factions"] if f["faction_id"] == "fac_thieves")
        assert thieves["name"] == "Thieves Guild"  # Unchanged

    def test_merge_locations(self):
        payload = _rich_setup()
        new_locs = [{"location_id": "loc_new", "name": "Tavern", "description": "", "tags": []}]
        result = builder._merge_regenerated_section(payload, "locations", new_locs)
        assert len(result["locations"]) == 3

    def test_merge_npc_seeds(self):
        payload = _rich_setup()
        new_npcs = [
            {"npc_id": "npc_new", "name": "Lyra", "role": "bard", "description": "", "goals": []},
        ]
        result = builder._merge_regenerated_section(payload, "npc_seeds", new_npcs)
        assert len(result["npc_seeds"]) == 3


class TestAppendStrategy(unittest.TestCase):
    """Append strategy for threads."""

    def test_append_threads(self):
        payload = _rich_setup()
        payload.setdefault("metadata", {})["regenerated_threads"] = [
            {"thread_id": "t1", "title": "Thread 1"},
        ]
        new_threads = [
            {"thread_id": "t2", "title": "Thread 2"},
        ]
        result = builder._merge_regenerated_section(payload, "threads", new_threads)
        threads = result["metadata"]["regenerated_threads"]
        assert len(threads) == 2
        ids = [t["thread_id"] for t in threads]
        assert "t1" in ids
        assert "t2" in ids

    def test_append_deduplicates(self):
        payload = _rich_setup()
        payload.setdefault("metadata", {})["regenerated_threads"] = [
            {"thread_id": "t1", "title": "Thread 1"},
        ]
        new_threads = [
            {"thread_id": "t1", "title": "Thread 1 updated"},
        ]
        result = builder._merge_regenerated_section(payload, "threads", new_threads)
        threads = result["metadata"]["regenerated_threads"]
        # Should not duplicate — keeps original t1
        assert len(threads) == 1


class TestApplyDispatch(unittest.TestCase):
    """_apply_regenerated_section dispatches by strategy."""

    def test_dispatch_replace(self):
        payload = _rich_setup()
        new_factions = [{"faction_id": "fac_new", "name": "X", "description": "", "goals": []}]
        result = builder._apply_regenerated_section(payload, "factions", new_factions, strategy="replace")
        assert len(result["factions"]) == 1

    def test_dispatch_merge(self):
        payload = _rich_setup()
        new_factions = [{"faction_id": "fac_new", "name": "X", "description": "", "goals": []}]
        result = builder._apply_regenerated_section(payload, "factions", new_factions, strategy="merge")
        assert len(result["factions"]) == 3

    def test_dispatch_default_replace(self):
        payload = _rich_setup()
        new_factions = [{"faction_id": "fac_new", "name": "X", "description": "", "goals": []}]
        result = builder._apply_regenerated_section(payload, "factions", new_factions)
        assert len(result["factions"]) == 1

    def test_strategy_validation_in_regenerate(self):
        """Opening only supports replace — merge should fall back to replace."""
        result = builder.regenerate_setup_section(
            _rich_setup(), "opening", mode="apply", apply_strategy="merge"
        )
        assert result["success"] is True
        assert result["apply_strategy"] == "replace"

    def test_threads_append_strategy(self):
        result = builder.regenerate_setup_section(
            _rich_setup(), "threads", mode="apply", apply_strategy="append"
        )
        assert result["success"] is True
        assert result["apply_strategy"] == "append"


# ===========================================================================
# Diff computation helpers
# ===========================================================================


class TestComputeSectionDiff(unittest.TestCase):
    """Test the section diff computation helpers."""

    def test_entity_diff_all_new(self):
        before = [{"npc_id": "a"}, {"npc_id": "b"}]
        after = [{"npc_id": "c"}, {"npc_id": "d"}]
        diff = compute_section_diff("npc_seeds", before, after)
        assert diff["added"] == 2
        assert diff["removed"] == 2
        assert diff["changed"] == 0

    def test_entity_diff_no_change(self):
        items = [{"npc_id": "a", "name": "X"}, {"npc_id": "b", "name": "Y"}]
        diff = compute_section_diff("npc_seeds", items, items)
        assert diff["added"] == 0
        assert diff["removed"] == 0
        assert diff["changed"] == 0

    def test_entity_diff_one_changed(self):
        before = [{"npc_id": "a", "name": "X"}]
        after = [{"npc_id": "a", "name": "Y"}]
        diff = compute_section_diff("npc_seeds", before, after)
        assert diff["changed"] == 1
        assert diff["added"] == 0
        assert diff["removed"] == 0

    def test_entity_diff_mixed(self):
        before = [{"npc_id": "a"}, {"npc_id": "b"}, {"npc_id": "c"}]
        after = [{"npc_id": "a"}, {"npc_id": "d"}]
        diff = compute_section_diff("npc_seeds", before, after)
        assert diff["removed"] == 2  # b, c
        assert diff["added"] == 1    # d
        assert diff["changed"] == 0

    def test_entity_diff_summary_messages(self):
        before = [{"npc_id": "a"}, {"npc_id": "b"}]
        after = [{"npc_id": "c"}]
        diff = compute_section_diff("npc_seeds", before, after)
        assert len(diff["summary"]) > 0

    def test_faction_diff(self):
        before = [{"faction_id": "f1"}, {"faction_id": "f2"}]
        after = [{"faction_id": "f1"}, {"faction_id": "f3"}]
        diff = compute_section_diff("factions", before, after)
        assert diff["added"] == 1
        assert diff["removed"] == 1

    def test_location_diff(self):
        before = [{"location_id": "l1"}]
        after = [{"location_id": "l1"}, {"location_id": "l2"}]
        diff = compute_section_diff("locations", before, after)
        assert diff["added"] == 1
        assert diff["removed"] == 0

    def test_thread_diff(self):
        before = [{"thread_id": "t1"}]
        after = [{"thread_id": "t1"}, {"thread_id": "t2"}]
        diff = compute_section_diff("threads", before, after)
        assert diff["added"] == 1
        assert diff["removed"] == 0

    def test_opening_diff(self):
        before = {"location": "A", "summary": "X"}
        after = {"location": "B", "summary": "X"}
        diff = compute_section_diff("opening", before, after)
        assert diff["changed"] >= 1

    def test_opening_diff_no_change(self):
        data = {"location": "A", "summary": "X"}
        diff = compute_section_diff("opening", data, data)
        assert diff["changed"] == 0

    def test_empty_before_and_after(self):
        diff = compute_section_diff("npc_seeds", [], [])
        assert diff["added"] == 0
        assert diff["removed"] == 0

    def test_handles_non_list_gracefully(self):
        diff = compute_section_diff("npc_seeds", None, None)
        assert diff["added"] == 0
        assert diff["removed"] == 0


class TestComputeItemDiff(unittest.TestCase):
    """Test single-item diff computation."""

    def test_no_changes(self):
        item = {"npc_id": "a", "name": "X", "role": "hero"}
        diff = compute_item_diff(item, item)
        assert diff["changed_fields"] == []

    def test_some_changes(self):
        before = {"npc_id": "a", "name": "X", "role": "hero"}
        after = {"npc_id": "a", "name": "X", "role": "villain"}
        diff = compute_item_diff(before, after)
        assert "role" in diff["changed_fields"]
        assert "name" not in diff["changed_fields"]

    def test_new_field_added(self):
        before = {"npc_id": "a"}
        after = {"npc_id": "a", "extra": "data"}
        diff = compute_item_diff(before, after)
        assert "extra" in diff["changed_fields"]

    def test_handles_none_gracefully(self):
        diff = compute_item_diff(None, {"a": 1})
        assert "a" in diff["changed_fields"]


# ===========================================================================
# Merge helpers
# ===========================================================================


class TestMergeEntityLists(unittest.TestCase):
    """Test entity list merging."""

    def test_merge_new_items(self):
        current = [{"id": "a", "val": 1}]
        regen = [{"id": "b", "val": 2}]
        result = merge_entity_lists(current, regen, "id")
        assert len(result) == 2

    def test_merge_overwrite_existing(self):
        current = [{"id": "a", "val": 1}]
        regen = [{"id": "a", "val": 99}]
        result = merge_entity_lists(current, regen, "id")
        assert len(result) == 1
        assert result[0]["val"] == 99

    def test_merge_preserves_order(self):
        current = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        regen = [{"id": "b", "updated": True}, {"id": "d"}]
        result = merge_entity_lists(current, regen, "id")
        ids = [i["id"] for i in result]
        assert ids == ["a", "b", "c", "d"]
        assert result[1]["updated"] is True

    def test_merge_empty_current(self):
        result = merge_entity_lists([], [{"id": "a"}], "id")
        assert len(result) == 1

    def test_merge_empty_regen(self):
        result = merge_entity_lists([{"id": "a"}], [], "id")
        assert len(result) == 1

    def test_merge_handles_none(self):
        result = merge_entity_lists(None, None, "id")
        assert result == []


class TestMergeThreadLists(unittest.TestCase):
    """Test thread list merging."""

    def test_append_adds_new_threads(self):
        current = [{"thread_id": "t1"}]
        regen = [{"thread_id": "t2"}]
        result = merge_thread_lists(current, regen, strategy="append")
        assert len(result) == 2

    def test_append_deduplicates(self):
        current = [{"thread_id": "t1"}]
        regen = [{"thread_id": "t1"}]
        result = merge_thread_lists(current, regen, strategy="append")
        assert len(result) == 1

    def test_merge_strategy(self):
        current = [{"thread_id": "t1", "title": "old"}]
        regen = [{"thread_id": "t1", "title": "new"}, {"thread_id": "t2", "title": "fresh"}]
        result = merge_thread_lists(current, regen, strategy="merge")
        assert len(result) == 2
        t1 = next(t for t in result if t["thread_id"] == "t1")
        assert t1["title"] == "new"


# ===========================================================================
# Phase 1.4C — Single-item regeneration
# ===========================================================================


class TestSingleItemRegeneration(unittest.TestCase):
    """Test single entity regeneration."""

    def test_single_npc_regen(self):
        result = builder.regenerate_single_item(
            _rich_setup(), "npc_seeds", "npc_fixer"
        )
        assert result["success"] is True
        assert result["target"] == "npc_seeds"
        assert result["item_id"] == "npc_fixer"
        assert "before" in result
        assert "after" in result
        assert "diff" in result
        assert "updated_setup" in result

    def test_single_faction_regen(self):
        result = builder.regenerate_single_item(
            _rich_setup(), "factions", "fac_guard"
        )
        assert result["success"] is True
        assert result["item_id"] == "fac_guard"

    def test_single_location_regen(self):
        result = builder.regenerate_single_item(
            _rich_setup(), "locations", "loc_market"
        )
        assert result["success"] is True
        assert result["item_id"] == "loc_market"

    def test_item_not_found(self):
        result = builder.regenerate_single_item(
            _rich_setup(), "npc_seeds", "nonexistent_id"
        )
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_unsupported_target(self):
        result = builder.regenerate_single_item(
            _rich_setup(), "opening", "some_id"
        )
        assert result["success"] is False
        assert "only supported" in result["error"].lower()

    def test_threads_not_supported(self):
        result = builder.regenerate_single_item(
            _rich_setup(), "threads", "thread_id"
        )
        assert result["success"] is False

    def test_item_diff_has_changed_fields(self):
        result = builder.regenerate_single_item(
            _rich_setup(), "npc_seeds", "npc_fixer"
        )
        assert "changed_fields" in result["diff"]
        assert isinstance(result["diff"]["changed_fields"], list)

    def test_item_preserves_id(self):
        result = builder.regenerate_single_item(
            _rich_setup(), "npc_seeds", "npc_fixer"
        )
        assert result["after"]["npc_id"] == "npc_fixer"

    def test_updated_setup_has_regenerated_item(self):
        result = builder.regenerate_single_item(
            _rich_setup(), "npc_seeds", "npc_fixer"
        )
        updated_npcs = result["updated_setup"]["npc_seeds"]
        assert len(updated_npcs) == 2  # Same count as before
        fixer = next(n for n in updated_npcs if n["npc_id"] == "npc_fixer")
        assert fixer == result["after"]

    def test_blocking_validation_blocks(self):
        result = builder.regenerate_single_item(
            {"setup_id": "x"}, "npc_seeds", "npc_fixer"
        )
        assert result["success"] is False


# ===========================================================================
# Route integration tests
# ===========================================================================

try:
    from flask import Flask
    from app.rpg.creator_routes import creator_bp
    _HAS_FLASK = True
except ImportError:
    _HAS_FLASK = False


@unittest.skipUnless(_HAS_FLASK, "Flask not available")
class TestRegenerateRoutes(unittest.TestCase):
    """Test route-level integration for regeneration endpoints."""

    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(creator_bp)
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_regenerate_preview_mode(self):
        resp = self.client.post(
            "/api/rpg/adventure/regenerate",
            data=json.dumps({
                "target": "npc_seeds",
                "mode": "preview",
                "setup": _rich_setup(),
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["mode"] == "preview"
        assert "diff" in data

    def test_regenerate_apply_mode(self):
        resp = self.client.post(
            "/api/rpg/adventure/regenerate",
            data=json.dumps({
                "target": "factions",
                "mode": "apply",
                "apply_strategy": "replace",
                "setup": _rich_setup(),
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["mode"] == "apply"
        assert "updated_setup" in data

    def test_regenerate_merge_strategy(self):
        resp = self.client.post(
            "/api/rpg/adventure/regenerate",
            data=json.dumps({
                "target": "npc_seeds",
                "mode": "apply",
                "apply_strategy": "merge",
                "setup": _rich_setup(),
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["apply_strategy"] == "merge"

    def test_regenerate_missing_target(self):
        resp = self.client.post(
            "/api/rpg/adventure/regenerate",
            data=json.dumps({"mode": "preview", "setup": _rich_setup()}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_regenerate_missing_body(self):
        resp = self.client.post("/api/rpg/adventure/regenerate")
        assert resp.status_code == 400

    def test_regenerate_invalid_mode(self):
        resp = self.client.post(
            "/api/rpg/adventure/regenerate",
            data=json.dumps({
                "target": "npc_seeds",
                "mode": "bogus",
                "setup": _rich_setup(),
            }),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_regenerate_item_endpoint(self):
        resp = self.client.post(
            "/api/rpg/adventure/regenerate-item",
            data=json.dumps({
                "target": "npc_seeds",
                "item_id": "npc_fixer",
                "setup": _rich_setup(),
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["item_id"] == "npc_fixer"

    def test_regenerate_item_missing_id(self):
        resp = self.client.post(
            "/api/rpg/adventure/regenerate-item",
            data=json.dumps({
                "target": "npc_seeds",
                "setup": _rich_setup(),
            }),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_regenerate_item_missing_target(self):
        resp = self.client.post(
            "/api/rpg/adventure/regenerate-item",
            data=json.dumps({
                "item_id": "npc_fixer",
                "setup": _rich_setup(),
            }),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_regenerate_item_missing_body(self):
        resp = self.client.post("/api/rpg/adventure/regenerate-item")
        assert resp.status_code == 400

    def test_regenerate_item_unsupported_target(self):
        resp = self.client.post(
            "/api/rpg/adventure/regenerate-item",
            data=json.dumps({
                "target": "opening",
                "item_id": "some_id",
                "setup": _rich_setup(),
            }),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_preview_then_apply_flow(self):
        """Full preview → apply handshake."""
        # Step 1: Preview
        resp1 = self.client.post(
            "/api/rpg/adventure/regenerate",
            data=json.dumps({
                "target": "factions",
                "mode": "preview",
                "setup": _rich_setup(),
            }),
            content_type="application/json",
        )
        data1 = resp1.get_json()
        assert data1["success"] is True
        token = data1["apply_token"]

        # Step 2: Apply with token
        resp2 = self.client.post(
            "/api/rpg/adventure/regenerate",
            data=json.dumps({
                "target": "factions",
                "mode": "apply",
                "apply_token": token,
                "apply_strategy": "replace",
                "setup": _rich_setup(),
            }),
            content_type="application/json",
        )
        data2 = resp2.get_json()
        assert data2["success"] is True
        assert "updated_setup" in data2


# ===========================================================================
# Phase 1.4D — Undo / rollback (state helper tests)
# ===========================================================================


class TestPreviewStore(unittest.TestCase):
    """Test in-memory preview store."""

    def test_store_and_pop(self):
        builder._store_preview("tok1", {"target": "npc_seeds", "data": True})
        result = builder._pop_preview("tok1")
        assert result is not None
        assert result["target"] == "npc_seeds"

    def test_pop_removes_entry(self):
        builder._store_preview("tok2", {"target": "factions"})
        builder._pop_preview("tok2")
        assert builder._pop_preview("tok2") is None

    def test_pop_missing_returns_none(self):
        assert builder._pop_preview("nonexistent") is None

    def test_store_evicts_oldest(self):
        # Fill to max
        for i in range(builder._MAX_PREVIEW_STORE_SIZE + 5):
            builder._store_preview(f"evict_{i}", {"idx": i})
        # Oldest entries should be evicted
        assert builder._pop_preview("evict_0") is None


# ===========================================================================
# RegenerationOptions dataclass (existing from Phase 1.3)
# ===========================================================================


class TestRegenerationOptions(unittest.TestCase):
    """Test the RegenerationOptions dataclass."""

    def test_defaults(self):
        opts = RegenerationOptions(target="npc_seeds")
        assert opts.replace is True
        assert opts.preserve_ids is True
        assert opts.extra_context == {}

    def test_custom_values(self):
        opts = RegenerationOptions(
            target="factions",
            replace=False,
            preserve_ids=False,
            extra_context={"hint": "more political"},
        )
        assert opts.target == "factions"
        assert opts.replace is False


# ===========================================================================
# Backward compatibility — old API contract still works
# ===========================================================================


class TestBackwardCompatibility(unittest.TestCase):
    """Ensure Phase 1.3 API contract still works with Phase 1.4 changes."""

    def test_regenerate_without_mode(self):
        """Calling regenerate without mode parameter works (defaults to apply)."""
        result = builder.regenerate_setup_section(_rich_setup(), "npc_seeds")
        assert result["success"] is True
        assert "updated_setup" in result
        assert "regenerated" in result
        assert "validation" in result

    def test_regenerate_returns_preview_and_context(self):
        result = builder.regenerate_setup_section(_rich_setup(), "factions")
        assert "preview" in result
        assert "resolved_context" in result


if __name__ == "__main__":
    unittest.main()
