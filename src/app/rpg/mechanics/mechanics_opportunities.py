from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional
import re


@dataclass(frozen=True)
class MechanicOpportunity:
    id: str
    mechanic: str
    label: str
    command: str
    resolver: str
    location_id: str = ""
    location_aliases: tuple[str, ...] = ()
    npc_id: str = ""
    requires_flags: tuple[str, ...] = ()
    blocked_by_flags: tuple[str, ...] = ()
    required_items: tuple[str, ...] = ()
    effects_preview: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return str(value or "")


def _normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", _safe_str(value).strip().lower())


def _state_flags(state: Mapping[str, Any], scenario_state: Optional[Mapping[str, Any]] = None) -> set[str]:
    flags: set[str] = set()
    for source in (state, scenario_state or {}):
        source = _safe_dict(source)
        raw_flags = source.get("flags") or source.get("world_flags") or source.get("scenario_flags")
        if isinstance(raw_flags, dict):
            flags.update(str(k) for k, v in raw_flags.items() if v)
        elif isinstance(raw_flags, list):
            flags.update(str(v) for v in raw_flags)

        completed = source.get("completed_objectives") or source.get("completed_quests")
        if isinstance(completed, list):
            flags.update(str(v) for v in completed)

    return flags


def _inventory_item_ids(state: Mapping[str, Any]) -> set[str]:
    ids: set[str] = set()
    inventory = state.get("inventory") or state.get("items") or []
    if isinstance(inventory, dict):
        for key, value in inventory.items():
            if value:
                ids.add(str(key))
    elif isinstance(inventory, list):
        for item in inventory:
            if isinstance(item, dict):
                item_id = item.get("id") or item.get("item_id") or item.get("name")
                if item_id:
                    ids.add(str(item_id))
            elif item:
                ids.add(str(item))
    return ids


def _current_location(state: Mapping[str, Any], scenario_state: Optional[Mapping[str, Any]] = None) -> str:
    state = _safe_dict(state)
    scenario_state = _safe_dict(scenario_state)
    return _safe_str(
        state.get("current_location")
        or state.get("current_location_id")
        or state.get("location")
        or scenario_state.get("current_location")
        or scenario_state.get("location")
        or "scene:rusty_flagon"
    )


TAVERN_STORY_MECHANIC_OPPORTUNITIES: List[MechanicOpportunity] = [
    MechanicOpportunity(
        id="mechanic:lodging:common_room",
        mechanic="service_or_lodging",
        label="Rent a common room from Bran",
        command="I pay Bran 5 silver for a common room.",
        resolver="service_purchase",
        location_id="scene:rusty_flagon",
        npc_id="npc:bran",
        effects_preview={
            "service_result": {"service_id": "lodging:common_room", "name": "Common Room"},
            "currency_delta": {"silver": -5},
        },
        metadata={"price": {"silver": 5}, "service_id": "lodging:common_room"},
    ),
    MechanicOpportunity(
        id="mechanic:service:meal",
        mechanic="service_or_lodging",
        label="Buy a hot meal from Bran",
        command="I buy a hot meal from Bran.",
        resolver="service_purchase",
        location_id="scene:rusty_flagon",
        npc_id="npc:bran",
        effects_preview={
            "service_result": {"service_id": "service:hot_meal", "name": "Hot Meal"},
            "currency_delta": {"silver": -1},
        },
        metadata={"price": {"silver": 1}, "service_id": "service:hot_meal"},
    ),
    MechanicOpportunity(
        id="mechanic:buy:rations",
        mechanic="buying",
        label="Buy two rations from Bran",
        command="I buy two rations from Bran.",
        resolver="merchant_purchase",
        location_id="scene:rusty_flagon",
        npc_id="npc:bran",
        effects_preview={
            "purchase_result": {"item_id": "item:rations", "quantity": 2},
            "currency_delta": {"silver": -4},
            "inventory_delta": {"items_added": [{"id": "item:rations", "quantity": 2}]},
        },
        metadata={"item_id": "item:rations", "quantity": 2, "price": {"silver": 4}},
    ),
    MechanicOpportunity(
        id="mechanic:buy:torch",
        mechanic="buying",
        label="Buy a torch from Bran",
        command="I buy a torch from Bran.",
        resolver="merchant_purchase",
        location_id="scene:rusty_flagon",
        npc_id="npc:bran",
        effects_preview={
            "purchase_result": {"item_id": "item:torch", "quantity": 1},
            "currency_delta": {"copper": -5},
            "inventory_delta": {"items_added": [{"id": "item:torch", "quantity": 1}]},
        },
        metadata={"item_id": "item:torch", "quantity": 1, "price": {"copper": 5}},
    ),
    MechanicOpportunity(
        id="mechanic:party:recruit_mira",
        mechanic="party_recruitment",
        label="Ask Mira to join the road investigation",
        command="I ask Mira to join me for the road investigation.",
        resolver="party_recruitment",
        location_id="scene:rusty_flagon",
        npc_id="npc:mira",
        blocked_by_flags=("party:npc:mira_joined",),
        effects_preview={"party_delta": {"companions_added": ["npc:mira"]}},
        metadata={"companion_id": "npc:mira"},
    ),
    MechanicOpportunity(
        id="mechanic:travel:old_mill",
        mechanic="travel",
        label="Travel to the old mill",
        command="I travel to the old mill.",
        resolver="travel",
        location_id="scene:rusty_flagon",
        effects_preview={
            "travel_result": {
                "to_location": "location:old_mill",
                "to_location_name": "Old Mill",
            }
        },
        metadata={"to_location": "location:old_mill"},
    ),
    MechanicOpportunity(
        id="mechanic:combat:start_mill_bandits",
        mechanic="combat_started",
        label="Confront the bandit scouts",
        command="I confront the bandit scouts blocking the mill road.",
        resolver="combat_start",
        location_id="location:mill_bridge_road",
        location_aliases=("location:old_mill", "location:wagon_yard"),
        blocked_by_flags=("encounter:mill_bandit_scouts.resolved",),
        effects_preview={
            "combat_result": {
                "encounter_id": "encounter:mill_bandit_scouts",
                "started": True,
            }
        },
        metadata={"encounter_id": "encounter:mill_bandit_scouts"},
    ),
    MechanicOpportunity(
        id="mechanic:combat:resolve_mill_bandits",
        mechanic="combat_resolved",
        label="Press the attack and finish the bandit fight",
        command="I press the attack until the bandit scouts are defeated.",
        resolver="combat_resolve",
        location_id="location:mill_bridge_road",
        location_aliases=("location:old_mill", "location:wagon_yard"),
        requires_flags=("encounter:mill_bandit_scouts.started",),
        blocked_by_flags=("encounter:mill_bandit_scouts.resolved",),
        effects_preview={
            "combat_result": {
                "encounter_id": "encounter:mill_bandit_scouts",
                "resolved": True,
                "victory": True,
            },
            "xp_delta": 25,
            "inventory_delta": {
                "items_added": [
                    {"id": "item:marked_coin", "quantity": 1},
                    {"id": "item:bandit_knife", "quantity": 1},
                ]
            },
            "loot_result": {
                "items_added": [
                    {"id": "item:marked_coin", "quantity": 1},
                    {"id": "item:bandit_knife", "quantity": 1},
                ]
            },
        },
        metadata={
            "encounter_id": "encounter:mill_bandit_scouts",
            "xp": 25,
            "loot": ["item:marked_coin", "item:bandit_knife"],
        },
    ),
    MechanicOpportunity(
        id="mechanic:level:level_2",
        mechanic="level_up",
        label="Take a moment to level up after the fight",
        command="I take a moment to recover and level up from the hard-won experience.",
        resolver="level_up",
        location_id="location:mill_bridge_road",
        location_aliases=("location:old_mill", "location:wagon_yard"),
        requires_flags=("xp:level_2_ready",),
        blocked_by_flags=("player:level_2",),
        effects_preview={
            "level_up": True,
            "level_delta": {"old_level": 1, "new_level": 2},
        },
        metadata={"old_level": 1, "new_level": 2, "xp_threshold": 25},
    ),
    MechanicOpportunity(
        id="mechanic:travel:return_tavern",
        mechanic="travel",
        label="Return to the Rusty Flagon",
        command="I return to the Rusty Flagon tavern.",
        resolver="travel",
        location_id="location:mill_bridge_road",
        location_aliases=("location:old_mill", "location:wagon_yard"),
        requires_flags=("encounter:mill_bandit_scouts.resolved",),
        effects_preview={
            "travel_result": {
                "to_location": "scene:rusty_flagon",
                "to_location_name": "The Rusty Flagon Tavern",
            }
        },
        metadata={"to_location": "scene:rusty_flagon"},
    ),
    MechanicOpportunity(
        id="mechanic:sell:bandit_knife",
        mechanic="selling",
        label="Sell the bandit knife to Bran",
        command="I sell the bandit knife to Bran.",
        resolver="merchant_sale",
        location_id="scene:rusty_flagon",
        required_items=("item:bandit_knife",),
        effects_preview={
            "sale_result": {"item_id": "item:bandit_knife", "quantity": 1},
            "currency_delta": {"silver": 3},
            "inventory_delta": {"items_removed": [{"id": "item:bandit_knife", "quantity": 1}]},
        },
        metadata={"item_id": "item:bandit_knife", "quantity": 1, "value": {"silver": 3}},
    ),
    MechanicOpportunity(
        id="mechanic:quest:turn_in_marked_coin",
        mechanic="quest_progress",
        label="Show Bran the marked coin",
        command="I show Bran the marked coin and explain what happened on the mill road.",
        resolver="quest_turn_in",
        location_id="scene:rusty_flagon",
        required_items=("item:marked_coin",),
        effects_preview={
            "quest_log_delta": {
                "objective_completed": "objective:identify_marked_coin",
            },
            "xp_delta": 10,
        },
        metadata={"objective_id": "objective:identify_marked_coin", "xp": 10},
    ),
]


def list_available_mechanic_opportunities(
    *,
    state: Mapping[str, Any],
    scenario_state: Optional[Mapping[str, Any]] = None,
    missing_mechanics: Optional[Iterable[str]] = None,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    state = _safe_dict(state)
    scenario_state = _safe_dict(scenario_state)
    current = _current_location(state, scenario_state)
    flags = _state_flags(state, scenario_state)
    item_ids = _inventory_item_ids(state)
    missing = set(str(item) for item in (missing_mechanics or []))

    opportunities: List[Dict[str, Any]] = []

    for opportunity in TAVERN_STORY_MECHANIC_OPPORTUNITIES:
        allowed_locations = {
            opportunity.location_id,
            *tuple(opportunity.location_aliases or ()),
        }
        allowed_locations = {loc for loc in allowed_locations if loc}
        if allowed_locations and current not in allowed_locations:
            continue
        if missing and opportunity.mechanic not in missing:
            # Keep travel available because it may be required to reach missing mechanics.
            if opportunity.mechanic != "travel":
                continue
        if any(flag not in flags for flag in opportunity.requires_flags):
            continue
        if any(flag in flags for flag in opportunity.blocked_by_flags):
            continue
        if any(item_id not in item_ids for item_id in opportunity.required_items):
            continue

        opportunities.append(
            {
                "id": opportunity.id,
                "type": "mechanic",
                "mechanic": opportunity.mechanic,
                "label": opportunity.label,
                "command": opportunity.command,
                "resolver": opportunity.resolver,
                "location_id": opportunity.location_id,
                "location_aliases": list(opportunity.location_aliases or ()),
                "npc_id": opportunity.npc_id,
                "effects_preview": opportunity.effects_preview,
                "metadata": opportunity.metadata,
            }
        )

    # Put missing-mechanic opportunities first, travel second, everything else after.
    def sort_key(item: Dict[str, Any]) -> tuple[int, str]:
        mechanic = _safe_str(item.get("mechanic"))
        if mechanic in missing:
            return (0, mechanic)
        if mechanic == "travel":
            return (1, mechanic)
        return (2, mechanic)

    opportunities.sort(key=sort_key)
    return opportunities[: max(1, int(limit or 8))]


def describe_mechanic_opportunity_state(
    *,
    state: Mapping[str, Any],
    scenario_state: Optional[Mapping[str, Any]] = None,
    missing_mechanics: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    state = _safe_dict(state)
    scenario_state = _safe_dict(scenario_state)
    current = _current_location(state, scenario_state)
    flags = sorted(_state_flags(state, scenario_state))
    item_ids = sorted(_inventory_item_ids(state))
    missing = sorted(set(str(item) for item in (missing_mechanics or [])))

    by_location: Dict[str, int] = {}
    by_mechanic: Dict[str, int] = {}

    for opportunity in TAVERN_STORY_MECHANIC_OPPORTUNITIES:
        mechanic = _safe_str(opportunity.mechanic)
        if mechanic:
            by_mechanic[mechanic] = int(by_mechanic.get(mechanic, 0)) + 1

        locations = [
            opportunity.location_id,
            *list(opportunity.location_aliases or ()),
        ]
        for loc in locations:
            if loc:
                by_location[loc] = int(by_location.get(loc, 0)) + 1

    return {
        "current_location": current,
        "missing_mechanics": missing,
        "flags": flags[:80],
        "inventory_item_ids": item_ids[:80],
        "opportunity_count_for_current_location": int(by_location.get(current, 0)),
        "known_opportunity_locations": dict(sorted(by_location.items())),
        "known_opportunity_mechanics": dict(sorted(by_mechanic.items())),
    }


def _command_signature_tokens(value: Any) -> set[str]:
    text = _normalize(value)
    stopwords = {
        "i",
        "the",
        "a",
        "an",
        "to",
        "for",
        "from",
        "and",
        "or",
        "with",
        "of",
        "at",
        "on",
        "in",
        "me",
        "my",
        "bran",
        "mira",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9:_]+", text)
        if len(token) >= 3 and token not in stopwords
    }


def _mechanic_intent_matches(mechanic: str, normalized: str) -> bool:
    mechanic = _normalize(mechanic)

    if mechanic == "service_or_lodging":
        return bool(
            re.search(
                r"\b(rent|pay|buy|purchase)\b.*\b(room|lodging|meal|service|common room|hot meal)\b"
                r"|\b(room|lodging|meal|service|common room|hot meal)\b.*\b(rent|pay|buy|purchase)\b",
                normalized,
            )
        )

    if mechanic == "buying":
        return bool(re.search(r"\b(buy|purchase)\b", normalized))

    if mechanic == "selling":
        return bool(re.search(r"\b(sell|barter|trade)\b", normalized))

    if mechanic == "party_recruitment":
        return bool(re.search(r"\b(recruit|join me|come with me|hire|join the party)\b", normalized))

    if mechanic == "combat_started":
        return bool(
            re.search(r"\b(confront|attack|fight|engage|challenge)\b", normalized)
            or re.search(r"\bambush\b.*\b(bandit|scout|enemy|foe)\b", normalized)
            or re.search(r"\b(bandit|scout|enemy|foe)\b.*\bambush\b", normalized)
        )

    if mechanic == "combat_resolved":
        return bool(re.search(r"\b(press the attack|finish|defeat|end the fight|keep fighting|resolve)\b", normalized))

    if mechanic == "level_up":
        return bool(re.search(r"\b(level up|train|recover and level|spend xp)\b", normalized))

    if mechanic == "quest_progress":
        return bool(re.search(r"\b(show|turn in|report|explain|present)\b.*\b(marked coin|proof|evidence)\b", normalized))

    if mechanic == "travel":
        return bool(re.search(r"\b(travel|go|return|leave|head|walk)\b", normalized))

    return False


def match_mechanic_opportunity(
    *,
    player_input: str,
    state: Mapping[str, Any],
    scenario_state: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    normalized = _normalize(player_input)
    opportunities = list_available_mechanic_opportunities(
        state=state,
        scenario_state=scenario_state,
        missing_mechanics=None,
        limit=30,
    )

    best: Dict[str, Any] = {}
    best_score = 0
    best_reason = ""

    for opportunity in opportunities:
        mechanic = _safe_str(opportunity.get("mechanic"))
        command = _normalize(opportunity.get("command"))
        label = _normalize(opportunity.get("label"))
        metadata = _safe_dict(opportunity.get("metadata"))

        if not _mechanic_intent_matches(mechanic, normalized):
            continue

        command_tokens = _command_signature_tokens(command)
        label_tokens = _command_signature_tokens(label)
        input_tokens = _command_signature_tokens(normalized)

        command_overlap = len(command_tokens & input_tokens)
        label_overlap = len(label_tokens & input_tokens)

        score = 0
        reason = ""

        # Exact/near-exact command is always valid.
        if command and command in normalized:
            score = 1000
            reason = "exact_command_substring"

        # Label substring is also valid.
        elif label and label in normalized:
            score = 800
            reason = "label_substring"

        # Mechanic-specific entity match.
        else:
            if mechanic == "buying":
                item_id = _normalize(metadata.get("item_id"))
                if item_id and item_id.split(":")[-1].replace("_", " ") in normalized:
                    score = 400 + command_overlap + label_overlap
                    reason = "buy_item_match"

            elif mechanic == "service_or_lodging":
                service_id = _normalize(metadata.get("service_id"))
                service_name = service_id.split(":")[-1].replace("_", " ")
                if service_name and service_name in normalized:
                    score = 400 + command_overlap + label_overlap
                    reason = "service_match"
                elif any(token in normalized for token in ("room", "lodging", "meal")) and any(
                    token in normalized for token in ("rent", "pay", "buy", "purchase")
                ):
                    score = 350 + command_overlap + label_overlap
                    reason = "service_keyword_match"

            elif mechanic == "selling":
                item_id = _normalize(metadata.get("item_id"))
                if item_id and item_id.split(":")[-1].replace("_", " ") in normalized:
                    score = 400 + command_overlap + label_overlap
                    reason = "sell_item_match"

            elif mechanic == "party_recruitment":
                companion_id = _normalize(metadata.get("companion_id"))
                companion_name = companion_id.split(":")[-1]
                if companion_name and companion_name in normalized:
                    score = 400 + command_overlap + label_overlap
                    reason = "companion_match"

            elif mechanic in {"combat_started", "combat_resolved"}:
                encounter_id = _normalize(metadata.get("encounter_id"))
                # Require either a combat verb and a bandit/scout/enemy target,
                # or exact command/label above.
                has_combat_verb = bool(re.search(r"\b(confront|attack|fight|engage|challenge|defeat|finish)\b", normalized))
                has_target = any(token in normalized for token in ("bandit", "scouts", "enemy", "foe"))

                if has_combat_verb and has_target:
                    score = 400 + command_overlap + label_overlap
                    reason = "combat_target_match"

            elif mechanic == "quest_progress":
                objective_id = _normalize(metadata.get("objective_id"))
                if "marked coin" in normalized or "proof" in normalized or "evidence" in normalized:
                    score = 400 + command_overlap + label_overlap
                    reason = "quest_item_match"

            elif mechanic == "level_up":
                if "level" in normalized:
                    score = 400 + command_overlap + label_overlap
                    reason = "level_keyword_match"

            elif mechanic == "travel":
                to_location = _normalize(metadata.get("to_location"))
                to_name = to_location.split(":")[-1].replace("_", " ")
                if to_name and to_name in normalized:
                    score = 400 + command_overlap + label_overlap
                    reason = "travel_destination_match"
                elif "rusty flagon" in normalized or "tavern" in normalized:
                    score = 350 + command_overlap + label_overlap
                    reason = "travel_tavern_match"

        # Require meaningful overlap unless exact/label match.
        if score and score < 800 and command_overlap + label_overlap < 1:
            continue

        if score > best_score:
            best = opportunity
            best_score = score
            best_reason = reason

    if best and best_score > 0:
        return {
            "ok": True,
            "score": best_score,
            "match_reason": best_reason,
            "opportunity": best,
        }

    return {
        "ok": False,
        "reason": "no_strict_matching_mechanic_opportunity",
        "available_mechanics": opportunities,
    }