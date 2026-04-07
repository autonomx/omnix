from __future__ import annotations

import uuid

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


def _make_id(prefix: str) -> str:
    """Generate a stable unique id with the given prefix."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _generate_default_locations(genre: str, setting: str) -> list[dict]:
    """Generate default locations based on genre/setting when none provided."""
    genre_lower = (genre or "").lower()

    if "fantasy" in genre_lower:
        return [
            {
                "location_id": "loc_tavern",
                "name": "The Rusty Flagon Tavern",
                "description": "A cozy tavern where travelers gather for news and rumors.",
                "tags": ["urban", "safe", "social"],
                "metadata": {},
            },
            {
                "location_id": "loc_market",
                "name": "Central Market",
                "description": "A bustling marketplace where goods and information are traded.",
                "tags": ["urban", "social", "commerce"],
                "metadata": {},
            },
            {
                "location_id": "loc_forest",
                "name": "The Whispering Woods",
                "description": "An ancient forest on the edge of civilization, full of mystery and danger.",
                "tags": ["wilderness", "danger", "mystery"],
                "metadata": {},
            },
        ]
    elif "cyberpunk" in genre_lower:
        return [
            {
                "location_id": "loc_bar",
                "name": "The Neon Dive",
                "description": "A dimly lit bar where hackers and mercenaries meet.",
                "tags": ["urban", "safe", "social"],
                "metadata": {},
            },
            {
                "location_id": "loc_corp_plaza",
                "name": "Arasaka Plaza",
                "description": "A towering corporate complex, heavily guarded and full of secrets.",
                "tags": ["urban", "danger", "corporate"],
                "metadata": {},
            },
            {
                "location_id": "loc_underground",
                "name": "The Undercity",
                "description": "Beneath the neon lights lies a sprawling underground network of tunnels and hideouts.",
                "tags": ["underground", "danger", "hidden"],
                "metadata": {},
            },
        ]
    elif "mystery" in genre_lower or "noir" in genre_lower:
        return [
            {
                "location_id": "loc_office",
                "name": "The Detective's Office",
                "description": "A cluttered office with case files piled high and a bottle in the desk.",
                "tags": ["urban", "safe", "investigation"],
                "metadata": {},
            },
            {
                "location_id": "loc_crime_scene",
                "name": "The Crime Scene",
                "description": "A cordoned-off area where something terrible happened.",
                "tags": ["urban", "danger", "investigation"],
                "metadata": {},
            },
            {
                "location_id": "loc_club",
                "name": "The Velvet Lounge",
                "description": "An upscale nightclub where the city's elite mingle and secrets are exchanged.",
                "tags": ["urban", "social", "mystery"],
                "metadata": {},
            },
        ]
    elif "political" in genre_lower or "intrigue" in genre_lower:
        return [
            {
                "location_id": "loc_court",
                "name": "The Royal Court",
                "description": "The heart of political power, where nobles scheme and alliances shift.",
                "tags": ["urban", "political", "danger"],
                "metadata": {},
            },
            {
                "location_id": "loc_embassy",
                "name": "Foreign Embassy",
                "description": "A diplomatic building where foreign powers conduct their business.",
                "tags": ["urban", "political", "social"],
                "metadata": {},
            },
            {
                "location_id": "loc_tavern",
                "name": "The Gossiping Noble",
                "description": "A refined tavern where politicians and informants meet over wine.",
                "tags": ["urban", "safe", "social"],
                "metadata": {},
            },
        ]
    elif "grimdark" in genre_lower or "survival" in genre_lower:
        return [
            {
                "location_id": "loc_ruins",
                "name": "The Ruined Village",
                "description": "A burned-out settlement, picked clean by scavengers but still holding secrets.",
                "tags": ["wilderness", "danger", "resources"],
                "metadata": {},
            },
            {
                "location_id": "loc_camp",
                "name": "Survivor's Camp",
                "description": "A makeshift camp where desperate people cling to life.",
                "tags": ["wilderness", "safe", "social"],
                "metadata": {},
            },
            {
                "location_id": "loc_fortress",
                "name": "The Warlord's Keep",
                "description": "A fortified stronghold ruled by a ruthless leader.",
                "tags": ["urban", "danger", "political"],
                "metadata": {},
            },
        ]
    else:
        # Generic defaults
        return [
            {
                "location_id": "loc_starting_area",
                "name": "Starting Area",
                "description": f"A place in {setting or 'the world'} where the adventure begins.",
                "tags": ["safe", "starting"],
                "metadata": {},
            },
            {
                "location_id": "loc_town",
                "name": "Nearby Town",
                "description": "A small settlement with basic amenities and local rumors.",
                "tags": ["urban", "safe", "social"],
                "metadata": {},
            },
            {
                "location_id": "loc_wilderness",
                "name": "The Wilds",
                "description": "Untamed lands beyond civilization, full of danger and opportunity.",
                "tags": ["wilderness", "danger", "exploration"],
                "metadata": {},
            },
        ]


def _generate_default_factions(genre: str, setting: str) -> list[dict]:
    """Generate default factions based on genre/setting when none provided."""
    genre_lower = (genre or "").lower()

    if "fantasy" in genre_lower:
        return [
            {
                "faction_id": "faction_kings_guard",
                "name": "The King's Guard",
                "description": "Loyal soldiers sworn to protect the realm and uphold the crown.",
                "goals": ["maintain_order", "protect_the_realm"],
                "relationships": {"faction_rebels": "hostile", "faction_mages": "neutral"},
                "metadata": {},
            },
            {
                "faction_id": "faction_rebels",
                "name": "The Free Folk",
                "description": "Rebels who believe the crown has grown corrupt and must be overthrown.",
                "goals": ["overthrow_crown", "establish_freedom"],
                "relationships": {"faction_kings_guard": "hostile", "faction_mages": "allied"},
                "metadata": {},
            },
            {
                "faction_id": "faction_mages",
                "name": "The Arcane Circle",
                "description": "A secretive order of mages who seek to preserve magical knowledge.",
                "goals": ["preserve_magic", "remain_independent"],
                "relationships": {"faction_kings_guard": "neutral", "faction_rebels": "allied"},
                "metadata": {},
            },
        ]
    elif "cyberpunk" in genre_lower:
        return [
            {
                "faction_id": "faction_corp",
                "name": "SynTech Corporation",
                "description": "A megacorp that controls half the city's infrastructure.",
                "goals": ["expand_market", "eliminate_competition"],
                "relationships": {"faction_hackers": "hostile", "faction_street": "neutral"},
                "metadata": {},
            },
            {
                "faction_id": "faction_hackers",
                "name": "Ghost Net Collective",
                "description": "Underground hackers fighting corporate surveillance and control.",
                "goals": ["expose_corp_secrets", "free_the_net"],
                "relationships": {"faction_corp": "hostile", "faction_street": "allied"},
                "metadata": {},
            },
            {
                "faction_id": "faction_street",
                "name": "The Street Syndicate",
                "description": "A loose alliance of gangs and mercenaries who control the underworld.",
                "goals": ["control_territory", "make_profit"],
                "relationships": {"faction_corp": "neutral", "faction_hackers": "allied"},
                "metadata": {},
            },
        ]
    elif "mystery" in genre_lower or "noir" in genre_lower:
        return [
            {
                "faction_id": "faction_police",
                "name": "The Police Department",
                "description": "An overworked and underfunded force trying to keep the city safe.",
                "goals": ["solve_crimes", "maintain_order"],
                "relationships": {"faction_mob": "hostile", "faction_press": "neutral"},
                "metadata": {},
            },
            {
                "faction_id": "faction_mob",
                "name": "The Moretti Family",
                "description": "A crime family that runs the city's underworld with an iron fist.",
                "goals": ["expand_operations", "avoid_heat"],
                "relationships": {"faction_police": "hostile", "faction_press": "hostile"},
                "metadata": {},
            },
            {
                "faction_id": "faction_press",
                "name": "The City Chronicle",
                "description": "A newspaper that digs deep into corruption and scandal.",
                "goals": ["expose_truth", "sell_papers"],
                "relationships": {"faction_police": "neutral", "faction_mob": "hostile"},
                "metadata": {},
            },
        ]
    elif "political" in genre_lower or "intrigue" in genre_lower:
        return [
            {
                "faction_id": "faction_nobles",
                "name": "The Noble Council",
                "description": "A council of nobles seeking to seize control of the throne.",
                "goals": ["seize_throne", "maintain_order"],
                "relationships": {"faction_rebels": "hostile", "faction_church": "neutral"},
                "metadata": {},
            },
            {
                "faction_id": "faction_rebels",
                "name": "The People's Vanguard",
                "description": "A rebel faction seeking to establish a republic.",
                "goals": ["establish_republic", "overthrow_nobles"],
                "relationships": {"faction_nobles": "hostile", "faction_church": "allied"},
                "metadata": {},
            },
            {
                "faction_id": "faction_church",
                "name": "The Holy Order",
                "description": "A powerful religious institution that influences both nobles and commoners.",
                "goals": ["spread_faith", "gain_influence"],
                "relationships": {"faction_nobles": "neutral", "faction_rebels": "allied"},
                "metadata": {},
            },
        ]
    elif "grimdark" in genre_lower or "survival" in genre_lower:
        return [
            {
                "faction_id": "faction_warlord",
                "name": "The Iron Fist",
                "description": "A brutal warlord's army that conquers and enslaves settlements.",
                "goals": ["conquer_lands", "gather_slaves"],
                "relationships": {"faction_survivors": "hostile", "faction_raiders": "neutral"},
                "metadata": {},
            },
            {
                "faction_id": "faction_survivors",
                "name": "The Last Hope",
                "description": "Desperate survivors banding together to protect each other.",
                "goals": ["survive", "protect_the_weak"],
                "relationships": {"faction_warlord": "hostile", "faction_raiders": "hostile"},
                "metadata": {},
            },
            {
                "faction_id": "faction_raiders",
                "name": "The Scavengers",
                "description": "Ruthless raiders who take what they need and leave nothing behind.",
                "goals": ["gather_resources", "avoid_conflict"],
                "relationships": {"faction_warlord": "neutral", "faction_survivors": "hostile"},
                "metadata": {},
            },
        ]
    else:
        # Generic defaults
        return [
            {
                "faction_id": "faction_authority",
                "name": "The Authority",
                "description": "Those who hold power and seek to maintain it.",
                "goals": ["maintain_control", "preserve_order"],
                "relationships": {"faction_rebels": "hostile"},
                "metadata": {},
            },
            {
                "faction_id": "faction_rebels",
                "name": "The Resistance",
                "description": "Those who oppose the current power structure.",
                "goals": ["change_system", "gain_freedom"],
                "relationships": {"faction_authority": "hostile"},
                "metadata": {},
            },
        ]


def _generate_default_npcs(genre: str, setting: str, locations: list[dict]) -> list[dict]:
    """Generate default NPCs based on genre/setting when none provided."""
    genre_lower = (genre or "").lower()
    first_location_id = locations[0]["location_id"] if locations else "loc_starting_area"

    if "fantasy" in genre_lower:
        return [
            {
                "npc_id": "npc_innkeeper",
                "name": "Bran the Innkeeper",
                "role": "informant",
                "description": "A friendly innkeeper who knows all the local rumors.",
                "goals": ["keep_tavern_running", "gather_rumors"],
                "faction_id": None,
                "location_id": first_location_id,
                "must_survive": False,
                "metadata": {},
            },
            {
                "npc_id": "npc_merchant",
                "name": "Elara the Merchant",
                "role": "trader",
                "description": "A shrewd merchant looking for rare goods and profitable deals.",
                "goals": ["make_profit", "find_rare_goods"],
                "faction_id": None,
                "location_id": "loc_market" if any(loc["location_id"] == "loc_market" for loc in locations) else first_location_id,
                "must_survive": False,
                "metadata": {},
            },
            {
                "npc_id": "npc_guard_captain",
                "name": "Captain Aldric",
                "role": "guard",
                "description": "A seasoned guard captain who has seen too many wars.",
                "goals": ["protect_the_town", "find_the_traitor"],
                "faction_id": "faction_kings_guard",
                "location_id": first_location_id,
                "must_survive": True,
                "metadata": {},
            },
        ]
    elif "cyberpunk" in genre_lower:
        return [
            {
                "npc_id": "npc_fixer",
                "name": "Jax the Fixer",
                "role": "contact",
                "description": "A well-connected fixer who knows everyone and everything.",
                "goals": ["make_deals", "stay_alive"],
                "faction_id": None,
                "location_id": first_location_id,
                "must_survive": False,
                "metadata": {},
            },
            {
                "npc_id": "npc_hacker",
                "name": "Zero",
                "role": "hacker",
                "description": "A ghost in the machine, capable of breaching any system.",
                "goals": ["expose_corp_secrets", "stay_off_grid"],
                "faction_id": "faction_hackers",
                "location_id": "loc_underground" if any(loc["location_id"] == "loc_underground" for loc in locations) else first_location_id,
                "must_survive": True,
                "metadata": {},
            },
            {
                "npc_id": "npc_merc",
                "name": "Razor",
                "role": "mercenary",
                "description": "A heavily augmented mercenary with a code of honor.",
                "goals": ["complete_contracts", "find_redemption"],
                "faction_id": "faction_street",
                "location_id": first_location_id,
                "must_survive": False,
                "metadata": {},
            },
        ]
    elif "mystery" in genre_lower or "noir" in genre_lower:
        return [
            {
                "npc_id": "npc_detective",
                "name": "Detective Malone",
                "role": "ally",
                "description": "A hard-boiled detective who doesn't trust anyone.",
                "goals": ["solve_the_case", "find_the_truth"],
                "faction_id": "faction_police",
                "location_id": first_location_id,
                "must_survive": True,
                "metadata": {},
            },
            {
                "npc_id": "npc_informant",
                "name": "Slick Sammy",
                "role": "informant",
                "description": "A street-smart informant who sells information to the highest bidder.",
                "goals": ["make_money", "stay_alive"],
                "faction_id": None,
                "location_id": "loc_club" if any(loc["location_id"] == "loc_club" for loc in locations) else first_location_id,
                "must_survive": False,
                "metadata": {},
            },
            {
                "npc_id": "npc_femme_fatale",
                "name": "Vivian Cross",
                "role": "client",
                "description": "A mysterious woman with secrets and a dangerous agenda.",
                "goals": ["find_her_sister", "escape_the_past"],
                "faction_id": None,
                "location_id": first_location_id,
                "must_survive": True,
                "metadata": {},
            },
        ]
    elif "political" in genre_lower or "intrigue" in genre_lower:
        return [
            {
                "npc_id": "npc_diplomat",
                "name": "Lord Harrington",
                "role": "diplomat",
                "description": "A cunning diplomat who plays all sides against each other.",
                "goals": ["secure_peace", "gain_power"],
                "faction_id": "faction_nobles",
                "location_id": "loc_court" if any(loc["location_id"] == "loc_court" for loc in locations) else first_location_id,
                "must_survive": True,
                "metadata": {},
            },
            {
                "npc_id": "npc_spymaster",
                "name": "The Shadow",
                "role": "spymaster",
                "description": "A mysterious figure who controls the flow of information.",
                "goals": ["gather_secrets", "manipulate_events"],
                "faction_id": None,
                "location_id": first_location_id,
                "must_survive": True,
                "metadata": {},
            },
            {
                "npc_id": "npc_rebel_leader",
                "name": "Mira the Bold",
                "role": "rebel",
                "description": "A charismatic leader of the people's movement.",
                "goals": ["overthrow_the_council", "establish_democracy"],
                "faction_id": "faction_rebels",
                "location_id": "loc_tavern" if any(loc["location_id"] == "loc_tavern" for loc in locations) else first_location_id,
                "must_survive": True,
                "metadata": {},
            },
        ]
    elif "grimdark" in genre_lower or "survival" in genre_lower:
        return [
            {
                "npc_id": "npc_scout",
                "name": "Kael the Scout",
                "role": "scout",
                "description": "A hardened scout who knows the wasteland like the back of his hand.",
                "goals": ["find_resources", "protect_the_camp"],
                "faction_id": "faction_survivors",
                "location_id": "loc_camp" if any(loc["location_id"] == "loc_camp" for loc in locations) else first_location_id,
                "must_survive": True,
                "metadata": {},
            },
            {
                "npc_id": "npc_medic",
                "name": "Doc",
                "role": "healer",
                "description": "A weary medic who has seen too much death but refuses to give up.",
                "goals": ["save_lives", "find_medicine"],
                "faction_id": "faction_survivors",
                "location_id": first_location_id,
                "must_survive": True,
                "metadata": {},
            },
            {
                "npc_id": "npc_raider",
                "name": "Gristle",
                "role": "antagonist",
                "description": "A brutal raider leader who enjoys causing pain.",
                "goals": ["raid_settlements", "gather_plunder"],
                "faction_id": "faction_raiders",
                "location_id": "loc_ruins" if any(loc["location_id"] == "loc_ruins" for loc in locations) else first_location_id,
                "must_survive": False,
                "metadata": {},
            },
        ]
    else:
        # Generic defaults
        return [
            {
                "npc_id": "npc_guide",
                "name": "The Guide",
                "role": "guide",
                "description": "A helpful local who can point you in the right direction.",
                "goals": ["help_travelers", "stay_safe"],
                "faction_id": None,
                "location_id": first_location_id,
                "must_survive": False,
                "metadata": {},
            },
            {
                "npc_id": "npc_trader",
                "name": "The Merchant",
                "role": "trader",
                "description": "A traveling merchant with goods to sell and rumors to share.",
                "goals": ["make_profit", "spread_news"],
                "faction_id": None,
                "location_id": first_location_id,
                "must_survive": False,
                "metadata": {},
            },
        ]


def apply_adventure_defaults(setup_data: dict) -> dict:
    """Apply default values to a raw adventure setup dict.

    Missing or ``None`` fields receive sensible defaults so that
    downstream consumers always see a complete payload.

    If factions, locations, or NPCs are not provided, they are
    auto-generated based on the genre and setting.
    """
    result = dict(setup_data)

    if not result.get("hard_rules"):
        result["hard_rules"] = []
    if not result.get("soft_tone_rules"):
        result["soft_tone_rules"] = []
    if not result.get("lore_constraints"):
        result["lore_constraints"] = []
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

    # Auto-generate locationss, factions, and NPCs if not provided
    genre = result.get("genre", "")
    setting = result.get("setting", "")

    if not result.get("locations"):
        result["locations"] = _generate_default_locations(genre, setting)

    if not result.get("factions"):
        result["factions"] = _generate_default_factions(genre, setting)

    if not result.get("npc_seeds"):
        result["npc_seeds"] = _generate_default_npcs(genre, setting, result["locations"])

    # Set starting location to first location if not specified
    if not result.get("starting_location_id") and result.get("locations"):
        result["starting_location_id"] = result["locations"][0]["location_id"]

    # Set starting NPCs to first few NPCs if not specified
    if not result.get("starting_npc_ids") and result.get("npc_seeds"):
        result["starting_npc_ids"] = [npc["npc_id"] for npc in result["npc_seeds"][:3]]

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
