"""
Data models for the AI Role-Playing System.

Defines the persistent data structures for worlds, characters, players,
history logs, and game sessions.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class WorldRules:
    """Constraints and rules governing a game world."""
    technology_level: str = "pre-industrial"
    magic_system: str = "limited"
    allowed_items: List[str] = field(default_factory=lambda: ["swords", "bows", "magic artifacts"])
    forbidden_items: List[str] = field(default_factory=lambda: ["guns", "nuclear weapons"])
    custom_rules: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "technology_level": self.technology_level,
            "magic_system": self.magic_system,
            "allowed_items": list(self.allowed_items),
            "forbidden_items": list(self.forbidden_items),
            "custom_rules": list(self.custom_rules),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorldRules":
        return cls(
            technology_level=data.get("technology_level", "pre-industrial"),
            magic_system=data.get("magic_system", "limited"),
            allowed_items=data.get("allowed_items", ["swords", "bows", "magic artifacts"]),
            forbidden_items=data.get("forbidden_items", ["guns", "nuclear weapons"]),
            custom_rules=data.get("custom_rules", []),
        )


@dataclass
class Location:
    """A location in the game world."""
    name: str
    description: str
    connected_to: List[str] = field(default_factory=list)
    npcs_present: List[str] = field(default_factory=list)
    items_available: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "connected_to": list(self.connected_to),
            "npcs_present": list(self.npcs_present),
            "items_available": list(self.items_available),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Location":
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            connected_to=data.get("connected_to", []),
            npcs_present=data.get("npcs_present", []),
            items_available=data.get("items_available", []),
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
        )

    def get_location(self, name: str) -> Optional[Location]:
        """Find a location by name (case-insensitive)."""
        name_lower = name.lower()
        for loc in self.locations:
            if loc.name.lower() == name_lower:
                return loc
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
        )


@dataclass
class HistoryEvent:
    """A single event in the game history log."""
    event: str
    impact: Dict[str, Any] = field(default_factory=dict)
    turn: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event": self.event,
            "impact": dict(self.impact),
            "turn": self.turn,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HistoryEvent":
        return cls(
            event=data["event"],
            impact=data.get("impact", {}),
            turn=data.get("turn", 0),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )


@dataclass
class Quest:
    """A quest or mission in the game."""
    quest_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    giver: str = ""
    objectives: List[str] = field(default_factory=list)
    rewards: Dict[str, Any] = field(default_factory=dict)
    status: str = "active"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quest_id": self.quest_id,
            "title": self.title,
            "description": self.description,
            "giver": self.giver,
            "objectives": list(self.objectives),
            "rewards": dict(self.rewards),
            "status": self.status,
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

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "narration": self.narration,
            "events": [e.to_dict() for e in self.events],
            "state_changes": dict(self.state_changes),
            "choices": list(self.choices),
        }
        if self.error:
            result["error"] = self.error
        return result


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
