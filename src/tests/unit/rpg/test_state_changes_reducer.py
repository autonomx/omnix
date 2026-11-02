"""StateChange and the reducer: a closed vocabulary, one mutation point, and the patch of its writes (RQ-1.2)."""
from __future__ import annotations

import gzip
import json
import random
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.apps.rpg.foundation.persistence.state_delta import apply_state_delta
from app.apps.rpg.foundation.state import CampaignStateView
from app.apps.rpg.foundation.state.changes import (
    CHANGE_TYPES,
    CombatantHpChanged,
    CombatEnded,
    CompanionJoined,
    CompanionLeft,
    ExperienceGained,
    HotbarChanged,
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
    TimeAdvanced,
    TurnCounted,
    parse_changes,
)
from app.apps.rpg.foundation.state.reducer import ChangeRejected, reduce
from app.apps.rpg.session.campaign_state import upcast_campaign_document

FIXTURES = Path(__file__).resolve().parents[2] / "rpg" / "fixtures" / "campaign_documents_v5"


def _document(shape: str = "aurelia") -> dict:
    return upcast_campaign_document(json.loads(gzip.decompress((FIXTURES / f"{shape}.json.gz").read_bytes())))


def test_the_vocabulary_is_closed_and_serializes() -> None:
    assert len(CHANGE_TYPES) == len(set(CHANGE_TYPES)) == 72
    changes = [PurseChanged(delta_copper=-30), ItemAdded(item_id="item:potion", name="Healing Potion")]
    assert parse_changes([change.model_dump() for change in changes]) == changes
    with pytest.raises(ValidationError):
        parse_changes([{"type": "gold_from_nowhere", "amount": 1000}])
    with pytest.raises(ValidationError):
        PurseChanged(delta_copper=1, extra="no")


def test_a_hotbar_slot_is_set_and_cleared_on_the_sheet_and_its_mirror() -> None:
    document = _document()
    after, _ = reduce(document, [HotbarChanged(slot="7", ability_id="survival_make_camp")])
    assert after["state"]["hotbar"]["7"] == "survival_make_camp" == after["state"]["ability_state"]["hotbar"]["7"]
    cleared, _ = reduce(after, [HotbarChanged(slot="7")])
    assert "7" not in cleared["state"]["hotbar"] and "7" not in cleared["state"]["ability_state"]["hotbar"]
    with pytest.raises(ValidationError):
        HotbarChanged(slot="11", ability_id="survival_make_camp")


def test_a_purchase_reduces_purse_and_pack_and_the_screen_shows_it() -> None:
    document = _document()
    before = deepcopy(document)
    after, patch = reduce(document, [
        PurseChanged(delta_copper=-30, reason="bought"),
        ItemAdded(item_id="item:healing-potion", name="Healing Potion", category="consumable"),
        ItemAdded(item_id="item:healing-potion", name="Healing Potion"),
    ])
    assert document == before  # the reducer works on a copy
    view = CampaignStateView(after)
    assert view.inventory.purse.total_copper == CampaignStateView(before).inventory.purse.total_copper - 30
    assert {item.name: item.quantity for item in view.inventory.items}["Healing Potion"] == 2
    sheet = {item["name"]: item["quantity"] for item in after["state"]["player"]["inventory"]}
    assert sheet["Healing Potion"] == 2 and after["state"]["player"]["currency"] == after[
        "simulation_state"]["player_state"]["currency"]
    assert apply_state_delta(before, patch) == after


def test_dropped_things_lie_where_they_fell() -> None:
    document = _document()
    after, _ = reduce(document, [ItemDropped(item_id="item:lantern-bread", quantity=1, location_id="location:a")])
    view = CampaignStateView(after)
    assert {item.name: item.quantity for item in view.inventory.items}["Lantern Bread"] == 1
    assert [(item.name, item.quantity) for item in view.inventory.ground["location:a"]] == [("Lantern Bread", 1)]
    with pytest.raises(ChangeRejected):
        reduce(after, [ItemPickedUp(item_id="item:lantern-bread", location_id="location:b")])
    back, _ = reduce(after, [ItemPickedUp(item_id="item:lantern-bread", location_id="location:a")])
    assert {item.name: item.quantity for item in CampaignStateView(back).inventory.items}["Lantern Bread"] == 2


@pytest.mark.parametrize("change", [
    PurseChanged(delta_copper=-10_000),
    ItemRemoved(item_id="item:dragon"),
    QuestStatusChanged(quest_id="quest:unknown", status="active"),
    CombatEnded(),
    CombatantHpChanged(actor_id="enemy:nobody", delta=-1),
    ItemEquipped(slot="main_hand", item_id="item:dragon"),
])
def test_a_change_the_document_cannot_take_is_rejected_whole(change) -> None:
    with pytest.raises(ChangeRejected):
        reduce(_document(), [change])


def _random_changes(rng: random.Random, document: dict) -> list:
    """A plausible turn's changes: each one valid against the state the ones before it leave."""
    changes, state = [], document
    quests = [quest.quest_id for quest in CampaignStateView(document).quests.quests]
    makers = [
        lambda: PurseChanged(delta_copper=rng.randint(0, 50)),
        lambda: ItemAdded(item_id=f"item:{rng.choice('abc')}", name=rng.choice(["Rope", "Apple", "Torch"]),
                          quantity=rng.randint(1, 3)),
        lambda: HpChanged(delta=rng.randint(-30, 30)),
        lambda: ExperienceGained(amount=rng.randint(0, 40)),
        lambda: SkillProgressed(skill_id=rng.choice(["swordsmanship", "archery"]), level=rng.randint(0, 3),
                                xp=rng.randint(0, 20), xp_to_next=25),
        lambda: LocationChanged(location_id=rng.choice(["location:a", "location:b"]), location_name="A"),
        lambda: PresenceChanged(location_id="location:a", present_npc_ids=tuple(rng.sample(["npc:x", "npc:y"], 1))),
        lambda: TimeAdvanced(ticks=rng.randint(0, 3)),
        lambda: TurnCounted(turn_count=rng.randint(1, 99)),
        lambda: NeedsChanged(hunger=rng.randint(-5, 5), thirst=rng.randint(-5, 5), fatigue=rng.randint(-5, 5)),
        lambda: QuestStatusChanged(quest_id=rng.choice(quests), status=rng.choice(["active", "completed"])),
        lambda: QuestPlaceReached(quest_id=rng.choice(quests), location_id=rng.choice(["location:a", "location:b"])),
        lambda: CompanionJoined(npc_id=f"npc:{rng.randint(0, 9)}", name="Ally"),
        lambda: CompanionLeft(npc_id=f"npc:{rng.randint(0, 9)}"),
        lambda: ItemUnequipped(slot="cloak"),
        lambda: ItemDropped(item_id="item:lantern-bread", quantity=1, location_id="location:a"),
        lambda: ItemPickedUp(item_id="item:lantern-bread", quantity=1, location_id="location:a"),
        lambda: ItemRemoved(item_id=f"item:{rng.choice('abc')}"),
    ]
    for _ in range(rng.randint(1, 12)):
        change = rng.choice(makers)()
        try:
            state, _ = reduce(state, [change])
        except ChangeRejected:
            continue
        changes.append(change)
    return changes


@pytest.mark.parametrize("shape", ["aurelia", "starter", "demo"])
def test_applying_the_changes_and_applying_their_patch_give_the_same_document(shape: str) -> None:
    """The property behind replay (§4.1): for any valid sequence of changes, reducing them and applying the
    patch the reducer emitted to the document before give the same document. Seeded, 150 sequences a shape."""
    document = _document(shape)
    rng = random.Random(f"rq-1.2:{shape}")
    for _ in range(150):
        changes = _random_changes(rng, document)
        after, patch = reduce(document, changes)
        assert apply_state_delta(document, patch) == after, changes
        replayed, again = reduce(document, parse_changes([change.model_dump() for change in changes]))
        assert replayed == after and again == patch  # deterministic, and the changes serialize losslessly


def _facts(document: dict) -> dict:
    view = CampaignStateView(document)
    return {
        "purse": view.inventory.purse.total_copper if view.inventory.purse else None,
        "pack": sorted((item.item_id or item.name, item.quantity) for item in view.inventory.items),
        "ground": {place: sorted((item.item_id or item.name, item.quantity) for item in stacks)
                   for place, stacks in view.inventory.ground.items() if stacks},
        "hp": view.player.hp, "xp": view.player.xp,
        "skills": {name: (skill.level, skill.xp) for name, skill in view.player.skills.items()},
        "location": view.location.location_id, "present": view.npcs.present_npc_ids,
        "party": [companion.npc_id for companion in view.party.companions],
        "quests": {quest.quest_id: (quest.status, quest.visited_locations) for quest in view.quests.quests},
        "needs": (view.survival.hunger, view.survival.thirst, view.survival.fatigue),
        "turns": view.time.turn_count, "tick": view.time.tick,
    }


@pytest.mark.parametrize("shape", ["aurelia", "starter"])
def test_the_changes_read_off_two_documents_reduce_to_the_second(shape: str) -> None:
    """What TurnOutcome reports (RQ-1.3): changes_between(before, after), reduced onto before, gives after's facts."""
    from app.apps.rpg.foundation.state.extract import changes_between

    document = _document(shape)
    rng = random.Random(f"rq-1.3:{shape}")
    for _ in range(100):
        after, _ = reduce(document, _random_changes(rng, document))
        extracted = changes_between(document, after)
        replayed, _ = reduce(document, extracted)
        assert _facts(replayed) == _facts(after), extracted
