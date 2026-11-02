"""A turn's changes, read off the documents before and after it (RQ-1.3).

Until each mechanic proposes its changes to the reducer (RQ-1.4, RQ-2), ``changes_between`` says what a turn
did in the closed vocabulary by comparing the typed sections of the committed document with the document the
turn started from, so ``TurnOutcome.applied_changes`` is real today. Reducing the extracted changes onto the
document before gives the facts of the document after (the test checks it); what the vocabulary does not cover
yet (lore, memory, the world's own bookkeeping) is not reported.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .changes import (
    CombatantHpChanged,
    CombatEnded,
    CombatStarted,
    CompanionJoined,
    CompanionLeft,
    ExperienceGained,
    HpChanged,
    ItemAdded,
    ItemDropped,
    ItemEquipped,
    ItemPickedUp,
    ItemRemoved,
    ItemUnequipped,
    LocationChanged,
    NeedsChanged,
    PresenceChanged,
    PurseChanged,
    QuestPlaceReached,
    QuestStatusChanged,
    SkillProgressed,
    StateChange,
    TimeAdvanced,
    TurnCounted,
)
from .sections import InventoryStack
from .view import CampaignStateView

_QUEST_STATUSES = {"available", "active", "completed", "failed"}


def _key(item: InventoryStack) -> str:
    return item.item_id or item.name


def _stacks(items: list[InventoryStack]) -> dict[str, tuple[InventoryStack, int]]:
    stacks: dict[str, tuple[InventoryStack, int]] = {}
    for item in items:
        held = stacks.get(_key(item))
        stacks[_key(item)] = (item, (held[1] if held else 0) + item.quantity)
    return stacks


def _item_changes(before: CampaignStateView, after: CampaignStateView) -> list[StateChange]:
    changes: list[StateChange] = []
    pack_before, pack_after = _stacks(before.inventory.items), _stacks(after.inventory.items)
    ground_delta: dict[tuple[str, str], int] = {}
    for place in set(before.inventory.ground) | set(after.inventory.ground):
        was = _stacks(before.inventory.ground.get(place, []))
        now = _stacks(after.inventory.ground.get(place, []))
        for key in set(was) | set(now):
            delta = (now.get(key, (None, 0))[1]) - (was.get(key, (None, 0))[1])
            if delta:
                ground_delta[(place, key)] = delta
    for key in sorted(set(pack_before) | set(pack_after)):
        item = (pack_after.get(key) or pack_before[key])[0]
        delta = pack_after.get(key, (item, 0))[1] - pack_before.get(key, (item, 0))[1]
        for (place, ground_key), moved in sorted(ground_delta.items()):
            if ground_key != key or not delta or (moved > 0) == (delta > 0):
                continue
            amount = min(abs(delta), abs(moved))
            change: StateChange = (ItemDropped(item_id=key, quantity=amount, location_id=place) if delta < 0
                                   else ItemPickedUp(item_id=key, quantity=amount, location_id=place))
            changes.append(change)
            delta += amount if delta < 0 else -amount
            ground_delta[(place, ground_key)] = moved - amount if moved > 0 else moved + amount
        if delta > 0:
            changes.append(ItemAdded(item_id=key, name=item.name or key, quantity=delta, category=item.category,
                                     fields=dict(item.extensions)))
        elif delta < 0:
            changes.append(ItemRemoved(item_id=key, quantity=-delta))
    for slot in sorted(set(before.inventory.equipment) | set(after.inventory.equipment)):
        worn = after.inventory.equipment.get(slot)
        if worn == before.inventory.equipment.get(slot):
            continue
        changes.append(ItemEquipped(slot=slot, item_id=str(worn)) if worn else ItemUnequipped(slot=slot))
    return changes


def _combat_changes(before: CampaignStateView, after: CampaignStateView) -> list[StateChange]:
    was, now = before.combat, after.combat
    if now.active and not was.active:
        return [CombatStarted(combat_id=now.combat_id,
                              participants={actor: row.hp for actor, row in sorted(now.participants.items())})]
    changes: list[StateChange] = []
    if was.active:
        for actor, row in sorted(now.participants.items()):
            previous = was.participants.get(actor)
            if previous is not None and row.hp != previous.hp:
                changes.append(CombatantHpChanged(actor_id=actor, delta=row.hp - previous.hp))
        if not now.active:
            enemies = [row for actor, row in now.participants.items() if actor.startswith("enemy:")]
            hero = now.participants.get("player")
            if enemies and all(row.hp <= 0 for row in enemies):
                outcome = "victory"
            elif hero is not None and hero.hp <= 0:
                outcome = "defeat"
            elif "fled" in str(now.extensions.get("outcome") or now.extensions.get("end_reason") or ""):
                outcome = "fled"
            else:
                outcome = "ended"
            changes.append(CombatEnded(outcome=outcome))  # type: ignore[arg-type]
    return changes


def changes_between(before_document: Mapping[str, Any], after_document: Mapping[str, Any]) -> list[StateChange]:
    """What a turn changed, in the closed vocabulary, from the document it began with and the one it committed."""
    before, after = CampaignStateView(before_document), CampaignStateView(after_document)
    changes: list[StateChange] = []
    if after.time.turn_count != before.time.turn_count:
        changes.append(TurnCounted(turn_count=after.time.turn_count))
    if after.time.tick > before.time.tick:
        changes.append(TimeAdvanced(ticks=after.time.tick - before.time.tick))
    if after.location.location_id and after.location.location_id != before.location.location_id:
        changes.append(LocationChanged(location_id=after.location.location_id,
                                       location_name=after.location.location_name))
    if after.npcs.present_npc_ids != before.npcs.present_npc_ids and after.location.location_id:
        changes.append(PresenceChanged(location_id=after.location.location_id,
                                       present_npc_ids=tuple(after.npcs.present_npc_ids)))
    purse_before = before.inventory.purse.total_copper if before.inventory.purse else 0
    purse_after = after.inventory.purse.total_copper if after.inventory.purse else 0
    if after.inventory.purse is not None and purse_after != purse_before:
        changes.append(PurseChanged(delta_copper=purse_after - purse_before))
    changes.extend(_item_changes(before, after))
    if after.player.hp is not None and before.player.hp is not None and after.player.hp != before.player.hp:
        changes.append(HpChanged(delta=after.player.hp - before.player.hp))
    if after.player.xp > before.player.xp:
        changes.append(ExperienceGained(amount=after.player.xp - before.player.xp))
    for skill_id, skill in sorted(after.player.skills.items()):
        previous = before.player.skills.get(skill_id)
        was = (previous.level, previous.xp) if previous is not None else (0, 0)  # a skill sheet appears untrained
        if was != (skill.level, skill.xp):
            changes.append(SkillProgressed(skill_id=skill_id, level=skill.level, xp=skill.xp,
                                           xp_to_next=max(1, skill.xp_to_next)))
    needs = {need: getattr(after.survival, need) - getattr(before.survival, need)
             for need in ("hunger", "thirst", "fatigue")}
    if any(needs.values()):
        changes.append(NeedsChanged(**needs))
    quests_before = {quest.quest_id: quest for quest in before.quests.quests}
    for quest in after.quests.quests:
        earlier = quests_before.get(quest.quest_id)
        if earlier is None:
            continue
        if quest.status != earlier.status and quest.status in _QUEST_STATUSES:
            changes.append(QuestStatusChanged(quest_id=quest.quest_id, status=quest.status))  # type: ignore[arg-type]
        for place in quest.visited_locations:
            if place not in earlier.visited_locations:
                changes.append(QuestPlaceReached(quest_id=quest.quest_id, location_id=place))
    party_before = {companion.npc_id for companion in before.party.companions}
    party_after = {companion.npc_id: companion for companion in after.party.companions}
    for npc_id, companion in party_after.items():
        if npc_id not in party_before:
            changes.append(CompanionJoined(npc_id=npc_id, name=companion.name or npc_id, role=companion.role or "companion"))
    for npc_id in sorted(party_before - set(party_after)):
        changes.append(CompanionLeft(npc_id=npc_id))
    changes.extend(_combat_changes(before, after))
    return changes


# The section each change type belongs to: what the play screen refreshes after a turn.
CHANGE_SECTIONS: dict[str, str] = {
    "purse_changed": "inventory", "item_added": "inventory", "item_removed": "inventory",
    "item_dropped": "inventory", "item_picked_up": "inventory", "item_equipped": "inventory",
    "item_unequipped": "inventory", "hp_changed": "player", "experience_gained": "player",
    "skill_progressed": "player", "location_changed": "location", "presence_changed": "npcs",
    "time_advanced": "time", "turn_counted": "time", "needs_changed": "survival",
    "quest_status_changed": "quests", "quest_place_reached": "quests", "companion_joined": "party",
    "companion_left": "party", "combat_started": "combat", "combatant_hp_changed": "combat", "combat_ended": "combat",
    "world_ticked": "world", "journal_written": "narrative", "service_reserved": "economy",
    "stock_taken": "economy", "trade_remembered": "economy", "conditions_changed": "player",
    "rest_taken": "player", "service_used": "economy", "companion_ordered": "party",
    "dialogue_exchanged": "npcs", "knowledge_shared": "npcs", "quest_offered": "quests",
    "combat_advanced": "combat", "companion_hp_changed": "party", "level_reached": "player",
    "defeat_recorded": "player", "campaign_ended": "meta", "whereabouts_changed": "npcs",
    "regard_changed": "npcs", "resources_changed": "player", "ability_used": "player", "hotbar_changed": "player", "interaction_recorded": "interactions", "interactions_replayed": "interactions",
    "lifecycle_recorded": "interactions", "interaction_presented": "interactions",
    "check_resolved": "player", "level_choice_made": "player", "revision_restored": "meta",
    "quest_step_completed": "quests", "quest_progressed": "quests", "pressures_moved": "world",
    "local_map_entered": "location", "map_state_projected": "location",
    "entry_met": "knowledge", "fact_set": "facts", "fact_learned": "facts", "standing_changed": "facts",
    "phase_entered": "combat", "guard_set": "combat", "direction_tracked": "direction", "preference_noted": "direction",
    "beat_advanced": "npcs", "rumour_spread": "world", "rumour_heard": "world", "invention_added": "world",
    "area_detailed": "world", "site_found": "world", "room_cleared": "world", "item_improved": "inventory",
}
