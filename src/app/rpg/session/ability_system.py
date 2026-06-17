"""Capability-based RPG ability tree and deterministic effect helpers.

The ability system is intentionally dimension-first rather than class-first. The
AI may generate names and flavor later, but playable abilities must compile to
validated deterministic operations that alter at least one gameplay dimension.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

Capability = Literal["combat", "recon", "influence", "technical", "survival", "knowledge", "support", "custom"]
PowerSource = Literal[
    "mundane",
    "martial",
    "magic",
    "technology",
    "psionic",
    "divine",
    "occult",
    "mutation",
    "mythic",
    "social_power",
    "scrap",
    "custom",
]
GameplayDimension = Literal[
    "resources",
    "information",
    "relationships",
    "access",
    "environment",
    "position",
    "narrative",
    "economy",
    "world",
]
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

ALLOWED_CAPABILITIES = set(Capability.__args__)
ALLOWED_POWER_SOURCES = set(PowerSource.__args__)
ALLOWED_DIMENSIONS = set(GameplayDimension.__args__)
ALLOWED_KINDS = set(AbilityKind.__args__)
ALLOWED_PURPOSES = set(AbilityPurpose.__args__)
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


class RpgCharacterIdentity(BaseModel):
    genre: str = "classic_fantasy"
    tone: str = "heroic adventure"
    background: str = "Wanderer"
    primary_capability: Capability = "recon"
    secondary_capabilities: list[Capability] = Field(default_factory=list)
    power_source: PowerSource = "martial"
    generated_class_name: str = "Ranger"
    generated_class_summary: str = "A capable adventurer whose talents are expressed through deterministic gameplay dimensions."


class RpgEffectOp(BaseModel):
    dimension: GameplayDimension
    op: str
    target: str | None = None
    amount: int | None = None
    resource: str | None = None
    check: str | None = None
    status: str | None = None
    clue_tag: str | None = None
    affordance: str | None = None
    option_tag: str | None = None
    duration_turns: int | None = None
    strength: int | None = None
    signal: str | None = None
    faction: str | None = None
    relationship: str | None = None
    tag: str | None = None
    note: str | None = None


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
    "balanced_adventurer": {
        "primary_capability": "survival",
        "secondary_capabilities": ["combat", "recon"],
        "power_source": "mundane",
        "class_name": "Adventurer",
        "summary": "A flexible explorer with a balanced kit for travel, trouble, and discovery.",
    },
    "warrior": {
        "primary_capability": "combat",
        "secondary_capabilities": ["survival", "influence"],
        "power_source": "martial",
        "class_name": "Champion",
        "summary": "A frontline specialist who controls danger through force, discipline, and endurance.",
    },
    "ranger": {
        "primary_capability": "recon",
        "secondary_capabilities": ["survival", "combat"],
        "power_source": "martial",
        "class_name": "Ranger",
        "summary": "A trailwise scout who turns information, position, and terrain into advantage.",
    },
    "silver_tongue": {
        "primary_capability": "influence",
        "secondary_capabilities": ["knowledge", "recon"],
        "power_source": "social_power",
        "class_name": "Diplomat",
        "summary": "A social operator who wins access through reputation, leverage, and careful reading of people.",
    },
}

GENRE_CLASS_NAMES: dict[tuple[str, str, str], str] = {
    ("classic_fantasy", "knowledge", "magic"): "Runebinder",
    ("classic_fantasy", "combat", "martial"): "Champion",
    ("classic_fantasy", "recon", "martial"): "Ranger",
    ("classic_fantasy", "support", "divine"): "Cleric",
    ("cyberpunk", "technical", "technology"): "Netrunner",
    ("cyberpunk", "combat", "technology"): "Street Samurai",
    ("cyberpunk", "recon", "technology"): "Ghostwalker",
    ("detective_noir", "recon", "mundane"): "Private Eye",
    ("political_intrigue", "influence", "social_power"): "Court Schemer",
    ("post_apocalyptic", "survival", "scrap"): "Scavenger",
    ("space_opera", "knowledge", "psionic"): "Psionic",
    ("space_opera", "technical", "technology"): "Engineer",
    ("modern_occult", "knowledge", "occult"): "Ritualist",
}

GENRE_NORMALIZATION = {
    "classic_fantasy": "classic_fantasy",
    "fantasy": "classic_fantasy",
    "dark_fantasy": "dark_fantasy",
    "cyberpunk": "cyberpunk",
    "space_opera": "space_opera",
    "post_apocalyptic": "post_apocalyptic",
    "modern_occult": "modern_occult",
    "sandbox": "sandbox",
    "tavern_mystery": "classic_fantasy",
    "bandit_road": "classic_fantasy",
    "wilderness_survival": "classic_fantasy",
    "dungeon_delve": "classic_fantasy",
    "detective_noir": "detective_noir",
    "political_intrigue": "political_intrigue",
}

ABILITY_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "recon": [
        {
            "ability_id": "recon_aimed_shot",
            "name": "Aimed Shot",
            "icon": "✦",
            "description": "Take careful aim and convert position into a decisive opening.",
            "purpose": "damage",
            "dimensions": ["position", "resources"],
            "resource_cost": {"stamina": 10},
            "cooldown_turns": 1,
            "effect_ops": [
                {"dimension": "position", "op": "modify_next_check", "check": "ranged_attack", "amount": 2, "duration_turns": 1},
                {"dimension": "resources", "op": "resource_delta", "target": "target", "resource": "hp", "amount": -10},
            ],
        },
        {
            "ability_id": "recon_trail_sense",
            "name": "Trail Sense",
            "icon": "⌕",
            "description": "Read tracks, patterns, and subtle signs in the current scene.",
            "purpose": "information_gathering",
            "dimensions": ["information", "narrative"],
            "resource_cost": {"stamina": 5},
            "effect_ops": [
                {"dimension": "information", "op": "reveal_clue", "clue_tag": "local_tracks", "strength": 1},
                {"dimension": "narrative", "op": "unlock_dialogue_option", "option_tag": "ask_about_tracks", "duration_turns": 3},
            ],
        },
        {
            "ability_id": "recon_camouflage",
            "name": "Camouflage",
            "icon": "☘",
            "description": "Blend into cover and make the next stealth or ambush approach safer.",
            "purpose": "escape",
            "dimensions": ["position", "environment"],
            "resource_cost": {"stamina": 8},
            "cooldown_turns": 2,
            "effect_ops": [
                {"dimension": "position", "op": "modify_next_check", "check": "stealth", "amount": 2, "duration_turns": 3},
                {"dimension": "environment", "op": "apply_scene_status", "status": "concealment_found", "duration_turns": 3},
            ],
        },
        {
            "ability_id": "recon_dash",
            "name": "Dash",
            "icon": "⇥",
            "description": "Reposition quickly before danger closes in.",
            "purpose": "mobility",
            "dimensions": ["position"],
            "resource_cost": {"stamina": 12},
            "cooldown_turns": 1,
            "level_required": 2,
            "effect_ops": [
                {"dimension": "position", "op": "grant_temp_affordance", "affordance": "rapid_reposition", "duration_turns": 1},
            ],
        },
    ],
    "combat": [
        {
            "ability_id": "combat_guarded_strike",
            "name": "Guarded Strike",
            "icon": "⚔",
            "description": "Attack while keeping enough guard to blunt the next retaliation.",
            "purpose": "damage",
            "dimensions": ["resources", "position"],
            "resource_cost": {"stamina": 10},
            "cooldown_turns": 1,
            "effect_ops": [
                {"dimension": "resources", "op": "resource_delta", "target": "target", "resource": "hp", "amount": -12},
                {"dimension": "position", "op": "modify_next_check", "check": "defense", "amount": 1, "duration_turns": 1},
            ],
        },
        {
            "ability_id": "combat_rallying_presence",
            "name": "Rallying Presence",
            "icon": "▲",
            "description": "Steady nearby allies and recover momentum under pressure.",
            "purpose": "defense",
            "dimensions": ["relationships", "resources"],
            "resource_cost": {"stamina": 8},
            "effect_ops": [
                {"dimension": "relationships", "op": "modify_relationship", "relationship": "party_morale", "amount": 2},
                {"dimension": "resources", "op": "resource_delta", "target": "self", "resource": "stamina", "amount": 4},
            ],
        },
    ],
    "technical": [
        {
            "ability_id": "technical_signal_probe",
            "name": "Signal Probe",
            "icon": "⌁",
            "description": "Scan nearby systems, mechanisms, or devices for a weak point.",
            "purpose": "information_gathering",
            "dimensions": ["information", "access"],
            "resource_cost": {"mana": 6},
            "effect_ops": [
                {"dimension": "information", "op": "reveal_clue", "clue_tag": "system_weakness", "strength": 1},
                {"dimension": "access", "op": "unlock_scene_affordance", "affordance": "technical_bypass_hint", "duration_turns": 3},
            ],
        },
        {
            "ability_id": "technical_camera_loop",
            "name": "Camera Loop",
            "icon": "◉",
            "description": "Briefly loop or spoof surveillance to create a movement window.",
            "purpose": "access_bypass",
            "dimensions": ["access", "environment"],
            "resource_cost": {"mana": 10},
            "cooldown_turns": 3,
            "level_required": 2,
            "prerequisites": ["technical_signal_probe"],
            "effect_ops": [
                {"dimension": "access", "op": "unlock_scene_affordance", "affordance": "cross_monitored_route", "duration_turns": 3},
                {"dimension": "environment", "op": "apply_scene_status", "status": "surveillance_looped", "duration_turns": 3},
            ],
        },
    ],
    "knowledge": [
        {
            "ability_id": "knowledge_read_the_room",
            "name": "Read the Room",
            "icon": "◇",
            "description": "Study context, symbols, or social pressure and notice the hidden pattern.",
            "purpose": "information_gathering",
            "dimensions": ["information", "narrative"],
            "resource_cost": {"mana": 5},
            "effect_ops": [
                {"dimension": "information", "op": "reveal_clue", "clue_tag": "hidden_context", "strength": 1},
                {"dimension": "narrative", "op": "unlock_dialogue_option", "option_tag": "press_hidden_context", "duration_turns": 2},
            ],
        },
        {
            "ability_id": "knowledge_warding_formula",
            "name": "Warding Formula",
            "icon": "✹",
            "description": "Turn specialized knowledge into a short-lived protective pattern.",
            "purpose": "defense",
            "dimensions": ["environment", "position"],
            "resource_cost": {"mana": 12},
            "cooldown_turns": 2,
            "effect_ops": [
                {"dimension": "environment", "op": "apply_scene_status", "status": "warded", "duration_turns": 3},
                {"dimension": "position", "op": "modify_next_check", "check": "defense", "amount": 2, "duration_turns": 3},
            ],
        },
    ],
    "influence": [
        {
            "ability_id": "influence_call_in_favor",
            "name": "Call in a Favor",
            "icon": "☯",
            "description": "Spend social capital to open a route, request, or concession.",
            "purpose": "relationship_building",
            "dimensions": ["relationships", "access"],
            "resource_cost": {"mana": 5},
            "cooldown_turns": 2,
            "effect_ops": [
                {"dimension": "relationships", "op": "modify_relationship", "relationship": "local_contacts", "amount": 1},
                {"dimension": "access", "op": "unlock_dialogue_option", "option_tag": "call_in_favor", "duration_turns": 3},
            ],
        },
        {
            "ability_id": "influence_cutting_insight",
            "name": "Cutting Insight",
            "icon": "✧",
            "description": "Name the pressure point in a negotiation and shift the room's attitude.",
            "purpose": "social_manipulation",
            "dimensions": ["information", "relationships"],
            "resource_cost": {"stamina": 6},
            "effect_ops": [
                {"dimension": "information", "op": "reveal_clue", "clue_tag": "social_leverage", "strength": 1},
                {"dimension": "relationships", "op": "modify_reputation", "amount": 1},
            ],
        },
    ],
    "survival": [
        {
            "ability_id": "survival_make_camp",
            "name": "Make Camp",
            "icon": "♨",
            "description": "Create a safer short rest point and recover a little stamina.",
            "purpose": "survival",
            "dimensions": ["resources", "environment"],
            "resource_cost": {},
            "cooldown_turns": 4,
            "effect_ops": [
                {"dimension": "resources", "op": "resource_delta", "target": "self", "resource": "stamina", "amount": 12},
                {"dimension": "environment", "op": "apply_scene_status", "status": "safe_camp", "duration_turns": 4},
            ],
        },
        {
            "ability_id": "survival_scavenge",
            "name": "Scavenge",
            "icon": "▣",
            "description": "Search the area for usable scraps, supplies, or signs.",
            "purpose": "resource_generation",
            "dimensions": ["resources", "information"],
            "resource_cost": {"stamina": 6},
            "effect_ops": [
                {"dimension": "information", "op": "reveal_clue", "clue_tag": "salvage_source", "strength": 1},
                {"dimension": "narrative", "op": "grant_temp_affordance", "affordance": "found_minor_supplies", "duration_turns": 1},
            ],
        },
    ],
    "support": [
        {
            "ability_id": "support_field_aid",
            "name": "Field Aid",
            "icon": "✚",
            "description": "Stabilize injuries and restore a small amount of HP.",
            "purpose": "healing",
            "dimensions": ["resources"],
            "resource_cost": {"mana": 8},
            "cooldown_turns": 2,
            "effect_ops": [
                {"dimension": "resources", "op": "resource_delta", "target": "self", "resource": "hp", "amount": 18},
            ],
        },
        {
            "ability_id": "support_steady_voice",
            "name": "Steady Voice",
            "icon": "☼",
            "description": "Calm panic and make the next difficult group action easier.",
            "purpose": "defense",
            "dimensions": ["relationships", "position"],
            "resource_cost": {"stamina": 6},
            "effect_ops": [
                {"dimension": "relationships", "op": "modify_relationship", "relationship": "party_morale", "amount": 2},
                {"dimension": "position", "op": "modify_next_check", "check": "group_action", "amount": 1, "duration_turns": 2},
            ],
        },
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


def normalize_genre(value: Any) -> str:
    raw = _norm(value) or "classic_fantasy"
    return GENRE_NORMALIZATION.get(raw, raw)


def normalize_capability(value: Any, fallback: Capability = "survival") -> Capability:
    raw = _norm(value)
    return raw if raw in ALLOWED_CAPABILITIES else fallback


def normalize_power_source(value: Any, fallback: PowerSource = "mundane") -> PowerSource:
    raw = _norm(value)
    return raw if raw in ALLOWED_POWER_SOURCES else fallback


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
    class_name = str(request_payload.get("generated_class_name") or "").strip()
    if not class_name:
        class_name = GENRE_CLASS_NAMES.get((genre, primary, power_source)) or defaults.get("class_name") or primary.title()
    tone = str(request_payload.get("tone") or request_payload.get("campaign_tone") or "heroic adventure").strip()
    background = str(player.get("background") or request_payload.get("background") or "Wanderer").strip()
    summary = str(request_payload.get("generated_class_summary") or "").strip()
    if not summary:
        summary = defaults.get("summary") or f"A {class_name} whose capabilities are expressed through deterministic gameplay dimensions."
    return RpgCharacterIdentity(
        genre=genre,
        tone=tone,
        background=background,
        primary_capability=primary,
        secondary_capabilities=secondary,
        power_source=power_source,
        generated_class_name=class_name,
        generated_class_summary=summary,
    ).model_dump(mode="json")


def _ability(data: dict[str, Any], *, capability: str, power_source: str, level: int = 1) -> dict[str, Any]:
    payload = dict(data)
    payload.setdefault("kind", "active")
    payload.setdefault("capability", capability)
    payload.setdefault("power_source", power_source)
    payload.setdefault("level_required", level)
    payload.setdefault("rank", 1)
    payload.setdefault("max_rank", 3)
    payload.setdefault("resource_cost", {})
    payload.setdefault("cooldown_turns", 0)
    payload.setdefault("prerequisites", [])
    payload.setdefault("targeting", {})
    payload.setdefault("flavor_tags", [])
    return RpgAbilityDefinition.model_validate(payload).model_dump(mode="json")


def _category_label(capability: str, power_source: str, genre: str) -> str:
    if capability == "technical" and power_source == "technology":
        return "Systems & Devices"
    if capability == "knowledge" and power_source == "magic":
        return "Arcane Knowledge"
    if capability == "knowledge" and power_source == "occult":
        return "Forbidden Knowledge"
    if capability == "influence":
        return "Leverage & Influence"
    if capability == "recon":
        return "Recon & Position"
    if capability == "combat":
        return "Combat Discipline"
    if capability == "survival":
        return "Survival Craft"
    if capability == "support":
        return "Support & Recovery"
    return capability.replace("_", " ").title()


def build_ability_tree(identity: dict[str, Any], *, seed: int | None = None) -> dict[str, Any]:
    primary = normalize_capability(identity.get("primary_capability"), "survival")
    secondary = [normalize_capability(value, "custom") for value in _safe_list(identity.get("secondary_capabilities"))]
    power_source = normalize_power_source(identity.get("power_source"), "mundane")
    genre = normalize_genre(identity.get("genre"))
    class_name = str(identity.get("generated_class_name") or primary.title())
    capabilities = [primary, *[capability for capability in secondary if capability != primary]][:3]
    categories: list[dict[str, Any]] = []
    all_abilities: list[dict[str, Any]] = []
    for capability in capabilities:
        template = ABILITY_TEMPLATES.get(capability, ABILITY_TEMPLATES["survival"])
        abilities = [_ability(data, capability=capability, power_source=power_source) for data in template]
        categories.append(
            {
                "category_id": capability,
                "name": _category_label(capability, power_source, genre),
                "capability": capability,
                "dimensions": sorted({dimension for ability in abilities for dimension in ability.get("dimensions", [])}),
                "abilities": [ability["ability_id"] for ability in abilities],
            }
        )
        all_abilities.extend(abilities)
    tree_id = f"ability_tree_{genre}_{primary}_{power_source}_v1"
    if seed is not None:
        tree_id = f"{tree_id}_{abs(int(seed)) % 100000:05d}"
    tree = {
        "tree_id": tree_id,
        "version": 1,
        "source": "template_capability_v1",
        "class_name": class_name,
        "genre": genre,
        "primary_capability": primary,
        "secondary_capabilities": secondary,
        "power_source": power_source,
        "dimensions": sorted({dimension for ability in all_abilities for dimension in ability.get("dimensions", [])}),
        "categories": categories,
        "abilities": all_abilities,
        "design_rule": "Every active ability must alter at least one gameplay dimension through validated deterministic operations.",
    }
    validation = validate_ability_tree(tree)
    if not validation.ok:
        raise ValueError("Invalid ability tree: " + "; ".join(validation.errors))
    return tree


def build_initial_ability_state(tree: dict[str, Any], *, level: int = 1) -> dict[str, Any]:
    abilities = _safe_list(tree.get("abilities"))
    unlocked = [ability["ability_id"] for ability in abilities if int(ability.get("level_required") or 1) <= level and ability.get("kind") == "active"][:3]
    ranks = {ability_id: 1 for ability_id in unlocked}
    hotbar = {str(index + 1): ability_id for index, ability_id in enumerate(unlocked[:6])}
    return {
        "ability_points": max(0, int(level) - 1),
        "unlocked": unlocked,
        "ranks": ranks,
        "cooldowns": {},
        "active_effects": [],
        "hotbar": hotbar,
    }


def build_progression_package(request_payload: dict[str, Any], *, build_id: str, level: int = 1, seed: int | None = None) -> dict[str, Any]:
    identity = infer_character_identity(request_payload, build_id=build_id)
    tree = build_ability_tree(identity, seed=seed)
    ability_state = build_initial_ability_state(tree, level=level)
    return {"character_identity": identity, "ability_tree": tree, "ability_state": ability_state, "hotbar": ability_state["hotbar"]}


def validate_ability(ability: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    ability_id = str(ability.get("ability_id") or "").strip()
    if not ability_id:
        errors.append("missing ability_id")
    kind = str(ability.get("kind") or "active")
    if kind not in ALLOWED_KINDS:
        errors.append(f"{ability_id}: unsupported kind {kind}")
    capability = str(ability.get("capability") or "")
    if capability not in ALLOWED_CAPABILITIES:
        errors.append(f"{ability_id}: unsupported capability {capability}")
    purpose = str(ability.get("purpose") or "")
    if purpose and purpose not in ALLOWED_PURPOSES:
        errors.append(f"{ability_id}: unsupported purpose {purpose}")
    dimensions = _safe_list(ability.get("dimensions"))
    unknown_dimensions = [dimension for dimension in dimensions if dimension not in ALLOWED_DIMENSIONS]
    if unknown_dimensions:
        errors.append(f"{ability_id}: unsupported dimensions {unknown_dimensions}")
    effect_ops = _safe_list(ability.get("effect_ops"))
    if kind == "active" and not effect_ops:
        errors.append(f"{ability_id}: active ability has no effect_ops")
    for op in effect_ops:
        op_record = _safe_dict(op)
        dimension = op_record.get("dimension")
        op_name = op_record.get("op")
        if dimension not in ALLOWED_DIMENSIONS:
            errors.append(f"{ability_id}: effect has unsupported dimension {dimension}")
        if op_name not in ALLOWED_EFFECT_OPS:
            errors.append(f"{ability_id}: unsupported effect op {op_name}")
        if dimension and dimension not in dimensions:
            errors.append(f"{ability_id}: effect dimension {dimension} missing from ability dimensions")
    if int(ability.get("level_required") or 1) < 1:
        errors.append(f"{ability_id}: invalid level_required")
    if int(ability.get("rank") or 1) < 1 or int(ability.get("max_rank") or 1) < 1:
        errors.append(f"{ability_id}: invalid rank bounds")
    return errors


def validate_ability_tree(tree: dict[str, Any]) -> RpgAbilityValidationResult:
    errors: list[str] = []
    seen: set[str] = set()
    for ability in _safe_list(tree.get("abilities")):
        ability_record = _safe_dict(ability)
        ability_id = str(ability_record.get("ability_id") or "")
        if ability_id in seen:
            errors.append(f"duplicate ability_id {ability_id}")
        seen.add(ability_id)
        errors.extend(validate_ability(ability_record))
    for ability in _safe_list(tree.get("abilities")):
        for prerequisite in _safe_list(_safe_dict(ability).get("prerequisites")):
            if prerequisite not in seen:
                errors.append(f"{ability.get('ability_id')}: missing prerequisite {prerequisite}")
    return RpgAbilityValidationResult(ok=not errors, errors=errors)


def _ability_index(tree: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(ability.get("ability_id")): _safe_dict(ability) for ability in _safe_list(tree.get("abilities"))}


def _find_ability(state: dict[str, Any], *, ability_name: str | None = None, hotbar_slot: str | int | None = None) -> dict[str, Any] | None:
    tree = _safe_dict(state.get("ability_tree"))
    index = _ability_index(tree)
    ability_state = _safe_dict(state.get("ability_state"))
    if hotbar_slot is not None:
        hotbar = _safe_dict(state.get("hotbar")) or _safe_dict(ability_state.get("hotbar"))
        ability_id = hotbar.get(str(hotbar_slot))
        if ability_id in index:
            return index[ability_id]
    wanted = _norm(ability_name)
    if not wanted:
        return None
    for ability in index.values():
        if _norm(ability.get("name")) == wanted or _norm(ability.get("ability_id")) == wanted:
            return ability
    for ability in index.values():
        if wanted in _norm(ability.get("name")) or wanted in _norm(ability.get("ability_id")):
            return ability
    return None


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


def _resource_delta(state: dict[str, Any], resource: str, amount: int, *, target: str | None = None) -> dict[str, Any]:
    player = _player(state)
    metric = _resource_metric(player, resource)
    current = int(metric.get("current") or 0)
    maximum = int(metric.get("max") or current)
    # Enemy/target resources are traced for now. Player/party resource changes are applied directly.
    if target and target not in {"self", "player", "party"}:
        encounter = _safe_dict(state.get("encounter"))
        effects = _safe_list(encounter.get("target_effects"))
        effects.insert(0, {"target": target, "resource": resource, "amount": amount, "created_at": _utc_now()})
        encounter["target_effects"] = effects[:20]
        state["encounter"] = encounter
        return {"target": target, "resource": resource, "amount": amount, "applied": "target_trace"}
    metric["current"] = max(0, min(maximum, current + int(amount)))
    return {"target": "self", "resource": resource, "before": current, "after": metric["current"], "max": maximum}


def _append_unique(target: dict[str, Any], key: str, value: dict[str, Any], limit: int = 20) -> None:
    values = _safe_list(target.get(key))
    values.insert(0, value)
    target[key] = values[:limit]


def execute_effect_ops(state: dict[str, Any], ability: dict[str, Any], *, target: str | None = None) -> list[dict[str, Any]]:
    applied: list[dict[str, Any]] = []
    for raw_op in _safe_list(ability.get("effect_ops")):
        op = _safe_dict(raw_op)
        op_name = str(op.get("op") or "")
        dimension = str(op.get("dimension") or "")
        target_name = target or str(op.get("target") or "self")
        result: dict[str, Any] = {"dimension": dimension, "op": op_name, "target": target_name}
        if op_name == "resource_delta":
            result.update(_resource_delta(state, str(op.get("resource") or "hp"), int(op.get("amount") or 0), target=target_name))
        elif op_name == "modify_next_check":
            runtime = _safe_dict(state.get("runtime"))
            _append_unique(
                runtime,
                "effects",
                {
                    "source": ability.get("name"),
                    "dimension": dimension,
                    "check": op.get("check"),
                    "amount": op.get("amount"),
                    "duration_turns": op.get("duration_turns", 1),
                    "created_at": _utc_now(),
                },
            )
            state["runtime"] = runtime
        elif op_name == "reveal_clue":
            _append_unique(
                state,
                "clues",
                {
                    "source": ability.get("name"),
                    "tag": op.get("clue_tag") or op.get("tag") or "clue",
                    "strength": op.get("strength", 1),
                    "created_at": _utc_now(),
                },
            )
        elif op_name in {"unlock_dialogue_option", "unlock_travel_option", "unlock_scene_affordance", "grant_temp_affordance"}:
            affordances = _safe_dict(state.get("narrative_affordances"))
            bucket = "dialogue" if op_name == "unlock_dialogue_option" else "travel" if op_name == "unlock_travel_option" else "scene"
            _append_unique(
                affordances,
                bucket,
                {
                    "source": ability.get("name"),
                    "tag": op.get("option_tag") or op.get("affordance") or op.get("tag") or op_name,
                    "duration_turns": op.get("duration_turns"),
                    "created_at": _utc_now(),
                },
            )
            state["narrative_affordances"] = affordances
        elif op_name == "apply_scene_status":
            scene_state = _safe_dict(state.get("scene_state"))
            _append_unique(
                scene_state,
                "statuses",
                {"status": op.get("status") or "changed", "source": ability.get("name"), "duration_turns": op.get("duration_turns"), "created_at": _utc_now()},
            )
            state["scene_state"] = scene_state
        elif op_name == "apply_status":
            runtime = _safe_dict(state.get("runtime"))
            _append_unique(
                runtime,
                "statuses",
                {"target": target_name, "status": op.get("status") or "affected", "source": ability.get("name"), "duration_turns": op.get("duration_turns"), "created_at": _utc_now()},
            )
            state["runtime"] = runtime
        elif op_name == "modify_relationship":
            relationships = _safe_list(state.get("relationships"))
            relation_name = str(op.get("relationship") or target_name or "local_contacts")
            amount = int(op.get("amount") or 0)
            for relation in relationships:
                if _safe_dict(relation).get("name") == relation_name:
                    relation["score"] = int(relation.get("score") or 0) + amount
                    break
            else:
                relationships.append({"name": relation_name, "stance": "Noted", "score": amount})
            state["relationships"] = relationships
        elif op_name == "modify_reputation":
            world = _safe_dict(state.get("world"))
            reputation = _safe_dict(world.get("reputation"))
            reputation["score"] = int(reputation.get("score") or 0) + int(op.get("amount") or 0)
            reputation.setdefault("label", "Unknown")
            world["reputation"] = reputation
            state["world"] = world
        elif op_name == "add_world_rumor":
            world = _safe_dict(state.get("world"))
            _append_unique(world, "rumors", {"source": ability.get("name"), "tag": op.get("tag") or "rumor", "created_at": _utc_now()})
            state["world"] = world
        elif op_name in {"create_hazard", "clear_hazard", "change_location_state", "modify_faction_alert", "modify_price_modifier", "advance_quest_signal", "complete_objective", "clear_status"}:
            mechanics = _safe_dict(state.get("mechanics"))
            _append_unique(mechanics, "pending_dimension_effects", {**deepcopy(op), "source": ability.get("name"), "created_at": _utc_now()})
            state["mechanics"] = mechanics
        else:
            result["ignored"] = True
        applied.append(result)
    return applied


def _tick_cooldowns(ability_state: dict[str, Any]) -> None:
    cooldowns = _safe_dict(ability_state.get("cooldowns"))
    next_cooldowns: dict[str, int] = {}
    for ability_id, value in cooldowns.items():
        remaining = max(0, int(value or 0) - 1)
        if remaining > 0:
            next_cooldowns[str(ability_id)] = remaining
    ability_state["cooldowns"] = next_cooldowns


def apply_ability_to_state(state: dict[str, Any], *, ability_name: str | None = None, hotbar_slot: str | int | None = None, target: str | None = None) -> RpgAbilityUseResult:
    ability = _find_ability(state, ability_name=ability_name, hotbar_slot=hotbar_slot)
    if not ability:
        return RpgAbilityUseResult(ok=False, error="unknown_ability", detail="Ability was not found in the session ability tree.")
    validation = validate_ability(ability)
    if validation:
        return RpgAbilityUseResult(ok=False, ability_id=ability.get("ability_id"), name=ability.get("name"), error="invalid_ability", detail="; ".join(validation))
    ability_state = _safe_dict(state.get("ability_state"))
    state["ability_state"] = ability_state
    unlocked = set(str(value) for value in _safe_list(ability_state.get("unlocked")))
    ability_id = str(ability.get("ability_id"))
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
        maximum = int(metric.get("max") or current)
        if current < int(cost):
            return RpgAbilityUseResult(ok=False, ability_id=ability_id, name=ability.get("name"), error="insufficient_resource", detail=f"{ability.get('name')} requires {cost} {resource}, but only {current}/{maximum} is available.")
    for resource, cost in _safe_dict(ability.get("resource_cost")).items():
        metric = _resource_metric(player, str(resource))
        current = int(metric.get("current") or 0)
        metric["current"] = max(0, current - int(cost))
        cost_parts.append(f"{resource}: {metric['current']}/{metric.get('max')}")
    effects = execute_effect_ops(state, ability, target=target or "self")
    cooldown = int(ability.get("cooldown_turns") or 0)
    _tick_cooldowns(ability_state)
    if cooldown > 0:
        ability_state["cooldowns"][ability_id] = cooldown
    active_effects = _safe_list(ability_state.get("active_effects"))
    active_effects.insert(
        0,
        {
            "ability_id": ability_id,
            "name": ability.get("name"),
            "dimensions": ability.get("dimensions", []),
            "purpose": ability.get("purpose"),
            "target": target or "self",
            "created_at": _utc_now(),
        },
    )
    ability_state["active_effects"] = active_effects[:20]
    dimensions = ", ".join(str(value) for value in ability.get("dimensions", []))
    cost_detail = f" Costs now {', '.join(cost_parts)}." if cost_parts else ""
    detail = f"You used {ability.get('name')} on {target or 'the current situation'}, changing {dimensions}.{cost_detail}"
    return RpgAbilityUseResult(ok=True, ability_id=ability_id, name=str(ability.get("name")), detail=detail, effects=effects)


def hotbar_preview_from_state(state: dict[str, Any]) -> list[dict[str, str]]:
    tree = _safe_dict(state.get("ability_tree"))
    ability_index = _ability_index(tree)
    ability_state = _safe_dict(state.get("ability_state"))
    hotbar = _safe_dict(state.get("hotbar")) or _safe_dict(ability_state.get("hotbar"))
    previews: list[dict[str, str]] = []
    for slot in sorted(hotbar, key=lambda value: int(value) if str(value).isdigit() else 999):
        ability = ability_index.get(str(hotbar[slot]))
        if ability:
            previews.append({"key": str(slot), "icon": str(ability.get("icon") or "✦"), "label": str(ability.get("name") or ability.get("ability_id"))})
    return previews
