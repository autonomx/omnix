"""RQ-2.9 (roadmap §4.3): one owner per mechanic, and one writer per state section.

Each mechanic on the turn pipeline has one rule that owns it (``MECHANIC_OWNERS``). Every change of the closed
vocabulary writes only the document sections it is declared to (``CHANGE_WRITES``), as the sections themselves name
their paths (``SECTION_PATHS``); a change that writes another section, or a path no section owns, fails here, so a
second writer of a section has to be declared. Writes outside the reducer on the turn path are AL019's.
"""
from __future__ import annotations

import ast
import gzip
import importlib
import json
from pathlib import Path
from typing import get_args

import pytest

from app.apps.rpg.foundation.state import changes as c
from app.apps.rpg.foundation.state.changes import CHANGE_TYPES
from app.apps.rpg.foundation.state.extract import CHANGE_SECTIONS
from app.apps.rpg.foundation.state.reducer import reduce
from app.apps.rpg.foundation.state.sections import SECTION_PATHS
from app.apps.rpg.session.campaign_state import upcast_campaign_document
from app.apps.rpg.session.turn.planning import PipelineMechanic

FIXTURE = Path(__file__).resolve().parents[2] / "rpg" / "fixtures" / "campaign_documents_v5" / "aurelia.json.gz"
TURN_PACKAGE = Path(__file__).resolve().parents[3] / "app" / "apps" / "rpg" / "session" / "turn"

MECHANIC_OWNERS = {
    "look": "app.apps.rpg.session.turn.resolvers", "wait": "app.apps.rpg.session.turn.resolvers",
    "clarify": "app.apps.rpg.session.turn.resolvers", "travel": "app.apps.rpg.session.turn.travel",
    "trade": "app.apps.rpg.rules.economy.trade", "use_item": "app.apps.rpg.rules.interactions.items",
    "drop": "app.apps.rpg.rules.interactions.items", "take": "app.apps.rpg.rules.interactions.items",
    "give": "app.apps.rpg.rules.interactions.items",
    "equip": "app.apps.rpg.rules.interactions.items", "unequip": "app.apps.rpg.rules.interactions.items",
    "rest": "app.apps.rpg.rules.rest", "quest": "app.apps.rpg.rules.player.requests",
    "practice": "app.apps.rpg.rules.player.requests", "status": "app.apps.rpg.rules.player.requests",
    "party": "app.apps.rpg.rules.player.requests", "order": "app.apps.rpg.rules.player.requests",
    "talk": "app.apps.rpg.rules.dialogue.plan", "fight": "app.apps.rpg.rules.combat.fight",
    "ability": "app.apps.rpg.rules.ability_use", "hotbar": "app.apps.rpg.rules.ability_use",
    "check": "app.apps.rpg.rules.checks",
    "grow": "app.apps.rpg.rules.player.progression", "rewind": "app.apps.rpg.session.turn.rewind",
    "note_preference": "app.apps.rpg.rules.direction",  # a wish the game master's panel offered (EV-0)
    "explore": "app.apps.rpg.rules.exploration",  # a search for what is hidden (EV-10)
    "act": "app.apps.rpg.session.turn.resolution",  # a free action: no rule of the game decides it
}
# The world tick's own rules (step 6): people's days, and the beats of their goals (EV-4).
TICK_OWNERS = ("app.apps.rpg.rules.routines",)
# What a turn led to (step 5), judged after every turn: what the hero now knows (EV-1).
CONSEQUENCE_OWNERS = ("app.apps.rpg.rules.hero_knowledge", "app.apps.rpg.rules.direction",
                      "app.apps.rpg.rules.exploration")
# Each kind of proposal a turn folds in at its load (EV-11) and the rule that owns it.
FOLD_IN_OWNERS = {
    "heard_of": "app.apps.rpg.rules.hero_knowledge:heard_of",
    "gm_fact": "app.apps.rpg.rules.consequences:fold_fact",
    "gm_complication": "app.apps.rpg.rules.consequences:fold_complication",
    "gm_quest_offer": "app.apps.rpg.rules.quest.progress:fold_quest_offer",
    "gm_move_person": "app.apps.rpg.rules.routines:fold_move",
    "gm_encounter": "app.apps.rpg.rules.combat.encounters:fold_encounter",
    "gm_beat": "app.apps.rpg.rules.routines:fold_beat",
    "gm_rumour": "app.apps.rpg.rules.rumours:fold_rumour",
    "gm_invent": "app.apps.rpg.rules.inventions:fold_invention",
    "gm_area": "app.apps.rpg.rules.inventions:fold_area_entry",
}

# The sections each change writes besides the play screen's sheet (its projection, ``state``).
CHANGE_WRITES = {
    **{kind: {CHANGE_SECTIONS[kind]} for kind in CHANGE_TYPES},
    "turn_counted": {"time"},  # the turn is counted on the campaign clock's section
    "presence_changed": {"npcs", "location"},  # who is present, and the scene of the place the hero is in
    "journal_written": {"narrative", "time"},  # the journal entry, and the calendar it is dated by
    "regard_changed": {"npcs"},
    "resources_changed": {"player"},
    "ability_used": {"player"},
    "hotbar_changed": {"player"},
    "check_resolved": {"player"},
    "invention_added": {"world", "inventory"},  # an invented item may lie where the hero can pick it up (EV-0)
    "level_choice_made": {"player"},
    # a rewind puts back the game of an earlier revision: the sheet and the simulation whole (paths above any one
    # section), and every section in them
    "revision_restored": {"player", "inventory", "location", "time", "party", "combat", "quests", "survival", "npcs",
                          "world", "economy", "narrative", "knowledge", "facts", "direction", "meta", "(no section)"},
}


def _document() -> dict:
    return upcast_campaign_document(json.loads(gzip.decompress(FIXTURE.read_bytes())))


def _section(path: tuple[str, ...]) -> str:
    if path[0] == "state" and path[:2] not in {("state", "ability_state"), ("state", "world_binding"),
                                               ("state", "current_map_instance_id")}:
        return "(sheet)"
    owner, length = "(no section)", 0
    for name, paths in SECTION_PATHS.items():
        for prefix in paths:
            if path[: len(prefix)] == tuple(prefix) and len(prefix) > length:
                owner, length = name, len(prefix)
    return owner


def _examples(doc: dict) -> list:
    sim = doc["simulation_state"]
    here = sim["player_state"]["location_id"]
    npc = "npc:elyra-moonroot"
    joined, _ = reduce(doc, [c.CompanionJoined(npc_id=npc, name="Elyra")])
    dropped, _ = reduce(doc, [c.ItemDropped(item_id="item:lantern-bread", location_id=here)])
    reserved, _ = reduce(doc, [c.ServiceReserved(offer_id="offer:room", service_kind="lodging", label="A room")])
    combat = {"active": True, "participants": {"player": {"actor_id": "player", "side": "party", "hp": 10, "max_hp": 10},
                                               "enemy:a": {"actor_id": "enemy:a", "side": "enemy", "hp": 5, "max_hp": 5}}}
    fighting, _ = reduce(doc, [c.CombatAdvanced(combat_state=combat)])
    return [
        (c.PurseChanged(delta_copper=5), doc), (c.ItemAdded(item_id="item:x", name="X"), doc),
        (c.ItemRemoved(item_id="item:lantern-bread"), doc), (c.ItemDropped(item_id="item:lantern-bread", location_id=here), doc),
        (c.ItemPickedUp(item_id="item:lantern-bread", location_id=here), dropped),
        (c.ItemEquipped(slot="tool", item_id="item:gateborn-compass"), doc), (c.ItemUnequipped(slot="tool"),
         reduce(doc, [c.ItemEquipped(slot="tool", item_id="item:gateborn-compass")])[0]),
        (c.HpChanged(delta=-1), doc), (c.ExperienceGained(amount=5), doc),
        (c.SkillProgressed(skill_id="swordsmanship", level=1, xp=5, xp_to_next=100), doc),
        (c.LocationChanged(location_id="location:aurelia:starfall-village", location_name="Starfall Village"), doc),
        (c.PresenceChanged(location_id=here, present_npc_ids=(npc,)), doc), (c.TimeAdvanced(ticks=1, minutes=10), doc),
        (c.TurnCounted(turn_count=9), doc), (c.NeedsChanged(hunger=1), doc),
        (c.QuestStatusChanged(quest_id="quest:voices-in-the-phone", status="active"), doc),
        (c.QuestPlaceReached(quest_id="quest:first-night-in-aurelia", location_id="location:aurelia:starfall-village"), doc),
        (c.CompanionJoined(npc_id=npc, name="Elyra"), doc), (c.CompanionLeft(npc_id=npc), joined),
        (c.CombatStarted(combat_id="c:1", participants={"player": 10, "enemy:a": 5}), doc), (c.CombatantHpChanged(actor_id="enemy:a", delta=-1), fighting),
        (c.CombatEnded(), fighting), (c.WorldTicked(simulation={"environment": {"absolute_minutes": 600}}), doc),
        (c.JournalWritten(calendar={"day": 1}, journal={"entries": []}), doc), (c.ServiceReserved(offer_id="offer:room", service_kind="lodging"), doc),
        (c.StockTaken(offer_id="offer:bread", remaining=1), doc), (c.TradeRemembered(provider_id=npc, deal="bought"), doc),
        (c.ConditionsChanged(actor_id="player"), doc), (c.RestTaken(location_id=here), doc),
        (c.ServiceUsed(offer_id="offer:room"), reserved), (c.CompanionOrdered(npc_id=npc, order="keep watch"), joined),
        (c.DialogueExchanged(npc_id=npc), doc), (c.KnowledgeShared(npc_id=npc, fact_id="fact:x"), doc),
        (c.QuestOffered(quest_id="quest:voices-in-the-phone", npc_id=npc), doc), (c.CombatAdvanced(combat_state=combat), doc),
        (c.CompanionHpChanged(npc_id=npc, hp=3), joined), (c.LevelReached(level=2, xp=0, xp_to_next=200), doc),
        (c.DefeatRecorded(defeats=1), doc), (c.CampaignEnded(reason="hardcore"), doc),
        (c.WhereaboutsChanged(people=(c.PersonWhereabouts(npc_id=npc, location_id=here),)), doc),
        (c.RegardChanged(npc_id=npc, delta=-5), doc), (c.ResourcesChanged(stamina=-1), doc),
        (c.AbilityUsed(ability_id="a:x", ready_at_turn=3), doc), (c.HotbarChanged(slot="2", ability_id="a:x"), doc),
        (c.InteractionRecorded(event={"interaction_id": "interaction:900", "sequence": 900, "state_revision": 900}), doc),
        (c.LifecycleRecorded(interaction_id="interaction:900", turn_id="turn:900", lifecycle={"status": "runtime_resolved"}),
         doc),
        (c.InteractionPresented(fields={"narration": "Rain."}), doc),
        (c.InteractionsReplayed(events=[{"interaction_id": "interaction:901", "sequence": 901}]), doc),
        (c.MapStateProjected(map_state={"schema_version": 1, "current_map_id": "map:x"}, location_id=here), doc),
        (c.CheckResolved(kind="persuade", target_id=npc, natural=12, band="success"), doc),
        (c.RevisionRestored(source_revision=0, document=json.loads(json.dumps(doc))), joined),
        (c.QuestStepCompleted(quest_id="quest:voices-in-the-phone", stage=1, next_objective="Go on"), doc),
        (c.QuestProgressed(quest_id="quest:voices-in-the-phone", counts={"creature:echo-wolf": 1}), doc),
        (c.QuestOffered(quest_id="quest:pressure:roads:1", npc_id=npc, quest={"title": "Roads", "status": "available"}),
         doc),
        (c.PressuresMoved(moves=[], runtime={"pressure_plan": {}}), doc),
        (c.LocalMapEntered(map_instance_id="campaign:map:starfall-village:1"), doc),
        (c.EntryMet(entry_id="npc:elyra-moonroot", kind="heard_of"), doc),
        (c.FactSet(fact_id="fact:engine_fate", value="council", source="quest"), doc),
        (c.FactLearned(fact_id="fact:engine_fate"), reduce(doc, [c.FactSet(fact_id="fact:engine_fate", value="council",
                                                                          known=False)])[0]),
        (c.StandingChanged(group_id="faction:glass-synod", delta=-10), doc),
        (c.PhaseEntered(actor_id="enemy:a", phase=1, told="It splits."), fighting),
        (c.DirectionTracked(last_event_turn=4, day=1, complication_scene="loc:x"), doc),
        (c.PreferenceNoted(kind="danger", value="more"), doc),
        (c.GuardSet(guard_id="player", guarded_id="enemy:a"), fighting),
        (c.BeatAdvanced(person_id=npc, goal_id="goal:x", beat="b1", location_id=here), doc),
        (c.RumourSpread(rumour_id="r:1@x", place_id=here, text="Word goes about."), doc),
        (c.RumourHeard(rumour_id="r:1@x"), reduce(doc, [c.RumourSpread(rumour_id="r:1@x", place_id=here, text="W.")])[0]),
        (c.InventionAdded(entry_id="gm:c:blade", family="item", name="Blade", row={"id": "gm:c:blade", "name": "Blade"},
                          play={"location_id": here}), doc),
        (c.AreaDetailed(area_id="region:x", entry_id="lore:region:x:1", kind="lore", told="Old roads."), doc),
        (c.InventionAdded(entry_id="gm:c:hollow", family="place", name="Hollow", row={"name": "Hollow"},
                          play={"roads": [{"to": here}], "site": {"rooms": [{"id": "gm:c:hollow:room-1", "name": "Pit",
                                                                              "loot_item_id": "item:lantern-bread"}]}}),
         doc),
        (c.SiteFound(location_id="gm:c:cave"), reduce(doc, [c.InventionAdded(
            entry_id="gm:c:cave", family="place", name="Cave", row={"name": "Cave", "hidden": True},
            play={"roads": [{"to": here}]})])[0]),
        (c.RoomCleared(site_id="gm:c:cave", room_id="gm:c:cave:room-1"), doc),
        (c.ItemImproved(item_id="item:blade", tier=1, stats={"damage_max": 5}), reduce(doc, [c.ItemAdded(
            item_id="item:blade", name="Blade", fields={"equipment": {"slot": "main_hand", "stats": {"damage_max": 4}}})])[0]),
        (c.LevelChoiceMade(choice="attribute", attribute="strength", value=12),
         reduce(doc, [c.LevelReached(level=2, xp=0, xp_to_next=200, choices_pending=1)])[0]),
    ]




def _written(change, base: dict) -> set[str]:
    _, patch = reduce(base, [change])
    paths = {tuple(part.replace("~1", "/").replace("~0", "~") for part in op["path"].strip("/").split("/"))
             for op in patch}
    return {_section(path) for path in paths} - {"(sheet)"}


def test_every_pipeline_mechanic_has_one_owner_and_the_pipeline_uses_it() -> None:
    assert set(MECHANIC_OWNERS) == set(get_args(PipelineMechanic))
    imported: set[str] = set()
    for source in TURN_PACKAGE.glob("*.py"):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
                imported.update(f"{node.module}.{alias.name}" for alias in node.names)
    for module in {*MECHANIC_OWNERS.values(), *TICK_OWNERS, *CONSEQUENCE_OWNERS}:
        importlib.import_module(module)
        local = module.removeprefix("app.apps.rpg.session.turn.")
        assert module in imported or (TURN_PACKAGE / f"{local}.py").exists(), f"the pipeline never uses {module}"


def test_every_change_has_an_example_here() -> None:
    assert sorted({change.type for change, _ in _examples(_document())}) == sorted(CHANGE_TYPES)  # some have two


EXAMPLES = len(_examples(_document()))  # some changes have two (every one is checked)


@pytest.mark.parametrize("index", range(EXAMPLES))
def test_each_change_writes_only_the_sections_it_owns(index: int) -> None:
    change, base = _examples(_document())[index]
    written = _written(change, base)
    assert "(no section)" not in written or "(no section)" in CHANGE_WRITES[change.type], (
        f"{change.type} writes a path no section owns")
    assert written <= CHANGE_WRITES[change.type], f"{change.type} writes {sorted(written - CHANGE_WRITES[change.type])}"


def test_each_section_has_the_writers_declared_and_no_others() -> None:
    writers: dict[str, set[str]] = {}
    for kind, sections in CHANGE_WRITES.items():
        for section in sections:
            writers.setdefault(section, set()).add(kind)
    assert set(writers) - {"(no section)"} <= set(SECTION_PATHS)
    assert writers["location"] == {"location_changed", "presence_changed", "revision_restored", "local_map_entered",
                                   "map_state_projected"}
    assert writers["combat"] == {"combat_started", "combatant_hp_changed", "combat_ended", "combat_advanced",
                                 "phase_entered", "guard_set", "revision_restored"}


def test_every_proposal_kind_has_one_owning_rule() -> None:
    from app.apps.rpg.session.turn import proposals

    assert proposals.FOLD_IN_OWNERS == FOLD_IN_OWNERS
    for named in FOLD_IN_OWNERS.values():
        module, function = named.split(":")
        assert module.startswith("app.apps.rpg.rules."), f"{named}: a proposal is folded in by a rule"
        assert callable(getattr(importlib.import_module(module), function))
