"""Phase 8.2 — Encounter Unit Tests.

Coverage:
- encounter type derivation from scene type
- deterministic participant ordering
- player action modifies hp/stress correctly
- round/turn advancement
- resolve when no enemy remains
- ensure_encounter_state defaults
- build_player_actions by encounter type
"""

from __future__ import annotations

import pytest

from app.rpg.encounter import (
    EncounterResolver,
    build_encounter_from_scene,
    build_player_actions,
    ensure_encounter_state,
)


class TestEnsureEncounterState:
    def test_creates_defaults_on_empty(self):
        state = ensure_encounter_state({})
        enc = state["player_state"]["encounter_state"]
        assert enc["active"] is False
        assert enc["encounter_id"] == ""
        assert enc["scene_id"] == ""
        assert enc["encounter_type"] == ""
        assert enc["round"] == 0
        assert enc["turn_index"] == 0
        assert enc["active_actor_id"] == ""
        assert enc["participants"] == []
        assert enc["log"] == []
        assert enc["available_actions"] == []
        assert enc["status"] == "inactive"

    def test_preserves_existing(self):
        state = {"player_state": {"encounter_state": {"active": True, "round": 5}}}
        state = ensure_encounter_state(state)
        enc = state["player_state"]["encounter_state"]
        assert enc["active"] is True
        assert enc["round"] == 5


class TestEncounterTypeDerivation:
    def _get_encounter_type(self, scene_type):
        scene = {"scene_id": "s1", "scene_type": scene_type, "actors": [{"id": "player"}]}
        result = build_encounter_from_scene(scene, {})
        return result["encounter_type"]

    def test_combat_from_conflict(self):
        assert self._get_encounter_type("conflict") == "combat"

    def test_combat_from_combat(self):
        assert self._get_encounter_type("combat") == "combat"

    def test_social_from_political(self):
        assert self._get_encounter_type("political") == "social"

    def test_social_from_negotiation(self):
        assert self._get_encounter_type("negotiation") == "social"

    def test_stealth(self):
        assert self._get_encounter_type("stealth") == "stealth"

    def test_default_standoff(self):
        assert self._get_encounter_type("normal") == "standoff"


class TestDeterministicParticipantOrdering:
    def test_ordering_by_initiative(self):
        scene = {
            "scene_id": "s1",
            "scene_type": "combat",
            "actors": [
                {"id": "player", "name": "Player"},
                {"id": "npc1", "name": "NPC1", "faction_position": {"stance": "oppose"}},
                {"id": "npc2", "name": "NPC2", "faction_position": {"stance": "oppose"}},
            ],
        }
        result = build_encounter_from_scene(scene, {})
        ids = [p["actor_id"] for p in result["participants"]]
        # Player first (index 0, initiative 100), then npc1 (99), npc2 (98)
        assert ids[0] == "player"
        assert ids[1] == "npc1"
        assert ids[2] == "npc2"

    def test_max_12_participants(self):
        actors = [{"id": f"npc_{i}"} for i in range(20)]
        actors.insert(0, {"id": "player"})
        scene = {"scene_id": "s1", "scene_type": "combat", "actors": actors}
        result = build_encounter_from_scene(scene, {})
        assert len(result["participants"]) <= 12

    def test_side_assignment(self):
        scene = {
            "scene_id": "s1",
            "scene_type": "combat",
            "actors": [
                {"id": "player"},
                {"id": "ally", "faction_position": {"stance": "support"}},
                {"id": "enemy", "faction_position": {"stance": "oppose"}},
                {"id": "neutral"},
            ],
        }
        result = build_encounter_from_scene(scene, {})
        sides = {p["actor_id"]: p["side"] for p in result["participants"]}
        assert sides["player"] == "player"
        assert sides["ally"] == "ally"
        assert sides["enemy"] == "enemy"
        assert sides["neutral"] == "neutral"


class TestPlayerActions:
    def test_combat_actions(self):
        enc = {"encounter_type": "combat"}
        actions = build_player_actions(enc)
        action_ids = [a["action_id"] for a in actions]
        assert "attack" in action_ids
        assert "defend" in action_ids
        assert "withdraw" in action_ids
        assert "wait" in action_ids
        assert "observe" in action_ids

    def test_social_actions(self):
        enc = {"encounter_type": "social"}
        actions = build_player_actions(enc)
        action_ids = [a["action_id"] for a in actions]
        assert "persuade" in action_ids
        assert "pressure" in action_ids
        assert "concede" in action_ids

    def test_stealth_actions(self):
        enc = {"encounter_type": "stealth"}
        actions = build_player_actions(enc)
        action_ids = [a["action_id"] for a in actions]
        assert "hide" in action_ids
        assert "sneak" in action_ids
        assert "distract" in action_ids

    def test_standoff_actions(self):
        enc = {"encounter_type": "standoff"}
        actions = build_player_actions(enc)
        action_ids = [a["action_id"] for a in actions]
        assert "approach" in action_ids
        assert "threaten" in action_ids
        assert "retreat" in action_ids

    def test_max_12_actions(self):
        enc = {"encounter_type": "combat"}
        actions = build_player_actions(enc)
        assert len(actions) <= 12


class TestEncounterResolver:
    def _make_encounter(self):
        return {
            "active": True,
            "encounter_id": "enc:s1",
            "scene_id": "s1",
            "encounter_type": "combat",
            "round": 1,
            "turn_index": 0,
            "active_actor_id": "player",
            "participants": [
                {"actor_id": "player", "name": "Player", "side": "player", "initiative": 100, "hp": 10, "max_hp": 10, "stress": 0, "status_effects": [], "can_act": True},
                {"actor_id": "enemy1", "name": "Enemy1", "side": "enemy", "initiative": 99, "hp": 10, "max_hp": 10, "stress": 0, "status_effects": [], "can_act": True},
            ],
            "log": [{"round": 1, "text": "Encounter started: combat", "type": "system"}],
            "available_actions": [],
            "status": "active",
        }

    def test_start_populates_actions(self):
        resolver = EncounterResolver()
        enc = self._make_encounter()
        result = resolver.start(enc)
        assert len(result["available_actions"]) > 0

    def test_player_action_advances_turn(self):
        resolver = EncounterResolver()
        enc = self._make_encounter()
        enc = resolver.start(enc)
        assert enc["turn_index"] == 0
        enc = resolver.apply_player_action(enc, "wait")
        assert enc["turn_index"] == 1

    def test_attack_reduces_hp(self):
        resolver = EncounterResolver()
        enc = self._make_encounter()
        enc = resolver.start(enc)
        enc = resolver.apply_player_action(enc, "attack", "enemy1")
        enemy = [p for p in enc["participants"] if p["actor_id"] == "enemy1"][0]
        assert enemy["hp"] == 8  # 10 - 2

    def test_persuade_increases_stress(self):
        enc = self._make_encounter()
        enc["encounter_type"] = "social"
        resolver = EncounterResolver()
        enc = resolver.start(enc)
        enc = resolver.apply_player_action(enc, "persuade", "enemy1")
        enemy = [p for p in enc["participants"] if p["actor_id"] == "enemy1"][0]
        assert enemy["stress"] == 1

    def test_turn_wraps_to_next_round(self):
        resolver = EncounterResolver()
        enc = self._make_encounter()
        enc = resolver.start(enc)  # turn_index=0
        enc = resolver._advance_turn(enc)  # turn_index=1
        assert enc["turn_index"] == 1
        assert enc["round"] == 1
        enc = resolver._advance_turn(enc)
        # With 2 participants, turn_index wraps to 0, round increments
        assert enc["turn_index"] == 0
        assert enc["round"] == 2

    def test_resolve_when_no_enemies_alive(self):
        resolver = EncounterResolver()
        enc = self._make_encounter()
        enc["participants"][1]["hp"] = 0  # Enemy dead
        enc = resolver.resolve_if_finished(enc)
        assert enc["active"] is False
        assert enc["status"] == "resolved"

    def test_npc_turn_adds_log_entry(self):
        resolver = EncounterResolver()
        enc = self._make_encounter()
        enc = resolver.start(enc)
        before_len = len(enc["log"])
        enc = resolver.apply_npc_turn(enc)
        assert len(enc["log"]) == before_len + 1