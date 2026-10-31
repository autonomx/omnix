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
    step: str = ""  # the quest step the line answers, as the reading proposed and the plan accepted (EV-3)


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


class HotbarChanged(_Change):
    """A hotbar slot set to one of the hero's abilities, or cleared (``ability_id`` empty): the play screen's."""

    type: Literal["hotbar_changed"] = "hotbar_changed"
    slot: str = Field(pattern=r"^([1-9]|10)$")
    ability_id: str = ""


class MapStateProjected(_Change):
    """The world map the play screen shows, projected from where the hero stands (``map_world_integration``): the
    sheet's map state, and its place on the sheet."""

    type: Literal["map_state_projected"] = "map_state_projected"
    map_state: dict[str, Any]
    location_id: str = Field(min_length=1)


class InteractionRecorded(_Change):
    """The turn's interaction on the campaign's timeline (its bookkeeping, roadmap §4.1 step 9): the event appended
    (the timeline keeps the last 50), the sequence and state revision it carries the campaign's, the recent
    interactions the last 12, and the event the last interaction."""

    type: Literal["interaction_recorded"] = "interaction_recorded"
    event: dict[str, Any]


class InteractionsReplayed(_Change):
    """Interactions the campaign's event log holds, merged into its timeline on load (one per interaction id, in
    sequence order, the last 50 kept); the sequence and revision never go back."""

    type: Literal["interactions_replayed"] = "interactions_replayed"
    events: list[dict[str, Any]]


class LifecycleRecorded(_Change):
    """An interaction's lifecycle (resolved, narrated): kept by its id (the last 64), its turn's interaction by the
    turn id, and the interaction's timeline event carrying it."""

    type: Literal["lifecycle_recorded"] = "lifecycle_recorded"
    interaction_id: str = Field(min_length=1)
    turn_id: str = ""
    lifecycle: dict[str, Any]


class InteractionPresented(_Change):
    """How a recent interaction is presented (the narrative engine's canonical projection): ``fields`` set on the
    recent interaction of ``turn_id`` or ``response_id``, else on the latest."""

    type: Literal["interaction_presented"] = "interaction_presented"
    turn_id: str = ""
    response_id: str = ""
    fields: dict[str, Any]


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


# A group's standing with the hero, in words: the band's lower bound, highest first (EV-1, question 2).
STANDING_BANDS = ((50, "trusted"), (20, "respected"), (-19, "neutral"), (-49, "wary"), (-100, "hostile"))


def standing_band(value: int) -> str:
    return next(band for floor, band in STANDING_BANDS if value >= floor)


# How the hero knows an entry, weakest first: a stronger kind replaces a weaker one, never the reverse (EV-1).
KNOWING_RANK = {"": 0, "heard_of": 1, "met": 2, "visited": 2}


class EntryMet(_Change):
    """An entry of the world the hero now knows (evolution roadmap EV-1): a person or creature met, a place
    visited, a thing held, a quest or group heard of. A stronger kind replaces a weaker one, never the reverse."""

    type: Literal["entry_met"] = "entry_met"
    entry_id: str = Field(min_length=1)
    kind: Literal["heard_of", "met", "visited"] = "met"
    source: str = ""


class FactSet(_Change):
    """A world fact's value (EV-1, ``rules/consequences.py``): what a decision, an ending or an outcome left
    behind. ``known``: the hero saw it happen."""

    type: Literal["fact_set"] = "fact_set"
    fact_id: str = Field(min_length=1)
    value: str | int | bool
    source: str = ""
    known: bool = True
    told: str = ""  # the author's line for it, which "What has changed" shows while the hero knows it


class FactLearned(_Change):
    """The hero comes to know a fact that holds, by seeing it or being told."""

    type: Literal["fact_learned"] = "fact_learned"
    fact_id: str = Field(min_length=1)
    source: str = ""


class StandingChanged(_Change):
    """A group's standing with the hero moved, from -100 to 100."""

    type: Literal["standing_changed"] = "standing_changed"
    group_id: str = Field(min_length=1)
    delta: int
    source: str = ""


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


class DirectionTracked(_Change):
    """The game master's bookkeeping (EV-0): the turn of the last meaningful event; and, for one of its own events,
    the day it is counted against (``day``) and the scene a complication was had in."""

    type: Literal["direction_tracked"] = "direction_tracked"
    last_event_turn: int = Field(ge=0)
    day: int | None = Field(default=None, ge=0)
    complication_scene: str = ""


class PreferenceNoted(_Change):
    """A wish of the player's for the story (EV-0's panel): its kind and value; the latest of a kind stands."""

    type: Literal["preference_noted"] = "preference_noted"
    kind: Literal["pace", "danger", "tone", "focus"]
    value: str = Field(min_length=1, max_length=120)


class BeatAdvanced(_Change):
    """A person takes the next step toward a goal (EV-4, ``rules/routines.py``): the beat reached, and, when it moves
    them, where they keep to now (``location_id`` empty and ``gone``: they have left)."""

    type: Literal["beat_advanced"] = "beat_advanced"
    person_id: str = Field(min_length=1)
    goal_id: str = Field(min_length=1)
    beat: str = Field(min_length=1)
    location_id: str = ""
    activity: str = ""
    gone: bool = False
    source: str = ""
    at_minute: int | None = Field(default=None, ge=0)  # when it happened (the day it was rolled for); else now


class RumourSpread(_Change):
    """Word the people of a place come to know and will tell (EV-4, ``rules/rumours.py``). ``text_id`` names its
    authored line (a beat's rumour); ``text`` holds one no author wrote (the game master's)."""

    type: Literal["rumour_spread"] = "rumour_spread"
    rumour_id: str = Field(min_length=1)
    place_id: str = Field(min_length=1)
    text_id: str = ""
    text: str = Field(default="", max_length=600)
    source: str = ""


class RumourHeard(_Change):
    """The hero is told a rumour (EV-4): by someone of its place, or for a price."""

    type: Literal["rumour_heard"] = "rumour_heard"
    rumour_id: str = Field(min_length=1)
    source: str = ""


class InventionAdded(_Change):
    """Something the game master invented, played from now on (evolution roadmap EV-0, part 2; ``rules/inventions.py``):
    a person, place, item, creature or quest, its lore ``row`` in the world model's shape and its ``play`` data, kept
    in the campaign's lore layer with its ``provenance`` (the campaign, the turn, the game master's reason)."""

    type: Literal["invention_added"] = "invention_added"
    entry_id: str = Field(min_length=1)
    family: Literal["person", "place", "item", "creature", "quest"]
    name: str = Field(min_length=1, max_length=120)
    row: dict[str, Any] = Field(default_factory=dict)
    play: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)


class ItemImproved(_Change):
    """A carried piece of gear improved by one tier (evolution roadmap EV-5, the trade rule's ``upgrade``): its tier
    and the numbers it fights with now."""

    type: Literal["item_improved"] = "item_improved"
    item_id: str = Field(min_length=1)
    tier: int = Field(ge=1, le=5)
    stats: dict[str, int] = Field(default_factory=dict)
    slot: str = ""  # where it is worn: written when the carried row had no block of its own (it fought as its kind)


class AreaDetailed(_Change):
    """An entry of a larger area filled in as the hero approaches it (evolution roadmap EV-10): its id (an invention
    beside it, ``InventionAdded``), its kind, and for a rumour or a piece of lore its line."""

    type: Literal["area_detailed"] = "area_detailed"
    area_id: str = Field(min_length=1)
    entry_id: str = Field(min_length=1)
    kind: Literal["place", "site", "person", "creature", "item", "service", "quest", "rumour", "lore"]
    told: str = Field(default="", max_length=600)


class SiteFound(_Change):
    """A hidden place found by exploring (EV-10, ``rules/exploration.py``): it joins the roads, and the hero can go."""

    type: Literal["site_found"] = "site_found"
    location_id: str = Field(min_length=1)
    told: str = ""


class RoomCleared(_Change):
    """A room of a site whose encounter is beaten or whose loot is taken (EV-10)."""

    type: Literal["room_cleared"] = "room_cleared"
    site_id: str = Field(min_length=1)
    room_id: str = Field(min_length=1)
    how: Literal["beaten", "looted", "passed"] = "beaten"  # passed: the room's hazard met


class PhaseEntered(_Change):
    """A boss's fight enters its next phase (EV-2): it fights harder, calls an ally, or lays its weakness bare."""

    type: Literal["phase_entered"] = "phase_entered"
    actor_id: str = Field(min_length=1)
    phase: int = Field(ge=1)
    told: str = ""


class GuardSet(_Change):
    """One of the party guards another (EV-2): the blows aimed at the one guarded fall on the guard."""

    type: Literal["guard_set"] = "guard_set"
    guard_id: str = Field(min_length=1)
    guarded_id: str = Field(min_length=1)


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


class LocalMapEntered(_Change):
    """The local map the hero now stands on (its instance, "" where the place has none): the play screen's grid."""

    type: Literal["local_map_entered"] = "local_map_entered"
    map_instance_id: str = ""


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
    | DefeatRecorded | CampaignEnded | WhereaboutsChanged | RegardChanged | ResourcesChanged | AbilityUsed | HotbarChanged
    | MapStateProjected | InteractionRecorded | InteractionsReplayed | LifecycleRecorded | InteractionPresented | CheckResolved | LevelChoiceMade
    | RevisionRestored | QuestStepCompleted | QuestProgressed | PressuresMoved | LocalMapEntered
    | EntryMet | FactSet | FactLearned | StandingChanged | PhaseEntered | GuardSet | DirectionTracked
    | PreferenceNoted | BeatAdvanced | RumourSpread | RumourHeard | InventionAdded | AreaDetailed | SiteFound
    | RoomCleared | ItemImproved,
    Field(discriminator="type"),
]
STATE_CHANGES: TypeAdapter[list[StateChange]] = TypeAdapter(list[StateChange])
CHANGE_TYPES: tuple[str, ...] = tuple(model.model_fields["type"].default for model in get_args(get_args(StateChange)[0]))


def parse_changes(values: Any) -> list[StateChange]:
    """Changes from their serialized form (``pydantic.ValidationError`` for an unknown type)."""
    return STATE_CHANGES.validate_python(values)
