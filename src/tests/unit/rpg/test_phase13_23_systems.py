"""Phase 13-23 comprehensive tests.

Covers Social Sim 2.0, Director Integration, Encounter Tactical, Inventory Economy,
Travel Map, Quest Deepening, GM Tools, Save Packaging, Performance, UX Polish,
and Emergent Narrative Endgame.
"""
from __future__ import annotations

import copy
import importlib
import os
import sys
import types

_SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

# Bootstrap parent packages so that sub-packages can be imported
_PACKAGES = [
    ("app", "app"),
    ("app.rpg", os.path.join("app", "rpg")),
    ("app.rpg.social", os.path.join("app", "rpg", "social")),
    ("app.rpg.director", os.path.join("app", "rpg", "director")),
    ("app.rpg.encounter", os.path.join("app", "rpg", "encounter")),
    ("app.rpg.items", os.path.join("app", "rpg", "items")),
    ("app.rpg.travel", os.path.join("app", "rpg", "travel")),
    ("app.rpg.quest", os.path.join("app", "rpg", "quest")),
    ("app.rpg.creator", os.path.join("app", "rpg", "creator")),
    ("app.rpg.persistence", os.path.join("app", "rpg", "persistence")),
    ("app.rpg.core", os.path.join("app", "rpg", "core")),
    ("app.rpg.ux", os.path.join("app", "rpg", "ux")),
    ("app.rpg.narrative", os.path.join("app", "rpg", "narrative")),
]
for _mod_name, _rel_path in _PACKAGES:
    if _mod_name not in sys.modules:
        _m = types.ModuleType(_mod_name)
        _m.__path__ = [os.path.join(_SRC_DIR, _rel_path)]
        sys.modules[_mod_name] = _m

# Now load actual module files via importlib for non-package modules
def _load_module(dotted_name: str, file_path: str) -> types.ModuleType:
    """Load a .py file as a module with the given dotted name."""
    spec = importlib.util.spec_from_file_location(dotted_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {dotted_name} from {file_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[dotted_name] = mod
    spec.loader.exec_module(mod)
    return mod

_load_module("app.rpg.social.social_sim_v2",
             os.path.join(_SRC_DIR, "app", "rpg", "social", "social_sim_v2.py"))
_load_module("app.rpg.director.director_integration",
             os.path.join(_SRC_DIR, "app", "rpg", "director", "director_integration.py"))
_load_module("app.rpg.encounter.tactical_mode",
             os.path.join(_SRC_DIR, "app", "rpg", "encounter", "tactical_mode.py"))
_load_module("app.rpg.items.economy",
             os.path.join(_SRC_DIR, "app", "rpg", "items", "economy.py"))
_load_module("app.rpg.travel.travel_system",
             os.path.join(_SRC_DIR, "app", "rpg", "travel", "travel_system.py"))
_load_module("app.rpg.quest.quest_deepening",
             os.path.join(_SRC_DIR, "app", "rpg", "quest", "quest_deepening.py"))
_load_module("app.rpg.creator.gm_tools",
             os.path.join(_SRC_DIR, "app", "rpg", "creator", "gm_tools.py"))
_load_module("app.rpg.persistence.save_packaging",
             os.path.join(_SRC_DIR, "app", "rpg", "persistence", "save_packaging.py"))
_load_module("app.rpg.core.performance",
             os.path.join(_SRC_DIR, "app", "rpg", "core", "performance.py"))
_load_module("app.rpg.ux.production_polish",
             os.path.join(_SRC_DIR, "app", "rpg", "ux", "production_polish.py"))
_load_module("app.rpg.narrative.emergent_endgame",
             os.path.join(_SRC_DIR, "app", "rpg", "narrative", "emergent_endgame.py"))


# ═══════════════════════════════════════════════════════════════════════════
# Phase 13 — Social simulation 2.0
# ═══════════════════════════════════════════════════════════════════════════

from app.rpg.social.social_sim_v2 import (
    ReputationEdge, AllianceRecord, RumorRecord, SocialSimState,
    RelationshipDeepener, AllianceManager, BetrayalPropagator,
    GroupDecisionEngine, RumorEngine, SocialPressureEngine,
    SocialInspector, SocialDeterminismValidator,
    MAX_REPUTATION_EDGES, MAX_ALLIANCES, MAX_RUMORS,
)


class TestPhase13SocialSimState:
    def test_default(self):
        s = SocialSimState()
        assert s.tick == 0
        assert s.reputation_edges == []

    def test_round_trip(self):
        s = SocialSimState(tick=5, reputation_edges=[ReputationEdge(source_id="a", target_id="b", trust=0.5)])
        d = s.to_dict()
        s2 = SocialSimState.from_dict(d)
        assert s2.to_dict() == d

    def test_edge_clamped(self):
        e = ReputationEdge.from_dict({"trust": 5.0, "fear": -5.0})
        assert e.trust <= 1.0
        assert e.fear >= -1.0


class TestPhase13RelationshipDeepener:
    def test_help_event(self):
        e = ReputationEdge(source_id="a", target_id="b")
        RelationshipDeepener.apply_event(e, "help", 1)
        assert e.trust > 0

    def test_attack_event(self):
        e = ReputationEdge(source_id="a", target_id="b")
        RelationshipDeepener.apply_event(e, "attack", 1)
        assert e.hostility > 0
        assert e.trust < 0

    def test_decay(self):
        edges = [ReputationEdge(source_id="a", target_id="b", trust=0.8, last_tick=1)]
        RelationshipDeepener.decay_relationships(edges, 20)
        assert edges[0].trust < 0.8


class TestPhase13AllianceManager:
    def test_form_alliance(self):
        a = AllianceManager.form_alliance("f1", "f2", 1)
        assert a.status == "allied"
        assert a.strength == 0.5

    def test_strengthen(self):
        a = AllianceRecord(strength=0.5, status="allied")
        AllianceManager.strengthen(a, 0.3)
        assert a.strength == 0.8

    def test_weaken_to_dissolved(self):
        a = AllianceRecord(strength=0.3, status="allied")
        AllianceManager.weaken(a, 0.2)
        assert a.status == "dissolved"

    def test_dissolve(self):
        a = AllianceRecord(strength=0.5)
        AllianceManager.dissolve(a)
        assert a.strength == 0.0
        assert a.status == "dissolved"


class TestPhase13Betrayal:
    def test_propagate(self):
        edges = [ReputationEdge(source_id="victim", target_id="ally", trust=0.8)]
        events = BetrayalPropagator.propagate_betrayal("betrayer", "victim", edges, 1)
        assert any(e["type"] == "trust_collapse" for e in events)
        assert any(e["type"] == "social_shock" for e in events)


class TestPhase13GroupDecision:
    def test_oppose_stance(self):
        edges = [ReputationEdge(source_id="m1", target_id="t1", hostility=0.8),
                 ReputationEdge(source_id="m2", target_id="t1", hostility=0.6)]
        result = GroupDecisionEngine.compute_group_stance(edges, "t1")
        assert result["stance"] == "oppose"

    def test_neutral(self):
        result = GroupDecisionEngine.compute_group_stance([], "t1")
        assert result["stance"] == "neutral"


class TestPhase13Rumors:
    def test_create_and_spread(self):
        r = RumorEngine.create_rumor("secret", "npc1", 1, 0.8)
        assert r.credibility == 0.8
        RumorEngine.spread_rumor(r, 2)
        assert r.spread_count == 1
        assert r.credibility < 0.8

    def test_mutate(self):
        r = RumorEngine.create_rumor("original", "npc1", 1)
        RumorEngine.mutate_rumor(r, "mutated version")
        assert r.content == "mutated version"
        assert r.mutation_count == 1

    def test_decay(self):
        rumors = [RumorEngine.create_rumor("s", "npc1", 1, 0.5)]
        RumorEngine.decay_rumors(rumors, 20)
        assert rumors[0].credibility < 0.5


class TestPhase13SocialPressure:
    def test_encounter_pressure(self):
        edges = [ReputationEdge(source_id="a", target_id="b", hostility=0.8)]
        result = SocialPressureEngine.compute_encounter_pressure("a", "b", edges, [])
        assert result["aggression_modifier"] > 0

    def test_dialogue_pressure(self):
        edges = [ReputationEdge(source_id="a", target_id="b", trust=0.8)]
        result = SocialPressureEngine.compute_dialogue_pressure("a", "b", edges)
        assert result["tone_modifier"] == "friendly"


class TestPhase13Determinism:
    def test_validate_bounds_ok(self):
        s = SocialSimState()
        assert SocialDeterminismValidator.validate_bounds(s) == []

    def test_validate_bounds_exceeded(self):
        s = SocialSimState(reputation_edges=[ReputationEdge() for _ in range(210)])
        violations = SocialDeterminismValidator.validate_bounds(s)
        assert len(violations) > 0

    def test_normalize(self):
        s = SocialSimState(reputation_edges=[ReputationEdge() for _ in range(210)])
        norm = SocialDeterminismValidator.normalize_state(s)
        assert SocialDeterminismValidator.validate_bounds(norm) == []


# ═══════════════════════════════════════════════════════════════════════════
# Phase 14 — Story director system integration
# ═══════════════════════════════════════════════════════════════════════════

from app.rpg.director.director_integration import (
    StoryBeat, StoryArcState, DirectorState,
    TensionPacingController, ArcBeatTracker, SceneBiasEngine,
    DirectorDialogueInfluence, DirectorQuestInfluence,
    DirectorInspector, DirectorDeterminismValidator,
)


class TestPhase14DirectorState:
    def test_default(self):
        s = DirectorState()
        assert s.global_tension == 0.3

    def test_round_trip(self):
        s = DirectorState(tick=5, arcs=[StoryArcState(arc_id="a1", title="Arc 1")])
        d = s.to_dict()
        s2 = DirectorState.from_dict(d)
        assert s2.to_dict() == d


class TestPhase14Tension:
    def test_attack_raises_tension(self):
        s = DirectorState(global_tension=0.3)
        TensionPacingController.update_tension(s, [{"type": "attack"}], 1)
        assert s.global_tension > 0.3

    def test_peace_lowers_tension(self):
        s = DirectorState(global_tension=0.7)
        TensionPacingController.update_tension(s, [{"type": "peace"}], 1)
        assert s.global_tension < 0.7

    def test_tension_band(self):
        assert TensionPacingController.get_tension_band(0.1) == "calm"
        assert TensionPacingController.get_tension_band(0.9) == "critical"


class TestPhase14ArcBeat:
    def test_advance_phase(self):
        arc = StoryArcState(phase="setup")
        ArcBeatTracker.advance_arc_phase(arc)
        assert arc.phase == "rising"

    def test_trigger_beat(self):
        arc = StoryArcState(beats=[StoryBeat(beat_id="b1", tension_delta=0.1)])
        ArcBeatTracker.trigger_beat(arc, "b1", 1)
        assert arc.beats[0].status == "completed"

    def test_get_pending(self):
        arc = StoryArcState(beats=[
            StoryBeat(beat_id="b1", status="completed"),
            StoryBeat(beat_id="b2", status="pending"),
        ])
        pending = ArcBeatTracker.get_pending_beats(arc)
        assert len(pending) == 1


class TestPhase14SceneBias:
    def test_compute_bias(self):
        s = DirectorState(global_tension=0.8, arcs=[
            StoryArcState(arc_id="a1", title="War", priority=0.9,
                          focus_entities=["hero"], status="active"),
        ])
        bias = SceneBiasEngine.compute_scene_bias(s)
        assert bias["preferred_mood"] == "tense"
        assert "hero" in bias["entity_focus"]


class TestPhase14Determinism:
    def test_validate_ok(self):
        s = DirectorState()
        assert DirectorDeterminismValidator.validate_bounds(s) == []

    def test_normalize(self):
        s = DirectorState(arcs=[StoryArcState(priority=float(i)/20) for i in range(15)])
        norm = DirectorDeterminismValidator.normalize_state(s)
        assert DirectorDeterminismValidator.validate_bounds(norm) == []


# ═══════════════════════════════════════════════════════════════════════════
# Phase 15 — Encounter / tactical mode
# ═══════════════════════════════════════════════════════════════════════════

from app.rpg.encounter.tactical_mode import (
    CombatEffect, TacticalParticipant, TacticalAction, EncounterTacticalState,
    InitiativeSystem, ActionResolver, EffectManager, NonCombatResolver,
    CompanionTacticalAI, EncounterPresenter, EncounterAnalytics,
    EncounterDeterminismValidator,
)


class TestPhase15EncounterState:
    def test_round_trip(self):
        s = EncounterTacticalState(encounter_id="e1", mode="combat",
                                    participants=[TacticalParticipant(entity_id="p1")])
        d = s.to_dict()
        s2 = EncounterTacticalState.from_dict(d)
        assert s2.to_dict() == d


class TestPhase15Initiative:
    def test_turn_order(self):
        participants = [
            TacticalParticipant(entity_id="slow", initiative=1.0),
            TacticalParticipant(entity_id="fast", initiative=5.0),
        ]
        order = InitiativeSystem.compute_turn_order(participants)
        assert order[0] == "fast"

    def test_advance_turn(self):
        s = EncounterTacticalState(turn_order=["a", "b"], turn_index=0)
        InitiativeSystem.advance_turn(s)
        assert s.turn_index == 1


class TestPhase15ActionResolver:
    def test_attack(self):
        s = EncounterTacticalState(participants=[
            TacticalParticipant(entity_id="a", name="Attacker"),
            TacticalParticipant(entity_id="b", name="Target", hp=50),
        ])
        action = TacticalAction(actor_id="a", action_type="attack", target_id="b", value=10)
        result = ActionResolver.resolve_action(action, s)
        assert result["success"]
        assert s.participants[1].hp == 40

    def test_heal(self):
        s = EncounterTacticalState(participants=[
            TacticalParticipant(entity_id="a", name="Healer"),
            TacticalParticipant(entity_id="b", name="Target", hp=50, max_hp=100),
        ])
        action = TacticalAction(actor_id="a", action_type="heal", target_id="b", value=20)
        result = ActionResolver.resolve_action(action, s)
        assert result["success"]
        assert s.participants[1].hp == 70

    def test_flee(self):
        s = EncounterTacticalState(participants=[
            TacticalParticipant(entity_id="a", name="Runner"),
        ])
        action = TacticalAction(actor_id="a", action_type="flee")
        ActionResolver.resolve_action(action, s)
        assert s.participants[0].status == "fled"


class TestPhase15Effects:
    def test_apply_effect(self):
        p = TacticalParticipant(entity_id="p1")
        eff = EffectManager.apply_effect(p, "damage", 5.0, duration=2)
        assert len(p.effects) == 1
        assert eff.remaining == 2

    def test_tick_effects(self):
        p = TacticalParticipant(entity_id="p1", hp=50)
        EffectManager.apply_effect(p, "damage", 5.0, duration=2)
        results = EffectManager.tick_effects(p)
        assert p.hp == 45
        assert len(p.effects) == 1  # remaining=1


class TestPhase15CompanionAI:
    def test_heal_wounded_ally(self):
        comp = TacticalParticipant(entity_id="comp1")
        ally = TacticalParticipant(entity_id="ally1", hp=10, max_hp=100)
        action = CompanionTacticalAI.choose_action(comp, [ally], [])
        assert action.action_type == "heal"

    def test_attack_enemy(self):
        comp = TacticalParticipant(entity_id="comp1")
        enemy = TacticalParticipant(entity_id="e1", hp=50)
        action = CompanionTacticalAI.choose_action(comp, [], [enemy])
        assert action.action_type == "attack"


class TestPhase15Determinism:
    def test_validate(self):
        s = EncounterTacticalState()
        assert EncounterDeterminismValidator.validate_bounds(s) == []

    def test_normalize(self):
        s = EncounterTacticalState(participants=[TacticalParticipant(hp=-5)])
        norm = EncounterDeterminismValidator.normalize_state(s)
        assert norm.participants[0].hp >= 0


# ═══════════════════════════════════════════════════════════════════════════
# Phase 16 — Inventory / equipment / economy expansion
# ═══════════════════════════════════════════════════════════════════════════

from app.rpg.items.economy import (
    ItemDefinition, InventoryItem, InventoryState, ShopState,
    EquipmentManager, ConsumableManager, LootGenerator, ShopManager,
    ItemEffectEngine, InventoryPresenter, InventoryMigrator,
    InventoryDeterminismValidator,
    MAX_INVENTORY_SLOTS, MAX_STACK, EQUIPMENT_SLOT_NAMES,
)


class TestPhase16Inventory:
    def test_round_trip(self):
        inv = InventoryState(owner_id="p1", items=[InventoryItem(item_id="sword", quantity=1)])
        d = inv.to_dict()
        inv2 = InventoryState.from_dict(d)
        assert inv2.to_dict() == d

    def test_add_item(self):
        inv = InventoryState()
        result = ConsumableManager.add_item(inv, "potion", 3)
        assert result["success"]
        assert result["total"] == 3

    def test_add_stacks(self):
        inv = InventoryState(items=[InventoryItem(item_id="potion", quantity=5)])
        ConsumableManager.add_item(inv, "potion", 3)
        assert inv.items[0].quantity == 8

    def test_use_consumable(self):
        inv = InventoryState(items=[InventoryItem(item_id="potion", quantity=2)])
        result = ConsumableManager.use_consumable(inv, "potion")
        assert result["success"]
        assert result["remaining"] == 1

    def test_inventory_full(self):
        inv = InventoryState(items=[InventoryItem(item_id=f"i{i}") for i in range(MAX_INVENTORY_SLOTS)])
        result = ConsumableManager.add_item(inv, "new_item")
        assert not result["success"]


class TestPhase16Equipment:
    def test_equip(self):
        inv = InventoryState()
        result = EquipmentManager.equip(inv, "sword", "main_hand")
        assert result["success"]
        assert inv.equipment["main_hand"] == "sword"

    def test_unequip(self):
        inv = InventoryState(equipment={"main_hand": "sword"})
        result = EquipmentManager.unequip(inv, "main_hand")
        assert result["success"]
        assert "main_hand" not in inv.equipment

    def test_invalid_slot(self):
        inv = InventoryState()
        result = EquipmentManager.equip(inv, "sword", "invalid_slot")
        assert not result["success"]


class TestPhase16Shop:
    def test_buy(self):
        inv = InventoryState(currency={"gold": 100})
        shop = ShopState(buy_modifier=1.0)
        result = ShopManager.buy_item(inv, shop, "potion", 10)
        assert result["success"]
        assert inv.currency["gold"] == 90

    def test_buy_insufficient_gold(self):
        inv = InventoryState(currency={"gold": 5})
        shop = ShopState(buy_modifier=1.0)
        result = ShopManager.buy_item(inv, shop, "potion", 10)
        assert not result["success"]

    def test_sell(self):
        inv = InventoryState(items=[InventoryItem(item_id="sword", quantity=1)],
                             currency={"gold": 50})
        shop = ShopState(sell_modifier=0.5)
        result = ShopManager.sell_item(inv, shop, "sword", 20)
        assert result["success"]
        assert inv.currency["gold"] == 60


class TestPhase16Loot:
    def test_generate_common(self):
        loot = LootGenerator.generate_loot("common_enemy")
        assert len(loot) > 0

    def test_generate_unknown_table(self):
        loot = LootGenerator.generate_loot("nonexistent")
        assert loot == []


class TestPhase16Determinism:
    def test_validate_ok(self):
        inv = InventoryState()
        assert InventoryDeterminismValidator.validate_bounds(inv) == []

    def test_normalize(self):
        inv = InventoryState(
            items=[InventoryItem(item_id=f"i{i}") for i in range(60)],
            equipment={"invalid_slot": "x"},
        )
        norm = InventoryDeterminismValidator.normalize_state(inv)
        assert InventoryDeterminismValidator.validate_bounds(norm) == []


# ═══════════════════════════════════════════════════════════════════════════
# Phase 17 — Travel / map / discovery expansion
# ═══════════════════════════════════════════════════════════════════════════

from app.rpg.travel.travel_system import (
    MapNode, MapRoute, RegionState, WorldMapState,
    MapManager, TravelResolver, DiscoverySystem, TravelEventGenerator,
    CompanionTravelBehavior, MapPresenter, TravelAnalytics,
    TravelDeterminismValidator,
)


class TestPhase17MapState:
    def test_round_trip(self):
        s = WorldMapState(current_node="start",
                          nodes=[MapNode(node_id="start", name="Start")])
        d = s.to_dict()
        s2 = WorldMapState.from_dict(d)
        assert s2.to_dict() == d


class TestPhase17Travel:
    def _make_state(self):
        return WorldMapState(
            current_node="a",
            nodes=[
                MapNode(node_id="a", name="Town A", discovered=True, region_id="r1"),
                MapNode(node_id="b", name="Town B", region_id="r1"),
            ],
            routes=[MapRoute(route_id="r_ab", from_node="a", to_node="b", distance=2.0)],
            regions=[RegionState(region_id="r1", name="Region 1")],
        )

    def test_travel_success(self):
        s = self._make_state()
        result = TravelResolver.attempt_travel(s, "b", 1)
        assert result["success"]
        assert s.current_node == "b"

    def test_travel_no_route(self):
        s = self._make_state()
        result = TravelResolver.attempt_travel(s, "c", 1)
        assert not result["success"]

    def test_travel_blocked(self):
        s = self._make_state()
        s.routes[0].blocked = True
        result = TravelResolver.attempt_travel(s, "b", 1)
        assert not result["success"]


class TestPhase17Discovery:
    def test_discover_node(self):
        s = WorldMapState(nodes=[MapNode(node_id="x", name="Hidden")])
        result = DiscoverySystem.discover_node(s, "x")
        assert result["success"]
        assert s.nodes[0].discovered

    def test_already_discovered(self):
        s = WorldMapState(nodes=[MapNode(node_id="x", discovered=True)])
        result = DiscoverySystem.discover_node(s, "x")
        assert result["already_discovered"]


class TestPhase17Determinism:
    def test_validate_ok(self):
        s = WorldMapState()
        assert TravelDeterminismValidator.validate_bounds(s) == []


# ═══════════════════════════════════════════════════════════════════════════
# Phase 18 — Quest / objective deepening
# ═══════════════════════════════════════════════════════════════════════════

from app.rpg.quest.quest_deepening import (
    QuestObjectiveV2, QuestBranch, QuestV2, QuestSystemState,
    ObjectiveGraph, QuestBranchManager, DynamicQuestGenerator,
    QuestRecoveryEngine, QuestDirectorIntegration, QuestPresenter,
    QuestAnalytics, QuestDeterminismValidator,
)


class TestPhase18QuestState:
    def test_round_trip(self):
        q = QuestV2(quest_id="q1", title="Test Quest",
                     objectives=[QuestObjectiveV2(objective_id="o1")])
        d = q.to_dict()
        q2 = QuestV2.from_dict(d)
        assert q2.to_dict() == d


class TestPhase18ObjectiveGraph:
    def test_available_objectives(self):
        q = QuestV2(objectives=[
            QuestObjectiveV2(objective_id="o1", status="completed"),
            QuestObjectiveV2(objective_id="o2", dependencies=["o1"]),
        ])
        available = ObjectiveGraph.get_available_objectives(q)
        assert len(available) == 1
        assert available[0].objective_id == "o2"

    def test_dependency_not_met(self):
        q = QuestV2(objectives=[
            QuestObjectiveV2(objective_id="o1", status="pending"),
            QuestObjectiveV2(objective_id="o2", dependencies=["o1"]),
        ])
        available = ObjectiveGraph.get_available_objectives(q)
        assert len(available) == 1  # Only o1 is available

    def test_complete_objective(self):
        q = QuestV2(objectives=[QuestObjectiveV2(objective_id="o1")])
        assert ObjectiveGraph.complete_objective(q, "o1")
        assert q.objectives[0].status == "completed"

    def test_quest_completable(self):
        q = QuestV2(objectives=[
            QuestObjectiveV2(objective_id="o1", status="completed"),
            QuestObjectiveV2(objective_id="o2", status="pending", optional=True),
        ])
        assert ObjectiveGraph.is_quest_completable(q)


class TestPhase18DynamicQuest:
    def test_generate_rescue(self):
        q = DynamicQuestGenerator.generate_quest("rescue", {"entity": "princess"}, 1)
        assert q is not None
        assert "Rescue" in q.title
        assert len(q.objectives) == 3

    def test_unknown_template(self):
        q = DynamicQuestGenerator.generate_quest("unknown", {}, 1)
        assert q is None


class TestPhase18Branch:
    def test_choose_branch(self):
        q = QuestV2(
            objectives=[QuestObjectiveV2(objective_id="o_stealth", status="pending")],
            branches=[QuestBranch(branch_id="b1", target_objectives=["o_stealth"])],
        )
        result = QuestBranchManager.choose_branch(q, "b1")
        assert result["success"]


class TestPhase18Recovery:
    def test_recovery(self):
        q = QuestV2(objectives=[QuestObjectiveV2(objective_id="o1", status="failed")])
        result = QuestRecoveryEngine.attempt_recovery(q, 5)
        assert result["success"]
        assert q.objectives[0].status == "skipped"


class TestPhase18Determinism:
    def test_validate_ok(self):
        s = QuestSystemState()
        assert QuestDeterminismValidator.validate_bounds(s) == []

    def test_normalize(self):
        s = QuestSystemState(active_quests=[QuestV2() for _ in range(25)])
        norm = QuestDeterminismValidator.normalize_state(s)
        assert QuestDeterminismValidator.validate_bounds(norm) == []


# ═══════════════════════════════════════════════════════════════════════════
# Phase 19 — Creator / GM tools
# ═══════════════════════════════════════════════════════════════════════════

from app.rpg.creator.gm_tools import (
    GMPermissions, GMState,
    WorldEditTools, ActorEditTools, QuestAuthoringTools,
    RuntimeOverrideTools, ScenarioTemplateManager, GMConsole,
    ContentPackager, GMDeterminismValidator,
)


class TestPhase19GMState:
    def test_round_trip(self):
        s = GMState(gm_id="gm1")
        d = s.to_dict()
        s2 = GMState.from_dict(d)
        assert s2.to_dict() == d


class TestPhase19EditTools:
    def test_edit_location(self):
        gm = GMState()
        result = WorldEditTools.edit_location(gm, "loc1", {"name": "New Name"}, 1)
        assert result["success"]
        assert len(gm.edit_history) == 1

    def test_edit_npc(self):
        gm = GMState()
        result = ActorEditTools.edit_npc(gm, "npc1", {"hp": 100}, 1)
        assert result["success"]

    def test_no_permission(self):
        gm = GMState(permissions=GMPermissions(can_edit_world=False))
        result = WorldEditTools.edit_location(gm, "loc1", {}, 1)
        assert not result["success"]


class TestPhase19Overrides:
    def test_add_override(self):
        gm = GMState()
        result = RuntimeOverrideTools.add_override(gm, {"type": "test"}, 1)
        assert result["success"]
        assert len(gm.active_overrides) == 1

    def test_clear_overrides(self):
        gm = GMState(active_overrides=[{"type": "test"}])
        result = RuntimeOverrideTools.clear_overrides(gm)
        assert result["cleared"] == 1


class TestPhase19Templates:
    def test_list_templates(self):
        templates = ScenarioTemplateManager.list_templates()
        assert len(templates) == 3

    def test_get_template(self):
        t = ScenarioTemplateManager.get_template("tutorial")
        assert t is not None
        assert t["name"] == "Tutorial"


class TestPhase19Export:
    def test_export_import(self):
        gm = GMState()
        result = ContentPackager.export_state(gm, {"world": "data"})
        assert result["success"]
        imported = ContentPackager.import_state(result["package"])
        assert imported["success"]


class TestPhase19Determinism:
    def test_validate(self):
        gm = GMState()
        assert GMDeterminismValidator.validate_bounds(gm) == []


# ═══════════════════════════════════════════════════════════════════════════
# Phase 20 — Save / migration / packaging
# ═══════════════════════════════════════════════════════════════════════════

from app.rpg.persistence.save_packaging import (
    SaveHeader, SaveSnapshot, SnapshotManager, SaveValidator,
    MigrationPipeline, ReplayConsistencyChecker, ScenarioPackager,
    CorruptionRecovery, SaveInspector, SaveDeterminismValidator,
    CURRENT_SAVE_VERSION,
)


class TestPhase20SaveState:
    def test_create_snapshot(self):
        snap = SnapshotManager.create_snapshot({"tick": 5}, {"social": {"edges": []}}, 5)
        assert snap.header.version == CURRENT_SAVE_VERSION
        assert snap.header.checksum != ""

    def test_round_trip(self):
        snap = SnapshotManager.create_snapshot({"tick": 1}, {}, 1)
        d = snap.to_dict()
        snap2 = SaveSnapshot.from_dict(d)
        assert snap2.to_dict() == d


class TestPhase20Validation:
    def test_validate_ok(self):
        snap = SnapshotManager.create_snapshot({"tick": 1}, {}, 1)
        errors = SaveValidator.validate_snapshot(snap)
        assert errors == []

    def test_validate_missing_id(self):
        snap = SaveSnapshot()
        errors = SaveValidator.validate_snapshot(snap)
        assert any("save_id" in e for e in errors)


class TestPhase20Migration:
    def test_migrate_v7(self):
        data = {"header": {"version": 7}, "game_state": {"tick": 1}, "subsystem_states": {}}
        result = MigrationPipeline.migrate(data)
        assert result["header"]["version"] == 8
        assert "travel" in result["subsystem_states"]

    def test_is_current(self):
        data = {"header": {"version": CURRENT_SAVE_VERSION}}
        assert MigrationPipeline.is_current(data)


class TestPhase20Corruption:
    def test_diagnose_healthy(self):
        snap = SnapshotManager.create_snapshot({"tick": 1}, {}, 1)
        result = CorruptionRecovery.diagnose(snap)
        assert result["healthy"]

    def test_repair(self):
        snap = SaveSnapshot()
        snap = CorruptionRecovery.attempt_repair(snap)
        assert snap.header.save_id != ""


class TestPhase20Determinism:
    def test_validate(self):
        snap = SnapshotManager.create_snapshot({"tick": 1}, {}, 1)
        assert SaveDeterminismValidator.validate_bounds(snap) == []


# ═══════════════════════════════════════════════════════════════════════════
# Phase 21 — Performance / scaling / orchestration polish
# ═══════════════════════════════════════════════════════════════════════════

from app.rpg.core.performance import (
    PerformanceMetric, PerformanceState, HotPathOptimizer,
    IncrementalBuilder, BatchProcessor, StreamingOptimizer,
    StateCompactor, ScalingRules, BenchmarkHarness,
    PerformanceDeterminismValidator, MAX_METRICS,
)


class TestPhase21Performance:
    def test_record_metric(self):
        s = PerformanceState()
        s.record("test", 5.0)
        assert len(s.metrics) == 1

    def test_max_metrics(self):
        s = PerformanceState()
        for i in range(1100):
            s.record(f"m{i}", float(i))
        assert len(s.metrics) <= MAX_METRICS


class TestPhase21HotPath:
    def test_identify(self):
        s = PerformanceState(metrics=[
            PerformanceMetric(name="slow", value=50.0),
            PerformanceMetric(name="fast", value=1.0),
        ])
        hot = HotPathOptimizer.identify_hot_paths(s, threshold_ms=10.0)
        assert len(hot) == 1
        assert hot[0]["name"] == "slow"


class TestPhase21Batch:
    def test_batch_events(self):
        events = [{"type": f"e{i}"} for i in range(120)]
        batches = BatchProcessor.batch_events(events, 50)
        assert len(batches) == 3

    def test_merge_redundant(self):
        events = [
            {"type": "attack", "target_id": "t1", "actor_id": "a1"},
            {"type": "attack", "target_id": "t1", "actor_id": "a1"},
        ]
        merged = BatchProcessor.merge_redundant_events(events)
        assert len(merged) == 1
        assert merged[0]["count"] == 2


class TestPhase21Scaling:
    def test_small_scale(self):
        assert ScalingRules.get_scale(10, 5) == "small"

    def test_large_scale(self):
        assert ScalingRules.get_scale(80, 50) == "large"


class TestPhase21Benchmark:
    def test_benchmark(self):
        result = BenchmarkHarness.benchmark(lambda: None, iterations=10)
        assert result["iterations"] == 10
        assert result["avg_ms"] >= 0


class TestPhase21Determinism:
    def test_validate(self):
        s = PerformanceState()
        assert PerformanceDeterminismValidator.validate_bounds(s) == []


# ═══════════════════════════════════════════════════════════════════════════
# Phase 22 — UX / presentation / production polish
# ═══════════════════════════════════════════════════════════════════════════

from app.rpg.ux.production_polish import (
    UXConfig, UXState, DialogueUXPolish, StreamingUXManager,
    EmotionPresenter, GameUIPresenter, AccessibilityManager,
    AudioIntegration, QAValidator, UXDeterminismValidator,
    MAX_DIALOGUE_HISTORY,
)


class TestPhase22UXState:
    def test_round_trip(self):
        s = UXState()
        d = s.to_dict()
        s2 = UXState.from_dict(d)
        assert s2.to_dict() == d


class TestPhase22Dialogue:
    def test_format_turn(self):
        turn = DialogueUXPolish.format_dialogue_turn("Alice", "Hello", "happy")
        assert turn["emotion"] == "happy"
        assert turn["display_class"] == "npc-turn"

    def test_player_turn(self):
        turn = DialogueUXPolish.format_dialogue_turn("Player", "Hi", is_player=True)
        assert turn["display_class"] == "player-turn"


class TestPhase22Streaming:
    def test_streaming_flow(self):
        p = StreamingUXManager.create_streaming_placeholder("NPC")
        assert p["streaming"]
        StreamingUXManager.update_streaming_text(p, "Hello ")
        StreamingUXManager.update_streaming_text(p, "world")
        assert p["text"] == "Hello world"
        StreamingUXManager.finalize_streaming(p)
        assert p["complete"]


class TestPhase22Emotion:
    def test_emotion_display(self):
        d = EmotionPresenter.get_emotion_display("happy")
        assert d["icon"] == "😊"


class TestPhase22Accessibility:
    def test_high_contrast(self):
        config = UXConfig(accessibility_mode="high_contrast")
        result = AccessibilityManager.apply_accessibility(config, {})
        assert result["css_override"] == "high-contrast-theme"


class TestPhase22QA:
    def test_validate_ok(self):
        s = UXState()
        assert QAValidator.validate_ux_state(s) == []

    def test_validate_exceeded(self):
        s = UXState(dialogue_history=[{} for _ in range(60)])
        issues = QAValidator.validate_ux_state(s)
        assert len(issues) > 0


class TestPhase22Determinism:
    def test_normalize(self):
        s = UXState(dialogue_history=[{} for _ in range(60)])
        norm = UXDeterminismValidator.normalize_state(s)
        assert len(norm.dialogue_history) <= MAX_DIALOGUE_HISTORY


# ═══════════════════════════════════════════════════════════════════════════
# Phase 23 — Emergent narrative endgame
# ═══════════════════════════════════════════════════════════════════════════

from app.rpg.narrative.emergent_endgame import (
    NarrativeCoherenceState, ThemeTracker, CallbackPayoffSystem,
    ArcSynthesizer, RelationshipEmergenceEngine, ConvergenceEngine,
    CliMaxOrchestrator, NarrativeAnalytics, NarrativeDeterminismValidator,
    MAX_THEMES, MAX_CALLBACKS,
)


class TestPhase23CoherenceState:
    def test_round_trip(self):
        s = NarrativeCoherenceState(tick=5, coherence_score=0.8)
        d = s.to_dict()
        s2 = NarrativeCoherenceState.from_dict(d)
        assert s2.to_dict() == d


class TestPhase23Themes:
    def test_register_theme(self):
        s = NarrativeCoherenceState()
        result = ThemeTracker.register_theme(s, "revenge", 1)
        assert result["new"]
        assert len(s.themes) == 1

    def test_increment_theme(self):
        s = NarrativeCoherenceState()
        ThemeTracker.register_theme(s, "revenge", 1)
        result = ThemeTracker.register_theme(s, "revenge", 2)
        assert not result["new"]
        assert result["occurrences"] == 2

    def test_register_motif(self):
        s = NarrativeCoherenceState()
        result = ThemeTracker.register_motif(s, "fire", "hero", 1)
        assert result["new"]


class TestPhase23Callbacks:
    def test_register_and_payoff(self):
        s = NarrativeCoherenceState()
        reg = CallbackPayoffSystem.register_callback(s, "The prophecy", ["hero"], 1)
        assert reg["success"]
        cb_id = reg["callback_id"]
        payoff = CallbackPayoffSystem.trigger_payoff(s, cb_id, 10, "Prophecy fulfilled")
        assert payoff["success"]
        assert len(s.payoffs) == 1

    def test_pending_callbacks(self):
        s = NarrativeCoherenceState()
        CallbackPayoffSystem.register_callback(s, "Setup", ["x"], 1)
        pending = CallbackPayoffSystem.get_pending_callbacks(s)
        assert len(pending) == 1


class TestPhase23ArcSynthesis:
    def test_synthesize(self):
        s = NarrativeCoherenceState(themes=[{"theme": "war", "occurrences": 3}])
        arcs = [
            {"focus_entities": ["hero", "villain"]},
            {"focus_entities": ["hero", "sage"]},
        ]
        result = ArcSynthesizer.synthesize_arcs(s, arcs, 10)
        assert result["success"]
        assert "hero" in result["synthesis"]["common_entities"]

    def test_insufficient_arcs(self):
        s = NarrativeCoherenceState()
        result = ArcSynthesizer.synthesize_arcs(s, [{"focus_entities": []}], 1)
        assert not result["success"]


class TestPhase23Emergence:
    def test_deep_bond(self):
        rels = [{"source_id": "a", "target_id": "b", "trust": 0.9, "hostility": 0.0}]
        result = RelationshipEmergenceEngine.detect_emergence(rels)
        assert any(e["type"] == "deep_bond" for e in result)

    def test_rivalry(self):
        rels = [{"source_id": "a", "target_id": "b", "trust": 0.0, "hostility": 0.9}]
        result = RelationshipEmergenceEngine.detect_emergence(rels)
        assert any(e["type"] == "rivalry" for e in result)


class TestPhase23Convergence:
    def test_compute(self):
        result = ConvergenceEngine.compute_convergence(
            {"global_tension": 0.7},
            {"avg_fear": 0.6},
            {"avg_priority": 0.8},
        )
        assert 0 <= result["alignment_score"] <= 1


class TestPhase23Climax:
    def test_readiness(self):
        s = NarrativeCoherenceState(
            callbacks=[{"paid_off": True}] * 8 + [{"paid_off": False}] * 2,
            coherence_score=0.9,
        )
        result = CliMaxOrchestrator.evaluate_climax_readiness(
            s, [{"id": "arc1"}], [{"id": "arc2"}] * 3,
        )
        assert 0 <= result["readiness"] <= 1


class TestPhase23Analytics:
    def test_coherence_report(self):
        s = NarrativeCoherenceState(
            themes=[{"theme": "x", "occurrences": 1}],
            callbacks=[{"paid_off": False}],
        )
        report = NarrativeAnalytics.get_coherence_report(s)
        assert report["theme_count"] == 1
        assert report["pending_callbacks"] == 1


class TestPhase23Determinism:
    def test_validate_ok(self):
        s = NarrativeCoherenceState()
        assert NarrativeDeterminismValidator.validate_bounds(s) == []

    def test_validate_exceeded(self):
        s = NarrativeCoherenceState(themes=[{} for _ in range(15)])
        violations = NarrativeDeterminismValidator.validate_bounds(s)
        assert len(violations) > 0

    def test_normalize(self):
        s = NarrativeCoherenceState(
            themes=[{"occurrences": i} for i in range(15)],
            callbacks=[{"paid_off": False}] * 40,
        )
        norm = NarrativeDeterminismValidator.normalize_state(s)
        assert NarrativeDeterminismValidator.validate_bounds(norm) == []
