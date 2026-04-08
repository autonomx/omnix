"""Phase 18.3B — Integration tests for canonical session backbone,
authoritative mechanics, session-aware player routes, app LLM wiring,
payload shapes, and presentation payloads.

Run with:
    cd src && PYTHONPATH="." python3 -m pytest tests/unit/rpg/test_phase183b_integration.py -v --noconftest
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys
import types
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Import helpers (importlib-based to avoid conftest cross-package issues)
# ---------------------------------------------------------------------------

SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..")
sys.path.insert(0, SRC_DIR)


def _load_module(module_path: str, module_name: str):
    """Load a module by file path."""
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# 1. Player progression state tests
# ---------------------------------------------------------------------------

class TestPlayerProgressionState:
    """Verify progression state returns dict (not tuple) with _level_ups."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from app.rpg.player.player_progression_state import (
            ensure_player_progression_state,
            allocate_starting_stats,
            award_player_xp,
            award_skill_xp,
            resolve_level_ups,
            resolve_skill_level_ups,
            get_stat_modifier,
            get_skill_level,
        )
        self.ensure = ensure_player_progression_state
        self.allocate = allocate_starting_stats
        self.award_xp = award_player_xp
        self.award_skill_xp = award_skill_xp
        self.resolve_levels = resolve_level_ups
        self.resolve_skills = resolve_skill_level_ups
        self.stat_mod = get_stat_modifier
        self.skill_level = get_skill_level

    def test_ensure_idempotent(self):
        ps = self.ensure({})
        assert ps["level"] == 1
        assert ps["xp"] == 0
        assert "stats" in ps
        assert "skills" in ps
        ps2 = self.ensure(ps)
        assert ps2["level"] == ps["level"]

    def test_resolve_level_ups_returns_dict(self):
        ps = self.ensure({})
        ps["xp"] = 200
        ps["xp_to_next"] = 100
        result = self.resolve_levels(ps)
        assert isinstance(result, dict), "resolve_level_ups must return dict, not tuple"
        assert "_level_ups" in result
        assert result["level"] >= 2

    def test_resolve_skill_level_ups_returns_dict(self):
        ps = self.ensure({})
        ps["skills"]["swordsmanship"]["xp"] = 50
        ps["skills"]["swordsmanship"]["xp_to_next"] = 25
        result = self.resolve_skills(ps)
        assert isinstance(result, dict), "resolve_skill_level_ups must return dict, not tuple"
        assert "_skill_level_ups" in result
        assert result["skills"]["swordsmanship"]["level"] >= 1

    def test_award_xp_increments(self):
        ps = self.ensure({})
        ps = self.award_xp(ps, 50, "test")
        assert ps["xp"] == 50
        assert len(ps["progression_log"]) >= 1

    def test_award_skill_xp(self):
        ps = self.ensure({})
        ps = self.award_skill_xp(ps, "archery", 10, "combat")
        assert ps["skills"]["archery"]["xp"] == 10

    def test_allocate_starting_stats(self):
        ps = self.ensure({})
        ps = self.allocate(ps, {"strength": 3, "dexterity": 2})
        assert ps["stats"]["strength"] == 8  # 5 + 3
        assert ps["stats"]["dexterity"] == 7  # 5 + 2

    def test_stat_modifier(self):
        assert self.stat_mod(10) == 0
        assert self.stat_mod(14) == 2
        assert self.stat_mod(8) == -1

    def test_skill_level_returns_zero_default(self):
        ps = self.ensure({})
        assert self.skill_level(ps, "swordsmanship") == 0

    def test_no_level_up_when_xp_low(self):
        ps = self.ensure({})
        ps["xp"] = 50
        result = self.resolve_levels(ps)
        assert result["level"] == 1
        assert result.get("_level_ups") == []

    def test_multiple_level_ups(self):
        ps = self.ensure({})
        ps["xp"] = 350  # 100 + 200 + leftover
        result = self.resolve_levels(ps)
        assert result["level"] >= 2


# ---------------------------------------------------------------------------
# 2. Action resolver tests
# ---------------------------------------------------------------------------

class TestActionResolver:
    """Verify action_resolver produces authoritative outcomes."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from app.rpg.action_resolver import (
            resolve_player_action,
            resolve_attack_roll,
            resolve_noncombat_check,
            select_equipped_weapon,
            compute_defense_rating,
            compute_weapon_damage,
            apply_damage,
        )
        self.resolve = resolve_player_action
        self.attack = resolve_attack_roll
        self.check = resolve_noncombat_check
        self.weapon = select_equipped_weapon
        self.defense = compute_defense_rating
        self.damage = compute_weapon_damage
        self.apply_dmg = apply_damage

    def test_resolve_player_action_combat(self):
        sim = {"player_state": {"stats": {"strength": 14, "dexterity": 12}, "skills": {}}}
        action = {"action_type": "attack_melee", "target": {"stats": {"dexterity": 10}, "hp": 20}}
        result = self.resolve(sim, action, seed=42)
        assert "result" in result
        assert result["result"]["action_type"] == "attack_melee"
        assert result["result"]["outcome"] in ("hit", "miss", "crit", "graze")

    def test_resolve_noncombat_check(self):
        ps = {"stats": {"charisma": 16}, "skills": {"persuasion": {"level": 3}}}
        result = self.check(ps, "persuade", "normal", seed=42)
        assert result["action_type"] == "persuade"
        assert result["stat_used"] == "charisma"
        assert result["skill_id"] == "persuasion"
        assert result["outcome"] in ("success", "critical_success", "partial", "failure")

    def test_select_equipped_weapon_fallback(self):
        weapon = self.weapon({})
        assert weapon["item_id"] == "unarmed"
        assert weapon["combat_stats"]["damage"] == 3

    def test_select_equipped_weapon_main_hand(self):
        ps = {"inventory_state": {"equipment": {"main_hand": {"item_id": "iron_sword", "combat_stats": {"damage": 28}}}}}
        weapon = self.weapon(ps)
        assert weapon["item_id"] == "iron_sword"

    def test_compute_defense_rating(self):
        actor = {"stats": {"constitution": 14}, "defense": 2}
        rating = self.defense(actor)
        assert rating >= 2  # base_def + con_mod

    def test_apply_damage_dict(self):
        target = {"hp": 20}
        actual = self.apply_dmg(target, 5)
        assert target["hp"] == 15
        assert actual == 5

    def test_apply_damage_clamps_at_zero(self):
        target = {"hp": 3}
        self.apply_dmg(target, 10)
        assert target["hp"] == 0

    def test_deterministic_with_seed(self):
        ps = {"stats": {"intelligence": 12}, "skills": {}}
        r1 = self.check(ps, "investigate", "normal", seed=99)
        r2 = self.check(ps, "investigate", "normal", seed=99)
        assert r1["roll"] == r2["roll"]
        assert r1["outcome"] == r2["outcome"]

    def test_resolve_item_actions(self):
        sim = {"player_state": {"stats": {}, "skills": {}}}
        for action_type in ["pickup_item", "equip_item", "unequip_item", "use_item"]:
            result = self.resolve(sim, {"action_type": action_type, "item_id": "test"})
            assert result["result"]["outcome"] == "success"


# ---------------------------------------------------------------------------
# 3. Item actions tests
# ---------------------------------------------------------------------------

class TestItemActions:
    """Verify inventory and world item operations."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from app.rpg.items.inventory_state import (
            add_inventory_items,
            remove_inventory_item,
            equip_inventory_item,
            unequip_inventory_slot,
            find_inventory_item,
            get_equipped_weapon,
            get_equipped_armor,
            normalize_inventory_state,
        )
        from app.rpg.items.item_effects import apply_item_use, apply_item_effects
        from app.rpg.items.world_items import (
            spawn_world_item,
            pickup_world_item,
            drop_world_item,
            list_scene_items,
            ensure_world_item_state,
        )
        self.add_items = add_inventory_items
        self.remove_item = remove_inventory_item
        self.equip_item = equip_inventory_item
        self.unequip_slot = unequip_inventory_slot
        self.find_item = find_inventory_item
        self.get_weapon = get_equipped_weapon
        self.get_armor = get_equipped_armor
        self.normalize = normalize_inventory_state
        self.apply_use = apply_item_use
        self.apply_effects = apply_item_effects
        self.spawn_item = spawn_world_item
        self.pickup_item = pickup_world_item
        self.drop_item = drop_world_item
        self.list_items = list_scene_items
        self.ensure_world = ensure_world_item_state

    def test_add_and_find_item(self):
        inv = self.normalize({})
        inv = self.add_items(inv, [{"item_id": "healing_potion", "qty": 3}])
        found = self.find_item(inv, "healing_potion")
        assert found["item_id"] == "healing_potion"
        assert found["qty"] == 3

    def test_remove_item(self):
        inv = self.normalize({})
        inv = self.add_items(inv, [{"item_id": "healing_potion", "qty": 5}])
        inv = self.remove_item(inv, "healing_potion", 2)
        found = self.find_item(inv, "healing_potion")
        assert found["qty"] == 3

    def test_equip_and_get_weapon(self):
        inv = self.normalize({})
        inv = self.add_items(inv, [{"item_id": "iron_sword", "name": "Iron Sword", "equipment": {"slot": "main_hand"}}])
        inv = self.equip_item(inv, "iron_sword", "main_hand")
        weapon = self.get_weapon(inv)
        assert weapon.get("item_id") == "iron_sword"

    def test_unequip_slot(self):
        inv = self.normalize({})
        inv = self.add_items(inv, [{"item_id": "iron_sword", "equipment": {"slot": "main_hand"}}])
        inv = self.equip_item(inv, "iron_sword", "main_hand")
        inv = self.unequip_slot(inv, "main_hand")
        weapon = self.get_weapon(inv)
        assert not weapon.get("item_id")

    def test_world_item_spawn_and_list(self):
        sim = self.ensure_world({})
        sim = self.spawn_item(sim, "tavern", {"item_id": "gold_coin", "qty": 10})
        items = self.list_items(sim, "tavern")
        assert len(items) >= 1
        assert items[0]["item_id"] == "gold_coin"

    def test_world_item_pickup(self):
        sim = self.ensure_world({})
        sim = self.spawn_item(sim, "tavern", {"item_id": "healing_potion", "instance_id": "wi_abc"})
        sim = self.pickup_item(sim, "wi_abc")
        picked = sim.get("_picked_up_item", {})
        assert picked.get("item_id") == "healing_potion"
        items = self.list_items(sim, "tavern")
        assert len(items) == 0

    def test_apply_item_use_potion(self):
        sim = {
            "player_state": {
                "inventory_state": {
                    "items": [{"item_id": "healing_potion", "qty": 2}],
                    "equipment": {},
                    "capacity": 50,
                    "currency": {},
                    "last_loot": [],
                },
            },
        }
        result = self.apply_use(sim, "healing_potion")
        assert result["result"]["ok"] is True
        assert result["result"]["item_id"] == "healing_potion"

    def test_apply_item_use_not_owned(self):
        sim = {"player_state": {"inventory_state": {"items": [], "equipment": {}, "capacity": 50, "currency": {}, "last_loot": []}}}
        result = self.apply_use(sim, "healing_potion")
        assert result["result"]["ok"] is False
        assert result["result"]["reason"] == "item_not_owned"


# ---------------------------------------------------------------------------
# 4. Session routes (Flask conversion) tests
# ---------------------------------------------------------------------------

class TestSessionRoutes:
    """Verify session routes are Flask-based (not FastAPI)."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.routes_path = os.path.join(SRC_DIR, "app", "rpg", "api", "rpg_session_routes.py")

    def test_file_exists(self):
        assert os.path.exists(self.routes_path)

    def test_uses_flask_blueprint(self):
        with open(self.routes_path) as f:
            content = f.read()
        assert "Blueprint" in content, "Should use Flask Blueprint"
        assert "rpg_session_bp" in content, "Should define rpg_session_bp"

    def test_no_fastapi_imports(self):
        with open(self.routes_path) as f:
            content = f.read()
        assert "from fastapi" not in content, "Should not import from fastapi"
        assert "APIRouter" not in content, "Should not use APIRouter"
        assert "async def" not in content, "Should not have async functions"

    def test_uses_jsonify(self):
        with open(self.routes_path) as f:
            content = f.read()
        assert "jsonify" in content, "Should use Flask jsonify"

    def test_has_turn_endpoint(self):
        with open(self.routes_path) as f:
            content = f.read()
        assert "/api/rpg/session/turn" in content

    def test_has_stream_endpoint(self):
        with open(self.routes_path) as f:
            content = f.read()
        assert "/api/rpg/session/turn/stream" in content


# ---------------------------------------------------------------------------
# 5. Legacy routes deprecation tests
# ---------------------------------------------------------------------------

class TestLegacyRoutesDeprecated:
    """Verify legacy routes return 410."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.routes_path = os.path.join(SRC_DIR, "app", "rpg", "routes.py")

    def test_file_exists(self):
        assert os.path.exists(self.routes_path)

    def test_returns_410(self):
        with open(self.routes_path) as f:
            content = f.read()
        assert "410" in content, "Should return 410 status"
        assert "legacy_rpg_games_api_removed" in content, "Should include deprecation message"

    def test_has_recommended_endpoints(self):
        with open(self.routes_path) as f:
            content = f.read()
        assert "/api/rpg/adventure/start" in content
        assert "/api/rpg/session/turn" in content


# ---------------------------------------------------------------------------
# 6. Nearby NPC cards tests
# ---------------------------------------------------------------------------

class TestNearbyNPCCards:
    """Verify build_nearby_npc_cards produces correct output."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from app.rpg.presentation.speaker_cards import build_nearby_npc_cards
        self.build = build_nearby_npc_cards

    def test_empty_state(self):
        cards = self.build({}, {})
        assert isinstance(cards, list)
        assert len(cards) == 0

    def test_present_npcs(self):
        sim = {
            "npcs": {
                "npc_a": {"name": "Alice", "role": "merchant"},
                "npc_b": {"name": "Bob", "role": "guard"},
            },
        }
        scene = {"present_npc_ids": ["npc_a", "npc_b"]}
        cards = self.build(sim, scene)
        assert len(cards) == 2
        assert cards[0]["npc_id"] == "npc_a"
        assert cards[0]["name"] == "Alice"
        assert cards[0]["is_present"] is True

    def test_nearby_from_player_state(self):
        sim = {
            "player_state": {"nearby_npc_ids": ["npc_c"]},
            "npc_seeds": [{"npc_id": "npc_c", "name": "Charlie"}],
        }
        cards = self.build(sim, {})
        assert len(cards) == 1
        assert cards[0]["npc_id"] == "npc_c"


# ---------------------------------------------------------------------------
# 7. Memory UI summary tests
# ---------------------------------------------------------------------------

class TestMemoryPayload:
    """Verify build_memory_ui_summary produces correct output."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from app.rpg.presentation.memory_inspector import build_memory_ui_summary
        self.build = build_memory_ui_summary

    def test_empty_state(self):
        result = self.build({})
        assert "important_memory" in result
        assert "recent_memory" in result
        assert "recent_world_events" in result
        assert "total_memories" in result
        assert result["total_memories"] == 0

    def test_with_actor_memories(self):
        sim = {
            "actor_memory_state": {
                "npc_a": [
                    {"text": "Important event", "strength": 0.9},
                    {"text": "Minor event", "strength": 0.3},
                ],
            },
        }
        result = self.build(sim)
        assert result["total_memories"] == 2
        assert len(result["important_memory"]) >= 1

    def test_deduplication(self):
        sim = {
            "actor_memory_state": {
                "npc_a": [{"text": "Duplicate", "strength": 0.8}],
                "npc_b": [{"text": "Duplicate", "strength": 0.8}],
            },
        }
        result = self.build(sim)
        assert result["total_memories"] == 1  # Deduped


# ---------------------------------------------------------------------------
# 8. World expansion tests
# ---------------------------------------------------------------------------

class TestWorldExpansion:
    """Verify bounded world expansion."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from app.rpg.creator.world_expansion import (
            maybe_spawn_dynamic_npc,
            maybe_spawn_dynamic_location,
            maybe_spawn_dynamic_faction,
        )
        self.spawn_npc = maybe_spawn_dynamic_npc
        self.spawn_location = maybe_spawn_dynamic_location
        self.spawn_faction = maybe_spawn_dynamic_faction

    def test_spawn_npc(self):
        sim = {"world_expansion": {"world_growth_budget": 20, "entities_spawned": 0}}
        sim = self.spawn_npc(sim, {"name": "New NPC", "role": "merchant"})
        assert sim["_spawn_result"]["ok"] is True
        assert len(sim.get("npcs", [])) == 1
        assert sim["world_expansion"]["entities_spawned"] == 1

    def test_budget_exceeded(self):
        sim = {"world_expansion": {"world_growth_budget": 1, "entities_spawned": 1}}
        sim = self.spawn_npc(sim, {"name": "Over Budget"})
        assert sim["_spawn_result"]["ok"] is False
        assert sim["_spawn_result"]["reason"] == "budget_exceeded"

    def test_spawn_location(self):
        sim = {"world_expansion": {"world_growth_budget": 20, "entities_spawned": 0}}
        sim = self.spawn_location(sim, {"name": "New Place", "type": "town"})
        assert sim["_spawn_result"]["ok"] is True

    def test_spawn_faction(self):
        sim = {"world_expansion": {"world_growth_budget": 20, "entities_spawned": 0}}
        sim = self.spawn_faction(sim, {"name": "New Guild"})
        assert sim["_spawn_result"]["ok"] is True

    def test_npc_disabled(self):
        sim = {"world_expansion": {"allow_dynamic_npc_generation": False}}
        sim = self.spawn_npc(sim, {"name": "Disabled"})
        assert sim["_spawn_result"]["ok"] is False
        assert sim["_spawn_result"]["reason"] == "npc_generation_disabled"


# ---------------------------------------------------------------------------
# 9. Response adapter canonical payload shape tests
# ---------------------------------------------------------------------------

class TestResponseAdapterPayloadShape:
    """Verify adapt_session_to_frontend produces canonical shape."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from app.rpg.services.adventure_response_adapter import adapt_session_to_frontend
        self.adapt = adapt_session_to_frontend

    def _make_session(self):
        return {
            "manifest": {"id": "test_session_1", "title": "Test Adventure"},
            "runtime_state": {
                "opening": "Your adventure begins.",
                "world": {"genre": "fantasy"},
                "npcs": [{"id": "npc_a", "name": "Alice"}],
                "current_scene": {"scene_id": "scene:opening"},
            },
            "simulation_state": {
                "player_state": {
                    "stats": {"strength": 12},
                    "skills": {"swordsmanship": {"level": 1, "xp": 0, "xp_to_next": 25}},
                    "level": 2,
                    "xp": 50,
                    "xp_to_next": 200,
                    "inventory_state": {"items": [], "equipment": {}, "capacity": 50, "currency": {}, "last_loot": []},
                    "nearby_npc_ids": ["npc_a"],
                    "available_checks": [],
                },
                "memory_state": {"short_term": []},
                "events": [],
            },
        }

    def test_has_required_fields(self):
        result = self.adapt(self._make_session())
        assert result["success"] is True
        assert result["session_id"] == "test_session_1"
        assert result["title"] == "Test Adventure"
        assert "player" in result
        assert "nearby_npcs" in result
        assert "known_npcs" in result
        assert "scene" in result
        assert "memory_summary" in result
        assert "narration" in result

    def test_player_has_canonical_fields(self):
        result = self.adapt(self._make_session())
        player = result["player"]
        assert "stats" in player
        assert "skills" in player
        assert "level" in player
        assert "xp" in player
        assert "xp_to_next" in player
        assert "inventory_state" in player
        assert "equipment" in player
        assert "nearby_npc_ids" in player
        assert "available_checks" in player

    def test_scene_has_canonical_fields(self):
        result = self.adapt(self._make_session())
        scene = result["scene"]
        assert "scene_id" in scene
        assert "items" in scene
        assert "available_checks" in scene
        assert "present_npc_ids" in scene

    def test_memory_summary_structure(self):
        result = self.adapt(self._make_session())
        mem = result["memory_summary"]
        assert "important_memory" in mem
        assert "recent_memory" in mem
        assert "recent_world_events" in mem

    def test_legacy_compat_fields(self):
        result = self.adapt(self._make_session())
        assert "npcs" in result  # Legacy
        assert "worldEvents" in result  # Legacy
        assert "voice_assignments" in result


# ---------------------------------------------------------------------------
# 10. App LLM provider wiring tests
# ---------------------------------------------------------------------------

class TestAppLLMProviderWiring:
    """Verify adventure_builder_service uses app LLM provider."""

    def test_build_game_loop_sets_llm_gateway(self):
        """_build_game_loop should set llm_gateway on the game loop."""
        import_path = os.path.join(SRC_DIR, "app", "rpg", "services", "adventure_builder_service.py")
        with open(import_path) as f:
            content = f.read()
        assert "build_app_llm_gateway" in content, "Should import build_app_llm_gateway"
        assert "loop.llm_gateway" in content, "Should set llm_gateway on loop"

    def test_run_regeneration_uses_app_llm(self):
        """_run_regeneration should use app LLM provider, not _NullDependency."""
        import_path = os.path.join(SRC_DIR, "app", "rpg", "services", "adventure_builder_service.py")
        with open(import_path) as f:
            content = f.read()
        # Check that _run_regeneration no longer passes _NullDependency as llm_gateway
        lines = content.split("\n")
        in_run_regen = False
        found_null_llm = False
        found_app_llm = False
        for line in lines:
            if "def _run_regeneration" in line:
                in_run_regen = True
            if in_run_regen:
                if "llm_gateway=_NullDependency()" in line:
                    found_null_llm = True
                if "build_app_llm_gateway" in line:
                    found_app_llm = True
                if line.strip().startswith("def ") and "def _run_regeneration" not in line:
                    break
        assert not found_null_llm, "_run_regeneration should not pass _NullDependency as llm_gateway"
        assert found_app_llm, "_run_regeneration should use build_app_llm_gateway"


# ---------------------------------------------------------------------------
# 11. AppLLMGateway unit tests
# ---------------------------------------------------------------------------

class TestAppLLMGateway:
    """Verify AppLLMGateway wraps the app provider correctly."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        # Use importlib to load the module directly, avoiding circular imports
        # through app/__init__.py → Flask → providers
        mod_path = os.path.join(SRC_DIR, "app", "rpg", "llm_app_gateway.py")
        try:
            from app.rpg.llm_app_gateway import AppLLMGateway
            self.cls = AppLLMGateway
        except ImportError:
            # If direct import fails due to circular deps, load with stubs
            if "app.providers.base" not in sys.modules:
                base_mod = types.ModuleType("app.providers.base")
                base_mod.ChatMessage = type("ChatMessage", (), {"__init__": lambda self, **kw: None, "role": "", "content": ""})
                base_mod.ChatResponse = type("ChatResponse", (), {"__init__": lambda self, **kw: None, "content": ""})
                sys.modules["app.providers.base"] = base_mod
            spec = importlib.util.spec_from_file_location("app.rpg.llm_app_gateway", mod_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self.cls = mod.AppLLMGateway

    def test_call_generate(self):
        mock_provider = MagicMock()
        mock_provider.chat_completion.return_value = "Hello world"
        gw = self.cls(mock_provider)
        result = gw.call("generate", "test prompt")
        assert result == "Hello world"
        mock_provider.chat_completion.assert_called_once()

    def test_call_unsupported_method(self):
        mock_provider = MagicMock()
        gw = self.cls(mock_provider)
        with pytest.raises(ValueError, match="Unsupported"):
            gw.call("invalid", "test")

    def test_generate_with_context(self):
        mock_provider = MagicMock()
        mock_provider.chat_completion.return_value = "response"
        gw = self.cls(mock_provider)
        result = gw.generate("prompt", context={"key": "value"})
        assert result == "response"

    def test_none_response(self):
        mock_provider = MagicMock()
        mock_provider.chat_completion.return_value = None
        gw = self.cls(mock_provider)
        result = gw.generate("prompt")
        assert result == ""


# ---------------------------------------------------------------------------
# 12. Narration emphasis tests
# ---------------------------------------------------------------------------

class TestNarrationEmphasis:
    """Verify apply_narration_emphasis."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from app.rpg.ai.world_scene_narrator import apply_narration_emphasis
        self.apply = apply_narration_emphasis

    def test_bold_damage(self):
        result = self.apply({"narration": "You deal 15 damage to the enemy."})
        assert "**15 damage**" in result["narration"]

    def test_bold_level_up(self):
        result = self.apply({"narration": "Level up! You are now stronger."})
        assert "**Level up!**" in result["narration"]

    def test_bold_item_names(self):
        result = self.apply({
            "narration": "You found a Healing Potion.",
            "items": [{"name": "Healing Potion"}],
        })
        assert "**Healing Potion**" in result["narration"]

    def test_empty_narration(self):
        result = self.apply({})
        assert isinstance(result, dict)

    def test_no_double_bold(self):
        result = self.apply({"narration": "**already bold** and 10 damage"})
        assert "****" not in result["narration"]


# ---------------------------------------------------------------------------
# 13. Player creation tests
# ---------------------------------------------------------------------------

class TestPlayerCreation:
    """Verify character creation contract."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from app.rpg.player.player_creation import (
            build_default_stat_allocation,
            validate_stat_allocation,
            apply_character_creation,
        )
        self.build_default = build_default_stat_allocation
        self.validate = validate_stat_allocation
        self.apply_creation = apply_character_creation

    def test_default_allocation(self):
        alloc = self.build_default()
        total = sum(alloc.values())
        assert total == 12  # Default total

    def test_validate_ok(self):
        result = self.validate({"strength": 4, "dexterity": 4, "constitution": 4})
        assert result["ok"] is True

    def test_validate_exceeds(self):
        result = self.validate({"strength": 10, "dexterity": 10})
        assert result["ok"] is False

    def test_apply_character_creation(self):
        ps = {}
        ps = self.apply_creation(ps, {
            "name": "Hero",
            "class_id": "warrior",
            "stat_allocation": {"strength": 4, "dexterity": 4, "constitution": 4},
        })
        assert ps["name"] == "Hero"
        assert ps["class_id"] == "warrior"


# ---------------------------------------------------------------------------
# 14. XP rules tests
# ---------------------------------------------------------------------------

class TestXPRules:
    """Verify XP computation formulas."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from app.rpg.player.player_xp_rules import (
            compute_enemy_difficulty_xp,
            compute_quest_xp,
            compute_action_skill_xp,
            compute_stat_influence_bonus,
        )
        self.enemy_xp = compute_enemy_difficulty_xp
        self.quest_xp = compute_quest_xp
        self.action_xp = compute_action_skill_xp
        self.stat_bonus = compute_stat_influence_bonus

    def test_enemy_xp(self):
        assert self.enemy_xp({"difficulty_tier": 1}) == 35
        assert self.enemy_xp({"difficulty_tier": 3}) == 65

    def test_quest_xp(self):
        assert self.quest_xp({"quest_rank": 1}) == 75
        assert self.quest_xp({"quest_rank": 2}) == 100

    def test_action_skill_xp(self):
        result = self.action_xp({"skill_id": "swordsmanship", "outcome": "hit", "difficulty": "normal"})
        assert "swordsmanship" in result
        assert result["swordsmanship"] > 0

    def test_action_skill_xp_empty(self):
        result = self.action_xp({})
        assert result == {}

    def test_stat_influence_bonus(self):
        ps = {"stats": {"strength": 16}}
        result = self.stat_bonus(ps, {"stat_used": "strength"})
        assert result == 3  # (16-10)//2


# ---------------------------------------------------------------------------
# 15. Consequence engine reward events tests
# ---------------------------------------------------------------------------

class TestConsequenceRewards:
    """Verify build_reward_events."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from app.rpg.choice.consequence_engine import build_reward_events
        self.build_rewards = build_reward_events

    def test_quest_completion(self):
        events = self.build_rewards({"quest_completed": True, "quest_id": "q1", "faction_id": "f1"})
        types = [e["type"] for e in events]
        assert "xp_award" in types
        assert "reputation_reward" in types

    def test_item_rewards(self):
        events = self.build_rewards({"item_rewards": [{"item_id": "gold_coin", "qty": 10}]})
        assert any(e["type"] == "item_reward" for e in events)

    def test_skill_xp_awards(self):
        events = self.build_rewards({"skill_xp_awards": {"swordsmanship": 5}})
        assert any(e["type"] == "skill_xp_award" for e in events)

    def test_empty(self):
        events = self.build_rewards({})
        assert events == []


# ---------------------------------------------------------------------------
# 16. Runtime schema version tests
# ---------------------------------------------------------------------------

class TestRuntimeSchemaVersion:
    """Verify runtime uses schema version 3."""

    def test_schema_version(self):
        import_path = os.path.join(SRC_DIR, "app", "rpg", "session", "runtime.py")
        with open(import_path) as f:
            content = f.read()
        assert "_SCHEMA_VERSION = 3" in content


# ---------------------------------------------------------------------------
# 17. Item stats normalization tests
# ---------------------------------------------------------------------------

class TestItemStats:
    """Verify item stat normalization and classification."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from app.rpg.items.item_stats import (
            normalize_item_stats,
            is_weapon,
            is_armor,
            is_shield,
            get_weapon_skill,
            get_weapon_attack_stat,
        )
        self.normalize = normalize_item_stats
        self.is_weapon = is_weapon
        self.is_armor = is_armor
        self.is_shield = is_shield
        self.weapon_skill = get_weapon_skill
        self.weapon_stat = get_weapon_attack_stat

    def test_normalize_adds_defaults(self):
        result = self.normalize({})
        assert "combat_stats" in result
        assert "equipment" in result
        assert "quality" in result

    def test_is_weapon(self):
        assert self.is_weapon({"combat_stats": {"damage": 10}})
        assert not self.is_weapon({"combat_stats": {"damage": 0}})

    def test_is_armor(self):
        assert self.is_armor({"combat_stats": {"defense_bonus": 5}})
        assert not self.is_armor({"combat_stats": {"defense_bonus": 0}})

    def test_weapon_skill_sword(self):
        assert self.weapon_skill({"combat_stats": {"weapon_type": "sword"}}) == "swordsmanship"

    def test_weapon_stat_bow(self):
        assert self.weapon_stat({"combat_stats": {"weapon_type": "bow"}}) == "dexterity"


# ---------------------------------------------------------------------------
# 18. Generated item builder tests
# ---------------------------------------------------------------------------

class TestGeneratedItemBuilder:
    """Verify LLM-generated item clamping."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from app.rpg.items.generated_item_builder import (
            build_item_definition_from_llm,
            clamp_generated_item_stats,
            derive_item_power_band,
        )
        self.build = build_item_definition_from_llm
        self.clamp = clamp_generated_item_stats
        self.power_band = derive_item_power_band

    def test_power_band_common(self):
        band = self.power_band(0, "common")
        assert band["max_damage"] == 20

    def test_power_band_legendary(self):
        band = self.power_band(0, "legendary")
        assert band["max_damage"] > 20

    def test_build_clamps_damage(self):
        result = self.build({"name": "OP Sword", "combat_stats": {"damage": 999}}, world_tier=0)
        assert result["combat_stats"]["damage"] <= 100

    def test_build_generates_id(self):
        result = self.build({"name": "Test Item"})
        assert result["item_id"].startswith("gen_")

    def test_build_preserves_given_id(self):
        result = self.build({"item_id": "custom_id", "name": "Custom"})
        assert result["item_id"] == "custom_id"
