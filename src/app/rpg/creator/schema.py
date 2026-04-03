from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class LoreConstraint:
    name: str
    description: str
    authority: str = "creator_canon"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "LoreConstraint":
        return cls(**data)


@dataclass
class FactionSeed:
    faction_id: str
    name: str
    description: str
    goals: list[str] = field(default_factory=list)
    relationships: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "FactionSeed":
        return cls(**data)


@dataclass
class LocationSeed:
    location_id: str
    name: str
    description: str
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "LocationSeed":
        return cls(**data)


@dataclass
class NPCSeed:
    npc_id: str
    name: str
    role: str
    description: str
    goals: list[str] = field(default_factory=list)
    faction_id: str | None = None
    location_id: str | None = None
    must_survive: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "NPCSeed":
        return cls(**data)


@dataclass
class ThemeConstraint:
    name: str
    description: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ThemeConstraint":
        return cls(**data)


@dataclass
class PacingProfile:
    style: str = "balanced"
    danger_level: str = "medium"
    mystery_weight: float = 0.25
    combat_weight: float = 0.25
    politics_weight: float = 0.15
    social_weight: float = 0.35

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PacingProfile":
        return cls(**data)


@dataclass
class SafetyConstraint:
    forbidden_themes: list[str] = field(default_factory=list)
    soft_avoid_themes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SafetyConstraint":
        return cls(**data)


@dataclass
class ContentBalance:
    mystery: float = 0.2
    combat: float = 0.2
    politics: float = 0.2
    exploration: float = 0.2
    social: float = 0.2

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ContentBalance":
        return cls(**data)


@dataclass
class AdventureSetup:
    setup_id: str
    title: str
    genre: str
    setting: str
    premise: str
    hard_rules: list[str] = field(default_factory=list)
    soft_tone_rules: list[str] = field(default_factory=list)
    lore_constraints: list[LoreConstraint] = field(default_factory=list)
    factions: list[FactionSeed] = field(default_factory=list)
    locations: list[LocationSeed] = field(default_factory=list)
    npc_seeds: list[NPCSeed] = field(default_factory=list)
    themes: list[ThemeConstraint] = field(default_factory=list)
    pacing: PacingProfile | None = None
    safety: SafetyConstraint | None = None
    content_balance: ContentBalance | None = None
    forbidden_content: list[str] = field(default_factory=list)
    canon_notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    difficulty_style: str | None = None
    mood: str | None = None
    starting_location_id: str | None = None
    starting_npc_ids: list[str] = field(default_factory=list)

    def validate(self) -> None:
        if not self.setup_id:
            raise ValueError("AdventureSetup.setup_id is required")
        if not self.title:
            raise ValueError("AdventureSetup.title is required")
        if not self.genre:
            raise ValueError("AdventureSetup.genre is required")
        if not self.setting:
            raise ValueError("AdventureSetup.setting is required")
        if not self.premise:
            raise ValueError("AdventureSetup.premise is required")

        seen_locations = set()
        for location in self.locations:
            if location.location_id in seen_locations:
                raise ValueError(f"Duplicate location_id: {location.location_id}")
            seen_locations.add(location.location_id)

        seen_factions = set()
        for faction in self.factions:
            if faction.faction_id in seen_factions:
                raise ValueError(f"Duplicate faction_id: {faction.faction_id}")
            seen_factions.add(faction.faction_id)

        seen_npcs = set()
        for npc in self.npc_seeds:
            if npc.npc_id in seen_npcs:
                raise ValueError(f"Duplicate npc_id: {npc.npc_id}")
            seen_npcs.add(npc.npc_id)

    # ------------------------------------------------------------------
    # Phase 7.1 — defaults, normalisation, UI-friendly validation
    # ------------------------------------------------------------------

    def with_defaults(self) -> "AdventureSetup":
        """Return a copy with defaults applied through the canonical dict path.

        This keeps defaults application aligned with serialize/deserialize
        behavior and avoids partial deep-copy mutation drift.
        """
        from .defaults import apply_adventure_defaults

        data = self.to_dict()
        data = apply_adventure_defaults(data)
        return AdventureSetup.from_dict(data)

    def normalize(self) -> "AdventureSetup":
        """Return a normalized copy of this setup.

        Normalization rules:
        - trim strings
        - collapse empty strings to None where appropriate
        - lowercase enum-like fields
        - deduplicate ordered lists of ids
        - keep normalization deterministic
        """
        import copy

        def _norm_str(value: str | None, *, lower: bool = False, none_if_empty: bool = False) -> str | None:
            if value is None:
                return None
            value = " ".join(value.strip().split())
            if lower:
                value = value.lower()
            if none_if_empty and not value:
                return None
            return value

        def _dedupe_keep_order(values: list[str]) -> list[str]:
            out: list[str] = []
            seen = set()
            for value in values:
                if value not in seen:
                    out.append(value)
                    seen.add(value)
            return out

        result = copy.deepcopy(self)

        result.title = _norm_str(result.title) or ""
        result.genre = _norm_str(result.genre, lower=True) or ""
        result.setting = _norm_str(result.setting) or ""
        result.premise = _norm_str(result.premise) or ""

        result.mood = _norm_str(result.mood, lower=True, none_if_empty=True)
        result.difficulty_style = _norm_str(result.difficulty_style, lower=True, none_if_empty=True)
        result.starting_location_id = _norm_str(result.starting_location_id, none_if_empty=True)

        result.hard_rules = [_norm_str(x) for x in result.hard_rules if _norm_str(x)]
        result.soft_tone_rules = [_norm_str(x) for x in result.soft_tone_rules if _norm_str(x)]
        result.forbidden_content = [_norm_str(x) for x in result.forbidden_content if _norm_str(x)]
        result.canon_notes = [_norm_str(x) for x in result.canon_notes if _norm_str(x)]

        normalized_starting_npcs = []
        for npc_id in result.starting_npc_ids:
            norm = _norm_str(npc_id, none_if_empty=True)
            if norm:
                normalized_starting_npcs.append(norm)
        result.starting_npc_ids = _dedupe_keep_order(normalized_starting_npcs)

        return result

    def validate_for_ui(self) -> dict:
        """Run structured validation and return a UI-ready result dict."""
        from .validation import validate_adventure_setup_payload

        return validate_adventure_setup_payload(self.to_dict()).to_dict()

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "setup_id": self.setup_id,
            "title": self.title,
            "genre": self.genre,
            "setting": self.setting,
            "premise": self.premise,
            "hard_rules": list(self.hard_rules),
            "soft_tone_rules": list(self.soft_tone_rules),
            "lore_constraints": [x.to_dict() for x in self.lore_constraints],
            "factions": [x.to_dict() for x in self.factions],
            "locations": [x.to_dict() for x in self.locations],
            "npc_seeds": [x.to_dict() for x in self.npc_seeds],
            "themes": [x.to_dict() for x in self.themes],
            "pacing": self.pacing.to_dict() if self.pacing else None,
            "safety": self.safety.to_dict() if self.safety else None,
            "content_balance": self.content_balance.to_dict() if self.content_balance else None,
            "forbidden_content": list(self.forbidden_content),
            "canon_notes": list(self.canon_notes),
            "metadata": dict(self.metadata),
            "difficulty_style": self.difficulty_style,
            "mood": self.mood,
            "starting_location_id": self.starting_location_id,
            "starting_npc_ids": list(self.starting_npc_ids),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AdventureSetup":
        return cls(
            setup_id=data["setup_id"],
            title=data["title"],
            genre=data["genre"],
            setting=data["setting"],
            premise=data["premise"],
            hard_rules=list(data.get("hard_rules", [])),
            soft_tone_rules=list(data.get("soft_tone_rules", [])),
            lore_constraints=[
                LoreConstraint.from_dict(x) for x in data.get("lore_constraints", [])
            ],
            factions=[FactionSeed.from_dict(x) for x in data.get("factions", [])],
            locations=[LocationSeed.from_dict(x) for x in data.get("locations", [])],
            npc_seeds=[NPCSeed.from_dict(x) for x in data.get("npc_seeds", [])],
            themes=[ThemeConstraint.from_dict(x) for x in data.get("themes", [])],
            pacing=PacingProfile.from_dict(data["pacing"]) if data.get("pacing") else None,
            safety=SafetyConstraint.from_dict(data["safety"]) if data.get("safety") else None,
            content_balance=ContentBalance.from_dict(data["content_balance"])
            if data.get("content_balance")
            else None,
            forbidden_content=list(data.get("forbidden_content", [])),
            canon_notes=list(data.get("canon_notes", [])),
            metadata=dict(data.get("metadata", {})),
            difficulty_style=data.get("difficulty_style"),
            mood=data.get("mood"),
            starting_location_id=data.get("starting_location_id"),
            starting_npc_ids=list(data.get("starting_npc_ids", [])),
        )
