"""Consequences: facts the world remembers, and what they change (evolution roadmap EV-1). Pure.

A decision leaves facts behind. A quest way's ``sets`` (``[{"fact": id, "value": v}]``, beside its ``told``) is
written when the way is taken, and a quest's own ``sets`` when it is completed (an ending): ``FactSet``, known to the
hero, who saw it happen. Each fact may carry the author's line for it ("The engine is the guilds' now"), which the
journal's "What has changed" shows while the fact holds and the hero knows it.

The world's ``fact_effects`` play section says what a fact changes. Each entry is a condition on facts (``when``:
``{fact id: value}``, all of which must hold; empty, it always holds) and one effect, read by the rule that owns that
mechanic:

- ``price``: ``{"provider" | "region": id, "percent": n}``, a seller's or a region's prices moved
  (``rules/economy/trade.py``, ``price_factor``);
- ``waive``: ``{"provider": id, "offer": key}``, an offer given free once (a new arrival's first night), while the
  condition holds (``waived``);
- ``closes``: ``{"provider": id}``, a seller who no longer trades (``trade.sellers_here``);
- ``place``: ``{"location": id, "line": text}``, a line added to a place's description (``place_lines``);
- ``whereabouts``: ``{"npc": id, "location": id, "activity": text}``, a person's day replaced: they keep to one place,
  or, with no place, they are gone (``rules/routines.py``, ``moved_people``);
- ``standing``: ``{"group": id, "delta": n}``, a group's standing with the hero moved, once, when the condition comes
  to hold (``StandingChanged``; a change of band is told);
- ``quest``: ``{"opens" | "closes": id}``, a quest offered to the hero or closed to them, once, when the condition comes
  to hold; a quest's own ``requires`` and ``forbids`` facts gate its offer too (``quest_open``).

Group standing is shown in words, by band (``standing_band``); a group's members (``group_members``, the play
section, or ``members`` on the group) answer for it in conversation.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state import access as _sections
from app.apps.rpg.foundation.state.changes import (
    FactSet,
    QuestOffered,
    QuestStatusChanged,
    QuestStepCompleted,
    ServiceReserved,
    STANDING_BANDS,
    StandingChanged,
    StateChange,
    standing_band,
    StockTaken,
)

if TYPE_CHECKING:
    from app.apps.rpg.foundation.state.proposals import Folded

BANDS = STANDING_BANDS


def world_facts(simulation: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(fact): _d(row) for fact, row in _d(_sections.world_facts_of(simulation)).items()}


def fact_value(simulation: Mapping[str, Any], fact_id: str) -> Any:
    return world_facts(simulation).get(fact_id, {}).get("value")


def _holds(when: Mapping[str, Any], facts: Mapping[str, Mapping[str, Any]]) -> bool:
    return all(fact in facts and facts[fact].get("value") == value for fact, value in when.items())


def fact_effects(simulation: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The world's ``fact_effects`` (its play section, kept in the world model)."""
    return [_d(row) for row in _l(_d(_sections.world_model_of(simulation)).get("fact_effects")) if isinstance(row, Mapping)]


def holding(simulation: Mapping[str, Any], effect: str) -> list[dict[str, Any]]:
    """The ``effect`` of every entry whose condition holds now."""
    facts = world_facts(simulation)
    return [_d(row.get(effect)) for row in fact_effects(simulation)
            if isinstance(row.get(effect), Mapping) and _holds(_d(row.get("when")), facts)]


# -- read by the rules that own each mechanic ------------------------------------------------------------------

def price_factor(simulation: Mapping[str, Any], provider_id: str, location_id: str) -> tuple[float, list[str]]:
    """How the world's facts move a seller's prices: the factor and why (trade's price)."""
    region = _s(_d(_d(_d(_sections.world_model_of(simulation)).get("locations")).get(location_id)).get("region_id"))
    factor, why = 1.0, []
    for effect in holding(simulation, "price"):
        if provider_id and _s(effect.get("provider")) == provider_id or region and _s(effect.get("region")) == region:
            percent = int(effect.get("percent") or 0)
            factor *= max(0.0, 1 + percent / 100)
            if _s(effect.get("why")):
                why.append(_s(effect.get("why")))
    return factor, why


def _waiver_fact(provider_id: str, offer_key: str) -> str:
    return f"waived:{provider_id}:{offer_key}"


def waived(simulation: Mapping[str, Any], provider_id: str, offer_key: str) -> str:
    """Why the offer is free this once ("" when it is not): a waiver that holds and has not been used."""
    if fact_value(simulation, _waiver_fact(provider_id, offer_key)) is True:
        return ""
    return next((_s(effect.get("why")) or "it is on the house"
                 for effect in holding(simulation, "waive")
                 if _s(effect.get("provider")) == provider_id and _s(effect.get("offer")) == offer_key), "")


def closed_providers(simulation: Mapping[str, Any]) -> set[str]:
    return {_s(effect.get("provider")) for effect in holding(simulation, "closes") if _s(effect.get("provider"))}


def moved_people(simulation: Mapping[str, Any]) -> dict[str, tuple[str, str]]:
    """The people whose day the world's facts replaced: where they keep to now, and doing what ("" place: gone)."""
    return {_s(effect.get("npc")): (_s(effect.get("location")), _s(effect.get("activity")))
            for effect in holding(simulation, "whereabouts") if _s(effect.get("npc"))}


def place_lines(simulation: Mapping[str, Any], location_id: str) -> list[str]:
    """What the world's facts add to a place's description."""
    return [_s(effect.get("line")) for effect in holding(simulation, "place")
            if _s(effect.get("location")) == location_id and _s(effect.get("line"))]


def quest_open(simulation: Mapping[str, Any], quest: Mapping[str, Any]) -> bool:
    """Whether a quest may be offered: its ``requires`` facts hold, its ``forbids`` do not, and no effect closed it."""
    facts = world_facts(simulation)
    quest_id = _s(quest.get("quest_id") or quest.get("id"))
    if quest_id in {_s(effect.get("closes")) for effect in holding(simulation, "quest")}:
        return False
    requires, forbids = _d(quest.get("requires")), _d(quest.get("forbids"))
    return _holds(requires, facts) and not (forbids and _holds(forbids, facts))


def group_members(simulation: Mapping[str, Any]) -> dict[str, str]:
    """Each person who answers for a group, by their id: the play section's, else a group's own ``members``, else the
    group a person's own lore names (``group_id``)."""
    world = _d(_sections.world_model_of(simulation))
    own = {str(npc_id): _s(_d(row).get("group_id")) for npc_id, row in _d(world.get("npcs")).items()
           if _s(_d(row).get("group_id"))}
    members: dict[str, str] = {}
    for group_id, row in _d(world.get("groups")).items():
        for npc_id in _l(_d(row).get("members")):
            members.setdefault(_s(npc_id), str(group_id))
    members = {**own, **members}  # a group's own members over a person's lore
    for row in _l(world.get("group_members")):
        for npc_id in _l(_d(row).get("members")):
            members[_s(npc_id)] = _s(_d(row).get("group_id"))
    return members


def standing_with(simulation: Mapping[str, Any], npc_id: str) -> tuple[str, int] | None:
    """The group a person answers for and its standing with the hero; None when they answer for none."""
    group = group_members(simulation).get(npc_id)
    if not group:
        return None
    return group, int(_d(_sections.group_standing_of(simulation)).get(group) or 0)


# -- what a turn led to ----------------------------------------------------------------------------------------

def _logged(simulation: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {_s(_d(row).get("quest_id") or _d(row).get("id")): _d(row)
            for row in _l(_d(_sections.quest_state_of(simulation)).get("quests"))}


def _quest_rows(simulation: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """The world's quests, as the log holds them where it does."""
    world = {str(quest_id): _d(row) for quest_id, row in _d(_d(_sections.world_model_of(simulation)).get("quests")).items()}
    return {**world, **_logged(simulation)}


def _sets_of_way(quest: Mapping[str, Any], step_id: str, branch: int | None) -> list[dict[str, Any]]:
    step = next((_d(row) for row in _l(quest.get("steps")) if _s(_d(row).get("id")) == step_id), {})
    ways = _l(step.get("any_of"))
    way = _d(ways[branch]) if ways and branch is not None and branch < len(ways) else step
    return [_d(row) for row in _l(way.get("sets")) if _s(_d(row).get("fact"))]


def facts_written(simulation: Mapping[str, Any], applied: Sequence[StateChange]) -> list[FactSet]:
    """The facts the turn's quest steps and endings write."""
    quests = _quest_rows(simulation)
    written: list[FactSet] = []
    for change in applied:
        if isinstance(change, QuestStepCompleted):
            rows = _sets_of_way(quests.get(change.quest_id, {}), change.step_id, change.branch)
            source = f"{change.quest_id}:{change.step_id}"
        elif isinstance(change, QuestStatusChanged) and change.status == "completed":
            rows = [_d(row) for row in _l(quests.get(change.quest_id, {}).get("sets")) if _s(_d(row).get("fact"))]
            source = change.quest_id
        else:
            continue
        written += [FactSet(fact_id=_s(row["fact"]), value=row.get("value", True), source=source,
                            told=_s(row.get("told"))) for row in rows]
    return written


def _used_waivers(simulation: Mapping[str, Any], applied: Sequence[StateChange]) -> list[FactSet]:
    """A waiver taken up this turn is used: its fact is written, so it is not given again."""
    offers = {_s(_d(offer).get("offer_id")): (str(provider), _d(offer))
              for provider, rows in _d(_d(_sections.world_model_of(simulation)).get("offers")).items()
              for offer in _l(rows)}
    used: list[FactSet] = []
    for change in applied:
        if isinstance(change, (ServiceReserved, StockTaken)) and change.offer_id in offers:
            provider, offer = offers[change.offer_id]
            key = _s(offer.get("offer_key")) or change.offer_id.rsplit(":", 1)[-1]
            if waived(simulation, provider, key) and all(fact.fact_id != _waiver_fact(provider, key) for fact in used):
                used.append(FactSet(fact_id=_waiver_fact(provider, key), value=True, source="waiver"))
    return used


def consequences(simulation: Mapping[str, Any], applied: Sequence[StateChange],
                 *, groups: Mapping[str, Any] | None = None) -> tuple[list[StateChange], list[str]]:
    """What the turn's facts led to: the facts written, the one-time effects of the conditions that came to hold, and
    how to say it (an effect's line, a change of band)."""
    written: list[StateChange] = [*facts_written(simulation, applied), *_used_waivers(simulation, applied)]
    # Facts the turn already wrote (a beat a person reached, a proposal folded in) are in the simulation: their
    # effects fire as the quests' do, though their lines were told where they were written.
    earlier = {change.fact_id for change in applied if isinstance(change, FactSet)}
    if not written and not earlier:
        return [], []
    now = world_facts(simulation)
    before = {fact: row for fact, row in now.items() if fact not in earlier}
    after = {**now, **{change.fact_id: {"value": change.value} for change in written if isinstance(change, FactSet)}}
    changes: list[StateChange] = list(written)
    lines = [change.told for change in written if isinstance(change, FactSet) and change.told]
    standing = {str(group): int(value) for group, value in _d(_sections.group_standing_of(simulation)).items()}
    names = {str(group): _s(_d(row).get("name")) or str(group)
             for group, row in _d(groups if groups is not None else _d(_sections.world_model_of(simulation)).get("groups")).items()}
    quests, logged = _quest_rows(simulation), _logged(simulation)
    for row in fact_effects(simulation):
        when = _d(row.get("when"))
        if not when or _holds(when, before) or not _holds(when, after):
            continue  # one-time effects fire when their condition comes to hold
        if isinstance(row.get("standing"), Mapping):
            effect = _d(row["standing"])
            group, delta = _s(effect.get("group")), int(effect.get("delta") or 0)
            if group and delta:
                was = standing.get(group, 0)
                standing[group] = max(-100, min(100, was + delta))
                changes.append(StandingChanged(group_id=group, delta=delta, source=",".join(sorted(when))))
                if standing_band(standing[group]) != standing_band(was):
                    lines.append(f"{names.get(group, group)} now regards you as {standing_band(standing[group])}.")
        if isinstance(row.get("quest"), Mapping):
            effect = _d(row["quest"])
            opens, closes = _s(effect.get("opens")), _s(effect.get("closes"))
            if opens in quests and _s(quests[opens].get("status") or "available") == "available":
                quest = quests[opens]
                giver = _s(quest.get("giver_id") or quest.get("offered_by")) or "world"
                changes.append(QuestOffered(quest_id=opens, npc_id=giver, quest={**quest, "status": "available"}))
                lines.append(f"A new quest is open to you: {_s(quest.get('title')) or opens}.")
            # One the log holds is failed; one it does not is never offered (``quest_open``).
            if closes in logged and _s(logged[closes].get("status")) in {"available", "active"}:
                changes.append(QuestStatusChanged(quest_id=closes, status="failed"))
                lines.append(f"{_s(logged[closes].get('title')) or closes} is closed to you now.")
        if _s(row.get("told")):
            lines.append(_s(row.get("told")))
    return changes, lines


def _fact_keys(value: Any) -> Iterable[str]:
    """Every fact a quest's or an effect's structure names: a ``fact`` written, a ``requires``/``forbids``/``when``
    condition's keys."""
    if isinstance(value, Mapping):
        if isinstance(value.get("fact"), str):
            yield value["fact"]
        for key in ("requires", "forbids", "when"):
            if isinstance(value.get(key), Mapping):
                yield from (str(fact) for fact in value[key])
        for item in value.values():
            yield from _fact_keys(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _fact_keys(item)


def authored_outcome(simulation: Mapping[str, Any], fact_id: str) -> bool:
    """Whether ``fact_id`` is one the world's author ties to the hero's deeds: written by a quest's way or ending,
    or read by a quest's offer or a fact effect. The game master never sets one (EV-0's bounds)."""
    world = _d(_sections.world_model_of(simulation))
    return fact_id in set(_fact_keys([_d(world.get("quests")), _l(world.get("fact_effects"))]))


def fold_fact(document: Mapping[str, Any], payload: Mapping[str, Any]) -> "Folded":
    """A fact the game master proposes (EV-0), or a consequence brought forward: folded in when its id is a fact's,
    it contradicts no fact that holds (by id and value), and its line names no secret; within the day's limit."""
    from app.apps.rpg.foundation.state.proposals import Folded, refused
    from app.apps.rpg.rules.direction import allows, counted

    simulation = _d(_sections.simulation_state_of(document))
    fact_id, told = _s(payload.get("fact")), _s(payload.get("told"))
    value = payload.get("value", True)
    if not fact_id or not isinstance(value, (str, int, bool)) or ":" in fact_id and fact_id.startswith("waived:"):
        return refused("no fact named")
    held = world_facts(simulation).get(fact_id)
    if held is not None and held.get("value") != value:
        return refused(f"it contradicts {fact_id} = {held.get('value')!r}, which holds")
    if held is not None:
        return refused(f"{fact_id} already holds")
    if authored_outcome(simulation, fact_id):
        return refused(f"{fact_id} is an outcome the world's author left to the hero")
    if names_a_secret_here(simulation, told):
        return refused("its line names a secret")
    limit = allows(simulation, "fact")
    if limit:
        return refused(limit)
    return Folded([FactSet(fact_id=fact_id, value=value, source="game_master", known=payload.get("known") is not False,
                           told=told), counted(simulation, "fact")])


def fold_complication(document: Mapping[str, Any], payload: Mapping[str, Any]) -> "Folded":
    """A complication in the current scene (EV-0): a fact with its line, one a scene, within the day's limit."""
    from app.apps.rpg.foundation.state.proposals import Folded, refused
    from app.apps.rpg.rules.direction import allows, counted
    from app.apps.rpg.rules.routines import hero_location

    simulation = _d(_sections.simulation_state_of(document))
    scene = hero_location(simulation)
    told = _s(payload.get("told"))
    if not told or names_a_secret_here(simulation, told):
        return refused("a complication needs a line, and names no secret")
    limit = allows(simulation, "complication", scene=scene)
    if limit:
        return refused(limit)
    fact_id = f"complication:{_s(payload.get('id')) or len(world_facts(simulation)) + 1}"
    return Folded([FactSet(fact_id=fact_id, value=True, source="game_master", told=told),
                   counted(simulation, "complication", scene=scene)])


def names_a_secret_here(simulation: Mapping[str, Any], text: str) -> bool:
    """Whether ``text`` tells a secret one of the world's people keeps."""
    from app.apps.rpg.rules.contracts import secrets_held
    from app.apps.rpg.rules.secrets import names_a_secret

    return bool(text) and names_a_secret(text, secrets_held(_d(_sections.world_model_of(simulation)).get("npcs")))


def what_has_changed(simulation: Mapping[str, Any]) -> list[str]:
    """The journal's "What has changed": the author's line of each fact that holds and that the hero knows."""
    return [_s(row.get("told")) for _, row in sorted(world_facts(simulation).items())
            if row.get("known") is True and _s(row.get("told"))]


def epilogue(simulation: Mapping[str, Any], applied: Iterable[StateChange]) -> list[str]:
    """An ending's epilogue: when the turn completes a finale, each known fact's line, in fact order (the narrator
    phrases them; the claim checker holds the phrasing to them)."""
    quests = _quest_rows(simulation)
    ended = any(isinstance(change, QuestStatusChanged) and change.status == "completed"
                and _s(quests.get(change.quest_id, {}).get("tier")) == "finale" for change in applied)
    return what_has_changed(simulation) if ended else []


__all__ = ["BANDS", "closed_providers", "consequences", "epilogue", "fact_effects", "fact_value", "facts_written",
           "names_a_secret_here", "authored_outcome",
           "fold_complication", "fold_fact",
           "group_members", "holding", "moved_people", "place_lines", "price_factor", "quest_open", "standing_band", "standing_with",
           "waived", "what_has_changed", "world_facts"]
