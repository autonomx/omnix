"""Capability-based RPG ability tree and deterministic effect helpers.

Core rule: every active ability must alter at least one gameplay dimension
through validated deterministic operations. AI may generate fiction later; the
engine owns mechanics, costs, cooldowns, state writes, and validation.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Literal, cast, get_args

from pydantic import BaseModel, Field

Capability = Literal["combat", "recon", "influence", "technical", "survival", "knowledge", "support", "custom"]
PowerSource = Literal["mundane", "martial", "magic", "technology", "psionic", "divine", "occult", "mutation", "mythic", "social_power", "scrap", "custom"]
GameplayDimension = Literal["resources", "information", "relationships", "access", "environment", "position", "narrative", "economy", "world"]
AbilityKind = Literal["active", "passive", "narrative_trait"]
AbilityPurpose = Literal[
    "damage",
    "defense",
    "healing",
    "information_gathering",
    "mobility",
    "social_manipulation",
    "access_bypass",
    "crafting",
    "resource_generation",
    "control",
    "escape",
    "summoning",
    "world_influence",
    "quest_progression",
    "economic_advantage",
    "relationship_building",
    "survival",
    "utility",
]

ALLOWED_CAPABILITIES = set(get_args(Capability))
ALLOWED_POWER_SOURCES = set(get_args(PowerSource))
ALLOWED_DIMENSIONS = set(get_args(GameplayDimension))
ALLOWED_KINDS = set(get_args(AbilityKind))
ALLOWED_PURPOSES = set(get_args(AbilityPurpose))
ALLOWED_EFFECT_OPS = {
    "resource_delta",
    "modify_next_check",
    "apply_status",
    "clear_status",
    "reveal_clue",
    "unlock_dialogue_option",
    "unlock_travel_option",
    "unlock_scene_affordance",
    "modify_relationship",
    "modify_reputation",
    "modify_faction_alert",
    "modify_price_modifier",
    "apply_scene_status",
    "create_hazard",
    "clear_hazard",
    "change_location_state",
    "add_world_rumor",
    "advance_quest_signal",
    "complete_objective",
    "grant_temp_affordance",
}
ALLOWED_COST_RESOURCES = {"hp", "stamina", "mana", "gold", "silver", "copper", "renown"}


class RpgCharacterIdentity(BaseModel):
    genre: str = "classic_fantasy"
    tone: str = "heroic adventure"
    background: str = "Wanderer"
    primary_capability: Capability = "recon"
    secondary_capabilities: list[Capability] = Field(default_factory=list)
    power_source: PowerSource = "martial"
    generated_class_name: str = "Ranger"
    generated_class_summary: str = "A capable character whose talents alter deterministic gameplay dimensions."


class RpgEffectOp(BaseModel):
    dimension: GameplayDimension
    op: str
    target: str | None = None
    target_id: str | None = None
    amount: int | None = None
    resource: str | None = None
    check: str | None = None
    status: str | None = None
    hazard: str | None = None
    clue_tag: str | None = None
    affordance: str | None = None
    option_tag: str | None = None
    duration_turns: int | None = None
    strength: int | None = None
    relationship: str | None = None
    tag: str | None = None
    faction_id: str | None = None
    location_id: str | None = None
    quest_id: str | None = None
    objective_id: str | None = None
    state_key: str | None = None
    state_value: str | int | bool | None = None
    rumor_id: str | None = None
    rumor: str | None = None
    signal: str | None = None


class RpgAbilityDefinition(BaseModel):
    ability_id: str
    kind: AbilityKind = "active"
    name: str
    icon: str = "✦"
    description: str
    capability: Capability
    power_source: PowerSource = "mundane"
    purpose: AbilityPurpose
    dimensions: list[GameplayDimension]
    level_required: int = 1
    rank: int = 1
    max_rank: int = 3
    resource_cost: dict[str, int] = Field(default_factory=dict)
    cooldown_turns: int = 0
    prerequisites: list[str] = Field(default_factory=list)
    targeting: dict[str, Any] = Field(default_factory=dict)
    effect_ops: list[RpgEffectOp] = Field(default_factory=list)
    hooks: list[str] = Field(default_factory=list)
    influence_tags: list[str] = Field(default_factory=list)
    flavor_tags: list[str] = Field(default_factory=list)


class RpgAbilityValidationResult(BaseModel):
    ok: bool
    errors: list[str] = Field(default_factory=list)


class RpgAbilityUseResult(BaseModel):
    ok: bool
    ability_id: str | None = None
    name: str | None = None
    detail: str
    error: str | None = None
    effects: list[dict[str, Any]] = Field(default_factory=list)


BUILD_IDENTITY_DEFAULTS: dict[str, dict[str, Any]] = {
    "balanced_adventurer": {"primary_capability": "recon", "secondary_capabilities": ["survival", "combat"], "power_source": "mundane", "class_name": "Adventurer"},
    "warrior": {"primary_capability": "combat", "secondary_capabilities": ["survival", "influence"], "power_source": "martial", "class_name": "Champion"},
    "ranger": {"primary_capability": "recon", "secondary_capabilities": ["survival", "combat"], "power_source": "martial", "class_name": "Ranger"},
    "silver_tongue": {"primary_capability": "influence", "secondary_capabilities": ["knowledge", "recon"], "power_source": "social_power", "class_name": "Diplomat"},
}

GENRE_NORMALIZATION = {
    "classic_fantasy": "classic_fantasy",
    "fantasy": "classic_fantasy",
    "tavern_mystery": "classic_fantasy",
    "bandit_road": "classic_fantasy",
    "wilderness_survival": "classic_fantasy",
    "dungeon_delve": "classic_fantasy",
    "dark_fantasy": "dark_fantasy",
    "cyberpunk": "cyberpunk",
    "space_opera": "space_opera",
    "post_apocalyptic": "post_apocalyptic",
    "modern_occult": "modern_occult",
    "detective_noir": "detective_noir",
    "political_intrigue": "political_intrigue",
    "survival_horror": "survival_horror",
    "sandbox": "sandbox",
}

GENRE_CLASS_NAMES = {
    ("classic_fantasy", "knowledge", "magic"): "Runebinder",
    ("classic_fantasy", "combat", "martial"): "Champion",
    ("classic_fantasy", "recon", "martial"): "Ranger",
    ("classic_fantasy", "recon", "mundane"): "Ranger",
    ("cyberpunk", "technical", "technology"): "Netrunner",
    ("cyberpunk", "combat", "technology"): "Street Samurai",
    ("cyberpunk", "recon", "technology"): "Ghostwalker",
    ("detective_noir", "recon", "mundane"): "Private Eye",
    ("political_intrigue", "influence", "social_power"): "Court Schemer",
    ("post_apocalyptic", "survival", "scrap"): "Scavenger",
    ("space_opera", "knowledge", "psionic"): "Psionic",
    ("space_opera", "technical", "technology"): "Science Officer",
    ("modern_occult", "knowledge", "occult"): "Ritualist",
    ("survival_horror", "survival", "mundane"): "Survivor",
}

TEMPLATE_FAMILIES: dict[tuple[str, str, str], dict[str, Any]] = {
    ("classic_fantasy", "knowledge", "magic"): {
        "family_id": "classic_fantasy_knowledge_magic_v1",
        "class_name": "Runebinder",
        "category_name": "Runes & Arcana",
        "passive": ("runic_memory", "Runic Memory", "on_investigation_check", "Improves symbol and lore checks."),
        "trait": ("academy_exile", "Academy Exile", ["recognize_arcane_orders", "unlock_mage_dialogue_paths"]),
    },
    ("classic_fantasy", "combat", "martial"): {
        "family_id": "classic_fantasy_combat_martial_v1",
        "class_name": "Champion",
        "category_name": "Arms & Command",
        "passive": ("shield_drilled", "Shield Drilled", "on_combat_start", "Improves opening defense."),
        "trait": ("oathbound_warrior", "Oathbound Warrior", ["recognized_by_soldiers", "unlock_honor_dialogue_paths"]),
    },
    ("classic_fantasy", "recon", "martial"): {
        "family_id": "classic_fantasy_recon_martial_v1",
        "class_name": "Ranger",
        "category_name": "Trail & Bowcraft",
        "passive": ("keen_trail_eye", "Keen Trail Eye", "on_investigation_check", "Improves track and terrain reads."),
        "trait": ("borderlands_guide", "Borderlands Guide", ["recognize_wilderness_signs", "unlock_ranger_dialogue_paths"]),
    },
    ("classic_fantasy", "recon", "mundane"): {
        "family_id": "classic_fantasy_recon_mundane_v1",
        "class_name": "Ranger",
        "category_name": "Trailcraft",
        "passive": ("fieldcraft", "Fieldcraft", "on_enter_location", "Improves mundane travel reads."),
        "trait": ("roadwise_wanderer", "Roadwise Wanderer", ["recognize_road_signs", "unlock_travel_story_paths"]),
    },
    ("cyberpunk", "technical", "technology"): {
        "family_id": "cyberpunk_technical_technology_v1",
        "class_name": "Netrunner",
        "category_name": "Systems Intrusion",
        "passive": ("packet_sense", "Packet Sense", "on_investigation_check", "Improves device and network reads."),
        "trait": ("corporate_defector", "Corporate Defector", ["recognize_corp_protocols", "unlock_corporate_dialogue_paths"]),
    },
    ("cyberpunk", "combat", "technology"): {
        "family_id": "cyberpunk_combat_technology_v1",
        "class_name": "Street Samurai",
        "category_name": "Augmented Combat",
        "passive": ("cybernetic_reflexes", "Cybernetic Reflexes", "on_combat_start", "Improves initiative and position checks."),
        "trait": ("street_code", "Street Code", ["recognize_gang_signals", "unlock_street_contact_paths"]),
    },
    ("detective_noir", "recon", "mundane"): {
        "family_id": "detective_noir_recon_mundane_v1",
        "class_name": "Private Eye",
        "category_name": "Casework",
        "passive": ("keen_eye", "Keen Eye", "on_investigation_check", "Improves clue discovery."),
        "trait": ("former_detective", "Former Detective", ["recognize_police_procedure", "unlock_detective_dialogue_paths"]),
    },
    ("political_intrigue", "influence", "social_power"): {
        "family_id": "political_intrigue_influence_social_power_v1",
        "class_name": "Court Schemer",
        "category_name": "Court Leverage",
        "passive": ("courtly_read", "Courtly Read", "on_social_check", "Improves social pressure reads."),
        "trait": ("disgraced_envoy", "Disgraced Envoy", ["recognize_court_factions", "unlock_court_dialogue_paths"]),
    },
    ("post_apocalyptic", "survival", "scrap"): {
        "family_id": "post_apocalyptic_survival_scrap_v1",
        "class_name": "Scavenger",
        "category_name": "Scrapcraft",
        "passive": ("scrap_sense", "Scrap Sense", "on_enter_location", "Improves salvage discovery."),
        "trait": ("wasteland_survivor", "Wasteland Survivor", ["recognize_salvage_value", "unlock_wasteland_paths"]),
    },
    ("space_opera", "knowledge", "psionic"): {
        "family_id": "space_opera_knowledge_psionic_v1",
        "class_name": "Psionic",
        "category_name": "Psi Studies",
        "passive": ("psionic_focus", "Psionic Focus", "on_investigation_check", "Improves strange-signal interpretation."),
        "trait": ("trained_mind", "Trained Mind", ["recognize_psionic_echoes", "unlock_psionic_dialogue_paths"]),
    },
    ("space_opera", "technical", "technology"): {
        "family_id": "space_opera_technical_technology_v1",
        "class_name": "Science Officer",
        "category_name": "Ship Systems",
        "passive": ("systems_discipline", "Systems Discipline", "on_investigation_check", "Improves ship and station diagnostics."),
        "trait": ("fleet_academy", "Fleet Academy", ["recognize_fleet_protocols", "unlock_science_dialogue_paths"]),
    },
    ("modern_occult", "knowledge", "occult"): {
        "family_id": "modern_occult_knowledge_occult_v1",
        "class_name": "Ritualist",
        "category_name": "Rites & Omens",
        "passive": ("occult_index", "Occult Index", "on_investigation_check", "Improves cult and ritual clue reads."),
        "trait": ("cult_survivor", "Cult Survivor", ["recognize_cult_symbols", "unlock_cult_dialogue_paths"]),
    },
    ("survival_horror", "survival", "mundane"): {
        "family_id": "survival_horror_survival_mundane_v1",
        "class_name": "Survivor",
        "category_name": "Last Light",
        "passive": ("steady_breathing", "Steady Breathing", "on_turn_start", "Improves panic and fatigue recovery."),
        "trait": ("sole_survivor", "Sole Survivor", ["recognize_horror_tells", "unlock_survivor_dialogue_paths"]),
    },
}

# Template abilities are capability-based but keep the first six recon labels
# aligned with the existing UI hotbar until the full tree UI lands.
ABILITY_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "recon": [
        {"ability_id": "recon_aimed_shot", "name": "Aimed Shot", "icon": "✦", "description": "Take careful aim and turn position into a decisive opening.", "purpose": "damage", "dimensions": ["position", "resources"], "resource_cost": {"stamina": 10}, "cooldown_turns": 1, "effect_ops": [{"dimension": "position", "op": "modify_next_check", "check": "ranged_attack", "amount": 2, "duration_turns": 1}, {"dimension": "resources", "op": "resource_delta", "target": "target", "resource": "hp", "amount": -10}]},
        {"ability_id": "recon_frost_arrow", "name": "Frost Arrow", "icon": "↯", "description": "Slow a dangerous target and create a safer window to move.", "purpose": "control", "dimensions": ["position", "environment"], "resource_cost": {"mana": 12}, "cooldown_turns": 2, "effect_ops": [{"dimension": "position", "op": "modify_next_check", "check": "enemy_mobility", "amount": -2, "duration_turns": 2}, {"dimension": "environment", "op": "apply_scene_status", "status": "frosted_ground", "duration_turns": 2}]},
        {"ability_id": "recon_camouflage", "name": "Camouflage", "icon": "☘", "description": "Blend into terrain and improve stealth or ambush positioning.", "purpose": "escape", "dimensions": ["position", "environment"], "resource_cost": {"stamina": 8}, "cooldown_turns": 2, "effect_ops": [{"dimension": "position", "op": "modify_next_check", "check": "stealth", "amount": 2, "duration_turns": 3}, {"dimension": "environment", "op": "apply_scene_status", "status": "concealment_found", "duration_turns": 3}]},
        {"ability_id": "recon_radiant_flare", "name": "Radiant Flare", "icon": "✹", "description": "Reveal threats, clues, or hidden movement in the immediate area.", "purpose": "information_gathering", "dimensions": ["information", "environment"], "resource_cost": {"mana": 15}, "cooldown_turns": 3, "effect_ops": [{"dimension": "information", "op": "reveal_clue", "clue_tag": "hidden_threat", "strength": 1}, {"dimension": "environment", "op": "apply_scene_status", "status": "illuminated", "duration_turns": 2}]},
        {"ability_id": "recon_volley", "name": "Volley", "icon": "⟡", "description": "Pressure clustered enemies or force movement across a zone.", "purpose": "control", "dimensions": ["position", "resources"], "resource_cost": {"stamina": 15}, "cooldown_turns": 2, "level_required": 2, "effect_ops": [{"dimension": "position", "op": "grant_temp_affordance", "affordance": "suppress_area", "duration_turns": 1}, {"dimension": "resources", "op": "resource_delta", "target": "target", "resource": "hp", "amount": -6}]},
        {"ability_id": "recon_dash", "name": "Dash", "icon": "⇥", "description": "Reposition quickly before danger closes in.", "purpose": "mobility", "dimensions": ["position"], "resource_cost": {"stamina": 12}, "cooldown_turns": 1, "effect_ops": [{"dimension": "position", "op": "grant_temp_affordance", "affordance": "rapid_reposition", "duration_turns": 1}]},
        {"ability_id": "recon_trail_sense", "name": "Trail Sense", "icon": "⌕", "description": "Read tracks, patterns, and subtle signs in the current scene.", "purpose": "information_gathering", "dimensions": ["information", "narrative"], "resource_cost": {"stamina": 5}, "effect_ops": [{"dimension": "information", "op": "reveal_clue", "clue_tag": "local_tracks", "strength": 1}, {"dimension": "narrative", "op": "unlock_dialogue_option", "option_tag": "ask_about_tracks", "duration_turns": 3}]},
    ],
    "combat": [
        {"ability_id": "combat_guarded_strike", "name": "Guarded Strike", "icon": "⚔", "description": "Attack while keeping guard high.", "purpose": "damage", "dimensions": ["resources", "position"], "resource_cost": {"stamina": 10}, "cooldown_turns": 1, "effect_ops": [{"dimension": "resources", "op": "resource_delta", "target": "target", "resource": "hp", "amount": -12}, {"dimension": "position", "op": "modify_next_check", "check": "defense", "amount": 1, "duration_turns": 1}]},
        {"ability_id": "combat_rallying_presence", "name": "Rallying Presence", "icon": "▲", "description": "Steady allies and recover momentum.", "purpose": "defense", "dimensions": ["relationships", "resources"], "resource_cost": {"stamina": 8}, "effect_ops": [{"dimension": "relationships", "op": "modify_relationship", "relationship": "party_morale", "amount": 2}, {"dimension": "resources", "op": "resource_delta", "target": "self", "resource": "stamina", "amount": 4}]},
    ],
    "technical": [
        {"ability_id": "technical_signal_probe", "name": "Signal Probe", "icon": "⌁", "description": "Scan systems or devices for a weak point.", "purpose": "information_gathering", "dimensions": ["information", "access"], "resource_cost": {"mana": 6}, "effect_ops": [{"dimension": "information", "op": "reveal_clue", "clue_tag": "system_weakness", "strength": 1}, {"dimension": "access", "op": "unlock_scene_affordance", "affordance": "technical_bypass_hint", "duration_turns": 3}]},
        {"ability_id": "technical_camera_loop", "name": "Camera Loop", "icon": "◉", "description": "Spoof surveillance to create a movement window.", "purpose": "access_bypass", "dimensions": ["access", "environment"], "resource_cost": {"mana": 10}, "cooldown_turns": 3, "level_required": 2, "prerequisites": ["technical_signal_probe"], "effect_ops": [{"dimension": "access", "op": "unlock_scene_affordance", "affordance": "cross_monitored_route", "duration_turns": 3}, {"dimension": "environment", "op": "apply_scene_status", "status": "surveillance_looped", "duration_turns": 3}]},
    ],
    "knowledge": [
        {"ability_id": "knowledge_read_the_room", "name": "Read the Room", "icon": "◇", "description": "Notice hidden patterns, symbols, or social pressure.", "purpose": "information_gathering", "dimensions": ["information", "narrative"], "resource_cost": {"mana": 5}, "effect_ops": [{"dimension": "information", "op": "reveal_clue", "clue_tag": "hidden_context", "strength": 1}, {"dimension": "narrative", "op": "unlock_dialogue_option", "option_tag": "press_hidden_context", "duration_turns": 2}]},
        {"ability_id": "knowledge_warding_formula", "name": "Warding Formula", "icon": "✹", "description": "Use knowledge to create a short-lived protection.", "purpose": "defense", "dimensions": ["environment", "position"], "resource_cost": {"mana": 12}, "cooldown_turns": 2, "effect_ops": [{"dimension": "environment", "op": "apply_scene_status", "status": "warded", "duration_turns": 3}, {"dimension": "position", "op": "modify_next_check", "check": "defense", "amount": 2, "duration_turns": 3}]},
    ],
    "influence": [
        {"ability_id": "influence_call_in_favor", "name": "Call in a Favor", "icon": "☯", "description": "Spend social capital to open a route or concession.", "purpose": "relationship_building", "dimensions": ["relationships", "access"], "resource_cost": {"mana": 5}, "cooldown_turns": 2, "effect_ops": [{"dimension": "relationships", "op": "modify_relationship", "relationship": "local_contacts", "amount": 1}, {"dimension": "access", "op": "unlock_dialogue_option", "option_tag": "call_in_favor", "duration_turns": 3}]},
        {"ability_id": "influence_cutting_insight", "name": "Cutting Insight", "icon": "✧", "description": "Name the pressure point in a negotiation.", "purpose": "social_manipulation", "dimensions": ["information", "relationships"], "resource_cost": {"stamina": 6}, "effect_ops": [{"dimension": "information", "op": "reveal_clue", "clue_tag": "social_leverage", "strength": 1}, {"dimension": "relationships", "op": "modify_reputation", "amount": 1}]},
    ],
    "survival": [
        {"ability_id": "survival_make_camp", "name": "Make Camp", "icon": "♨", "description": "Create a safer short rest point and recover stamina.", "purpose": "survival", "dimensions": ["resources", "environment"], "resource_cost": {}, "cooldown_turns": 4, "effect_ops": [{"dimension": "resources", "op": "resource_delta", "target": "self", "resource": "stamina", "amount": 12}, {"dimension": "environment", "op": "apply_scene_status", "status": "safe_camp", "duration_turns": 4}]},
        {"ability_id": "survival_scavenge", "name": "Scavenge", "icon": "▣", "description": "Search for usable scraps, supplies, or signs.", "purpose": "resource_generation", "dimensions": ["resources", "information", "narrative"], "resource_cost": {"stamina": 6}, "effect_ops": [{"dimension": "information", "op": "reveal_clue", "clue_tag": "salvage_source", "strength": 1}, {"dimension": "narrative", "op": "grant_temp_affordance", "affordance": "found_minor_supplies", "duration_turns": 1}]},
    ],
    "support": [
        {"ability_id": "support_field_aid", "name": "Field Aid", "icon": "✚", "description": "Stabilize injuries and restore HP.", "purpose": "healing", "dimensions": ["resources"], "resource_cost": {"mana": 8}, "cooldown_turns": 2, "effect_ops": [{"dimension": "resources", "op": "resource_delta", "target": "self", "resource": "hp", "amount": 18}]},
        {"ability_id": "support_steady_voice", "name": "Steady Voice", "icon": "☼", "description": "Calm panic and ease the next group action.", "purpose": "defense", "dimensions": ["relationships", "position"], "resource_cost": {"stamina": 6}, "effect_ops": [{"dimension": "relationships", "op": "modify_relationship", "relationship": "party_morale", "amount": 2}, {"dimension": "position", "op": "modify_next_check", "check": "group_action", "amount": 1, "duration_turns": 2}]},
    ],
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _norm(value: Any) -> str:
    return str(value or "").strip().casefold().replace(" ", "_")


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _is_plain_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _non_empty_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def normalize_genre(value: Any) -> str:
    return GENRE_NORMALIZATION.get(_norm(value) or "classic_fantasy", _norm(value) or "classic_fantasy")


def normalize_capability(value: Any, fallback: Capability = "recon") -> Capability:
    raw = _norm(value)
    return cast(Capability, raw) if raw in ALLOWED_CAPABILITIES else fallback


def normalize_power_source(value: Any, fallback: PowerSource = "mundane") -> PowerSource:
    raw = _norm(value)
    return cast(PowerSource, raw) if raw in ALLOWED_POWER_SOURCES else fallback


def infer_character_identity(request_payload: dict[str, Any], build_id: str = "balanced_adventurer") -> dict[str, Any]:
    player = _safe_dict(request_payload.get("player"))
    defaults = BUILD_IDENTITY_DEFAULTS.get(build_id, BUILD_IDENTITY_DEFAULTS["balanced_adventurer"])
    genre = normalize_genre(request_payload.get("genre") or request_payload.get("campaign_template"))
    primary = normalize_capability(request_payload.get("primary_capability"), defaults["primary_capability"])
    secondary = [normalize_capability(value, "custom") for value in _safe_list(request_payload.get("secondary_capabilities"))]
    if not secondary:
        secondary = list(defaults.get("secondary_capabilities", []))
    secondary = [value for value in secondary if value != primary and value in ALLOWED_CAPABILITIES][:3]
    power_source = normalize_power_source(request_payload.get("power_source"), defaults["power_source"])
    class_name = str(request_payload.get("generated_class_name") or "").strip() or GENRE_CLASS_NAMES.get((genre, primary, power_source)) or defaults.get("class_name") or primary.title()
    summary = str(request_payload.get("generated_class_summary") or "").strip() or f"A {class_name} whose abilities alter deterministic gameplay dimensions."
    return RpgCharacterIdentity(
        genre=genre,
        tone=str(request_payload.get("tone") or "heroic adventure"),
        background=str(player.get("background") or request_payload.get("background") or "Wanderer"),
        primary_capability=primary,
        secondary_capabilities=secondary,
        power_source=power_source,
        generated_class_name=class_name,
        generated_class_summary=summary,
    ).model_dump(mode="json")


def _ability(data: dict[str, Any], *, capability: str, power_source: str) -> dict[str, Any]:
    payload = dict(data)
    payload.setdefault("kind", "active")
    payload.setdefault("capability", capability)
    payload.setdefault("power_source", power_source)
    payload.setdefault("level_required", 1)
    payload.setdefault("rank", 1)
    payload.setdefault("max_rank", 3)
    payload.setdefault("resource_cost", {})
    payload.setdefault("cooldown_turns", 0)
    payload.setdefault("prerequisites", [])
    payload.setdefault("targeting", {})
    payload.setdefault("flavor_tags", [])
    return RpgAbilityDefinition.model_validate(payload).model_dump(mode="json")


def _category_label(capability: str, power_source: str) -> str:
    if capability == "technical" and power_source == "technology":
        return "Systems & Devices"
    labels = {
        "combat": "Combat Discipline",
        "recon": "Recon & Position",
        "influence": "Leverage & Influence",
        "survival": "Survival Craft",
        "knowledge": "Knowledge & Signs",
        "support": "Support & Recovery",
    }
    return labels.get(capability, capability.replace("_", " ").title())


def _family_bonus_abilities(family: dict[str, Any], *, capability: str, power_source: str) -> list[dict[str, Any]]:
    passive_id, passive_name, hook, passive_description = family["passive"]
    trait_id, trait_name, influence_tags = family["trait"]
    return [
        _ability(
            {
                "ability_id": passive_id,
                "kind": "passive",
                "name": passive_name,
                "icon": "+",
                "description": passive_description,
                "purpose": "utility",
                "dimensions": ["information", "position"],
                "resource_cost": {},
                "cooldown_turns": 0,
                "max_rank": 3,
                "hooks": [hook],
                "effect_ops": [],
            },
            capability=capability,
            power_source=power_source,
        ),
        _ability(
            {
                "ability_id": trait_id,
                "kind": "narrative_trait",
                "name": trait_name,
                "icon": "*",
                "description": "A grounded background trait that unlocks deterministic story affordances.",
                "purpose": "information_gathering",
                "dimensions": ["information", "relationships", "narrative"],
                "resource_cost": {},
                "cooldown_turns": 0,
                "max_rank": 1,
                "influence_tags": list(influence_tags),
                "effect_ops": [],
            },
            capability=capability,
            power_source=power_source,
        ),
    ]


def build_ability_tree(identity: dict[str, Any], *, seed: int | None = None) -> dict[str, Any]:
    primary = normalize_capability(identity.get("primary_capability"), "recon")
    secondary = [normalize_capability(value, "custom") for value in _safe_list(identity.get("secondary_capabilities"))]
    power_source = normalize_power_source(identity.get("power_source"), "mundane")
    genre = normalize_genre(identity.get("genre"))
    family = TEMPLATE_FAMILIES.get((genre, primary, power_source))
    capabilities = [primary, *[capability for capability in secondary if capability != primary]][:3]
    categories: list[dict[str, Any]] = []
    all_abilities: list[dict[str, Any]] = []
    for capability in capabilities:
        abilities = [_ability(data, capability=capability, power_source=power_source) for data in ABILITY_TEMPLATES.get(capability, ABILITY_TEMPLATES["recon"])]
        if capability == primary and family:
            abilities.extend(_family_bonus_abilities(family, capability=capability, power_source=power_source))
        category_name = str(family.get("category_name")) if family and capability == primary else _category_label(capability, power_source)
        categories.append({"category_id": capability, "name": category_name, "capability": capability, "dimensions": sorted({dimension for ability in abilities for dimension in ability.get("dimensions", [])}), "abilities": [ability["ability_id"] for ability in abilities]})
        all_abilities.extend(abilities)
    starting_unlocks = [ability["ability_id"] for ability in all_abilities if ability.get("kind") == "active" and int(ability.get("level_required") or 1) <= 1]
    recommended_hotbar = [ability_id for ability_id in starting_unlocks[:6]]
    tree_id = f"ability_tree_{genre}_{primary}_{power_source}_v1"
    if seed is not None:
        tree_id = f"{tree_id}_{abs(int(seed)) % 100000:05d}"
    tree = {
        "tree_id": tree_id,
        "version": 1,
        "source": "template_family_v1" if family else "template_capability_v1",
        "template_family": family.get("family_id") if family else None,
        "class_name": str(identity.get("generated_class_name") or (family or {}).get("class_name") or primary.title()),
        "genre": genre,
        "primary_capability": primary,
        "secondary_capabilities": secondary,
        "power_source": power_source,
        "dimensions": sorted({dimension for ability in all_abilities for dimension in ability.get("dimensions", [])}),
        "categories": categories,
        "abilities": all_abilities,
        "starting_unlocks": starting_unlocks,
        "recommended_hotbar": recommended_hotbar,
        "design_rule": "Every active ability must alter at least one gameplay dimension through validated deterministic operations.",
    }
    validation = validate_ability_tree(tree)
    if not validation.ok:
        raise ValueError("Invalid ability tree: " + "; ".join(validation.errors))
    return tree


def build_initial_ability_state(tree: dict[str, Any], *, level: int = 1) -> dict[str, Any]:
    abilities = _safe_list(tree.get("abilities"))
    unlocked = [ability["ability_id"] for ability in abilities if ability.get("kind") == "active" and int(ability.get("level_required") or 1) <= level]
    ranks = {ability_id: 1 for ability_id in unlocked}
    recommended = [ability_id for ability_id in _safe_list(tree.get("recommended_hotbar")) if ability_id in unlocked]
    hotbar_ids = [*recommended, *[ability_id for ability_id in unlocked if ability_id not in recommended]][:6]
    hotbar = {str(index + 1): ability_id for index, ability_id in enumerate(hotbar_ids)}
    return {"ability_points": max(0, int(level) - 1), "unlocked": unlocked, "ranks": ranks, "cooldowns": {}, "active_effects": [], "hotbar": hotbar}


def build_progression_package(request_payload: dict[str, Any], *, build_id: str, level: int = 1, seed: int | None = None) -> dict[str, Any]:
    identity = infer_character_identity(request_payload, build_id=build_id)
    tree = build_ability_tree(identity, seed=seed)
    ability_state = build_initial_ability_state(tree, level=level)
    return {"character_identity": identity, "ability_tree": tree, "ability_state": ability_state, "hotbar": ability_state["hotbar"]}


def validate_ability(ability: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    ability_id = str(ability.get("ability_id") or "").strip()
    kind = str(ability.get("kind") or "active")
    dimensions = _safe_list(ability.get("dimensions"))
    effect_ops = _safe_list(ability.get("effect_ops"))
    resource_cost = ability.get("resource_cost")
    cooldown_turns = ability.get("cooldown_turns", 0)
    level_required = ability.get("level_required", 1)
    rank = ability.get("rank", 1)
    max_rank = ability.get("max_rank", 3)
    prerequisites = ability.get("prerequisites", [])
    if not ability_id:
        errors.append("missing ability_id")
    if kind not in ALLOWED_KINDS:
        errors.append(f"{ability_id}: unsupported kind {kind}")
    if ability.get("capability") not in ALLOWED_CAPABILITIES:
        errors.append(f"{ability_id}: unsupported capability {ability.get('capability')}")
    if ability.get("power_source") not in ALLOWED_POWER_SOURCES:
        errors.append(f"{ability_id}: unsupported power_source {ability.get('power_source')}")
    if ability.get("purpose") not in ALLOWED_PURPOSES:
        errors.append(f"{ability_id}: unsupported purpose {ability.get('purpose')}")
    if not dimensions or any(dimension not in ALLOWED_DIMENSIONS for dimension in dimensions):
        errors.append(f"{ability_id}: invalid dimensions")
    if kind == "active" and not effect_ops:
        errors.append(f"{ability_id}: active ability has no effect_ops")
    if kind == "narrative_trait" and not effect_ops:
        if not (_non_empty_strings(ability.get("influence_tags")) or _non_empty_strings(ability.get("hooks"))):
            errors.append(f"{ability_id}: narrative_trait without effect_ops requires deterministic influence_tags or hooks")
    if not isinstance(resource_cost, dict):
        errors.append(f"{ability_id}: invalid resource_cost")
    else:
        for resource, cost in resource_cost.items():
            if resource not in ALLOWED_COST_RESOURCES:
                errors.append(f"{ability_id}: invalid cost resource {resource}")
            if not _is_plain_int(cost) or cost < 0:
                errors.append(f"{ability_id}: invalid cost value for {resource}")
    if not _is_plain_int(cooldown_turns) or cooldown_turns < 0:
        errors.append(f"{ability_id}: invalid cooldown_turns")
    if not _is_plain_int(level_required) or level_required < 1:
        errors.append(f"{ability_id}: invalid level_required")
    if not _is_plain_int(rank) or rank < 1:
        errors.append(f"{ability_id}: invalid rank")
    if not _is_plain_int(max_rank) or max_rank < 1:
        errors.append(f"{ability_id}: invalid max_rank")
    if _is_plain_int(rank) and _is_plain_int(max_rank) and rank > max_rank:
        errors.append(f"{ability_id}: rank exceeds max_rank")
    if not isinstance(prerequisites, list):
        errors.append(f"{ability_id}: invalid prerequisites")
    else:
        seen_prerequisites: set[str] = set()
        for prerequisite in prerequisites:
            if not isinstance(prerequisite, str) or not prerequisite.strip():
                errors.append(f"{ability_id}: invalid prerequisite {prerequisite}")
                continue
            if prerequisite == ability_id:
                errors.append(f"{ability_id}: prerequisite cannot reference itself")
            if prerequisite in seen_prerequisites:
                errors.append(f"{ability_id}: duplicate prerequisite {prerequisite}")
            seen_prerequisites.add(prerequisite)
    for op in effect_ops:
        record = _safe_dict(op)
        if record.get("dimension") not in ALLOWED_DIMENSIONS:
            errors.append(f"{ability_id}: effect has invalid dimension")
        if record.get("dimension") not in dimensions:
            errors.append(f"{ability_id}: effect dimension missing from ability dimensions")
        if record.get("op") not in ALLOWED_EFFECT_OPS:
            errors.append(f"{ability_id}: unsupported effect op {record.get('op')}")
    return errors


def validate_ability_tree(tree: dict[str, Any]) -> RpgAbilityValidationResult:
    errors: list[str] = []
    seen: set[str] = set()
    for ability in _safe_list(tree.get("abilities")):
        ability_id = str(_safe_dict(ability).get("ability_id") or "")
        if ability_id in seen:
            errors.append(f"duplicate ability_id {ability_id}")
        seen.add(ability_id)
        errors.extend(validate_ability(_safe_dict(ability)))
    for ability in _safe_list(tree.get("abilities")):
        for prerequisite in _safe_list(_safe_dict(ability).get("prerequisites")):
            if prerequisite not in seen:
                errors.append(f"{ability.get('ability_id')}: missing prerequisite {prerequisite}")
    return RpgAbilityValidationResult(ok=not errors, errors=errors)


def _ability_index(tree: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(ability.get("ability_id")): _safe_dict(ability) for ability in _safe_list(tree.get("abilities"))}


def _find_ability(state: dict[str, Any], *, ability_name: str | None = None, hotbar_slot: str | int | None = None) -> dict[str, Any] | None:
    index = _ability_index(_safe_dict(state.get("ability_tree")))
    ability_state = _safe_dict(state.get("ability_state"))
    hotbar = _safe_dict(state.get("hotbar")) or _safe_dict(ability_state.get("hotbar"))
    if hotbar_slot is not None and str(hotbar_slot) in hotbar:
        return index.get(str(hotbar[str(hotbar_slot)]))
    wanted = _norm(ability_name)
    if not wanted:
        return None
    for ability in index.values():
        if _norm(ability.get("name")) == wanted or _norm(ability.get("ability_id")) == wanted:
            return ability
    return next((ability for ability in index.values() if wanted in _norm(ability.get("name")) or wanted in _norm(ability.get("ability_id"))), None)


def _player(state: dict[str, Any]) -> dict[str, Any]:
    player = _safe_dict(state.get("player"))
    state["player"] = player
    return player


def _resource_metric(player: dict[str, Any], resource: str) -> dict[str, Any]:
    resources = _safe_dict(player.get("resources"))
    player["resources"] = resources
    metric = _safe_dict(resources.get(resource))
    metric.setdefault("current", 0)
    metric.setdefault("max", metric.get("current", 0))
    resources[resource] = metric
    return metric


def _append(target: dict[str, Any], key: str, value: dict[str, Any], limit: int = 20) -> None:
    values = _safe_list(target.get(key))
    values.insert(0, value)
    target[key] = values[:limit]


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _target_unavailable(op_name: str, target_name: str, detail: str = "") -> dict[str, Any]:
    result = {"applied": False, "error": "target_unavailable", "op": op_name, "target": target_name}
    if detail:
        result["detail"] = detail
    return result


def _mechanics(state: dict[str, Any]) -> dict[str, Any]:
    mechanics = _safe_dict(state.get("mechanics"))
    state["mechanics"] = mechanics
    return mechanics


def _record_effect_trace(state: dict[str, Any], ability: dict[str, Any], op: dict[str, Any], result: dict[str, Any]) -> None:
    trace = {
        "ability_id": ability.get("ability_id"),
        "ability_name": ability.get("name"),
        "dimension": result.get("dimension") or op.get("dimension"),
        "op": result.get("op") or op.get("op"),
        "target": result.get("target") or op.get("target"),
        "applied": result.get("applied") is not False,
        "error": result.get("error"),
        "created_at": _utc_now(),
    }
    _append(_mechanics(state), "ability_effect_trace", trace, limit=80)


def _append_player_visible_ability_event(state: dict[str, Any], ability: dict[str, Any], effects: list[dict[str, Any]]) -> None:
    if not effects:
        return
    applied = [effect for effect in effects if effect.get("applied") is not False]
    if not applied:
        return
    turn = _safe_int(state.get("current_turn") or state.get("turn_count"), 0)
    event = {
        "turn": turn,
        "time": _safe_dict(state.get("world")).get("time") or f"Turn {turn}",
        "title": f"Ability effect: {ability.get('name')}",
        "actor": "Player",
        "detail": f"{ability.get('name')} changed {', '.join(str(value) for value in ability.get('dimensions', []))}.",
        "kind": "ability_effect",
        "effects": effects,
        "timestamp": _utc_now(),
    }
    timeline = _safe_list(state.get("timeline"))
    state["timeline"] = [event, *timeline][:50]
    journal = _safe_dict(state.get("journal"))
    entries = _safe_list(journal.get("entries"))
    journal["entries"] = [event, *entries][:50]
    state["journal"] = journal


def _status_bucket(state: dict[str, Any], target_name: str) -> tuple[dict[str, Any], str]:
    if target_name in {"", "self", "player", "the current situation"}:
        return _player(state), "statuses"
    encounter = _safe_dict(state.get("encounter"))
    state["encounter"] = encounter
    return encounter, "target_statuses"


def _resource_delta(state: dict[str, Any], resource: str, amount: int, *, target: str | None = None) -> dict[str, Any]:
    if target and target not in {"self", "player", "party", "the current situation"}:
        encounter = _safe_dict(state.get("encounter"))
        _append(encounter, "target_effects", {"target": target, "resource": resource, "amount": amount, "created_at": _utc_now()})
        state["encounter"] = encounter
        return {"target": target, "resource": resource, "amount": amount, "applied": True, "mode": "target_trace"}
    metric = _resource_metric(_player(state), resource)
    before = int(metric.get("current") or 0)
    maximum = int(metric.get("max") or before)
    metric["current"] = max(0, min(maximum, before + int(amount)))
    return {"target": "self", "resource": resource, "before": before, "after": metric["current"], "max": maximum, "applied": True}


def _apply_status(state: dict[str, Any], ability: dict[str, Any], op: dict[str, Any], target_name: str) -> dict[str, Any]:
    status = _text(op.get("status") or op.get("tag"), "status")
    target_state, key = _status_bucket(state, target_name)
    _append(
        target_state,
        key,
        {
            "status": status,
            "target": target_name,
            "source": ability.get("name"),
            "duration_turns": op.get("duration_turns"),
            "created_at": _utc_now(),
        },
    )
    return {"status": status, "target": target_name, "applied": True}


def _clear_status(state: dict[str, Any], op: dict[str, Any], target_name: str) -> dict[str, Any]:
    status = _text(op.get("status") or op.get("tag"), "status")
    target_state, key = _status_bucket(state, target_name)
    before = _safe_list(target_state.get(key))
    after = [item for item in before if _safe_dict(item).get("status") != status]
    target_state[key] = after
    return {"status": status, "target": target_name, "removed": len(before) - len(after), "applied": True}


def _modify_relationship(state: dict[str, Any], ability: dict[str, Any], op: dict[str, Any], target_name: str) -> dict[str, Any]:
    relationships = _safe_list(state.get("relationships"))
    relation_name = _text(op.get("relationship") or op.get("target_id") or target_name, "local_contacts")
    amount = _safe_int(op.get("amount"))
    for relation in relationships:
        if _safe_dict(relation).get("name") == relation_name:
            before = _safe_int(relation.get("score"))
            relation["score"] = before + amount
            relation.setdefault("stance", "Noted")
            break
    else:
        before = 0
        relationships.append({"name": relation_name, "stance": "Noted", "score": amount})
    state["relationships"] = relationships
    return {"relationship": relation_name, "before": before, "after": before + amount, "source": ability.get("name"), "applied": True}


def _modify_reputation(state: dict[str, Any], op: dict[str, Any]) -> dict[str, Any]:
    world = _safe_dict(state.get("world"))
    reputation = _safe_dict(world.get("reputation"))
    before = _safe_int(reputation.get("score"))
    reputation["score"] = before + _safe_int(op.get("amount"))
    reputation.setdefault("label", "Unknown")
    world["reputation"] = reputation
    state["world"] = world
    return {"before": before, "after": reputation["score"], "applied": True}


def _modify_faction_alert(state: dict[str, Any], ability: dict[str, Any], op: dict[str, Any], target_name: str) -> dict[str, Any]:
    faction_id = _text(op.get("faction_id") or op.get("target_id") or target_name)
    if not faction_id or faction_id == "the current situation":
        return _target_unavailable("modify_faction_alert", target_name, "missing faction_id")
    faction_state = _safe_dict(state.get("faction_state"))
    factions = _safe_dict(faction_state.get("factions"))
    faction = _safe_dict(factions.get(faction_id))
    before = _safe_int(faction.get("alert"))
    faction.update({"faction_id": faction_id, "alert": before + _safe_int(op.get("amount")), "updated_by": ability.get("name")})
    factions[faction_id] = faction
    faction_state["factions"] = factions
    state["faction_state"] = faction_state
    return {"target": faction_id, "faction_id": faction_id, "before": before, "after": faction["alert"], "applied": True}


def _modify_price_modifier(state: dict[str, Any], ability: dict[str, Any], op: dict[str, Any], target_name: str) -> dict[str, Any]:
    modifier_id = _text(op.get("tag") or op.get("target_id") or target_name, "general")
    economy = _safe_dict(state.get("economy"))
    modifiers = _safe_dict(economy.get("price_modifiers"))
    modifier = _safe_dict(modifiers.get(modifier_id))
    before = _safe_int(modifier.get("amount"))
    modifier.update({"amount": before + _safe_int(op.get("amount")), "source": ability.get("name"), "updated_at": _utc_now()})
    modifiers[modifier_id] = modifier
    economy["price_modifiers"] = modifiers
    state["economy"] = economy
    return {"target": modifier_id, "modifier_id": modifier_id, "before": before, "after": modifier["amount"], "applied": True}


def _apply_scene_status(state: dict[str, Any], ability: dict[str, Any], op: dict[str, Any]) -> dict[str, Any]:
    scene_state = _safe_dict(state.get("scene_state"))
    status = _text(op.get("status") or op.get("tag"), "changed")
    _append(scene_state, "statuses", {"status": status, "source": ability.get("name"), "duration_turns": op.get("duration_turns"), "created_at": _utc_now()})
    state["scene_state"] = scene_state
    return {"status": status, "applied": True}


def _create_hazard(state: dict[str, Any], ability: dict[str, Any], op: dict[str, Any]) -> dict[str, Any]:
    scene_state = _safe_dict(state.get("scene_state"))
    hazard = _text(op.get("hazard") or op.get("status") or op.get("tag"), "hazard")
    _append(scene_state, "hazards", {"hazard": hazard, "source": ability.get("name"), "strength": op.get("strength"), "duration_turns": op.get("duration_turns"), "created_at": _utc_now()})
    state["scene_state"] = scene_state
    return {"hazard": hazard, "applied": True}


def _clear_hazard(state: dict[str, Any], op: dict[str, Any]) -> dict[str, Any]:
    scene_state = _safe_dict(state.get("scene_state"))
    hazard = _text(op.get("hazard") or op.get("status") or op.get("tag"), "hazard")
    before = _safe_list(scene_state.get("hazards"))
    after = [item for item in before if _safe_dict(item).get("hazard") != hazard]
    scene_state["hazards"] = after
    state["scene_state"] = scene_state
    return {"hazard": hazard, "removed": len(before) - len(after), "applied": True}


def _change_location_state(state: dict[str, Any], ability: dict[str, Any], op: dict[str, Any], target_name: str) -> dict[str, Any]:
    location_id = _text(op.get("location_id") or op.get("target_id") or target_name)
    if not location_id or location_id == "the current situation":
        return _target_unavailable("change_location_state", target_name, "missing location_id")
    state_key = _text(op.get("state_key") or op.get("tag"), "state")
    locations = _safe_dict(state.get("locations"))
    location = _safe_dict(locations.get(location_id))
    location.setdefault("location_id", location_id)
    location_state = _safe_dict(location.get("state"))
    before = location_state.get(state_key)
    location_state[state_key] = op.get("state_value", True)
    location["state"] = location_state
    location["updated_by"] = ability.get("name")
    locations[location_id] = location
    state["locations"] = locations
    return {"target": location_id, "location_id": location_id, "state_key": state_key, "before": before, "after": location_state[state_key], "applied": True}


def _add_world_rumor(state: dict[str, Any], ability: dict[str, Any], op: dict[str, Any]) -> dict[str, Any]:
    world = _safe_dict(state.get("world"))
    rumor = {
        "rumor_id": _text(op.get("rumor_id") or op.get("tag"), f"rumor:{len(_safe_list(world.get('rumors'))) + 1}"),
        "text": _text(op.get("rumor") or op.get("state_value") or op.get("tag"), "A new rumor spreads."),
        "source": ability.get("name"),
        "created_at": _utc_now(),
    }
    _append(world, "rumors", rumor, limit=80)
    state["world"] = world
    return {"rumor_id": rumor["rumor_id"], "applied": True}


def _advance_quest_signal(state: dict[str, Any], ability: dict[str, Any], op: dict[str, Any], target_name: str) -> dict[str, Any]:
    quest_id = _text(op.get("quest_id") or op.get("target_id") or target_name)
    if not quest_id or quest_id == "the current situation":
        return _target_unavailable("advance_quest_signal", target_name, "missing quest_id")
    signal = _text(op.get("signal") or op.get("tag"), "ability_signal")
    quest_signals = _safe_list(state.get("quest_signals"))
    record = {"quest_id": quest_id, "signal": signal, "source": ability.get("name"), "created_at": _utc_now()}
    state["quest_signals"] = [record, *quest_signals][:80]
    for quest in _safe_list(state.get("quests")):
        quest_record = _safe_dict(quest)
        if _text(quest_record.get("quest_id") or quest_record.get("id")) == quest_id:
            signals = _safe_list(quest_record.get("signals"))
            quest_record["signals"] = [record, *signals][:20]
            break
    return {"target": quest_id, "quest_id": quest_id, "signal": signal, "applied": True}


def _complete_objective(state: dict[str, Any], ability: dict[str, Any], op: dict[str, Any], target_name: str) -> dict[str, Any]:
    quest_id = _text(op.get("quest_id") or op.get("target_id") or target_name)
    objective_id = _text(op.get("objective_id") or op.get("tag"))
    if not quest_id or quest_id == "the current situation" or not objective_id:
        return _target_unavailable("complete_objective", target_name, "missing quest_id or objective_id")
    for quest in _safe_list(state.get("quests")):
        quest_record = _safe_dict(quest)
        if _text(quest_record.get("quest_id") or quest_record.get("id")) != quest_id:
            continue
        for objective in _safe_list(quest_record.get("objectives")):
            objective_record = _safe_dict(objective)
            if _text(objective_record.get("objective_id") or objective_record.get("id")) == objective_id:
                objective_record["status"] = "completed"
                objective_record["completed"] = True
                objective_record["completed_by"] = ability.get("name")
                objective_record["completed_at"] = _utc_now()
                return {"target": quest_id, "quest_id": quest_id, "objective_id": objective_id, "applied": True}
        return _target_unavailable("complete_objective", quest_id, f"missing objective {objective_id}")
    return _target_unavailable("complete_objective", quest_id, f"missing quest {quest_id}")


def execute_effect_ops(state: dict[str, Any], ability: dict[str, Any], *, target: str | None = None) -> list[dict[str, Any]]:
    applied: list[dict[str, Any]] = []
    for raw_op in _safe_list(ability.get("effect_ops")):
        op = _safe_dict(raw_op)
        op_name = str(op.get("op") or "")
        dimension = str(op.get("dimension") or "")
        target_name = _text(op.get("target_id") or op.get("target") or target, "self")
        result: dict[str, Any] = {"dimension": dimension, "op": op_name, "target": target_name}
        if op_name == "resource_delta":
            result.update(_resource_delta(state, str(op.get("resource") or "hp"), _safe_int(op.get("amount")), target=target_name if op.get("target") == "target" else op.get("target") or target_name))
        elif op_name == "modify_next_check":
            runtime = _safe_dict(state.get("runtime"))
            effect = {"source": ability.get("name"), "dimension": dimension, "check": op.get("check"), "amount": _safe_int(op.get("amount")), "duration_turns": op.get("duration_turns", 1), "created_at": _utc_now()}
            _append(runtime, "effects", effect)
            state["runtime"] = runtime
            result.update({"check": effect["check"], "amount": effect["amount"], "duration_turns": effect["duration_turns"], "applied": True})
        elif op_name == "apply_status":
            result.update(_apply_status(state, ability, op, target_name))
        elif op_name == "clear_status":
            result.update(_clear_status(state, op, target_name))
        elif op_name == "reveal_clue":
            clue_tag = _text(op.get("clue_tag") or op.get("tag"), "clue")
            _append(state, "clues", {"source": ability.get("name"), "tag": clue_tag, "strength": op.get("strength", 1), "created_at": _utc_now()})
            result.update({"clue_tag": clue_tag, "applied": True})
        elif op_name in {"unlock_dialogue_option", "unlock_travel_option", "unlock_scene_affordance", "grant_temp_affordance"}:
            affordances = _safe_dict(state.get("narrative_affordances"))
            bucket = "dialogue" if op_name == "unlock_dialogue_option" else "travel" if op_name == "unlock_travel_option" else "scene"
            tag = _text(op.get("option_tag") or op.get("affordance") or op.get("tag"), op_name)
            _append(affordances, bucket, {"source": ability.get("name"), "tag": tag, "duration_turns": op.get("duration_turns"), "created_at": _utc_now()})
            state["narrative_affordances"] = affordances
            result.update({"bucket": bucket, "tag": tag, "applied": True})
        elif op_name == "modify_relationship":
            result.update(_modify_relationship(state, ability, op, target_name))
        elif op_name == "modify_reputation":
            result.update(_modify_reputation(state, op))
        elif op_name == "modify_faction_alert":
            result.update(_modify_faction_alert(state, ability, op, target_name))
        elif op_name == "modify_price_modifier":
            result.update(_modify_price_modifier(state, ability, op, target_name))
        elif op_name == "apply_scene_status":
            result.update(_apply_scene_status(state, ability, op))
        elif op_name == "create_hazard":
            result.update(_create_hazard(state, ability, op))
        elif op_name == "clear_hazard":
            result.update(_clear_hazard(state, op))
        elif op_name == "change_location_state":
            result.update(_change_location_state(state, ability, op, target_name))
        elif op_name == "add_world_rumor":
            result.update(_add_world_rumor(state, ability, op))
        elif op_name == "advance_quest_signal":
            result.update(_advance_quest_signal(state, ability, op, target_name))
        elif op_name == "complete_objective":
            result.update(_complete_objective(state, ability, op, target_name))
        else:
            result.update({"applied": False, "error": "unsupported_effect_op"})
            _append(_mechanics(state), "pending_dimension_effects", {**deepcopy(op), "source": ability.get("name"), "created_at": _utc_now()})
        _record_effect_trace(state, ability, op, result)
        applied.append(result)
    return applied


def _tick_cooldowns(ability_state: dict[str, Any]) -> None:
    cooldowns = _safe_dict(ability_state.get("cooldowns"))
    ability_state["cooldowns"] = {str(key): max(0, int(value or 0) - 1) for key, value in cooldowns.items() if max(0, int(value or 0) - 1) > 0}


def apply_ability_to_state(state: dict[str, Any], *, ability_name: str | None = None, hotbar_slot: str | int | None = None, target: str | None = None) -> RpgAbilityUseResult:
    ability = _find_ability(state, ability_name=ability_name, hotbar_slot=hotbar_slot)
    if not ability:
        return RpgAbilityUseResult(ok=False, error="unknown_ability", detail="Ability was not found in the session ability tree.")
    errors = validate_ability(ability)
    if errors:
        return RpgAbilityUseResult(ok=False, ability_id=ability.get("ability_id"), name=ability.get("name"), error="invalid_ability", detail="; ".join(errors))
    ability_id = str(ability.get("ability_id"))
    ability_state = _safe_dict(state.get("ability_state"))
    state["ability_state"] = ability_state
    unlocked = set(str(value) for value in _safe_list(ability_state.get("unlocked")))
    if ability_id not in unlocked:
        return RpgAbilityUseResult(ok=False, ability_id=ability_id, name=ability.get("name"), error="ability_locked", detail=f"{ability.get('name')} is not unlocked yet.")
    cooldowns = _safe_dict(ability_state.get("cooldowns"))
    if int(cooldowns.get(ability_id) or 0) > 0:
        return RpgAbilityUseResult(ok=False, ability_id=ability_id, name=ability.get("name"), error="ability_on_cooldown", detail=f"{ability.get('name')} is on cooldown for {cooldowns[ability_id]} more turn(s).")
    player = _player(state)
    cost_parts: list[str] = []
    for resource, cost in _safe_dict(ability.get("resource_cost")).items():
        metric = _resource_metric(player, str(resource))
        current = int(metric.get("current") or 0)
        if current < int(cost):
            return RpgAbilityUseResult(ok=False, ability_id=ability_id, name=ability.get("name"), error="insufficient_resource", detail=f"{ability.get('name')} requires {cost} {resource}, but only {current}/{metric.get('max')} is available.")
    for resource, cost in _safe_dict(ability.get("resource_cost")).items():
        metric = _resource_metric(player, str(resource))
        metric["current"] = max(0, int(metric.get("current") or 0) - int(cost))
        cost_parts.append(f"{resource}: {metric['current']}/{metric.get('max')}")
    effects = execute_effect_ops(state, ability, target=target or "the current situation")
    if effects and not any(effect.get("applied") is not False for effect in effects):
        details = "; ".join(str(effect.get("detail") or effect.get("error") or "effect failed") for effect in effects)
        return RpgAbilityUseResult(ok=False, ability_id=ability_id, name=ability.get("name"), error="effect_target_unavailable", detail=details, effects=effects)
    _append_player_visible_ability_event(state, ability, effects)
    _tick_cooldowns(ability_state)
    cooldown = int(ability.get("cooldown_turns") or 0)
    if cooldown > 0:
        ability_state.setdefault("cooldowns", {})[ability_id] = cooldown
    active_effects = _safe_list(ability_state.get("active_effects"))
    active_effects.insert(0, {"ability_id": ability_id, "name": ability.get("name"), "dimensions": ability.get("dimensions", []), "purpose": ability.get("purpose"), "target": target or "the current situation", "created_at": _utc_now()})
    ability_state["active_effects"] = active_effects[:20]
    dimensions = ", ".join(str(value) for value in ability.get("dimensions", []))
    cost_detail = f" Costs now {', '.join(cost_parts)}." if cost_parts else ""
    return RpgAbilityUseResult(ok=True, ability_id=ability_id, name=str(ability.get("name")), detail=f"You used {ability.get('name')} on {target or 'the current situation'}, changing {dimensions}.{cost_detail}", effects=effects)


def hotbar_preview_from_state(state: dict[str, Any]) -> list[dict[str, str]]:
    ability_index = _ability_index(_safe_dict(state.get("ability_tree")))
    ability_state = _safe_dict(state.get("ability_state"))
    hotbar = _safe_dict(state.get("hotbar")) or _safe_dict(ability_state.get("hotbar"))
    previews: list[dict[str, str]] = []
    for slot in sorted(hotbar, key=lambda value: int(value) if str(value).isdigit() else 999):
        ability = ability_index.get(str(hotbar[slot]))
        if ability:
            previews.append({"key": str(slot), "icon": str(ability.get("icon") or "✦"), "label": str(ability.get("name") or ability.get("ability_id"))})
    return previews
