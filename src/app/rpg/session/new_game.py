"""RPG new-game and playable demo preset session creation.

These helpers intentionally do not call LLM, image, TTS, or worker queues. They
create deterministic disk-backed session payloads synchronously so the browser can
switch sessions immediately and then continue through the normal RPG turn queue.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.rpg.session.ability_coverage import write_ability_coverage_snapshot
from app.rpg.session.ability_system import build_progression_package
from app.rpg.session.service import archive_session, load_session, save_session

DEMO_PRESET_ID = "demo_glimmerdeep_pass_lvl14"
NEW_GAME_CONTRACT_VERSION = "rpg_new_game_v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_session_id(prefix: str = "rpg") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{stamp}_{secrets.token_hex(4)}"


class RpgPlayerOptions(BaseModel):
    name: str = "Alyndra"
    pronouns: str = "she/her"
    background: str = "Wanderer"
    build: Literal["balanced_adventurer", "warrior", "ranger", "silver_tongue"] = "balanced_adventurer"
    portrait_seed: int | None = None


class RpgFeatureOptions(BaseModel):
    autosave: bool = True
    validator: bool = True
    background_soft_audit: bool = True
    llm_narration: bool = True
    image_generation: bool = False
    tts: bool = False
    stt: bool = False


class RpgNewGameRequest(BaseModel):
    campaign_template: str = "classic_fantasy"
    genre: str | None = None
    tone: str = "heroic adventure"
    background: str | None = None
    starting_location: str = "rusty_flagon_tavern"
    player: RpgPlayerOptions = Field(default_factory=RpgPlayerOptions)
    primary_capability: str | None = None
    secondary_capabilities: list[str] = Field(default_factory=list)
    power_source: str | None = None
    generated_class_name: str | None = None
    generated_class_summary: str | None = None
    difficulty: Literal["story", "normal", "harsh"] = "normal"
    world_activity: Literal["quiet", "standard", "living_world"] = "standard"
    economy_pressure: Literal["relaxed", "normal", "strict"] = "normal"
    combat_lethality: Literal["safe", "normal", "deadly"] = "normal"
    companions_enabled: bool = True
    permadeath: bool = False
    seed: int | None = None
    features: RpgFeatureOptions = Field(default_factory=RpgFeatureOptions)


class RpgRenameSessionRequest(BaseModel):
    name: str


STARTING_BUILDS: dict[str, dict[str, Any]] = {
    "balanced_adventurer": {
        "label": "Balanced Adventurer",
        "role": "Adventurer",
        "stats": {"strength": 10, "dexterity": 10, "constitution": 10, "intelligence": 10, "wisdom": 10, "charisma": 10},
        "hp": {"current": 100, "max": 100},
        "stamina": {"current": 100, "max": 100},
        "mana": {"current": 40, "max": 40},
    },
    "warrior": {
        "label": "Warrior",
        "role": "Warrior",
        "stats": {"strength": 14, "dexterity": 10, "constitution": 13, "intelligence": 8, "wisdom": 10, "charisma": 9},
        "hp": {"current": 120, "max": 120},
        "stamina": {"current": 110, "max": 110},
        "mana": {"current": 20, "max": 20},
    },
    "ranger": {
        "label": "Ranger",
        "role": "Ranger",
        "stats": {"strength": 10, "dexterity": 14, "constitution": 11, "intelligence": 9, "wisdom": 13, "charisma": 9},
        "hp": {"current": 105, "max": 105},
        "stamina": {"current": 115, "max": 115},
        "mana": {"current": 30, "max": 30},
    },
    "silver_tongue": {
        "label": "Silver Tongue",
        "role": "Face",
        "stats": {"strength": 8, "dexterity": 10, "constitution": 10, "intelligence": 11, "wisdom": 11, "charisma": 14},
        "hp": {"current": 95, "max": 95},
        "stamina": {"current": 95, "max": 95},
        "mana": {"current": 50, "max": 50},
    },
}

CAMPAIGN_STAT_KEYS = ("strength", "agility", "endurance", "intellect", "charisma", "perception", "archery", "survival")
CAMPAIGN_STAT_MIN = 8
CAMPAIGN_STAT_MAX = 16
CORE_STAT_MAP = {
    "strength": "strength",
    "agility": "dexterity",
    "endurance": "constitution",
    "intellect": "intelligence",
    "charisma": "charisma",
    "perception": "wisdom",
}
RPG_ONLY_STAT_KEYS = ("archery", "survival")


STARTING_LOCATIONS: dict[str, dict[str, Any]] = {
    "rusty_flagon_tavern": {
        "title": "Rusty Flagon Tavern",
        "region": "Market Road",
        "location": "Rusty Flagon Tavern",
        "time_label": "Day 1 • 08:00",
        "weather": "Rainy",
        "summary": (
            "You sit near the hearth of the Rusty Flagon Tavern as rain taps against the shutters. "
            "Bran, the innkeeper, polishes a cup behind the counter while Elara the merchant argues quietly "
            "with a road-worn guard near the door. A notice board beside the stairs lists work for caravan guards, "
            "rat catchers, and anyone willing to investigate strange lights near the old quarry."
        ),
        "timeline": [
            {"turn": 0, "time": "Day 1 • 08:00", "title": "New campaign started", "detail": "You arrived at the Rusty Flagon Tavern.", "kind": "new_game"},
            {"turn": 0, "time": "Day 1 • 08:00", "title": "Services available", "detail": "Bran is available for rooms, food, and rumors.", "kind": "service"},
            {"turn": 0, "time": "Day 1 • 08:00", "title": "Merchant nearby", "detail": "Elara is available for trade.", "kind": "economy"},
        ],
        "quick_actions": ["Talk to Bran", "Check the notice board", "Buy supplies", "Rent a room", "Leave for the market"],
    },
    "market_district": {
        "title": "Market District",
        "region": "Town",
        "location": "Market District",
        "time_label": "Day 1 • 09:00",
        "weather": "Cloudy",
        "summary": "Market stalls crowd the square, and voices rise over the smell of bread, rain, and horse leather.",
        "timeline": [
            {"turn": 0, "time": "Day 1 • 09:00", "title": "New campaign started", "detail": "You arrived at the Market District.", "kind": "new_game"},
            {"turn": 0, "time": "Day 1 • 09:00", "title": "Open market", "detail": "Merchants are setting out supplies, tools, and caravan notices.", "kind": "economy"},
        ],
        "quick_actions": ["Browse the stalls", "Talk to a merchant", "Look for rumors", "Check caravan notices", "Travel to the tavern"],
    },
    "northern_road": {
        "title": "Northern Road",
        "region": "Trade Road",
        "location": "Northern Road",
        "time_label": "Day 1 • 10:15",
        "weather": "Overcast",
        "summary": (
            "The Northern Road cuts between wet pines and wagon-rutted mud. A broken milestone leans beside the ditch, "
            "and fresh hoofprints lead toward the pass while older tracks vanish into the brush."
        ),
        "timeline": [
            {"turn": 0, "time": "Day 1 • 10:15", "title": "New campaign started", "detail": "You started on the Northern Road.", "kind": "new_game"},
            {"turn": 0, "time": "Day 1 • 10:15", "title": "Road signs", "detail": "Fresh hoofprints and a damaged milestone point toward recent trouble.", "kind": "discovery"},
        ],
        "quick_actions": ["Inspect the hoofprints", "Follow the road north", "Search the brush", "Check supplies", "Return to town"],
    },
    "glimmerdeep_pass": {
        "title": "Glimmerdeep Pass",
        "region": "Mountain Pass",
        "location": "Glimmerdeep Pass",
        "time_label": "Day 1 • 09:42",
        "weather": "Cold, Windy",
        "temperature": -12,
        "summary": "The mountain winds howl through the narrow pass, carrying the scent of pine and snow. Jagged cliffs rise on both sides, and an ancient stone archway stands ahead, half-buried in drifts.",
        "timeline": [
            {"turn": 0, "time": "Day 1 • 09:42", "title": "New campaign started", "detail": "You arrived at Glimmerdeep Pass.", "kind": "new_game"},
            {"turn": 0, "time": "Day 1 • 09:42", "title": "Ancient archway", "detail": "A half-buried stone archway blocks part of the pass.", "kind": "discovery"},
        ],
        "quick_actions": ["Inspect the archway", "Look for tracks", "Listen to the wind", "Check your gear", "Travel back down the pass"],
    },
    "old_quarry": {
        "title": "Old Quarry",
        "region": "Abandoned Works",
        "location": "Old Quarry",
        "time_label": "Day 1 • 16:20",
        "weather": "Grey and still",
        "summary": (
            "The old quarry yawns open beneath a rim of cracked stone. Rusted pulleys creak in the breeze, and pale light "
            "glows from a fissure that should have gone dark years ago."
        ),
        "timeline": [
            {"turn": 0, "time": "Day 1 • 16:20", "title": "New campaign started", "detail": "You arrived at the Old Quarry.", "kind": "new_game"},
            {"turn": 0, "time": "Day 1 • 16:20", "title": "Strange lights", "detail": "A pale glow seeps from a deep quarry fissure.", "kind": "mystery"},
        ],
        "quick_actions": ["Inspect the fissure", "Search the quarry floor", "Check the old pulley", "Light a torch", "Return to the road"],
    },
}


OPENING_HOOKS: dict[str, dict[str, Any]] = {
    "tavern_rumor": {
        "label": "Tavern Rumor",
        "summary": "A fresh rumor is already moving through the room, giving the first turn an immediate social lead.",
        "quest": {"id": "tavern_rumor", "title": "Rumor at the Rusty Flagon", "status": "active", "objective": "Ask Bran or the tavern regulars which rumor is true."},
        "timeline": {"title": "Rumor overheard", "detail": "A low conversation near the hearth hints at trouble outside town.", "kind": "rumor"},
        "quick_actions": ["Ask Bran about the rumor", "Listen to the hearth-side conversation", "Check the notice board"],
    },
    "bandit_trail": {
        "label": "Bandit Trail",
        "summary": "A witness points to fresh tracks and missing supplies, pushing the first objective toward recon and danger.",
        "quest": {"id": "bandit_trail", "title": "Bandit Trail", "status": "active", "objective": "Question the witness and inspect the tracks before the trail goes cold."},
        "timeline": {"title": "Bandit trail reported", "detail": "A road-worn witness describes raiders and fresh hoofprints beyond the market road.", "kind": "danger"},
        "quick_actions": ["Question the witness", "Inspect the tracks", "Prepare for a road fight"],
    },
    "missing_person": {
        "label": "Missing Person",
        "summary": "A local disappearance creates an investigation-forward start with clear stakes and witnesses.",
        "quest": {"id": "missing_person", "title": "Missing Person", "status": "active", "objective": "Find out who vanished and collect the first clue."},
        "timeline": {"title": "Missing person reported", "detail": "A worried local asks for help finding someone who failed to return by dawn.", "kind": "investigation"},
        "quick_actions": ["Speak to the worried local", "Search for the first clue", "Ask who saw them last"],
    },
    "guard_trouble": {
        "label": "Guard Trouble",
        "summary": "The watch is already paying attention, turning the opening toward authority, consequences, and guarded choices.",
        "quest": {"id": "guard_trouble", "title": "Trouble with the Watch", "status": "active", "objective": "Learn why the guards are watching you and avoid escalating the scene."},
        "timeline": {"title": "Guard attention", "detail": "A watch captain studies you from the doorway while a patrol blocks the street outside.", "kind": "faction"},
        "quick_actions": ["Approach the watch captain", "Keep a low profile", "Ask Bran why the guards are tense"],
    },
    "merchant_job": {
        "label": "Merchant Job",
        "summary": "A merchant has paid work ready, making trade, supplies, and delivery pressure available immediately.",
        "quest": {"id": "merchant_job", "title": "Merchant's Ledger", "status": "active", "objective": "Speak with Elara about a paid delivery job before leaving the tavern."},
        "timeline": {"title": "Merchant job offered", "detail": "Elara taps a ledger and mentions paid work for someone who can move quietly and quickly.", "kind": "economy"},
        "quick_actions": ["Speak with Elara", "Review the delivery terms", "Buy supplies for the job"],
    },
}

OPENING_HOOK_ORDER = ["tavern_rumor", "bandit_trail", "missing_person", "guard_trouble", "merchant_job"]
OPENING_PACE_LABELS = {"slow_roleplay": "Slow roleplay", "balanced": "Balanced", "immediate_action": "Immediate action"}
RELATIONSHIP_PRESETS: dict[str, dict[str, Any]] = {
    "unknown_outsider": {"label": "Unknown outsider", "relationships": [], "timeline": None},
    "local_regular": {
        "label": "Local regular",
        "relationships": [{"name": "Bran", "stance": "Familiar", "score": 18, "role": "Innkeeper"}],
        "timeline": {"title": "Recognized by Bran", "detail": "Bran remembers your usual seat and starts neutral-warm.", "kind": "relationship"},
    },
    "known_contact_nearby": {
        "label": "Known contact nearby",
        "relationships": [{"name": "Elara", "stance": "Contact", "score": 24, "role": "Merchant"}],
        "timeline": {"title": "Known contact nearby", "detail": "Elara recognizes you and can be approached as an opening contact.", "kind": "relationship"},
    },
    "owes_someone_a_favor": {
        "label": "Owes someone a favor",
        "relationships": [{"name": "Bran", "stance": "Favor owed", "score": 10, "role": "Innkeeper"}],
        "timeline": {"title": "Favor owed", "detail": "Someone nearby remembers a debt that can become an early objective.", "kind": "relationship"},
    },
    "guard_suspicion": {
        "label": "Guard suspicion",
        "relationships": [{"name": "Captain Aldric", "stance": "Suspicious", "score": -12, "role": "Guard"}],
        "timeline": {"title": "Guard suspicion", "detail": "Captain Aldric has already heard your name and watches for trouble.", "kind": "relationship"},
    },
}

OPENING_HOOK_LABELS = {value["label"].lower(): key for key, value in OPENING_HOOKS.items()} | {"random from seed": "random_from_seed"}
OPENING_PACE_KEYS_BY_LABEL = {label.lower(): key for key, label in OPENING_PACE_LABELS.items()}
RELATIONSHIP_KEYS_BY_LABEL = {value["label"].lower(): key for key, value in RELATIONSHIP_PRESETS.items()}

DEFAULT_INVENTORY: list[dict[str, Any]] = [
    {"id": "travelers_cloak", "name": "Traveler's cloak", "quantity": 1, "type": "clothing"},
    {"id": "bedroll", "name": "Bedroll", "quantity": 1, "type": "camping"},
    {"id": "waterskin", "name": "Waterskin", "quantity": 1, "type": "supply"},
    {"id": "ration", "name": "Ration", "quantity": 3, "type": "food"},
    {"id": "torch", "name": "Torch", "quantity": 2, "type": "tool"},
    {"id": "iron_dagger", "name": "Iron dagger", "quantity": 1, "type": "weapon"},
    {"id": "simple_bow", "name": "Simple bow", "quantity": 1, "type": "weapon"},
    {"id": "arrow", "name": "Arrow", "quantity": 20, "type": "ammo"},
    {"id": "journal", "name": "Journal", "quantity": 1, "type": "quest"},
]
DEFAULT_CURRENCY = {"gold": 10, "silver": 25, "copper": 50}
DEFAULT_EQUIPMENT = [
    {"slot": "Weapon", "name": "Iron dagger"},
    {"slot": "Ranged", "name": "Simple bow"},
    {"slot": "Cloak", "name": "Traveler's cloak"},
]
REQUIRED_STARTER_ITEMS = [
    {"id": "waterskin", "name": "Waterskin", "quantity": 1, "type": "supply"},
    {"id": "journal", "name": "Journal", "quantity": 1, "type": "quest"},
]
STARTER_GEAR_CATALOG: dict[str, dict[str, Any]] = {
    "travel cloak": {"id": "travel_cloak", "name": "Travel cloak", "type": "clothing", "slot": "Cloak"},
    "fine cloak": {"id": "fine_cloak", "name": "Fine cloak", "type": "clothing", "slot": "Cloak"},
    "iron dagger": {"id": "iron_dagger", "name": "Iron dagger", "type": "weapon", "slot": "Weapon"},
    "shortbow": {"id": "shortbow", "name": "Shortbow", "type": "weapon", "slot": "Ranged"},
    "hand axe": {"id": "hand_axe", "name": "Hand axe", "type": "weapon", "slot": "Weapon"},
    "arrow bundle": {"id": "arrow", "name": "Arrow", "type": "ammo", "quantity": 20},
    "trail rations": {"id": "ration", "name": "Trail rations", "type": "food"},
    "rations": {"id": "ration", "name": "Rations", "type": "food"},
    "torch": {"id": "torch", "name": "Torch", "type": "tool"},
    "bedroll": {"id": "bedroll", "name": "Bedroll", "type": "camping"},
    "ledger note": {"id": "ledger_note", "name": "Ledger note", "type": "quest"},
    "field kit": {"id": "field_kit", "name": "Field kit", "type": "tool"},
    "rope coil": {"id": "rope_coil", "name": "Rope coil", "type": "tool"},
    "field journal": {"id": "field_journal", "name": "Field journal", "type": "quest"},
    "ink kit": {"id": "ink_kit", "name": "Ink kit", "type": "tool"},
    "old map": {"id": "old_map", "name": "Old map", "type": "quest"},
}


def _normal_key(value: Any, fallback: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    return text or fallback


def _summary_field(summary: str | None, field_name: str) -> str | None:
    if not summary:
        return None
    marker = f"{field_name}:"
    start = summary.lower().find(marker.lower())
    if start < 0:
        return None
    start += len(marker)
    end = summary.find(".", start)
    value = summary[start : end if end >= 0 else len(summary)].strip()
    return value or None


def _story_option(request: RpgNewGameRequest, field_name: str, fallback: str) -> str:
    summary = request.generated_class_summary
    if field_name == "opening_hook":
        label = _summary_field(summary, "Opening")
        if label:
            return OPENING_HOOK_LABELS.get(label.lower(), _normal_key(label, fallback))
    if field_name == "opening_pace":
        label = _summary_field(summary, "Pace")
        if label:
            return OPENING_PACE_KEYS_BY_LABEL.get(label.lower(), _normal_key(label, fallback))
    if field_name == "relationship_preset":
        label = _summary_field(summary, "Relationship")
        if label:
            return RELATIONSHIP_KEYS_BY_LABEL.get(label.lower(), _normal_key(label, fallback))
    return fallback


def _resolve_opening_hook(request: RpgNewGameRequest, seed: int) -> str:
    hook = _story_option(request, "opening_hook", "tavern_rumor")
    if hook in {"random", "random_seed", "random_from_seed"}:
        return OPENING_HOOK_ORDER[seed % len(OPENING_HOOK_ORDER)]
    return hook if hook in OPENING_HOOKS else "tavern_rumor"


def _build_story_setup(request: RpgNewGameRequest, location: dict[str, Any], seed: int) -> dict[str, Any]:
    hook_key = _resolve_opening_hook(request, seed)
    pace_key = _story_option(request, "opening_pace", "balanced")
    if pace_key not in OPENING_PACE_LABELS:
        pace_key = "balanced"
    relationship_key = _story_option(request, "relationship_preset", "unknown_outsider")
    if relationship_key not in RELATIONSHIP_PRESETS:
        relationship_key = "unknown_outsider"
    relationship = RELATIONSHIP_PRESETS[relationship_key]
    hook = OPENING_HOOKS[hook_key]
    time_label = str(location.get("time_label") or "Day 1 • 08:00")
    timeline = [{"turn": 0, "time": time_label, **hook["timeline"]}]
    if relationship.get("timeline"):
        timeline.append({"turn": 0, "time": time_label, **relationship["timeline"]})
    base_actions = list(hook["quick_actions"])
    location_actions = list(location.get("quick_actions") or [])
    if pace_key == "slow_roleplay":
        quick_actions = ["Take in the scene", *location_actions[:2], *base_actions[:2]]
    elif pace_key == "immediate_action":
        quick_actions = [base_actions[0], *base_actions[1:], "Check supplies"]
    else:
        quick_actions = [base_actions[0], *location_actions[:2], *base_actions[1:]]
    return {
        "opening_hook": hook_key,
        "opening_hook_label": hook["label"],
        "opening_pace": pace_key,
        "opening_pace_label": OPENING_PACE_LABELS[pace_key],
        "relationship_preset": relationship_key,
        "relationship_label": relationship["label"],
        "summary": hook["summary"],
        "quests": [dict(hook["quest"])],
        "relationships": [dict(entry) for entry in relationship.get("relationships", [])],
        "timeline": timeline,
        "quick_actions": list(dict.fromkeys(quick_actions))[:6],
    }


def _coerce_initial_stat(raw_value: Any) -> int | None:
    if isinstance(raw_value, bool) or raw_value is None:
        return None
    if isinstance(raw_value, int):
        value = raw_value
    elif isinstance(raw_value, float) and raw_value.is_integer():
        value = int(raw_value)
    elif isinstance(raw_value, str):
        text = raw_value.strip()
        if not text or not text.lstrip("-").isdigit():
            return None
        value = int(text)
    else:
        return None
    return max(CAMPAIGN_STAT_MIN, min(CAMPAIGN_STAT_MAX, value))


def _normalize_initial_stats(initial_stats: dict[str, Any] | None) -> dict[str, int]:
    if not isinstance(initial_stats, dict):
        return {}
    normalized: dict[str, int] = {}
    for key in CAMPAIGN_STAT_KEYS:
        if key not in initial_stats:
            continue
        value = _coerce_initial_stat(initial_stats.get(key))
        if value is not None:
            normalized[key] = value
    return normalized


def _stats_from_summary(summary: str | None) -> dict[str, int]:
    value = _summary_field(summary, "Stats")
    if not value:
        return {}
    raw_stats: dict[str, Any] = {}
    for entry in value.split(","):
        label = entry.strip()
        if not label:
            continue
        key_text, _, value_text = label.replace(":", " ").rpartition(" ")
        key = _normal_key(key_text, "")
        if key:
            raw_stats[key] = value_text.strip()
    return _normalize_initial_stats(raw_stats)


def _initial_stats_from_request(request: RpgNewGameRequest) -> dict[str, int]:
    return _stats_from_summary(request.generated_class_summary)


def _resource_snapshot(value: dict[str, Any]) -> dict[str, int]:
    maximum = int(value.get("max") or value.get("current") or 0)
    current = int(value.get("current") or maximum)
    return {"current": current, "max": maximum}


def _derive_resources(build: dict[str, Any], stats: dict[str, int]) -> dict[str, dict[str, int]]:
    baseline_stats = {key: int(value) for key, value in dict(build["stats"]).items()}
    base_hp = _resource_snapshot(dict(build["hp"]))["max"]
    base_stamina = _resource_snapshot(dict(build["stamina"]))["max"]
    base_mana = _resource_snapshot(dict(build["mana"]))["max"]
    constitution_delta = stats["constitution"] - baseline_stats["constitution"]
    dexterity_delta = stats["dexterity"] - baseline_stats["dexterity"]
    strength_delta = stats["strength"] - baseline_stats["strength"]
    intelligence_delta = stats["intelligence"] - baseline_stats["intelligence"]
    wisdom_delta = stats["wisdom"] - baseline_stats["wisdom"]
    charisma_delta = stats["charisma"] - baseline_stats["charisma"]
    hp = max(50, base_hp + constitution_delta * 8)
    stamina = max(40, base_stamina + constitution_delta * 3 + dexterity_delta * 4 + strength_delta * 2)
    mana = max(0, base_mana + intelligence_delta * 5 + wisdom_delta * 3 + charisma_delta * 2)
    return {
        "hp": {"current": hp, "max": hp},
        "stamina": {"current": stamina, "max": stamina},
        "mana": {"current": mana, "max": mana},
    }


def _player_stat_profile(request: RpgNewGameRequest, build: dict[str, Any]) -> dict[str, Any]:
    normalized = _initial_stats_from_request(request)
    core_stats = {key: int(value) for key, value in dict(build["stats"]).items()}
    for frontend_key, core_key in CORE_STAT_MAP.items():
        if frontend_key in normalized:
            core_stats[core_key] = normalized[frontend_key]
    rpg_only_stats = {key: normalized[key] for key in RPG_ONLY_STAT_KEYS if key in normalized}
    source = "new_game_point_buy" if normalized else "build_default"
    resources = _derive_resources(build, core_stats) if normalized else {
        "hp": _resource_snapshot(dict(build["hp"])),
        "stamina": _resource_snapshot(dict(build["stamina"])),
        "mana": _resource_snapshot(dict(build["mana"])),
    }
    skill_progression = {
        "starting_stats": {key: {"value": value, "source": source} for key, value in rpg_only_stats.items()}
    } if rpg_only_stats else {}
    affordance = {
        "core_stats": dict(core_stats),
        "rpg_only_stats": rpg_only_stats,
        "source": source,
    }
    return {
        "initial_stats": normalized,
        "stat_source": source,
        "stats": core_stats,
        "resources": resources,
        "skill_progression": skill_progression,
        "affordance": affordance,
    }


def _starter_gear_labels(request: RpgNewGameRequest) -> list[str]:
    value = _summary_field(request.generated_class_summary, "Starter gear")
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _split_quantity(raw_label: str) -> tuple[str, int]:
    label = raw_label.strip()
    name, marker, quantity_text = label.rpartition(" x")
    if marker and quantity_text.isdigit():
        return name.strip(), max(1, int(quantity_text))
    return label, 1


def _currency_from_label(raw_label: str) -> tuple[str, int] | None:
    parts = raw_label.strip().lower().split()
    if len(parts) != 2 or not parts[0].isdigit():
        return None
    coin = parts[1].rstrip("s")
    if coin not in {"gold", "silver", "copper"}:
        return None
    return coin, int(parts[0])


def _gear_key(label: str) -> str:
    return label.strip().lower().replace("'", "").replace("’", "")


def _add_inventory_item(inventory: list[dict[str, Any]], item: dict[str, Any]) -> None:
    key = str(item.get("id") or item.get("name") or "").lower()
    for existing in inventory:
        existing_key = str(existing.get("id") or existing.get("name") or "").lower()
        if existing_key == key:
            existing["quantity"] = int(existing.get("quantity") or 1) + int(item.get("quantity") or 1)
            return
    inventory.append(dict(item))


def _starter_item_from_label(raw_label: str) -> tuple[dict[str, Any], dict[str, str] | None]:
    base_name, quantity = _split_quantity(raw_label)
    catalog = STARTER_GEAR_CATALOG.get(_gear_key(base_name))
    if catalog is None:
        item = {"id": _gear_key(base_name).replace(" ", "_"), "name": base_name, "quantity": quantity, "type": "misc"}
        return item, None
    item_quantity = int(catalog.get("quantity") or 1) * quantity
    item = {key: value for key, value in catalog.items() if key != "slot"}
    item["quantity"] = item_quantity
    equipment = {"slot": str(catalog["slot"]), "name": str(catalog["name"])} if catalog.get("slot") else None
    return item, equipment


def _starter_loadout(request: RpgNewGameRequest) -> dict[str, Any]:
    labels = _starter_gear_labels(request)
    if not labels:
        return {
            "starter_gear": [],
            "inventory": [dict(item) for item in DEFAULT_INVENTORY],
            "currency": dict(DEFAULT_CURRENCY),
            "equipment": [dict(item) for item in DEFAULT_EQUIPMENT],
        }
    inventory: list[dict[str, Any]] = []
    equipment_by_slot: dict[str, dict[str, str]] = {}
    currency = {"gold": 0, "silver": 0, "copper": 0}
    for label in labels:
        coin = _currency_from_label(label)
        if coin is not None:
            coin_name, amount = coin
            currency[coin_name] += amount
            continue
        item, equipment = _starter_item_from_label(label)
        _add_inventory_item(inventory, item)
        if equipment is not None:
            equipment_by_slot.setdefault(equipment["slot"], equipment)
    for item in REQUIRED_STARTER_ITEMS:
        _add_inventory_item(inventory, item)
    return {
        "starter_gear": labels,
        "inventory": inventory,
        "currency": currency,
        "equipment": list(equipment_by_slot.values()),
    }


def _simulation_state_stub(seed: int) -> dict[str, Any]:
    return {
        "seed": seed,
        "presentation_state": {"visual_state": {"image_requests": [], "visual_assets": []}},
        "memory_state": {"actor_memory": {}, "world_memory": {"rumors": []}},
        "survival": {"enabled": False, "events": []},
    }


def _base_manifest(session_id: str, title: str, now: str, *, source_template_id: str, kind: str) -> dict[str, Any]:
    return {
        "id": session_id,
        "session_id": session_id,
        "schema_version": 2,
        "title": title,
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "source_pack_id": "rpg-core",
        "source_template_id": source_template_id,
        "archived": False,
        "kind": kind,
    }


def _new_game_state(request: RpgNewGameRequest, session_id: str, now: str) -> dict[str, Any]:
    build = STARTING_BUILDS.get(request.player.build, STARTING_BUILDS["balanced_adventurer"])
    location = STARTING_LOCATIONS.get(request.starting_location, STARTING_LOCATIONS["rusty_flagon_tavern"])
    features = request.features.model_dump(mode="json")
    seed = int(request.seed or secrets.randbits(31))
    request_payload = request.model_dump(mode="json")
    progression = build_progression_package(request_payload, build_id=request.player.build, level=1, seed=seed)
    identity = progression["character_identity"]
    story_setup = _build_story_setup(request, location, seed)
    loadout = _starter_loadout(request)
    stat_profile = _player_stat_profile(request, build)
    timeline = [*location["timeline"], *story_setup["timeline"]]
    return {
        "contract_version": NEW_GAME_CONTRACT_VERSION,
        "session_id": session_id,
        "title": f"{request.player.name} — {location['title']}",
        "location": location["location"],
        "current_location": location["location"],
        "summary": f"{location['summary']} {story_setup['summary']}",
        "current_turn": 0,
        "turn_count": 0,
        "updated_at": now,
        "metadata": {
            "kind": "new_game",
            "campaign_template": request.campaign_template,
            "genre": identity["genre"],
            "tone": identity["tone"],
            "primary_capability": identity["primary_capability"],
            "secondary_capabilities": identity["secondary_capabilities"],
            "power_source": identity["power_source"],
            "generated_class_name": identity["generated_class_name"],
            "difficulty": request.difficulty,
            "world_activity": request.world_activity,
            "economy_pressure": request.economy_pressure,
            "combat_lethality": request.combat_lethality,
            "opening_hook": story_setup["opening_hook"],
            "opening_pace": story_setup["opening_pace"],
            "relationship_preset": story_setup["relationship_preset"],
            "starter_gear": loadout["starter_gear"],
            "initial_stats": stat_profile["initial_stats"],
            "stat_source": stat_profile["stat_source"],
            "seed": seed,
            "created_from_preset": None,
        },
        "character_identity": identity,
        "ability_tree": progression["ability_tree"],
        "ability_state": progression["ability_state"],
        "hotbar": progression["hotbar"],
        "skill_progression": stat_profile["skill_progression"],
        "mechanics": {"dimension_effects": [], "pending_dimension_effects": []},
        "narrative_affordances": {
            "opening_story": story_setup,
            "starter_loadout": loadout,
            "stat_profile": stat_profile["affordance"],
            "suggested_actions": story_setup["quick_actions"],
        },
        "player": {
            "name": request.player.name,
            "pronouns": request.player.pronouns,
            "background": request.player.background,
            "class": identity["generated_class_name"],
            "role": identity["primary_capability"],
            "build": request.player.build,
            "level": 1,
            "xp": {"current": 0, "max": 100},
            "stats": stat_profile["stats"],
            "resources": stat_profile["resources"],
            "currency": loadout["currency"],
            "renown": "Unknown (0)",
            "equipment": loadout["equipment"],
            "inventory": loadout["inventory"],
        },
        "world": {
            "time": location["time_label"],
            "weather": location["weather"],
            "temperature": location.get("temperature"),
            "reputation": {"label": "Unknown", "score": 0},
        },
        "party": [],
        "quests": story_setup["quests"],
        "relationships": story_setup["relationships"],
        "encounter": {"status": "inactive", "title": "No active combat", "summary": "All quiet for now."},
        "timeline": timeline,
        "journal": {"entries": timeline},
        "quick_actions": story_setup["quick_actions"],
        "features": {**features, "companions_enabled": request.companions_enabled, "permadeath": request.permadeath},
    }


def _setup_payload_with_identity(request: RpgNewGameRequest, identity: dict[str, Any]) -> dict[str, Any]:
    payload = request.model_dump(mode="json")
    player = dict(payload.get("player") or {})
    player["background"] = identity["background"]
    payload["player"] = player
    payload["genre"] = identity["genre"]
    payload["tone"] = identity["tone"]
    payload["background"] = identity["background"]
    payload["primary_capability"] = identity["primary_capability"]
    payload["secondary_capabilities"] = list(identity["secondary_capabilities"])
    payload["power_source"] = identity["power_source"]
    payload["generated_class_name"] = identity["generated_class_name"]
    payload["generated_class_summary"] = identity["generated_class_summary"]
    return payload


def _demo_state(session_id: str, now: str) -> dict[str, Any]:
    demo_payload = {
        "campaign_template": "classic_fantasy",
        "genre": "classic_fantasy",
        "tone": "heroic mountain mystery",
        "player": {"name": "Alyndra", "pronouns": "she/her", "background": "Wanderer of the North", "build": "ranger"},
        "primary_capability": "recon",
        "secondary_capabilities": ["survival", "combat"],
        "power_source": "martial",
        "generated_class_name": "Ranger",
    }
    progression = build_progression_package(demo_payload, build_id="ranger", level=14, seed=140914)
    return {
        "contract_version": NEW_GAME_CONTRACT_VERSION,
        "session_id": session_id,
        "title": "Demo: Glimmerdeep Pass",
        "location": "Glimmerdeep Pass",
        "current_location": "Glimmerdeep Pass",
        "summary": "Faint tracks—large, clawed, and fresh—mar the snow near the archway. A torn banner from the Northern Watch flutters in the wind. Something big passed through here not long ago.",
        "current_turn": 73,
        "turn_count": 73,
        "updated_at": now,
        "metadata": {"kind": "playable_demo_clone", "created_from_preset": DEMO_PRESET_ID, "seed": 140914, "genre": "classic_fantasy"},
        "character_identity": progression["character_identity"],
        "ability_tree": progression["ability_tree"],
        "ability_state": progression["ability_state"],
        "hotbar": progression["hotbar"],
        "skill_progression": {"tracking": {"xp": 240, "rank": 4}, "marksmanship": {"xp": 310, "rank": 5}},
        "mechanics": {"dimension_effects": [], "pending_dimension_effects": []},
        "narrative_affordances": {},
        "player": {
            "name": "Alyndra",
            "pronouns": "she/her",
            "background": "Wanderer of the North",
            "class": "Ranger",
            "role": "recon",
            "level": 14,
            "xp": {"current": 7450, "max": 12000},
            "resources": {"hp": {"current": 86, "max": 110}, "stamina": {"current": 72, "max": 100}, "mana": {"current": 64, "max": 120}},
            "currency": {"gold": 1248},
            "renown": "Honored (35)",
            "equipment": [
                {"slot": "Weapon", "name": "Longbow of the Boreal Wind"},
                {"slot": "Armor", "name": "Shadow Leather Armor +2"},
                {"slot": "Cloak", "name": "Cloak of the Owl"},
                {"slot": "Ring", "name": "Band of Keen Senses"},
            ],
            "inventory": [
                {"name": "Health Potion", "quantity": 12},
                {"name": "Mana Potion", "quantity": 7},
                {"name": "Trail Rations", "quantity": 5},
                {"name": "Focus Crystal", "quantity": 3},
                {"name": "Rope Coil", "quantity": 2},
                {"name": "Torch", "quantity": 9},
                {"name": "Keenleaf", "quantity": 4},
                {"name": "Ancient Scroll", "quantity": 6},
            ],
        },
        "world": {"time": "Day 18 • 09:42", "weather": "Cold, Windy", "temperature": -12, "reputation": {"label": "Honored", "score": 35}},
        "party": [
            {"name": "Thorin Ironfist", "class": "Warrior", "level": 14, "resources": {"hp": {"current": 112, "max": 140}}},
            {"name": "Elandra", "class": "Mage", "level": 13, "resources": {"hp": {"current": 78, "max": 90}}},
            {"name": "Kael", "class": "Rogue", "level": 12, "resources": {"hp": {"current": 68, "max": 85}}},
        ],
        "quests": [
            {"id": "frostbound_relic", "title": "The Frostbound Relic", "status": "active", "objective": "Find the relic in Glimmerdeep."},
            {"id": "secrets_in_snow", "title": "Secrets in the Snow", "status": "active", "objective": "Investigate the old watchtower."},
            {"id": "icefang_alpha", "title": "Bounty: Icefang Alpha", "status": "active", "objective": "Track down the alpha beast."},
        ],
        "relationships": [
            {"name": "Thorin Ironfist", "stance": "Ally", "score": 78},
            {"name": "Elandra", "stance": "Ally", "score": 64},
            {"name": "Kael", "stance": "Ally", "score": 52},
            {"name": "Captain Bryn", "stance": "Neutral", "score": 10},
        ],
        "encounter": {"status": "inactive", "title": "No active combat", "summary": "All quiet for now."},
        "timeline": [
            {"turn": 73, "time": "Day 18 • 09:42", "title": "Arrived at Glimmerdeep Pass", "detail": "The party makes its way through the winding mountain trail and reaches the ancient pass.", "kind": "travel"},
            {"turn": 73, "time": "Day 18 • 09:42", "title": "Thorin watches the pass", "actor": "Thorin Ironfist", "detail": "Best keep our eyes open. This place gives me the chills.", "kind": "dialogue"},
            {"turn": 72, "time": "Day 18 • 09:40", "title": "Trail sign found", "detail": "Detected tracks near the northern archway.", "kind": "discovery"},
            {"turn": 69, "time": "Day 18 • 08:15", "title": "Left Frostpine Hollow", "detail": "Followed the northern trail.", "kind": "travel"},
            {"turn": 61, "time": "Day 17 • 21:30", "title": "Long Rest at Frostpine", "detail": "Recovered after the Icefang fight.", "kind": "rest"},
        ],
        "journal": {"entries": []},
        "features": {"autosave": True, "validator": True, "background_soft_audit": True, "llm_narration": True, "image_generation": False, "tts": False, "stt": False, "companions_enabled": True, "permadeath": False},
    }


def _save_created_session(session: dict[str, Any]) -> dict[str, Any]:
    state = session.get("state") if isinstance(session.get("state"), dict) else None
    if state is not None:
        write_ability_coverage_snapshot(state)
    saved = save_session(session, compact=False)
    manifest = saved.get("manifest", {})
    return {"ok": True, "session_id": manifest.get("session_id") or manifest.get("id"), "status": "ready", "session": saved, "game": saved.get("state", {})}


def create_new_game_session(request: RpgNewGameRequest) -> dict[str, Any]:
    now = _utc_now()
    session_id = _new_session_id("rpg")
    state = _new_game_state(request, session_id, now)
    seed = int(request.seed or state.get("metadata", {}).get("seed") or 0)
    setup_payload = _setup_payload_with_identity(request, state["character_identity"])
    session = {
        "manifest": _base_manifest(session_id, state["title"], now, source_template_id=request.campaign_template, kind="new_game"),
        "state": state,
        "setup_payload": setup_payload,
        "simulation_state": _simulation_state_stub(seed),
        "runtime_state": {"active_job_id": None, "last_error": None, "created_from": "new_game"},
    }
    return _save_created_session(session)


def list_rpg_presets() -> dict[str, Any]:
    return {
        "ok": True,
        "presets": [
            {
                "preset_id": DEMO_PRESET_ID,
                "name": "Demo: Glimmerdeep Pass",
                "description": "Level 14 ranger party at Glimmerdeep Pass with quests, equipment, journal, relationships, and world state preloaded.",
                "kind": "in_progress_demo",
                "level": 14,
                "location": "Glimmerdeep Pass",
                "clone_on_start": True,
            }
        ],
    }


def start_rpg_preset(preset_id: str) -> dict[str, Any]:
    if preset_id != DEMO_PRESET_ID:
        return {"ok": False, "error": "unknown_rpg_preset", "preset_id": preset_id}
    now = _utc_now()
    session_id = _new_session_id("rpg_demo")
    state = _demo_state(session_id, now)
    session = {
        "manifest": {
            **_base_manifest(session_id, "Demo: Glimmerdeep Pass", now, source_template_id=preset_id, kind="playable_demo_clone"),
            "created_from_preset": preset_id,
            "preset_name": "Demo: Glimmerdeep Pass",
        },
        "state": state,
        "setup_payload": {"preset_id": preset_id, "mode": "clone_on_start"},
        "simulation_state": _simulation_state_stub(140914),
        "runtime_state": {"active_job_id": None, "last_error": None, "created_from": preset_id},
    }
    return _save_created_session(session)


def continue_rpg_session(session_id: str) -> dict[str, Any]:
    session = load_session(session_id)
    if not session:
        return {"ok": False, "error": "session_not_found", "session_id": session_id}
    return {"ok": True, "session_id": session_id, "status": "ready", "session": session, "game": session.get("state", {})}


def delete_rpg_session(session_id: str) -> dict[str, Any]:
    return archive_session(session_id)


def rename_rpg_session(session_id: str, name: str) -> dict[str, Any]:
    session = load_session(session_id)
    if not session:
        return {"ok": False, "error": "session_not_found", "session_id": session_id}
    manifest = dict(session.get("manifest") or {})
    manifest["title"] = str(name or "").strip() or manifest.get("title") or session_id
    manifest["updated_at"] = _utc_now()
    session["manifest"] = manifest
    saved = save_session(session, compact=False)
    return {"ok": True, "session_id": session_id, "session": saved}
