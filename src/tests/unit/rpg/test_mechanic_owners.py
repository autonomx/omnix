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
    "equip": "app.apps.rpg.rules.interactions.items", "unequip": "app.apps.rpg.rules.interactions.items",
    "rest": "app.apps.rpg.rules.rest", "quest": "app.apps.rpg.rules.player.requests",
    "practice": "app.apps.rpg.rules.player.requests", "status": "app.apps.rpg.rules.player.requests",
    "party": "app.apps.rpg.rules.player.requests", "order": "app.apps.rpg.rules.player.requests",
    "talk": "app.apps.rpg.rules.dialogue.plan", "fight": "app.apps.rpg.rules.combat.fight",
    "ability": "app.apps.rpg.rules.ability_use", "check": "app.apps.rpg.rules.checks",
    "grow": "app.apps.rpg.rules.player.progression",
}
# The world tick's own rules (step 6): people's days.
TICK_OWNERS = ("app.apps.rpg.rules.routines",)

# The sections each change writes besides the play screen's sheet (its projection, ``state``).
CHANGE_WRITES = {
    **{kind: {CHANGE_SECTIONS[kind]} for kind in CHANGE_TYPES},
    "turn_counted": {"time"},  # the turn is counted on the campaign clock's section
    "presence_changed": {"npcs", "location"},  # who is present, and the scene of the place the hero is in
    "journal_written": {"narrative", "time"},  # the journal entry, and the calendar it is dated by
    "regard_changed": {"npcs"},
    "resources_changed": {"player"},
    "ability_used": {"player"},
    "check_resolved": {"player"},
    "level_choice_made": {"player"},
}


def _document() -> dict:
    return upcast_campaign_document(json.loads(gzip.decompress(FIXTURE.read_bytes())))


def _section(path: tuple[str, ...]) -> str:
    if path[0] == "state" and path[:2] not in {("state", "ability_state"), ("state", "world_binding")}:
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
        (c.AbilityUsed(ability_id="a:x", ready_at_turn=3), doc),
        (c.CheckResolved(kind="persuade", target_id=npc, natural=12, band="success"), doc),
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
    for module in {*MECHANIC_OWNERS.values(), *TICK_OWNERS}:
        importlib.import_module(module)
        local = module.removeprefix("app.apps.rpg.session.turn.")
        assert module in imported or (TURN_PACKAGE / f"{local}.py").exists(), f"the pipeline never uses {module}"


def test_every_change_has_an_example_here() -> None:
    assert sorted(change.type for change, _ in _examples(_document())) == sorted(CHANGE_TYPES)


@pytest.mark.parametrize("index", range(len(CHANGE_TYPES)))
def test_each_change_writes_only_the_sections_it_owns(index: int) -> None:
    change, base = _examples(_document())[index]
    written = _written(change, base)
    assert "(no section)" not in written, f"{change.type} writes a path no section owns"
    assert written <= CHANGE_WRITES[change.type], f"{change.type} writes {sorted(written - CHANGE_WRITES[change.type])}"


def test_each_section_has_the_writers_declared_and_no_others() -> None:
    writers: dict[str, set[str]] = {}
    for kind, sections in CHANGE_WRITES.items():
        for section in sections:
            writers.setdefault(section, set()).add(kind)
    assert set(writers) <= set(SECTION_PATHS)
    assert writers["location"] == {"location_changed", "presence_changed"}
    assert writers["combat"] == {"combat_started", "combatant_hp_changed", "combat_ended", "combat_advanced"}
