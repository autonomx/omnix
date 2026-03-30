"""
Data models for the AI Role-Playing System.

Defines the persistent data structures for worlds, characters, players,
history logs, and game sessions.
"""

import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Agent Identity
# ---------------------------------------------------------------------------

@dataclass
class AgentProfile:
    """Persistent identity for an LLM agent, ensuring consistent tone/style."""
    name: str = ""
    tone: str = ""
    style_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "tone": self.tone,
            "style_notes": list(self.style_notes),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentProfile":
        return cls(
            name=data.get("name", ""),
            tone=data.get("tone", ""),
            style_notes=data.get("style_notes", []),
        )

    def to_prompt_prefix(self) -> str:
        """Generate a prompt prefix that injects agent identity."""
        if not self.tone:
            return ""
        parts = [f"Your narrative tone is: {self.tone}."]
        for note in self.style_notes:
            parts.append(note)
        return " ".join(parts)


# ---------------------------------------------------------------------------
# World Time
# ---------------------------------------------------------------------------

HOURS_PER_PERIOD = {"morning": (6, 11), "afternoon": (12, 16), "evening": (17, 20), "night": (21, 5)}
SEASONS = ["spring", "summer", "autumn", "winter"]


@dataclass
class WorldTime:
    """Granular world clock with hour, day, and season tracking."""
    hour: int = 8
    day: int = 1
    season: str = "spring"

    def to_dict(self) -> Dict[str, Any]:
        return {"hour": self.hour, "day": self.day, "season": self.season}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorldTime":
        return cls(
            hour=data.get("hour", 8),
            day=data.get("day", 1),
            season=data.get("season", "spring"),
        )

    @property
    def period(self) -> str:
        """Get time-of-day period from hour."""
        if 6 <= self.hour <= 11:
            return "morning"
        if 12 <= self.hour <= 16:
            return "afternoon"
        if 17 <= self.hour <= 20:
            return "evening"
        return "night"

    def advance(self, hours: int = 1) -> None:
        """Advance time by a number of hours."""
        self.hour += hours
        while self.hour >= 24:
            self.hour -= 24
            self.day += 1
            # Season changes every 30 days.
            # Day 1 is excluded (initial season). Transitions happen at day 31, 61, 91, 121 …
            if self.day >= 31 and (self.day - 1) % 30 == 0:
                idx = SEASONS.index(self.season) if self.season in SEASONS else 0
                self.season = SEASONS[(idx + 1) % len(SEASONS)]

    def __str__(self) -> str:
        return f"Day {self.day}, {self.hour:02d}:00 ({self.period}, {self.season})"


# ---------------------------------------------------------------------------
# Economy: Item Model
# ---------------------------------------------------------------------------

@dataclass
class Item:
    """An item with economic properties."""
    name: str
    base_price: int = 10
    rarity: str = "common"
    description: str = ""

    # Rarity multipliers for pricing
    RARITY_MULTIPLIERS = {"common": 1.0, "uncommon": 1.5, "rare": 3.0, "legendary": 10.0}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "base_price": self.base_price,
            "rarity": self.rarity,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Item":
        return cls(
            name=data.get("name", "unknown"),
            base_price=data.get("base_price", 10),
            rarity=data.get("rarity", "common"),
            description=data.get("description", ""),
        )


def calculate_price(item: Item, location_modifier: float = 1.0,
                    relationship: int = 0) -> int:
    """
    Calculate the actual price of an item based on economy factors.

    Formula: base_price * rarity_mult * location_mod * relationship_mod

    Relationship is expected in range -100 to +100.
    Dividing by 500 maps this to a +-0.2 adjustment around 1.0:
      rel=+100 -> mod=0.8 (20% discount)
      rel=0    -> mod=1.0 (no change)
      rel=-100 -> mod=1.2 (20% markup)
    Clamped to [0.8, 1.3] to prevent extreme outliers.
    """
    rarity_mult = Item.RARITY_MULTIPLIERS.get(item.rarity, 1.0)
    # Relationship modifier: see docstring for formula explanation.
    # Positive relationship → discount (mod < 1), negative → markup (mod > 1).
    rel_mod = 1.0 - (relationship / 500.0)
    rel_mod = max(0.8, min(1.3, rel_mod))
    price = item.base_price * rarity_mult * location_modifier * rel_mod
    return max(1, int(round(price)))


# ---------------------------------------------------------------------------
# Crafting System
# ---------------------------------------------------------------------------

@dataclass
class CraftingRecipe:
    """A recipe that transforms input items into an output item."""
    name: str
    inputs: Dict[str, int] = field(default_factory=dict)  # item_name → quantity
    output: str = ""
    output_quantity: int = 1
    required_skill: str = ""       # e.g. "blacksmithing"
    required_skill_level: int = 0
    difficulty: int = 5            # DC for crafting skill check

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "inputs": dict(self.inputs),
            "output": self.output,
            "output_quantity": self.output_quantity,
            "required_skill": self.required_skill,
            "required_skill_level": self.required_skill_level,
            "difficulty": self.difficulty,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CraftingRecipe":
        return cls(
            name=data.get("name", ""),
            inputs=data.get("inputs", {}),
            output=data.get("output", ""),
            output_quantity=data.get("output_quantity", 1),
            required_skill=data.get("required_skill", ""),
            required_skill_level=data.get("required_skill_level", 0),
            difficulty=data.get("difficulty", 5),
        )


@dataclass
class SkillNode:
    """A node in a skill tree, representing a learnable ability."""
    name: str
    description: str = ""
    max_level: int = 5
    prerequisites: List[str] = field(default_factory=list)  # other skill names
    stat_bonus: Dict[str, int] = field(default_factory=dict)  # stat → bonus per level

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "max_level": self.max_level,
            "prerequisites": list(self.prerequisites),
            "stat_bonus": dict(self.stat_bonus),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SkillNode":
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            max_level=data.get("max_level", 5),
            prerequisites=data.get("prerequisites", []),
            stat_bonus=data.get("stat_bonus", {}),
        )


def can_learn_skill(
    current_skills: Dict[str, Dict[str, int]],
    skill_node: SkillNode,
) -> bool:
    """Check if a character meets prerequisites and level cap for a skill."""
    current = current_skills.get(skill_node.name, {})
    if current.get("level", 0) >= skill_node.max_level:
        return False
    for prereq in skill_node.prerequisites:
        if prereq not in current_skills or current_skills[prereq].get("level", 0) < 1:
            return False
    return True


def attempt_craft(
    recipe: CraftingRecipe,
    inventory: List[str],
    skills: Dict[str, Dict[str, int]],
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Attempt to craft an item from a recipe.

    Checks inventory for required inputs, validates skill requirements,
    and performs a skill check.  Does NOT mutate inventory — caller
    should apply the result.

    Returns dict with keys: success, outcome, missing_items, skill_too_low.
    """
    # Check skill requirement
    if recipe.required_skill:
        skill_data = skills.get(recipe.required_skill, {})
        if skill_data.get("level", 0) < recipe.required_skill_level:
            return {
                "success": False,
                "outcome": "skill_too_low",
                "missing_items": [],
                "skill_too_low": True,
            }

    # Check inventory
    inv_counts: Dict[str, int] = {}
    for item in inventory:
        inv_counts[item] = inv_counts.get(item, 0) + 1

    missing: List[str] = []
    for item_name, qty in recipe.inputs.items():
        if inv_counts.get(item_name, 0) < qty:
            missing.append(item_name)

    if missing:
        return {
            "success": False,
            "outcome": "missing_materials",
            "missing_items": missing,
            "skill_too_low": False,
        }

    # Skill check for crafting
    stat_value = skills.get(recipe.required_skill, {}).get("level", 0)
    result = skill_check(stat_value, recipe.difficulty, seed=seed)

    return {
        "success": result["outcome"] in ("success", "critical_success"),
        "outcome": result["outcome"],
        "missing_items": [],
        "skill_too_low": False,
    }


# ---------------------------------------------------------------------------
# Dice / Probability System
# ---------------------------------------------------------------------------

def skill_check(stat_value: int, difficulty: int, seed: Optional[int] = None) -> Dict[str, Any]:
    """
    Perform a d20 skill check with tiered outcomes (soft failure system).

    Roll = random(1, 20) + stat_value
    DC = difficulty + 10

    Outcome tiers:
      critical_fail   — natural 1
      fail            — total < DC - 3
      partial_success — total in [DC-3, DC-1]
      success         — total >= DC
      critical_success— natural 20

    Returns dict with roll, total, difficulty, passed, outcome tier, and critical flags.
    """
    rng = random.Random(seed) if seed is not None else random
    roll = rng.randint(1, 20)
    total = roll + stat_value
    dc = difficulty + 10
    critical_success = roll == 20
    critical_failure = roll == 1

    # Determine outcome tier
    if critical_failure:
        outcome = "critical_fail"
        passed = False
    elif critical_success:
        outcome = "critical_success"
        passed = True
    elif total >= dc:
        outcome = "success"
        passed = True
    elif total >= dc - 3:
        outcome = "partial_success"
        passed = True  # partial counts as passed with consequences
    else:
        outcome = "fail"
        passed = False

    return {
        "roll": roll,
        "stat_value": stat_value,
        "total": total,
        "difficulty": difficulty,
        "dc": dc,
        "passed": passed,
        "outcome": outcome,
        "critical_success": critical_success,
        "critical_failure": critical_failure,
    }


@dataclass
class WorldRules:
    """Constraints and rules governing a game world."""
    technology_level: str = "pre-industrial"
    magic_system: str = "limited"
    allowed_items: List[str] = field(default_factory=lambda: ["swords", "bows", "magic artifacts"])
    forbidden_items: List[str] = field(default_factory=lambda: ["guns", "nuclear weapons"])
    custom_rules: List[str] = field(default_factory=list)
    existing_creatures: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "technology_level": self.technology_level,
            "magic_system": self.magic_system,
            "allowed_items": list(self.allowed_items),
            "forbidden_items": list(self.forbidden_items),
            "custom_rules": list(self.custom_rules),
            "existing_creatures": list(self.existing_creatures),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorldRules":
        return cls(
            technology_level=data.get("technology_level", "pre-industrial"),
            magic_system=data.get("magic_system", "limited"),
            allowed_items=data.get("allowed_items", ["swords", "bows", "magic artifacts"]),
            forbidden_items=data.get("forbidden_items", ["guns", "nuclear weapons"]),
            custom_rules=data.get("custom_rules", []),
            existing_creatures=data.get("existing_creatures", []),
        )


@dataclass
class Location:
    """A location in the game world."""
    name: str
    description: str
    connected_to: List[str] = field(default_factory=list)
    npcs_present: List[str] = field(default_factory=list)
    items_available: List[str] = field(default_factory=list)
    market_modifier: float = 1.0
    shop_open_hours: List[int] = field(default_factory=lambda: list(range(6, 21)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "connected_to": list(self.connected_to),
            "npcs_present": list(self.npcs_present),
            "items_available": list(self.items_available),
            "market_modifier": self.market_modifier,
            "shop_open_hours": list(self.shop_open_hours),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Location":
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            connected_to=data.get("connected_to", []),
            npcs_present=data.get("npcs_present", []),
            items_available=data.get("items_available", []),
            market_modifier=data.get("market_modifier", 1.0),
            shop_open_hours=data.get("shop_open_hours", list(range(6, 21))),
        )


@dataclass
class Faction:
    """A faction or group in the game world."""
    name: str
    description: str
    alignment: str = "neutral"
    members: List[str] = field(default_factory=list)
    goals: List[str] = field(default_factory=list)
    # Faction ideology drives NPC behaviour via utility scoring
    ideology: Dict[str, float] = field(default_factory=dict)
    # Relations with other factions (-100..100)
    relations: Dict[str, int] = field(default_factory=dict)
    # Faction-level strategy: "expand", "defend", "deceive", "trade", "neutral"
    strategy: str = "neutral"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "alignment": self.alignment,
            "members": list(self.members),
            "goals": list(self.goals),
            "ideology": dict(self.ideology),
            "relations": dict(self.relations),
            "strategy": self.strategy,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Faction":
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            alignment=data.get("alignment", "neutral"),
            members=data.get("members", []),
            goals=data.get("goals", []),
            ideology=data.get("ideology", {}),
            relations=data.get("relations", {}),
            strategy=data.get("strategy", "neutral"),
        )


@dataclass
class WorldState:
    """The complete state of a game world."""
    world_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    seed: int = 0
    name: str = ""
    genre: str = "medieval fantasy"
    description: str = ""
    rules: WorldRules = field(default_factory=WorldRules)
    locations: List[Location] = field(default_factory=list)
    factions: List[Faction] = field(default_factory=list)
    lore: str = ""
    time_of_day: str = "morning"
    day_count: int = 1
    world_time: WorldTime = field(default_factory=WorldTime)
    agent_profiles: Dict[str, AgentProfile] = field(default_factory=dict)
    items_catalog: List[Item] = field(default_factory=list)
    active_world_events: List["WorldEvent"] = field(default_factory=list)
    # Global resources that drive emergent events (famine, unrest, etc.)
    resources: Dict[str, int] = field(default_factory=lambda: {
        "food": 100,
        "gold": 100,
        "security": 100,
    })
    # Global event log that NPCs can consume for shared world awareness
    world_events_log: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "world_id": self.world_id,
            "seed": self.seed,
            "name": self.name,
            "genre": self.genre,
            "description": self.description,
            "rules": self.rules.to_dict(),
            "locations": [loc.to_dict() for loc in self.locations],
            "factions": [fac.to_dict() for fac in self.factions],
            "lore": self.lore,
            "time_of_day": self.time_of_day,
            "day_count": self.day_count,
            "world_time": self.world_time.to_dict(),
            "agent_profiles": {k: v.to_dict() for k, v in self.agent_profiles.items()},
            "items_catalog": [item.to_dict() for item in self.items_catalog],
            "active_world_events": [we.to_dict() for we in self.active_world_events],
            "resources": dict(self.resources),
            "world_events_log": list(self.world_events_log),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorldState":
        return cls(
            world_id=data.get("world_id", str(uuid.uuid4())),
            seed=data.get("seed", 0),
            name=data.get("name", ""),
            genre=data.get("genre", "medieval fantasy"),
            description=data.get("description", ""),
            rules=WorldRules.from_dict(data.get("rules", {})),
            locations=[Location.from_dict(loc) for loc in data.get("locations", [])],
            factions=[Faction.from_dict(fac) for fac in data.get("factions", [])],
            lore=data.get("lore", ""),
            time_of_day=data.get("time_of_day", "morning"),
            day_count=data.get("day_count", 1),
            world_time=WorldTime.from_dict(data.get("world_time", {})),
            agent_profiles={k: AgentProfile.from_dict(v) for k, v in data.get("agent_profiles", {}).items()},
            items_catalog=[Item.from_dict(i) for i in data.get("items_catalog", [])],
            active_world_events=[WorldEvent.from_dict(we) for we in data.get("active_world_events", [])],
            resources=data.get("resources", {"food": 100, "gold": 100, "security": 100}),
            world_events_log=data.get("world_events_log", []),
        )

    def get_location(self, name: str) -> Optional[Location]:
        """Find a location by name (case-insensitive)."""
        name_lower = name.lower()
        for loc in self.locations:
            if loc.name.lower() == name_lower:
                return loc
        return None

    def get_item(self, name: str) -> Optional[Item]:
        """Find an item in the catalog by name (case-insensitive)."""
        name_lower = name.lower()
        for item in self.items_catalog:
            if item.name.lower() == name_lower:
                return item
        return None


@dataclass
class CharacterStats:
    """Stats for an NPC or player character."""
    strength: int = 5
    dexterity: int = 5
    constitution: int = 5
    intelligence: int = 5
    wisdom: int = 5
    charisma: int = 5
    wealth: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "strength": self.strength,
            "dexterity": self.dexterity,
            "constitution": self.constitution,
            "intelligence": self.intelligence,
            "wisdom": self.wisdom,
            "charisma": self.charisma,
            "wealth": self.wealth,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CharacterStats":
        return cls(
            strength=data.get("strength", 5),
            dexterity=data.get("dexterity", 5),
            constitution=data.get("constitution", 5),
            intelligence=data.get("intelligence", 5),
            wisdom=data.get("wisdom", 5),
            charisma=data.get("charisma", 5),
            wealth=data.get("wealth", 0),
        )


@dataclass
class NPCCharacter:
    """A non-player character in the game world."""
    name: str
    role: str
    personality: List[str] = field(default_factory=list)
    goals: List[str] = field(default_factory=list)
    stats: CharacterStats = field(default_factory=CharacterStats)
    relationships: Dict[str, int] = field(default_factory=dict)
    inventory: List[str] = field(default_factory=list)
    location: str = ""
    secret: str = ""
    fear: str = ""
    hidden_goal: str = ""
    # NPC Autonomy fields
    current_action: str = "idle"
    schedule: Dict[str, str] = field(default_factory=dict)
    known_facts: List[str] = field(default_factory=list)
    # Emotional memory model
    emotional_state: Dict[str, float] = field(default_factory=dict)
    memories: List[Dict[str, Any]] = field(default_factory=list)
    opinions: Dict[str, int] = field(default_factory=dict)
    # Personality traits (e.g. {"aggressive": 0.8, "greedy": 0.6, "loyal": 0.2})
    personality_traits: Dict[str, float] = field(default_factory=dict)
    # Needs drive NPC goals (e.g. {"wealth": 0.7, "safety": 0.3, "power": 0.5})
    needs: Dict[str, float] = field(default_factory=dict)
    # Structured goals with progress tracking
    # e.g. [{"type": "gain_power", "target": "village", "progress": 0.3, "priority": 0.8}]
    active_goals: List[Dict[str, Any]] = field(default_factory=list)
    # ── LLM-driven NPC Mind fields ──────────────────────────────────────────
    # Beliefs: subjective confidence scores (e.g. {"player_is_hostile": 0.7})
    beliefs: Dict[str, float] = field(default_factory=dict)
    # Hidden knowledge the NPC possesses but may not reveal
    secrets_knowledge: List[str] = field(default_factory=list)
    # Expressed state: what the NPC *shows* (may differ from true intent)
    expressed_state: Dict[str, str] = field(default_factory=dict)
    # Condensed narrative summary of memories for LLM context
    memory_summary: str = ""
    # Per-NPC LLM profile (system_prompt, temperature, style)
    llm_profile: Dict[str, Any] = field(default_factory=dict)
    # ── Advanced NPC Intelligence fields ─────────────────────────────────────
    # Causal belief graph: belief_key → [{"source": str, "weight": float}]
    belief_sources: Dict[str, List[Dict[str, float]]] = field(default_factory=dict)
    # Deception mode: "none", "conceal", "distort", "fabricate", "signal"
    deception_mode: str = "none"
    # Theory of mind: what this NPC thinks others believe
    # e.g. {"player": {"guard_is_friendly": 0.6}, "merchant": {"city_is_safe": 0.8}}
    theory_of_mind: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # Skill tree: skill_name → {"level": int, "xp": int, "max_level": int}
    skills: Dict[str, Dict[str, int]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "personality": list(self.personality),
            "goals": list(self.goals),
            "stats": self.stats.to_dict(),
            "relationships": dict(self.relationships),
            "inventory": list(self.inventory),
            "location": self.location,
            "secret": self.secret,
            "fear": self.fear,
            "hidden_goal": self.hidden_goal,
            "current_action": self.current_action,
            "schedule": dict(self.schedule),
            "known_facts": list(self.known_facts),
            "emotional_state": dict(self.emotional_state),
            "memories": [dict(m) for m in self.memories],
            "opinions": dict(self.opinions),
            "personality_traits": dict(self.personality_traits),
            "needs": dict(self.needs),
            "active_goals": [dict(g) for g in self.active_goals],
            "beliefs": dict(self.beliefs),
            "secrets_knowledge": list(self.secrets_knowledge),
            "expressed_state": dict(self.expressed_state),
            "memory_summary": self.memory_summary,
            "llm_profile": dict(self.llm_profile),
            "belief_sources": {k: [dict(s) for s in v] for k, v in self.belief_sources.items()},
            "deception_mode": self.deception_mode,
            "theory_of_mind": {k: dict(v) for k, v in self.theory_of_mind.items()},
            "skills": {k: dict(v) for k, v in self.skills.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NPCCharacter":
        return cls(
            name=data["name"],
            role=data.get("role", "villager"),
            personality=data.get("personality", []),
            goals=data.get("goals", []),
            stats=CharacterStats.from_dict(data.get("stats", {})),
            relationships=data.get("relationships", {}),
            inventory=data.get("inventory", []),
            location=data.get("location", ""),
            secret=data.get("secret", ""),
            fear=data.get("fear", ""),
            hidden_goal=data.get("hidden_goal", ""),
            current_action=data.get("current_action", "idle"),
            schedule=data.get("schedule", {}),
            known_facts=data.get("known_facts", []),
            emotional_state=data.get("emotional_state", {}),
            memories=data.get("memories", []),
            opinions=data.get("opinions", {}),
            personality_traits=data.get("personality_traits", {}),
            needs=data.get("needs", {}),
            active_goals=data.get("active_goals", []),
            beliefs=data.get("beliefs", {}),
            secrets_knowledge=data.get("secrets_knowledge", []),
            expressed_state=data.get("expressed_state", {}),
            memory_summary=data.get("memory_summary", ""),
            llm_profile=data.get("llm_profile", {}),
            belief_sources=data.get("belief_sources", {}),
            deception_mode=data.get("deception_mode", "none"),
            theory_of_mind=data.get("theory_of_mind", {}),
            skills=data.get("skills", {}),
        )


# ---------------------------------------------------------------------------
# Character Classes
# ---------------------------------------------------------------------------

CHARACTER_CLASSES: Dict[str, Dict[str, int]] = {
    "warrior": {"strength": 3, "constitution": 2},
    "mage": {"intelligence": 3, "wisdom": 2},
    "rogue": {"dexterity": 3, "charisma": 2},
}

DEFAULT_SKILLS: Dict[str, int] = {
    "swordsmanship": 1,
    "stealth": 1,
    "persuasion": 1,
    "magic": 1,
}

# ---------------------------------------------------------------------------
# Stat Check (d20 + stat + skill)
# ---------------------------------------------------------------------------

DIFFICULTY_TABLE: Dict[str, int] = {
    "easy": 8,
    "normal": 12,
    "hard": 16,
    "elite": 20,
}


def stat_check(
    stat_value: int,
    skill_value: int,
    difficulty: str = "normal",
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Perform a d20 stat check: roll = d20 + stat + skill vs difficulty target.

    Returns dict with roll, stat, skill, total, target, success, and critical flags.
    """
    rng = random.Random(seed) if seed is not None else random
    roll = rng.randint(1, 20)
    total = roll + stat_value + skill_value
    target = DIFFICULTY_TABLE.get(difficulty, 12)
    return {
        "roll": roll,
        "stat": stat_value,
        "skill": skill_value,
        "total": total,
        "target": target,
        "success": total >= target,
        "critical_success": roll == 20,
        "critical_fail": roll == 1,
    }


# ---------------------------------------------------------------------------
# XP / Leveling
# ---------------------------------------------------------------------------

def gain_xp(player: "PlayerState", amount: int) -> List[str]:
    """
    Award XP to a player.  Automatically triggers level-ups.

    Returns a list of messages describing any level-ups that occurred.
    """
    messages: List[str] = []
    player.xp += amount
    while player.xp >= player.xp_to_next:
        player.xp -= player.xp_to_next
        _level_up(player)
        messages.append(f"Level up! Now level {player.level}.")
    return messages


def _level_up(player: "PlayerState") -> None:
    """Apply a single level-up to *player*."""
    player.level += 1
    player.xp_to_next = int(player.xp_to_next * 1.5)
    player.max_hp += 10
    player.hp = player.max_hp
    player.unspent_points += 3


@dataclass
class PlayerState:
    """The player's character state."""
    name: str = "Player"
    character_class: str = ""
    level: int = 1
    xp: int = 0
    xp_to_next: int = 100
    hp: int = 100
    max_hp: int = 100
    stamina: int = 100
    max_stamina: int = 100
    mana: int = 50
    max_mana: int = 50
    unspent_points: int = 0
    stats: CharacterStats = field(default_factory=lambda: CharacterStats(
        strength=8, dexterity=5, constitution=5, intelligence=6, wisdom=5, charisma=3, wealth=50
    ))
    skills: Dict[str, int] = field(default_factory=lambda: dict(DEFAULT_SKILLS))
    inventory: List[str] = field(default_factory=list)
    location: str = ""
    reputation_local: int = 0
    reputation_global: int = 0
    quests_active: List[str] = field(default_factory=list)
    quests_completed: List[str] = field(default_factory=list)
    known_facts: List[str] = field(default_factory=list)
    is_alive: bool = True
    fail_state: str = ""
    reputation_factions: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "character_class": self.character_class,
            "level": self.level,
            "xp": self.xp,
            "xp_to_next": self.xp_to_next,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "stamina": self.stamina,
            "max_stamina": self.max_stamina,
            "mana": self.mana,
            "max_mana": self.max_mana,
            "unspent_points": self.unspent_points,
            "stats": self.stats.to_dict(),
            "skills": dict(self.skills),
            "inventory": list(self.inventory),
            "location": self.location,
            "reputation_local": self.reputation_local,
            "reputation_global": self.reputation_global,
            "quests_active": list(self.quests_active),
            "quests_completed": list(self.quests_completed),
            "known_facts": list(self.known_facts),
            "is_alive": self.is_alive,
            "fail_state": self.fail_state,
            "reputation_factions": dict(self.reputation_factions),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlayerState":
        return cls(
            name=data.get("name", "Player"),
            character_class=data.get("character_class", ""),
            level=data.get("level", 1),
            xp=data.get("xp", 0),
            xp_to_next=data.get("xp_to_next", 100),
            hp=data.get("hp", 100),
            max_hp=data.get("max_hp", 100),
            stamina=data.get("stamina", 100),
            max_stamina=data.get("max_stamina", 100),
            mana=data.get("mana", 50),
            max_mana=data.get("max_mana", 50),
            unspent_points=data.get("unspent_points", 0),
            stats=CharacterStats.from_dict(data.get("stats", {
                "strength": 8, "dexterity": 5, "constitution": 5,
                "intelligence": 6, "wisdom": 5, "charisma": 3, "wealth": 50
            })),
            skills=data.get("skills", dict(DEFAULT_SKILLS)),
            inventory=data.get("inventory", []),
            location=data.get("location", ""),
            reputation_local=data.get("reputation_local", 0),
            reputation_global=data.get("reputation_global", 0),
            quests_active=data.get("quests_active", []),
            quests_completed=data.get("quests_completed", []),
            known_facts=data.get("known_facts", []),
            is_alive=data.get("is_alive", True),
            fail_state=data.get("fail_state", ""),
            reputation_factions=data.get("reputation_factions", {}),
        )


@dataclass
class HistoryEvent:
    """A single event in the game history log with importance scoring."""
    event: str
    impact: Dict[str, Any] = field(default_factory=dict)
    turn: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    importance: float = 0.5
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event": self.event,
            "impact": dict(self.impact),
            "turn": self.turn,
            "timestamp": self.timestamp,
            "importance": self.importance,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HistoryEvent":
        return cls(
            event=data["event"],
            impact=data.get("impact", {}),
            turn=data.get("turn", 0),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            importance=data.get("importance", 0.5),
            tags=data.get("tags", []),
        )


@dataclass
class PendingConsequence:
    """
    A delayed consequence that triggers on a future turn.

    Represents causality chains: something happens now, and a resulting
    effect fires later when ``trigger_turn`` is reached (and, optionally,
    when ``condition`` evaluates truthy against the session state).
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trigger_turn: int = 0
    source_event: str = ""
    condition: Optional[str] = None
    effect_diff: Dict[str, Any] = field(default_factory=dict)
    narrative: str = ""
    importance: float = 0.7
    # Cascading consequences: follow-up consequences spawned when this one fires
    next_consequences: List[Dict[str, Any]] = field(default_factory=list)
    chain_id: Optional[str] = None
    # Consequence classification: "world", "npc", "narrative", "hidden"
    type: str = "world"
    # Visibility: "visible", "hidden", "foreshadowed"
    visibility: str = "visible"
    # Decay rate: how much importance decreases per turn (0 = no decay)
    decay_rate: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "id": self.id,
            "trigger_turn": self.trigger_turn,
            "source_event": self.source_event,
            "effect_diff": dict(self.effect_diff),
            "narrative": self.narrative,
            "importance": self.importance,
            "next_consequences": [dict(nc) for nc in self.next_consequences],
            "type": self.type,
            "visibility": self.visibility,
            "decay_rate": self.decay_rate,
        }
        if self.condition is not None:
            result["condition"] = self.condition
        if self.chain_id is not None:
            result["chain_id"] = self.chain_id
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PendingConsequence":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            trigger_turn=data.get("trigger_turn", 0),
            source_event=data.get("source_event", ""),
            condition=data.get("condition"),
            effect_diff=data.get("effect_diff", {}),
            narrative=data.get("narrative", ""),
            importance=data.get("importance", 0.7),
            next_consequences=data.get("next_consequences", []),
            chain_id=data.get("chain_id"),
            type=data.get("type", "world"),
            visibility=data.get("visibility", "visible"),
            decay_rate=data.get("decay_rate", 0.0),
        )


@dataclass
class WorldEvent:
    """
    A world-level event that affects locations, NPCs, and the economy.

    Events like wars, plagues, and festivals create macro-level world
    changes that persist for ``duration`` turns and apply ``effects``
    to ``affected_locations``.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: str = ""
    description: str = ""
    duration: int = 1
    remaining_turns: int = 0
    effects: Dict[str, Any] = field(default_factory=dict)
    affected_locations: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.remaining_turns == 0:
            self.remaining_turns = self.duration

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "description": self.description,
            "duration": self.duration,
            "remaining_turns": self.remaining_turns,
            "effects": dict(self.effects),
            "affected_locations": list(self.affected_locations),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorldEvent":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            type=data.get("type", ""),
            description=data.get("description", ""),
            duration=data.get("duration", 1),
            remaining_turns=data.get("remaining_turns", 0),
            effects=data.get("effects", {}),
            affected_locations=data.get("affected_locations", []),
        )


@dataclass
class Quest:
    """A quest or mission in the game with stages and branching paths."""
    quest_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    giver: str = ""
    objectives: List[str] = field(default_factory=list)
    rewards: Dict[str, Any] = field(default_factory=dict)
    status: str = "active"
    stages: List[str] = field(default_factory=list)
    current_stage: int = 0
    failure_conditions: List[str] = field(default_factory=list)
    branching_paths: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quest_id": self.quest_id,
            "title": self.title,
            "description": self.description,
            "giver": self.giver,
            "objectives": list(self.objectives),
            "rewards": dict(self.rewards),
            "status": self.status,
            "stages": list(self.stages),
            "current_stage": self.current_stage,
            "failure_conditions": list(self.failure_conditions),
            "branching_paths": [dict(p) for p in self.branching_paths],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Quest":
        return cls(
            quest_id=data.get("quest_id", str(uuid.uuid4())),
            title=data.get("title", ""),
            description=data.get("description", ""),
            giver=data.get("giver", ""),
            objectives=data.get("objectives", []),
            rewards=data.get("rewards", {}),
            status=data.get("status", "active"),
            stages=data.get("stages", []),
            current_stage=data.get("current_stage", 0),
            failure_conditions=data.get("failure_conditions", []),
            branching_paths=data.get("branching_paths", []),
        )


@dataclass
class PlayerIntent:
    """Structured representation of a player's action intent."""
    raw_input: str
    intent: str = ""
    target: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_input": self.raw_input,
            "intent": self.intent,
            "target": self.target,
            "details": dict(self.details),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlayerIntent":
        return cls(
            raw_input=data.get("raw_input", ""),
            intent=data.get("intent", ""),
            target=data.get("target", ""),
            details=data.get("details", {}),
        )


@dataclass
class TurnResult:
    """Result of a single turn execution."""
    narration: str = ""
    events: List[HistoryEvent] = field(default_factory=list)
    state_changes: Dict[str, Any] = field(default_factory=dict)
    choices: List[str] = field(default_factory=list)
    error: Optional[str] = None
    dice_roll: Optional[Dict[str, Any]] = None
    fail_state: str = ""

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "narration": self.narration,
            "events": [e.to_dict() for e in self.events],
            "state_changes": dict(self.state_changes),
            "choices": list(self.choices),
        }
        if self.error:
            result["error"] = self.error
        if self.dice_roll:
            result["dice_roll"] = self.dice_roll
        if self.fail_state:
            result["fail_state"] = self.fail_state
        return result


@dataclass
class TurnLog:
    """
    Deterministic replay log entry for a single turn.

    Captures every pipeline artifact so that turns can be reproduced,
    debugged, and audited.

    ``version`` tracks the schema revision so that older logs can be
    migrated when the format changes.  ``seed`` stores the exact RNG
    seed used for the turn's dice roll so replays are reproducible
    even if the seed-derivation strategy changes.
    ``diff_validation`` records any validation issues, rejected fields,
    or clamped values produced when applying the diff.
    """
    version: int = 1
    turn: int = 0
    seed: Optional[int] = None
    raw_input: str = ""
    normalized_intent: Dict[str, Any] = field(default_factory=dict)
    dice_roll: Optional[Dict[str, Any]] = None
    event_output: Dict[str, Any] = field(default_factory=dict)
    canon_check: Dict[str, Any] = field(default_factory=dict)
    applied_diff: Dict[str, Any] = field(default_factory=dict)
    diff_validation: Dict[str, Any] = field(default_factory=dict)
    narration: str = ""

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "version": self.version,
            "turn": self.turn,
            "raw_input": self.raw_input,
            "normalized_intent": dict(self.normalized_intent),
            "event_output": dict(self.event_output),
            "canon_check": dict(self.canon_check),
            "applied_diff": dict(self.applied_diff),
            "diff_validation": dict(self.diff_validation),
            "narration": self.narration,
        }
        if self.seed is not None:
            result["seed"] = self.seed
        if self.dice_roll is not None:
            result["dice_roll"] = dict(self.dice_roll)
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TurnLog":
        return cls(
            version=data.get("version", 1),
            turn=data.get("turn", 0),
            seed=data.get("seed"),
            raw_input=data.get("raw_input", ""),
            normalized_intent=data.get("normalized_intent", {}),
            dice_roll=data.get("dice_roll"),
            event_output=data.get("event_output", {}),
            canon_check=data.get("canon_check", {}),
            applied_diff=data.get("applied_diff", {}),
            diff_validation=data.get("diff_validation", {}),
            narration=data.get("narration", ""),
        )


@dataclass
class StoryArc:
    """
    A dynamic story arc that progresses through stages.

    Arcs are created from significant events and track narrative threads
    (e.g. revenge plots, wars, mysteries) through setup → rising →
    climax → resolution.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: str = ""           # e.g. "revenge", "war", "mystery", "romance"
    stage: str = "setup"     # setup, rising, climax, resolution
    participants: List[str] = field(default_factory=list)
    progress: float = 0.0   # 0.0 .. 1.0
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "stage": self.stage,
            "participants": list(self.participants),
            "progress": self.progress,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoryArc":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            type=data.get("type", ""),
            stage=data.get("stage", "setup"),
            participants=data.get("participants", []),
            progress=data.get("progress", 0.0),
            description=data.get("description", ""),
        )


@dataclass
class GameSession:
    """A complete game session with all state."""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    world: WorldState = field(default_factory=WorldState)
    player: PlayerState = field(default_factory=PlayerState)
    npcs: List[NPCCharacter] = field(default_factory=list)
    quests: List[Quest] = field(default_factory=list)
    history: List[HistoryEvent] = field(default_factory=list)
    turn_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    mid_term_summary: str = ""
    narrative_act: int = 1
    narrative_tension: float = 0.0
    turn_logs: List[TurnLog] = field(default_factory=list)
    pending_consequences: List[PendingConsequence] = field(default_factory=list)
    story_flags: Dict[str, bool] = field(default_factory=dict)
    story_arcs: List[StoryArc] = field(default_factory=list)
    voice_assignments: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "world": self.world.to_dict(),
            "player": self.player.to_dict(),
            "npcs": [npc.to_dict() for npc in self.npcs],
            "quests": [q.to_dict() for q in self.quests],
            "history": [h.to_dict() for h in self.history],
            "turn_count": self.turn_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "mid_term_summary": self.mid_term_summary,
            "narrative_act": self.narrative_act,
            "narrative_tension": self.narrative_tension,
            "turn_logs": [tl.to_dict() for tl in self.turn_logs],
            "pending_consequences": [pc.to_dict() for pc in self.pending_consequences],
            "story_flags": dict(self.story_flags),
            "story_arcs": [arc.to_dict() for arc in self.story_arcs],
            "voice_assignments": dict(self.voice_assignments),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GameSession":
        return cls(
            session_id=data.get("session_id", str(uuid.uuid4())),
            world=WorldState.from_dict(data.get("world", {})),
            player=PlayerState.from_dict(data.get("player", {})),
            npcs=[NPCCharacter.from_dict(npc) for npc in data.get("npcs", [])],
            quests=[Quest.from_dict(q) for q in data.get("quests", [])],
            history=[HistoryEvent.from_dict(h) for h in data.get("history", [])],
            turn_count=data.get("turn_count", 0),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            mid_term_summary=data.get("mid_term_summary", ""),
            narrative_act=data.get("narrative_act", 1),
            narrative_tension=data.get("narrative_tension", 0.0),
            turn_logs=[TurnLog.from_dict(tl) for tl in data.get("turn_logs", [])],
            pending_consequences=[PendingConsequence.from_dict(pc) for pc in data.get("pending_consequences", [])],
            story_flags=data.get("story_flags", {}),
            story_arcs=[StoryArc.from_dict(a) for a in data.get("story_arcs", [])],
            voice_assignments=data.get("voice_assignments", {}),
        )

    def get_npc(self, name: str) -> Optional[NPCCharacter]:
        """Find an NPC by name (case-insensitive)."""
        name_lower = name.lower()
        for npc in self.npcs:
            if npc.name.lower() == name_lower:
                return npc
        return None

    def get_quest(self, quest_id: str) -> Optional[Quest]:
        """Find a quest by ID."""
        for quest in self.quests:
            if quest.quest_id == quest_id:
                return quest
        return None

    def get_active_quests(self) -> List[Quest]:
        """Get all active quests."""
        return [q for q in self.quests if q.status == "active"]

    def get_npcs_at_location(self, location: str) -> List[NPCCharacter]:
        """Get all NPCs at a given location."""
        loc_lower = location.lower()
        return [npc for npc in self.npcs if npc.location.lower() == loc_lower]


# ---------------------------------------------------------------------------
# World State Diff (diff-based state mutation)
# ---------------------------------------------------------------------------

@dataclass
class WorldStateDiff:
    """
    A diff-based state update — agents produce diffs, not full state mutations.

    Fields use ``None`` for no change and explicit values for updates.
    Numeric values are *deltas* (e.g. ``health: -10`` means "subtract 10").
    """
    player_changes: Dict[str, Any] = field(default_factory=dict)
    npc_changes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    world_changes: Dict[str, Any] = field(default_factory=dict)
    events: List[HistoryEvent] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "player_changes": dict(self.player_changes),
            "npc_changes": {k: dict(v) for k, v in self.npc_changes.items()},
            "world_changes": dict(self.world_changes),
            "events": [e.to_dict() for e in self.events],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorldStateDiff":
        return cls(
            player_changes=data.get("player_changes", {}),
            npc_changes=data.get("npc_changes", {}),
            world_changes=data.get("world_changes", {}),
            events=[HistoryEvent.from_dict(e) for e in data.get("events", [])],
        )


# Whitelisted mutable stat fields on CharacterStats
_STAT_FIELDS = {"strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma", "wealth"}

# Whitelisted mutable fields on PlayerState that accept delta ints
_PLAYER_DELTA_FIELDS = {"reputation_local", "reputation_global", "hp", "stamina", "mana", "xp"}

# Whitelisted mutable fields on NPCCharacter that accept replacement values
_NPC_REPLACE_FIELDS = {"location", "current_action"}


def apply_diff(session: GameSession, diff: WorldStateDiff) -> Dict[str, Any]:
    """
    Apply a ``WorldStateDiff`` to a ``GameSession`` safely.

    - Validates field names before applying.
    - Numeric changes are *additive* (deltas).
    - Returns a summary dict of the changes actually applied.
    """
    applied: Dict[str, Any] = {}

    # --- Player changes -------------------------------------------------------
    pc = diff.player_changes
    if pc:
        # Stat deltas
        for stat, delta in pc.get("stat_changes", {}).items():
            if stat in _STAT_FIELDS and isinstance(delta, (int, float)):
                current = getattr(session.player.stats, stat, 0)
                setattr(session.player.stats, stat, current + int(delta))
                applied[f"player_{stat}"] = int(delta)

        # Reputation deltas
        for fld in _PLAYER_DELTA_FIELDS:
            delta = pc.get(fld, 0)
            if isinstance(delta, (int, float)) and delta:
                current = getattr(session.player, fld, 0)
                setattr(session.player, fld, current + int(delta))
                applied[fld] = int(delta)

        # Inventory
        for item in pc.get("inventory_add", []):
            if isinstance(item, str):
                session.player.inventory.append(item)
                applied.setdefault("inventory_gained", []).append(item)
        for item in pc.get("inventory_remove", []):
            if isinstance(item, str) and item in session.player.inventory:
                session.player.inventory.remove(item)
                applied.setdefault("inventory_lost", []).append(item)

        # Wealth delta shorthand
        wealth_delta = pc.get("wealth", 0)
        if isinstance(wealth_delta, (int, float)) and wealth_delta:
            session.player.stats.wealth += int(wealth_delta)
            applied["wealth_change"] = int(wealth_delta)

        # Location (replacement)
        new_loc = pc.get("location", "")
        if new_loc and isinstance(new_loc, str):
            session.player.location = new_loc
            applied["player_location"] = new_loc

        # Known facts (append)
        for fact in pc.get("new_known_facts", []):
            if isinstance(fact, str) and fact not in session.player.known_facts:
                session.player.known_facts.append(fact)

        # Faction reputation deltas
        for faction, delta in pc.get("reputation_factions", {}).items():
            if isinstance(delta, (int, float)):
                current = session.player.reputation_factions.get(faction, 0)
                session.player.reputation_factions[faction] = current + int(delta)
                applied[f"faction_{faction}"] = int(delta)

        # Alive flag
        if "is_alive" in pc:
            session.player.is_alive = bool(pc["is_alive"])
            if not session.player.is_alive:
                applied["player_died"] = True

    # --- NPC changes ----------------------------------------------------------
    for npc_name, changes in diff.npc_changes.items():
        npc = session.get_npc(npc_name)
        if not npc:
            continue
        rel_delta = changes.get("relationship", 0)
        if isinstance(rel_delta, (int, float)) and rel_delta:
            npc.relationships["player"] = npc.relationships.get("player", 0) + int(rel_delta)
            applied[f"{npc_name}_relationship"] = int(rel_delta)

        for fld in _NPC_REPLACE_FIELDS:
            val = changes.get(fld, "")
            if val and isinstance(val, str):
                setattr(npc, fld, val)
                applied[f"{npc_name}_{fld}"] = val

        for item in changes.get("inventory_add", []):
            if isinstance(item, str):
                npc.inventory.append(item)
        for item in changes.get("inventory_remove", []):
            if isinstance(item, str) and item in npc.inventory:
                npc.inventory.remove(item)

        # NPC-to-NPC relationship changes
        for target, delta in changes.get("relationship_changes", {}).items():
            if isinstance(delta, (int, float)):
                npc.relationships[target] = npc.relationships.get(target, 0) + int(delta)

        # NPC emotional state changes (deltas, clamped to [-1.0, 1.0])
        for emotion, delta in changes.get("emotional_state", {}).items():
            if isinstance(delta, (int, float)):
                current = npc.emotional_state.get(emotion, 0.0)
                npc.emotional_state[emotion] = max(-1.0, min(1.0, current + float(delta)))
                applied[f"{npc_name}_emotion_{emotion}"] = float(delta)

        # NPC memory additions
        for memory in changes.get("add_memories", []):
            if isinstance(memory, dict):
                npc.memories.append(memory)

        # NPC opinion changes (deltas)
        for opinion_key, delta in changes.get("opinions", {}).items():
            if isinstance(delta, (int, float)):
                current = npc.opinions.get(opinion_key, 0)
                npc.opinions[opinion_key] = current + int(delta)
                applied[f"{npc_name}_opinion_{opinion_key}"] = int(delta)

    # --- World changes --------------------------------------------------------
    wc = diff.world_changes
    if wc:
        time_advance = wc.get("time_advance_hours", 0)
        if isinstance(time_advance, (int, float)) and time_advance > 0:
            session.world.world_time.advance(hours=int(time_advance))
            applied["time_advance"] = int(time_advance)

    # --- Events ---------------------------------------------------------------
    for event in diff.events:
        session.history.append(event)

    return applied


def validate_diff(diff: WorldStateDiff, session: GameSession) -> Dict[str, Any]:
    """
    Validate a ``WorldStateDiff`` against a ``GameSession`` *without*
    mutating state.

    Returns a dict describing rejected fields, type mismatches, unknown
    NPCs, and any values that would be clamped.
    """
    result: Dict[str, Any] = {
        "valid": True,
        "rejected_fields": [],
        "unknown_npcs": [],
        "type_errors": [],
        "clamped_values": [],
    }

    pc = diff.player_changes
    if pc:
        for stat, delta in pc.get("stat_changes", {}).items():
            if stat not in _STAT_FIELDS:
                result["rejected_fields"].append(f"stat_changes.{stat}")
                result["valid"] = False
            elif not isinstance(delta, (int, float)):
                result["type_errors"].append(f"stat_changes.{stat}: expected number, got {type(delta).__name__}")
                result["valid"] = False

        for fld in _PLAYER_DELTA_FIELDS:
            delta = pc.get(fld, 0)
            if delta and not isinstance(delta, (int, float)):
                result["type_errors"].append(f"{fld}: expected number, got {type(delta).__name__}")
                result["valid"] = False

        wealth_delta = pc.get("wealth", 0)
        if wealth_delta and not isinstance(wealth_delta, (int, float)):
            result["type_errors"].append(f"wealth: expected number, got {type(wealth_delta).__name__}")
            result["valid"] = False

    for npc_name in diff.npc_changes:
        if not session.get_npc(npc_name):
            result["unknown_npcs"].append(npc_name)
            result["valid"] = False

    return result
