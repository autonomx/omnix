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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "alignment": self.alignment,
            "members": list(self.members),
            "goals": list(self.goals),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Faction":
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            alignment=data.get("alignment", "neutral"),
            members=data.get("members", []),
            goals=data.get("goals", []),
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
    charisma: int = 5
    intelligence: int = 5
    wealth: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "strength": self.strength,
            "charisma": self.charisma,
            "intelligence": self.intelligence,
            "wealth": self.wealth,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CharacterStats":
        return cls(
            strength=data.get("strength", 5),
            charisma=data.get("charisma", 5),
            intelligence=data.get("intelligence", 5),
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
        )


@dataclass
class PlayerState:
    """The player's character state."""
    name: str = "Player"
    stats: CharacterStats = field(default_factory=lambda: CharacterStats(
        strength=8, charisma=3, intelligence=6, wealth=50
    ))
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
            "stats": self.stats.to_dict(),
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
            stats=CharacterStats.from_dict(data.get("stats", {
                "strength": 8, "charisma": 3, "intelligence": 6, "wealth": 50
            })),
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
    """
    turn: int = 0
    raw_input: str = ""
    normalized_intent: Dict[str, Any] = field(default_factory=dict)
    dice_roll: Optional[Dict[str, Any]] = None
    event_output: Dict[str, Any] = field(default_factory=dict)
    canon_check: Dict[str, Any] = field(default_factory=dict)
    applied_diff: Dict[str, Any] = field(default_factory=dict)
    narration: str = ""

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "turn": self.turn,
            "raw_input": self.raw_input,
            "normalized_intent": dict(self.normalized_intent),
            "event_output": dict(self.event_output),
            "canon_check": dict(self.canon_check),
            "applied_diff": dict(self.applied_diff),
            "narration": self.narration,
        }
        if self.dice_roll is not None:
            result["dice_roll"] = dict(self.dice_roll)
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TurnLog":
        return cls(
            turn=data.get("turn", 0),
            raw_input=data.get("raw_input", ""),
            normalized_intent=data.get("normalized_intent", {}),
            dice_roll=data.get("dice_roll"),
            event_output=data.get("event_output", {}),
            canon_check=data.get("canon_check", {}),
            applied_diff=data.get("applied_diff", {}),
            narration=data.get("narration", ""),
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
_STAT_FIELDS = {"strength", "charisma", "intelligence", "wealth"}

# Whitelisted mutable fields on PlayerState that accept delta ints
_PLAYER_DELTA_FIELDS = {"reputation_local", "reputation_global"}

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
