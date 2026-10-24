"""The closed vocabulary of campaign state changes (RQ-1.2, roadmap §4.1).

A resolver decides what happens and says it as ``StateChange`` values; the reducer (``reducer.py``) is the only
code that applies them. Every change is a frozen model with a ``type`` tag, so a turn's changes serialize,
replay, and appear in ``TurnOutcome.applied_changes`` as they are. The vocabulary is closed: a mechanic that
needs a new kind of change adds it here, with its reduction, and nowhere else.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator


class _Change(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PurseChanged(_Change):
    """Coin gained (positive) or spent (negative), in copper."""

    type: Literal["purse_changed"] = "purse_changed"
    delta_copper: int
    reason: str = ""


class ItemAdded(_Change):
    """Stacks into the pack: onto the stack with the same item id, else a new stack."""

    type: Literal["item_added"] = "item_added"
    item_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    quantity: int = Field(default=1, ge=1)
    category: str = ""
    fields: dict[str, Any] = Field(default_factory=dict)


class ItemRemoved(_Change):
    """Taken from the pack's stack (used, sold, given); the stack goes when it is empty."""

    type: Literal["item_removed"] = "item_removed"
    item_id: str = Field(min_length=1)
    quantity: int = Field(default=1, ge=1)


class ItemDropped(_Change):
    """From the pack to the ground where the hero stands."""

    type: Literal["item_dropped"] = "item_dropped"
    item_id: str = Field(min_length=1)
    quantity: int = Field(default=1, ge=1)
    location_id: str = Field(min_length=1)


class ItemPickedUp(_Change):
    """From the ground back into the pack, onto its own stack."""

    type: Literal["item_picked_up"] = "item_picked_up"
    item_id: str = Field(min_length=1)
    quantity: int = Field(default=1, ge=1)
    location_id: str = Field(min_length=1)


class ItemEquipped(_Change):
    type: Literal["item_equipped"] = "item_equipped"
    slot: str = Field(min_length=1)
    item_id: str = Field(min_length=1)


class ItemUnequipped(_Change):
    type: Literal["item_unequipped"] = "item_unequipped"
    slot: str = Field(min_length=1)


class HpChanged(_Change):
    """The hero's health, kept between 0 and its maximum."""

    type: Literal["hp_changed"] = "hp_changed"
    delta: int


class ExperienceGained(_Change):
    type: Literal["experience_gained"] = "experience_gained"
    amount: int = Field(ge=0)


class SkillProgressed(_Change):
    """A skill's progress as the rules computed it (level-ups are the rules' decision, not the reducer's)."""

    type: Literal["skill_progressed"] = "skill_progressed"
    skill_id: str = Field(min_length=1)
    level: int = Field(ge=0)
    xp: int = Field(ge=0)
    xp_to_next: int = Field(ge=1)


class LocationChanged(_Change):
    type: Literal["location_changed"] = "location_changed"
    location_id: str = Field(min_length=1)
    location_name: str = ""


class PresenceChanged(_Change):
    """Who is present where the hero is."""

    type: Literal["presence_changed"] = "presence_changed"
    location_id: str = Field(min_length=1)
    present_npc_ids: tuple[str, ...] = ()


class PersonWhereabouts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    npc_id: str = Field(min_length=1)
    location_id: str = Field(min_length=1)
    activity: str = ""


class WhereaboutsChanged(_Change):
    """Where the world's people went as time passed, and what they are doing there (their routines, RQ-2.7)."""

    type: Literal["whereabouts_changed"] = "whereabouts_changed"
    people: tuple[PersonWhereabouts, ...] = Field(min_length=1)


class TimeAdvanced(_Change):
    """The turn's ticks of the campaign clock, and the in-game minutes they took (the world tick moves the clock)."""

    type: Literal["time_advanced"] = "time_advanced"
    ticks: int = Field(default=1, ge=0)
    minutes: int = Field(default=0, ge=0)


class TurnCounted(_Change):
    type: Literal["turn_counted"] = "turn_counted"
    turn_count: int = Field(ge=0)


class NeedsChanged(_Change):
    """Hunger, thirst and fatigue, each kept at zero or above."""

    type: Literal["needs_changed"] = "needs_changed"
    hunger: int = 0
    thirst: int = 0
    fatigue: int = 0


class QuestStatusChanged(_Change):
    type: Literal["quest_status_changed"] = "quest_status_changed"
    quest_id: str = Field(min_length=1)
    status: Literal["available", "active", "completed", "failed"]


class QuestPlaceReached(_Change):
    type: Literal["quest_place_reached"] = "quest_place_reached"
    quest_id: str = Field(min_length=1)
    location_id: str = Field(min_length=1)


class CompanionJoined(_Change):
    type: Literal["companion_joined"] = "companion_joined"
    npc_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    role: str = "companion"


class CompanionLeft(_Change):
    type: Literal["companion_left"] = "companion_left"
    npc_id: str = Field(min_length=1)


class CompanionOrdered(_Change):
    """A standing order a companion keeps until given another: keep watch, stay here, follow."""

    type: Literal["companion_ordered"] = "companion_ordered"
    npc_id: str = Field(min_length=1)
    order: str = Field(min_length=1)
    stance: str = ""


class DialogueExchanged(_Change):
    """What was said between the hero and someone, kept for the conversation's continuity; they are now the one the
    hero is talking to."""

    type: Literal["dialogue_exchanged"] = "dialogue_exchanged"
    npc_id: str = Field(min_length=1)
    name: str = ""
    player_line: str = ""
    npc_line: str = ""


class ResourcesChanged(_Change):
    """The hero's stamina and mana spent (an ability) or restored (a rest), within their pools."""

    type: Literal["resources_changed"] = "resources_changed"
    stamina: int = 0
    mana: int = 0
    reason: str = ""


class AbilityUsed(_Change):
    """An ability of the hero's used: ready again from ``ready_at_turn`` (its cooldown, in the hero's turns)."""

    type: Literal["ability_used"] = "ability_used"
    ability_id: str = Field(min_length=1)
    name: str = ""
    ready_at_turn: int = Field(ge=0)


class QuestStepCompleted(_Change):
    """A stage of a quest of steps done (quests.md): the quest now stands at ``stage``, the way it was done (the
    branch, when the stage had more than one), and what it asks next."""

    type: Literal["quest_step_completed"] = "quest_step_completed"
    quest_id: str = Field(min_length=1)
    stage: int = Field(ge=1)
    step_id: str = ""
    branch: int | None = None
    next_objective: str = ""


class QuestProgressed(_Change):
    """A quest's running tallies (the creatures of a "defeat" step felled so far)."""

    type: Literal["quest_progressed"] = "quest_progressed"
    quest_id: str = Field(min_length=1)
    counts: dict[str, int] = Field(default_factory=dict)


class RevisionRestored(_Change):
    """The game as it stood at an earlier revision, restored as a new revision (rewind.md): the sheet, the simulation
    and the game's runtime sections are the earlier document's; the campaign's bookkeeping (its revision, its
    interactions and narrations) goes on, so history is never rewritten."""

    type: Literal["revision_restored"] = "revision_restored"
    source_revision: int = Field(ge=0)
    document: dict[str, Any]


class LevelChoiceMade(_Change):
    """A level's choice made (progression.md): an attribute raised, an ability learned, or two skills a rank."""

    type: Literal["level_choice_made"] = "level_choice_made"
    choice: Literal["attribute", "ability", "skills"]
    attribute: str = ""
    value: int = 0
    ability_id: str = ""
    skills: tuple[str, ...] = ()


class CheckResolved(_Change):
    """A check outside a fight (checks.md): the roll against the difficulty, and its band."""

    type: Literal["check_resolved"] = "check_resolved"
    kind: str = Field(min_length=1)
    target_id: str = ""
    location_id: str = ""
    natural: int = Field(ge=1, le=20)
    bonus: int = 0
    total: int = 0
    difficulty: int = 0
    margin: int = 0
    band: Literal["strong", "success", "cost", "failure"]
    skill: str = ""
    minute: int = 0  # on the campaign clock: a haggle holds for its day (economy.md)


class RegardChanged(_Change):
    """How far someone trusts the hero moved (an attack, seen or suffered), from -100 to 100."""

    type: Literal["regard_changed"] = "regard_changed"
    npc_id: str = Field(min_length=1)
    name: str = ""
    delta: int
    reason: str = ""


class KnowledgeShared(_Change):
    """Something a person knows, now known to the hero."""

    type: Literal["knowledge_shared"] = "knowledge_shared"
    npc_id: str = Field(min_length=1)
    fact_id: str = Field(min_length=1)


class QuestOffered(_Change):
    """A quest put to the hero by someone; it names who offered it. A quest the log does not have yet (a side quest
    a pressure raised, quests.md) comes with its row."""

    type: Literal["quest_offered"] = "quest_offered"
    quest_id: str = Field(min_length=1)
    npc_id: str = Field(min_length=1)
    quest: dict[str, Any] = Field(default_factory=dict)


class CombatStarted(_Change):
    """A fight begins, with each participant's health."""

    type: Literal["combat_started"] = "combat_started"
    combat_id: str = ""
    participants: dict[str, int] = Field(default_factory=dict)


class CombatantHpChanged(_Change):
    type: Literal["combatant_hp_changed"] = "combatant_hp_changed"
    actor_id: str = Field(min_length=1)
    delta: int


class CombatEnded(_Change):
    type: Literal["combat_ended"] = "combat_ended"
    outcome: Literal["victory", "defeat", "fled", "ended"] = "ended"


class CombatAdvanced(_Change):
    """The fight as a turn of it leaves it: who stands at what health, the initiative order and whose turn it is,
    the round, and the log of blows. The combat section is the fight rule's own (``rules/combat/fight.py``)."""

    type: Literal["combat_advanced"] = "combat_advanced"
    combat_state: dict[str, Any] = Field(default_factory=dict)


class CompanionHpChanged(_Change):
    """A companion's health, as a fight leaves it."""

    type: Literal["companion_hp_changed"] = "companion_hp_changed"
    npc_id: str = Field(min_length=1)
    hp: int = Field(ge=0)


class LevelReached(_Change):
    """The hero rose a level (or several): where their progression now stands."""

    type: Literal["level_reached"] = "level_reached"
    level: int = Field(ge=1)
    xp: int = Field(ge=0)
    xp_to_next: int = Field(ge=1)
    unspent_points: int = Field(default=0, ge=0)
    unspent_skill_points: int = Field(default=0, ge=0)
    choices_pending: int = Field(default=0, ge=0)  # the levels' choices not yet made (progression.md)
    max_hp_gain: int = Field(default=0, ge=0)  # the health the levels add


class DefeatRecorded(_Change):
    """The hero lost a fight: how many they have lost."""

    type: Literal["defeat_recorded"] = "defeat_recorded"
    defeats: int = Field(ge=1)


class CampaignEnded(_Change):
    """The campaign is over (a hardcore hero fell)."""

    type: Literal["campaign_ended"] = "campaign_ended"
    reason: str = Field(min_length=1)
    defeated_by: tuple[str, ...] = ()


# What the world tick (pipeline step 6) owns: the causal runtime and the subsystems it projects onto, and its
# bookkeeping. The tick replaces these whole until RQ-2.7 says what it changes in typed terms.
WORLD_TICK_SECTIONS = frozenset({
    "causal_world_runtime", "causal_runtime_projection", "economy_state", "merchant_state", "travel_state",
    "faction_reputation", "npc_presence", "world_event_state", "environment",
})
WORLD_TICK_RUNTIME_KEYS = frozenset({
    "causal_applied_turn_keys", "causal_last_applied_turn_key", "causal_last_applied_tick",
})


class WorldTicked(_Change):
    """The world moved on: the sections the world tick owns, as it left them."""

    type: Literal["world_ticked"] = "world_ticked"
    simulation: dict[str, Any] = Field(default_factory=dict)
    runtime: dict[str, Any] = Field(default_factory=dict)
    # What the tick did, for a reader: the clock tick, the events it raised, the sections it replaced.
    summary: dict[str, Any] = Field(default_factory=dict)

    def reported(self) -> "WorldTicked":
        """As a turn outcome reports it: the summary, without the sections' contents (the turn's patch has them)."""
        return WorldTicked(summary={**self.summary, "sections": sorted(self.simulation)})

    @model_validator(mode="after")
    def _owned(self) -> "WorldTicked":
        stray = (set(self.simulation) - WORLD_TICK_SECTIONS) | (set(self.runtime) - WORLD_TICK_RUNTIME_KEYS)
        if stray:
            raise ValueError(f"the world tick does not own {sorted(stray)}")
        return self


class PressuresMoved(_Change):
    """What the hero did to the world's pressures (their levers, quests.md): each one's severity before and after, and
    the causal runtime as the pull left it (one replayable event, ``cause``)."""

    type: Literal["pressures_moved"] = "pressures_moved"
    moves: list[dict[str, Any]] = Field(default_factory=list)
    runtime: dict[str, Any] = Field(default_factory=dict)
    cause: str = ""

    def reported(self) -> "PressuresMoved":
        """As a turn outcome reports it: the moves, without the runtime (the turn's patch has it)."""
        return PressuresMoved(moves=self.moves, cause=self.cause)


class ServiceReserved(_Change):
    """A service paid for and kept for later: a room for the night."""

    type: Literal["service_reserved"] = "service_reserved"
    offer_id: str = Field(min_length=1)
    service_kind: str = Field(min_length=1)
    provider_id: str = ""
    provider_name: str = ""
    label: str = ""
    duration: str = ""


class StockTaken(_Change):
    """What an offer has left after a sale, and the campaign day of it (stock grows back from there)."""

    type: Literal["stock_taken"] = "stock_taken"
    offer_id: str = Field(min_length=1)
    remaining: int = Field(ge=0)
    day: int = Field(default=0, ge=0)


class TradeRemembered(_Change):
    """A trade in the campaign's ledger, which the trader's later dialogue can recall."""

    type: Literal["trade_remembered"] = "trade_remembered"
    provider_id: str = Field(min_length=1)
    provider_name: str = ""
    deal: Literal["bought", "sold"]
    what: str = ""
    copper: int = Field(default=0, ge=0)


class ConditionsChanged(_Change):
    """An actor's lingering conditions (battered, wounded), as the rule left them: the hero or a companion."""

    type: Literal["conditions_changed"] = "conditions_changed"
    actor_id: str = Field(min_length=1)
    conditions: tuple[dict[str, Any], ...] = ()


class RestTaken(_Change):
    """A full rest: where the hero last rested, and so where a beaten hero wakes."""

    type: Literal["rest_taken"] = "rest_taken"
    location_id: str = Field(min_length=1)


class ServiceUsed(_Change):
    """A service paid for and kept, used now: the room slept in."""

    type: Literal["service_used"] = "service_used"
    offer_id: str = Field(min_length=1)


class JournalWritten(_Change):
    """The turn in the player's journal and on the campaign calendar, as the journal keeper left them."""

    type: Literal["journal_written"] = "journal_written"
    calendar: dict[str, Any] = Field(default_factory=dict)
    journal: dict[str, Any] = Field(default_factory=dict)


StateChange = Annotated[
    PurseChanged | ItemAdded | ItemRemoved | ItemDropped | ItemPickedUp | ItemEquipped | ItemUnequipped
    | HpChanged | ExperienceGained | SkillProgressed | LocationChanged | PresenceChanged | TimeAdvanced
    | TurnCounted | NeedsChanged | QuestStatusChanged | QuestPlaceReached | CompanionJoined | CompanionLeft
    | CombatStarted | CombatantHpChanged | CombatEnded | WorldTicked | JournalWritten | ServiceReserved
    | StockTaken | TradeRemembered | ConditionsChanged | RestTaken | ServiceUsed | CompanionOrdered
    | DialogueExchanged | KnowledgeShared | QuestOffered | CombatAdvanced | CompanionHpChanged | LevelReached
    | DefeatRecorded | CampaignEnded | WhereaboutsChanged | RegardChanged | ResourcesChanged | AbilityUsed | CheckResolved | LevelChoiceMade
    | RevisionRestored | QuestStepCompleted | QuestProgressed | PressuresMoved,
    Field(discriminator="type"),
]
STATE_CHANGES: TypeAdapter[list[StateChange]] = TypeAdapter(list[StateChange])
CHANGE_TYPES: tuple[str, ...] = tuple(model.model_fields["type"].default for model in get_args(get_args(StateChange)[0]))


def parse_changes(values: Any) -> list[StateChange]:
    """Changes from their serialized form (``pydantic.ValidationError`` for an unknown type)."""
    return STATE_CHANGES.validate_python(values)
