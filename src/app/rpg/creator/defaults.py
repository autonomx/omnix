from __future__ import annotations

from .schema import ContentBalance, PacingProfile, SafetyConstraint


def default_pacing_profile() -> PacingProfile:
    """Return the default pacing profile for new adventures."""
    return PacingProfile(
        style="balanced",
        danger_level="medium",
        mystery_weight=0.25,
        combat_weight=0.25,
        politics_weight=0.15,
        social_weight=0.35,
    )


def default_safety_constraint() -> SafetyConstraint:
    """Return the default safety constraint for new adventures."""
    return SafetyConstraint(
        forbidden_themes=[],
        soft_avoid_themes=[],
    )


def default_content_balance() -> ContentBalance:
    """Return the default content balance for new adventures."""
    return ContentBalance(
        mystery=0.2,
        combat=0.2,
        politics=0.2,
        exploration=0.2,
        social=0.2,
    )


def apply_adventure_defaults(setup_data: dict) -> dict:
    """Apply default values to a raw adventure setup dict.

    Missing or ``None`` fields receive sensible defaults so that
    downstream consumers always see a complete payload.
    """
    result = dict(setup_data)

    if not result.get("hard_rules"):
        result["hard_rules"] = []
    if not result.get("soft_tone_rules"):
        result["soft_tone_rules"] = []
    if not result.get("lore_constraints"):
        result["lore_constraints"] = []
    if not result.get("factions"):
        result["factions"] = []
    if not result.get("locations"):
        result["locations"] = []
    if not result.get("npc_seeds"):
        result["npc_seeds"] = []
    if not result.get("themes"):
        result["themes"] = []
    if not result.get("forbidden_content"):
        result["forbidden_content"] = []
    if not result.get("canon_notes"):
        result["canon_notes"] = []
    if not result.get("metadata"):
        result["metadata"] = {}
    if not result.get("starting_npc_ids"):
        result["starting_npc_ids"] = []

    if result.get("pacing") is None:
        result["pacing"] = default_pacing_profile().to_dict()
    if result.get("safety") is None:
        result["safety"] = default_safety_constraint().to_dict()
    if result.get("content_balance") is None:
        result["content_balance"] = default_content_balance().to_dict()

    return result


# ---------------------------------------------------------------------------
# Setup templates
# ---------------------------------------------------------------------------

_TEMPLATES: dict[str, dict] = {
    "fantasy_adventure": {
        "genre": "fantasy",
        "setting": "A sprawling medieval kingdom on the edge of wild frontier lands",
        "premise": "An ancient evil stirs, and unlikely heroes must answer the call.",
        "hard_rules": [
            "Magic is real but has consequences",
            "The gods are distant and enigmatic",
        ],
        "soft_tone_rules": ["Heroic but grounded"],
        "pacing": PacingProfile(
            style="balanced",
            danger_level="medium",
            mystery_weight=0.2,
            combat_weight=0.3,
            politics_weight=0.1,
            social_weight=0.4,
        ).to_dict(),
        "content_balance": ContentBalance(
            mystery=0.15,
            combat=0.3,
            politics=0.1,
            exploration=0.25,
            social=0.2,
        ).to_dict(),
        "difficulty_style": "moderate",
        "mood": "heroic",
    },
    "political_intrigue": {
        "genre": "political intrigue",
        "setting": "A decadent renaissance court rife with hidden alliances",
        "premise": "Power is the only currency that matters, and everyone is buying.",
        "hard_rules": [
            "Violence has political consequences",
            "Reputation matters more than force",
        ],
        "soft_tone_rules": ["Tense and cerebral"],
        "pacing": PacingProfile(
            style="slow_burn",
            danger_level="low",
            mystery_weight=0.3,
            combat_weight=0.05,
            politics_weight=0.45,
            social_weight=0.2,
        ).to_dict(),
        "content_balance": ContentBalance(
            mystery=0.25,
            combat=0.05,
            politics=0.4,
            exploration=0.1,
            social=0.2,
        ).to_dict(),
        "difficulty_style": "hard",
        "mood": "tense",
    },
    "mystery_noir": {
        "genre": "mystery noir",
        "setting": "A rain-soaked 1940s city where everyone has something to hide",
        "premise": "A seemingly simple case spirals into a web of betrayal and danger.",
        "hard_rules": [
            "Clues must be discoverable through investigation",
            "NPCs lie unless motivated to tell the truth",
        ],
        "soft_tone_rules": ["Dark, atmospheric, morally ambiguous"],
        "pacing": PacingProfile(
            style="slow_burn",
            danger_level="medium",
            mystery_weight=0.5,
            combat_weight=0.1,
            politics_weight=0.1,
            social_weight=0.3,
        ).to_dict(),
        "content_balance": ContentBalance(
            mystery=0.45,
            combat=0.1,
            politics=0.1,
            exploration=0.15,
            social=0.2,
        ).to_dict(),
        "difficulty_style": "hard",
        "mood": "dark",
    },
    "grimdark_survival": {
        "genre": "grimdark",
        "setting": "A war-torn wasteland where resources are scarce and trust is rarer",
        "premise": "Survival is not guaranteed. Every choice has a cost.",
        "hard_rules": [
            "Death is permanent",
            "Resources must be tracked",
        ],
        "soft_tone_rules": ["Bleak and unforgiving"],
        "pacing": PacingProfile(
            style="relentless",
            danger_level="high",
            mystery_weight=0.1,
            combat_weight=0.4,
            politics_weight=0.1,
            social_weight=0.4,
        ).to_dict(),
        "content_balance": ContentBalance(
            mystery=0.05,
            combat=0.4,
            politics=0.1,
            exploration=0.3,
            social=0.15,
        ).to_dict(),
        "difficulty_style": "brutal",
        "mood": "grim",
    },
    "cyberpunk_heist": {
        "genre": "cyberpunk",
        "setting": "A neon-lit megacity controlled by megacorps and haunted by hackers",
        "premise": "One last job could set you free — or get you flatlined.",
        "hard_rules": [
            "Cyberware has side effects",
            "Corporate security is relentless",
        ],
        "soft_tone_rules": ["Stylish, fast-paced, morally grey"],
        "pacing": PacingProfile(
            style="fast",
            danger_level="high",
            mystery_weight=0.2,
            combat_weight=0.3,
            politics_weight=0.15,
            social_weight=0.35,
        ).to_dict(),
        "content_balance": ContentBalance(
            mystery=0.2,
            combat=0.25,
            politics=0.15,
            exploration=0.2,
            social=0.2,
        ).to_dict(),
        "difficulty_style": "hard",
        "mood": "edgy",
    },
}


def build_setup_template(template_name: str) -> dict:
    """Return a setup-data dict pre-populated from the named template.

    The returned dict is ready for ``apply_adventure_defaults`` and then
    ``AdventureSetup.from_dict`` after adding required ids/titles.

    Raises ``ValueError`` if the template name is unknown.
    """
    if template_name not in _TEMPLATES:
        raise ValueError(
            f"Unknown template '{template_name}'. "
            f"Available: {sorted(_TEMPLATES)}"
        )
    return dict(_TEMPLATES[template_name])


_TEMPLATE_META: dict[str, dict] = {
    "fantasy_adventure": {
        "label": "Fantasy Adventure",
        "description": "Classic high-fantasy with heroic quests, magical creatures, and ancient prophecies.",
        "recommended_for": "First-time players, heroic storytelling",
    },
    "political_intrigue": {
        "label": "Political Intrigue",
        "description": "Courtly machinations, hidden alliances, and power plays in a renaissance setting.",
        "recommended_for": "Players who enjoy dialogue, scheming, and consequences",
    },
    "mystery_noir": {
        "label": "Mystery Noir",
        "description": "A rain-soaked detective story where nothing is what it seems.",
        "recommended_for": "Players who enjoy investigation and moral ambiguity",
    },
    "grimdark_survival": {
        "label": "Grimdark Survival",
        "description": "A harsh, unforgiving world where every resource counts and death is permanent.",
        "recommended_for": "Experienced players seeking challenge and tension",
    },
    "cyberpunk_heist": {
        "label": "Cyberpunk Heist",
        "description": "Neon-lit megacities, corporate espionage, and one last job to pull off.",
        "recommended_for": "Players who enjoy fast-paced action and stylish storytelling",
    },
}


def list_setup_templates() -> list[dict]:
    """Return a list of available template descriptors for UI display."""
    result = []
    for name, tpl in _TEMPLATES.items():
        meta = _TEMPLATE_META.get(name, {})
        result.append({
            "name": name,
            "genre": tpl.get("genre", ""),
            "mood": tpl.get("mood", ""),
            "difficulty_style": tpl.get("difficulty_style", ""),
            "label": meta.get("label", name.replace("_", " ").title()),
            "description": meta.get("description", ""),
            "recommended_for": meta.get("recommended_for", ""),
            "setting": tpl.get("setting", ""),
            "premise": tpl.get("premise", ""),
        })
    return result
