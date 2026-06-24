from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

COMBAT_EVENT_CARD_VERSION = "combat_event_card_v1"


@dataclass(frozen=True)
class CombatEventCard:
    format_version: str
    card_type: str
    title: str
    actor: str
    target: str | None = None
    detail: str = ""
    result: str | None = None
    sort_key: int = 0

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "format_version": self.format_version,
            "card_type": self.card_type,
            "title": self.title,
            "actor": self.actor,
            "detail": self.detail,
            "sort_key": self.sort_key,
        }
        if self.target:
            payload["target"] = self.target
        if self.result:
            payload["result"] = self.result
        return payload


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _text(value: Any, default: str = "") -> str:
    text = str(value).strip() if value is not None else ""
    return text or default


def _actor(event: Mapping[str, Any]) -> str:
    return _text(event.get("actor") or event.get("actor_name") or event.get("source") or event.get("entity"), "Unknown actor")


def _target(event: Mapping[str, Any]) -> str | None:
    return _text(event.get("target") or event.get("target_name") or event.get("defender")) or None


def _coords(value: Any) -> str:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return "(" + ", ".join(_text(item) for item in value) + ")"
    return _text(value)


def card_from_combat_event(event: Mapping[str, Any], *, sort_key: int = 0) -> dict[str, Any]:
    """Convert one deterministic combat event into a UI-friendly card."""

    event = _dict(event)
    event_type = _text(event.get("type") or event.get("event_type") or event.get("kind"), "event").casefold()
    actor = _actor(event)
    target = _target(event)

    if event_type in {"move", "movement"}:
        destination = _coords(event.get("to") or event.get("destination") or event.get("position"))
        distance = _text(event.get("distance") or event.get("feet") or event.get("squares"))
        detail = f"Moves to {destination}" if destination else "Moves."
        if distance:
            detail = f"{detail} Distance: {distance}."
        return CombatEventCard(COMBAT_EVENT_CARD_VERSION, "movement", f"{actor} moves", actor, target, detail, sort_key=sort_key).as_dict()

    if event_type in {"ability", "feature", "spell"}:
        name = _text(event.get("name") or event.get("ability") or event.get("spell"), "Ability")
        detail = _text(event.get("detail") or event.get("description"), f"Uses {name}.")
        return CombatEventCard(COMBAT_EVENT_CARD_VERSION, "ability", f"{actor}: {name}", actor, target, detail, sort_key=sort_key).as_dict()

    if event_type in {"save", "saving_throw", "saving throw"}:
        save_name = _text(event.get("save") or event.get("ability") or event.get("stat"), "Saving throw")
        dc = _text(event.get("dc") or event.get("difficulty_class"))
        roll = _text(event.get("roll") or event.get("total"))
        result = _text(event.get("result") or event.get("outcome"))
        detail = f"{save_name} save"
        if dc:
            detail += f" vs DC {dc}"
        if roll:
            detail += f"; rolled {roll}"
        return CombatEventCard(COMBAT_EVENT_CARD_VERSION, "saving_throw", f"{target or actor} rolls {save_name}", actor, target, detail + ".", result or None, sort_key).as_dict()

    if event_type in {"condition", "status", "effect"}:
        condition = _text(event.get("condition") or event.get("status") or event.get("effect"), "Condition")
        result = _text(event.get("result") or event.get("outcome") or "applied")
        return CombatEventCard(COMBAT_EVENT_CARD_VERSION, "condition", f"{target or actor}: {condition}", actor, target, condition, result, sort_key).as_dict()

    if event_type in {"attack", "damage"}:
        attack = _text(event.get("attack") or event.get("weapon") or event.get("name"), "Attack")
        roll = _text(event.get("roll") or event.get("attack_roll"))
        damage = _text(event.get("damage") or event.get("damage_total"))
        result = _text(event.get("result") or event.get("outcome"))
        detail_parts = [attack]
        if roll:
            detail_parts.append(f"roll {roll}")
        if damage:
            detail_parts.append(f"damage {damage}")
        return CombatEventCard(COMBAT_EVENT_CARD_VERSION, "attack", f"{actor} attacks", actor, target, "; ".join(detail_parts), result or None, sort_key).as_dict()

    detail = _text(event.get("detail") or event.get("summary") or event.get("description"), event_type or "Combat event")
    return CombatEventCard(COMBAT_EVENT_CARD_VERSION, "event", f"{actor}: combat event", actor, target, detail, sort_key=sort_key).as_dict()


def _iter_combat_events(payload: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    payload = _dict(payload)
    for key in ("combat_events", "events", "combat_delta", "turn_events"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            nested_events = value.get("events") or value.get("combat_events") or value.get("turn_events")
            for item in _list(nested_events):
                if isinstance(item, Mapping):
                    yield item
        else:
            for item in _list(value):
                if isinstance(item, Mapping):
                    yield item
    for nested_key in ("result", "authoritative", "turn_runtime", "narration_payload"):
        nested = payload.get(nested_key)
        if isinstance(nested, Mapping):
            yield from _iter_combat_events(nested)


def build_combat_event_cards(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Build deterministic combat cards from a runtime result payload."""

    cards: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for index, event in enumerate(_iter_combat_events(payload)):
        card = card_from_combat_event(event, sort_key=index)
        key = (card.get("card_type", ""), card.get("title", ""), card.get("detail", ""))
        if key in seen:
            continue
        seen.add(key)
        cards.append(card)
    return cards


def attach_combat_event_cards(result: dict[str, Any]) -> dict[str, Any]:
    """Attach combat cards to a result and nested result payload without mutating state."""

    if not isinstance(result, dict):
        return result
    cards = build_combat_event_cards(result)
    if not cards:
        return result
    result["combat_event_cards"] = cards
    nested = result.get("result")
    if isinstance(nested, dict):
        nested["combat_event_cards"] = cards
        result["result"] = nested
    return result
