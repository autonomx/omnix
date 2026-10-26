"""What a published world gives the turn engine: its places, people, routes, starting kit and opening quests.

A campaign launched from a published world bootstraps its player sheet through the new-game builder, whose own
world is a small built-in starter town. These functions read the world's immutable revision and the chosen
opening instead, so the engine plays in the world that was published:

- ``creator_setup`` is the creator setup the turn engine reads every turn (its locations, factions, NPC seeds and
  starting place); without one, the engine fills in its built-in defaults.
- ``session_world_model`` is the per-session world the location registry and travel graph consult: each place's
  name, region, exits, the people found there and the services they offer.
- ``opening_kit``, ``opening_quests`` and ``location_label`` turn the opening's starting resources, story seeds and
  place into the player sheet's inventory, purse, quest log and display names.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from .lore_sections import joined_routes, lore_location_rows, lore_routes, lore_rows
from .world_play_sections import ProviderEconomy, ShopOffer, authorship, parse_play_sections

WORLD_MODEL_SCHEMA = "rpg_session_world_model_v1"

# NPC roles that offer a service where they are found (the location registry's service kinds).
_ROLE_SERVICES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("innkeeper", ("lodging", "meal", "drink")),
    ("tavern", ("lodging", "meal", "drink")),
    ("merchant", ("shop_goods",)),
    ("trader", ("shop_goods",)),
    ("shopkeeper", ("shop_goods",)),
    ("mechanic", ("repair",)),
    ("smith", ("repair",)),
    ("registrar", ("paid_information",)),
    ("archivist", ("paid_information",)),
)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in value or () if isinstance(row, Mapping)]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _label_from_id(entity_id: str) -> str:
    tail = entity_id.rsplit(":", 1)[-1]
    return " ".join(part.capitalize() for part in re.split(r"[-_]+", tail) if part) or entity_id


_STARTER_REGION = re.compile(r"^region:.+:starter$")


def _part_name(location_id: str, names: Mapping[str, str]) -> str:
    """A place the opening derives from another ("<place>:interior", "<place>:outskirts:frontier"): named after the
    place it belongs to ("Black Rain Station Interior"), never only by its id's last word ("Interior")."""
    parent, _, part = location_id.rpartition(":")
    if parent in names and part:
        return f"{names[parent]} {_label_from_id(part)}"
    return _label_from_id(location_id)


def _regions(canon: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {_text(row.get("id")): row for row in lore_rows(canon, "regions") if _text(row.get("id"))}


def published_locations(
    canon: Mapping[str, Any],
    topology: Mapping[str, Any],
    manifest_location_ids: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """The world's places with their display name, region and a description (the region's, when they have none)."""
    regions = _regions(canon)
    rows = lore_location_rows(canon, topology)  # a lore world's places by bare id are filled in from their entities
    known = {row.get("id") for row in rows}
    rows += [{"id": location_id} for location_id in manifest_location_ids
             if isinstance(location_id, str) and location_id not in known]
    names = {_text(row.get("id")): _text(row.get("name")) for row in rows if _text(row.get("name"))}
    places: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda row: len(_text(row.get("id")))):  # a place before the parts named after it
        location_id = _text(row.get("id"))
        if not location_id or _STARTER_REGION.match(location_id):
            continue  # the starter bubble's region holds the opening's places: it is none itself
        region = regions.get(_text(row.get("region_id")), {})
        name = _text(row.get("name")) or _part_name(location_id, names)
        names[location_id] = name
        places.append({
            **row,
            "id": location_id,
            "name": name,
            "region_id": _text(row.get("region_id")),
            "region_name": _text(region.get("name")),
            "description": _location_description({**row, "name": name}, region),
        })
    return places


def _locations(revision: Any) -> list[dict[str, Any]]:
    manifest = _mapping(getattr(revision, "entity_manifest", None))
    return published_locations(
        _mapping(getattr(revision, "canon", None)),
        _mapping(getattr(revision, "topology", None)),
        manifest.get("locations") or (),
    )


def location_label(revision: Any, location_id: str) -> str:
    """A place's display name from the world (``Starfall Grove``), never its id."""
    for row in _locations(revision):
        if _text(row.get("id")) == location_id:
            return _text(row.get("name")) or _label_from_id(location_id)
    entity = _mapping(_mapping(_mapping(getattr(revision, "canon", None)).get("entities")).get(location_id))
    return _text(entity.get("name")) or _label_from_id(location_id)


def _location_description(row: Mapping[str, Any], region: Mapping[str, Any]) -> str:
    name = _text(row.get("name"))
    for key in ("description", "summary", "short_summary"):
        if _text(row.get(key)):
            return _text(row.get(key))
    region_name = _text(region.get("name"))
    region_summary = _text(region.get("summary"))
    if region_name and region_summary:
        return f"{name}, in {region_name}: {region_summary[0].lower()}{region_summary[1:]}."
    return f"{name}, in {region_name}." if region_name else name


def _stem(word: str) -> str:
    return word.casefold().strip(".,'’").removesuffix("s")


def _npc_homes(
    characters: list[dict[str, Any]],
    locations: list[dict[str, Any]],
    *,
    start_location_id: str,
    present_at_start: Iterable[str],
    capital_id: str = "",
) -> dict[str, str]:
    """Where each character is found, decided from the published text alone.

    In order: on the opening's map; the place their role or story names in full; the one place of the kind their
    role names (a "village guard captain" in the only village); and, for someone who serves the public (an
    innkeeper, a merchant), the starting region's capital. Anyone else (a wanderer, a distant villain) is placed
    nowhere until the story puts them somewhere.
    """
    homes = {npc_id: start_location_id for npc_id in present_at_start}
    names = [(row["id"], _text(row.get("name"))) for row in locations if _text(row.get("name"))]
    kinds: dict[str, list[str]] = {}
    for location_id, name in names:
        kinds.setdefault(_stem(name.split()[-1]), []).append(location_id)
    for character in characters:
        npc_id = _text(character.get("id"))
        if not npc_id or npc_id in homes:
            continue
        explicit = _text(character.get("location_id") or character.get("home_location_id"))
        role = _text(character.get("role"))
        story = f"{role} {_text(character.get('biography'))}".casefold()
        named = next((location_id for location_id, name in names if name.casefold() in story), "")
        kind = next(
            (kinds[_stem(word)][0] for word in role.split() if len(kinds.get(_stem(word), ())) == 1),
            "",
        )
        serves = capital_id if (_role_services(role) or "guard" in role.casefold()) else ""
        home = explicit or named or kind or serves
        if home:
            homes[npc_id] = home
    return homes


def _rows_or_texts(value: Any) -> list[Any]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [row for row in value if row] if isinstance(value, list) else []


def _role_services(role: str) -> list[str]:
    role = role.casefold()
    services: list[str] = []
    for keyword, kinds in _ROLE_SERVICES:
        if keyword in role:
            services.extend(kind for kind in kinds if kind not in services)
    return services


def _price(text: str, fallback: dict[str, int]) -> dict[str, int]:
    """A price from the world's own wording ("5 silver/night", "8 copper"), else ``fallback``."""
    price = {"gold": 0, "silver": 0, "copper": 0}
    for amount, coin in re.findall(r"(\d+)\s*(gold|silver|copper)", text.casefold()):
        price[coin] += int(amount)
    return price if any(price.values()) else dict(fallback)


def _typical_price(canon: Mapping[str, Any], keywords: tuple[str, ...], fallback: dict[str, int]) -> dict[str, int]:
    prices = _mapping(_mapping(canon.get("economy")).get("typical_prices"))
    for key, value in prices.items():
        if any(keyword in str(key).casefold() for keyword in keywords):
            return _price(str(value), fallback)
    return dict(fallback)


def _offer(provider: Mapping[str, Any], kind: str, key: str, label: str, description: str,
           price: dict[str, int], effects: dict[str, Any], stock: int | None = None) -> dict[str, Any]:
    offer = {
        "offer_id": f"{provider['provider_id']}:{key}",
        "service_kind": kind,
        "provider_id": provider["provider_id"],
        "provider_name": provider["provider_name"],
        "label": label,
        "description": description,
        "price": price,
        "availability_rules": {"requires_provider_present": True, "requires_location": provider["location_id"]},
        "availability": "available",
        "effects": effects,
    }
    if stock is not None:
        offer["stock"] = stock
    return offer


def _service_offers(canon: Mapping[str, Any], provider: Mapping[str, Any]) -> list[dict[str, Any]]:
    """What a provider sells, priced from the world's economy where it says (an inn room, a meal, a potion)."""
    offers: list[dict[str, Any]] = []
    kinds = set(provider["service_kinds"])
    if "lodging" in kinds:
        offers.append(_offer(provider, "lodging", "night", "A night's lodging", "A bed for the night.",
                             _typical_price(canon, ("inn", "room", "lodging"), {"silver": 5}),
                             {"lodging_reserved": True, "rest_quality": "basic", "duration": "one_night"}, stock=6))
    if "meal" in kinds:
        offers.append(_offer(provider, "meal", "meal", "A hot meal", "A hot meal of the house.",
                             _typical_price(canon, ("meal", "food"), {"silver": 1}), {"meal_consumed": True, "morale": 1}))
    if "drink" in kinds:
        offers.append(_offer(provider, "drink", "drink", "A drink", "A drink of the house.",
                             _typical_price(canon, ("drink", "ale"), {"copper": 8}), {"drink_consumed": True}))
    if "shop_goods" in kinds:
        for item in lore_rows(canon, "items"):
            item_id, kind = _text(item.get("id")), _text(item.get("type")).casefold()
            if not item_id or _text(item.get("rarity")).casefold() not in {"", "common"}:
                continue
            if kind not in {"food", "drink", "tool", "consumable", "potion", "supply"}:
                continue
            name = _text(item.get("name")) or _label_from_id(item_id)
            price = _typical_price(canon, ("meal", "food"), {"silver": 1}) if kind == "food" else {"silver": 1}
            offers.append(_offer(provider, "shop_goods", item_id.rsplit(":", 1)[-1], name,
                                 _text(item.get("effect") or item.get("description")) or name, price,
                                 {"items_added": [{"item_id": item_id, "name": name, "quantity": 1, "type": kind,
                                                   "description": _text(item.get("effect"))}]}, stock=5))
        potion = _mapping(_mapping(canon.get("economy")).get("typical_prices")).get("healing_potion")
        if potion:
            offers.append(_offer(provider, "shop_goods", "healing-potion", "Healing Potion", "Restores health.",
                                 _price(str(potion), {"silver": 3}),
                                 {"items_added": [{"item_id": "healing_potion", "name": "Healing Potion", "quantity": 1,
                                                   "type": "potion", "description": "restores health"}]}, stock=3))
    if "repair" in kinds:
        offers.append(_offer(provider, "repair", "repair", "Gear repair", "Repair work on worn equipment.",
                             _typical_price(canon, ("repair",), {"silver": 4}), {"repair_quality": "basic"}))
    if "paid_information" in kinds:
        offers.append(_offer(provider, "paid_information", "information", "Local news", "What is going on around here.",
                             _typical_price(canon, ("information", "rumor", "contract"), {"silver": 2}),
                             {"rumor_added": True}))
    return offers


_SERVICE_EFFECTS: dict[str, dict[str, Any]] = {
    "lodging": {"lodging_reserved": True, "rest_quality": "basic", "duration": "one_night"},
    "meal": {"meal_consumed": True, "morale": 1},
    "drink": {"drink_consumed": True},
    "repair": {"repair_quality": "basic"},
    "paid_information": {"rumor_added": True},
}


def _authored_offer(canon: Mapping[str, Any], provider: Mapping[str, Any], offer: ShopOffer) -> dict[str, Any]:
    effects: dict[str, Any] = dict(_SERVICE_EFFECTS.get(offer.service, {}))
    if offer.service == "shop_goods":
        item = next((row for row in lore_rows(canon, "items") if _text(row.get("id")) == offer.item_id), {})
        effects = {"items_added": [{"item_id": offer.item_id, "name": offer.name, "quantity": 1,
                                    "type": _text(item.get("type")).casefold() or "goods",
                                    "description": _text(item.get("effect") or item.get("description"))}]}
    priced = {"gold": offer.price.gold, "silver": offer.price.silver, "copper": offer.price.copper}
    built = _offer(provider, offer.service, offer.offer_key, offer.name, offer.description or offer.name,
                   priced, effects, stock=offer.stock)
    if offer.stock is not None:
        built["restock_per_day"] = offer.restock_per_day  # as the world wrote it: 0 never restocks (economy.md)
    return built


def _authored_providers(
    canon: Mapping[str, Any],
    authored: tuple[ProviderEconomy, ...],
    npcs: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """The world's own economy: its sellers where it puts them, with its prices, stock and buy-back terms."""
    providers: dict[str, dict[str, Any]] = {}
    offers: dict[str, list[dict[str, Any]]] = {}
    for entry in authored:
        npc = _mapping(npcs.get(entry.provider_id))
        location_id = entry.location_id or _text(npc.get("location_id"))
        if not npc or not location_id:
            continue
        name = _text(npc.get("name")) or _label_from_id(entry.provider_id)
        provider: dict[str, Any] = {
            "provider_id": entry.provider_id,
            "provider_name": name,
            "aliases": sorted({name.casefold(), name.split()[0].casefold(), _text(npc.get("role")).casefold()} - {""}),
            "location_id": location_id,
            "service_kinds": sorted({offer.service for offer in entry.sells}),
        }
        if entry.buys is not None:
            provider["buys"] = {"item_types": list(entry.buys.item_types), "price_fraction": entry.buys.price_fraction}
        providers[entry.provider_id] = provider
        offers[entry.provider_id] = [_authored_offer(canon, provider, offer) for offer in entry.sells]
    return providers, offers


def session_world_model(revision: Any, scenario: Any, *, present_at_start: Iterable[str] = ()) -> dict[str, Any]:
    """The per-session world the location registry and travel graph read for a published campaign."""

    canon = _mapping(getattr(revision, "canon", None))
    locations = _locations(revision)
    start = _text(getattr(scenario, "starting_location_id", ""))
    characters = lore_rows(canon, "characters")
    start_region = next((_text(row.get("region_id")) for row in locations if _text(row.get("id")) == start), "")
    capital_id = _text(_regions(canon).get(start_region, {}).get("capital"))
    homes = _npc_homes(characters, locations, start_location_id=start, present_at_start=present_at_start,
                       capital_id=capital_id)
    by_id = {_text(row.get("id")): row for row in locations}
    npcs: dict[str, dict[str, Any]] = {}
    for character in characters:
        npc_id = _text(character.get("id"))
        if not npc_id:
            continue
        npcs[npc_id] = {
            "id": npc_id,
            "name": _text(character.get("name")) or _label_from_id(npc_id),
            "role": _text(character.get("role")),
            "description": _text(character.get("biography") or character.get("description")),
            "location_id": homes.get(npc_id, ""),
            # Who they are, as dialogue plays them (RQ-2.2): their voice and what they want, and what they keep to
            # themselves, which stays on the server (edge/api/payloads/player_view.py).
            **{key: value for key, value in {
                "species": _text(character.get("species")),
                "personality": [_text(trait) for trait in _rows_or_texts(character.get("personality"))],
                "speech_style": _text(character.get("speech_style")),
                "goals": [_text(goal) for goal in _rows_or_texts(character.get("goals"))],
                "relationships": dict(_mapping(character.get("relationships"))),
                "secrets": [_text(secret) for secret in _rows_or_texts(character.get("secrets"))],
                # What else they are called ("the barkeep"), as the author wrote it: commands may name them so.
                "aliases": [_text(alias) for alias in _rows_or_texts(character.get("aliases")) if _text(alias)],
            }.items() if value},
        }
    routes: list[dict[str, Any]] = []
    for route in _rows(_mapping(getattr(revision, "topology", None)).get("routes")):
        origin, target = _text(route.get("from")), _text(route.get("to"))
        if origin in by_id and target in by_id:
            routes.append({"id": _text(route.get("id")), "from": origin, "to": target,
                           "travel_time": _text(route.get("travel_time"))})
    if not routes:  # a world that names no roads: roads by its regions (lore_sections.py)
        routes = lore_routes(locations, lore_rows(canon, "regions"))
    routes = joined_routes(routes, locations, lore_rows(canon, "regions"), start=start)  # none left unreached
    sections, _findings = parse_play_sections(canon)
    providers: dict[str, dict[str, Any]] = {}
    if sections.providers:
        # The world wrote its economy: play it as written, not as inferred from people's roles.
        providers, offers = _authored_providers(canon, sections.providers, npcs)
    else:
        for npc in npcs.values():
            kinds = _role_services(npc["role"])
            if kinds and npc["location_id"]:
                name = npc["name"]
                providers[npc["id"]] = {
                    "provider_id": npc["id"],
                    "provider_name": name,
                    "aliases": sorted({name.casefold(), name.split()[0].casefold(), npc["role"].casefold()}),
                    "location_id": npc["location_id"],
                    "service_kinds": kinds,
                }
        offers = {provider_id: _service_offers(canon, provider) for provider_id, provider in providers.items()}
    world_locations: dict[str, dict[str, Any]] = {}
    for location_id, row in by_id.items():
        name = _text(row.get("name"))
        present = [
            {"id": npc["id"], "name": npc["name"], "role": npc["role"]}
            for npc in npcs.values()
            if npc["location_id"] == location_id
        ]
        services: list[str] = []
        for provider in providers.values():
            if provider["location_id"] == location_id:
                services.extend(kind for kind in provider["service_kinds"] if kind not in services)
        exits: dict[str, str] = {}
        for route in routes:
            other = route["to"] if route["from"] == location_id else route["from"] if route["to"] == location_id else ""
            if other:
                other_name = _text(by_id[other].get("name")) or _label_from_id(other)
                exits[other_name.casefold()] = other
        world_locations[location_id] = {
            "location_id": location_id,
            "name": name,
            "short_name": name.casefold(),
            "aliases": sorted({name.casefold(), _label_from_id(location_id).casefold(),
                               *(_text(alias).casefold() for alias in row.get("aliases") or () if _text(alias))}),
            "description": row["description"],
            "region_id": row["region_id"],
            "region_name": row["region_name"],
            "map_id": _text(row.get("map_id")),
            "deferred": bool(row.get("deferred")),
            "present_npcs": present,
            "services": services,
            "exits": exits,
            # How the world says the place is met: its climate, its weather at an opening, indoors or out.
            **({"environment": dict(_mapping(row.get("environment")))} if _mapping(row.get("environment")) else {}),
        }
    return {
        "schema_version": WORLD_MODEL_SCHEMA,
        "source": "published_world",
        "providers": providers,
        "items": [
            {"id": _text(item.get("id")), "name": _text(item.get("name")), "type": _text(item.get("type")),
             "effect": _text(item.get("effect") or item.get("description"))}
            for item in lore_rows(canon, "items")  # as authored, else the lore's (a world written as lore)
            if _text(item.get("id"))
        ],
        # The world's groups (its factions, unions, networks), by what the world says of them, for a question about
        # one ("what is the union?": the intent gate found none named in a world written as lore).
        "groups": {_text(row.get("id")): {"name": _text(row.get("name")),
                                          "summary": _text(row.get("summary") or row.get("agenda")
                                                           or row.get("description"))}
                   for row in [*_rows(canon.get("factions")), *lore_rows(canon, "groups")]
                   if _text(row.get("id")) and _text(row.get("name"))},
        "offers": offers,
        "world_id": _text(getattr(revision, "world_id", "")),
        "world_revision": int(getattr(revision, "revision", 0) or 0),
        "start_location_id": start,
        "locations": world_locations,
        "routes": routes,
        "npcs": npcs,
        # Which parts of how the world plays its author wrote, and which launch inferred (RQ-2.0).
        "authorship": authorship(sections),
        "routines": [routine.model_dump(mode="json") for routine in sections.routines],
        "knowledge": [entry.model_dump(mode="json") for entry in sections.knowledge],
        "pressures": [pressure.model_dump(mode="json") for pressure in sections.pressures],
        # Every quest the world has, as the log would keep it: one not in the log yet can be offered in play.
        "quests": {_text(quest.get("id")): world_quest_row(quest, start) for quest in _rows(canon.get("quests"))
                   if _text(quest.get("id"))},
    }


# Who will travel with the player when asked, from the world's own words: a "guide and first companion" at
# once, a "reluctant protector" once trusted.
_COMPANION_WORDS = (("companion", 0), ("guide", 0), ("protector", 20), ("ally", 20), ("mercenary", 20))


# A creature's fighting numbers by the world's threat rating for it (the bestiary rates threat, not stats).
_THREAT_STATS: dict[str, dict[str, int]] = {
    "low": {"level": 1, "hp": 10, "defense": 10, "damage_min": 1, "damage_max": 4, "accuracy_bonus": 1, "xp_value": 25},
    "medium": {"level": 3, "hp": 18, "defense": 12, "damage_min": 2, "damage_max": 6, "accuracy_bonus": 2, "xp_value": 60},
    "high": {"level": 5, "hp": 28, "defense": 13, "damage_min": 3, "damage_max": 8, "accuracy_bonus": 3, "xp_value": 120},
    "extreme": {"level": 8, "hp": 45, "defense": 15, "damage_min": 4, "damage_max": 10, "accuracy_bonus": 4, "xp_value": 250},
}
_THREAT_ALIASES = {"minor": "low", "moderate": "medium", "severe": "high", "boss": "extreme", "legendary": "extreme",
                   "mythic": "extreme", "deadly": "extreme", "situational": "low", "variable": "medium",
                   "dangerous": "medium", "elite": "high"}


def threat_stats(threat: str) -> dict[str, int]:
    """A creature's fighting numbers for the world's threat rating of it (an unknown rating is a medium threat)."""
    threat = threat.casefold()
    return dict(_THREAT_STATS.get(_THREAT_ALIASES.get(threat, threat), _THREAT_STATS["medium"]))


# A creature's behaviour as its lore tells it, where the world names none (encounters.md): the first that fits.
_BEHAVIOUR_WORDS = (
    ("guards", ("guard", "guardian", "sentinel", "warden", "oath", "oaths", "post", "territorial", "keeper")),
    ("ambushes", ("ambush", "ambushes", "lurk", "lurks", "stalk", "stalks", "stolen face", "disguise", "camouflage")),
    ("calls_allies", ("pack", "swarm", "horde", "splits", "summons", "calls", "hive", "brood")),
    ("flees_when_hurt", ("wolf", "hound", "jackal", "fox", "docile", "skittish", "timid", "cowardly", "scavenger")),
)


# Creatures that can be talked to, where the world does not say (encounters.md): people of a kind, and the knowing.
_SPEAKING_WORDS = ("bandit", "brigand", "thief", "raider", "smuggler", "pirate", "cultist", "knight", "soldier",
                   "guard", "warrior", "mage", "witch", "goblin", "orc", "ogre", "troll", "giant", "archon", "oath",
                   "oaths", "speaks", "talks", "bargains")


def derived_speaks(row: Mapping[str, Any]) -> bool:
    """Whether a creature can be talked to, from its name and traits."""
    lore = " ".join([_text(row.get("name")), *map(_text, row.get("traits") or ())]).casefold()
    words = f" {' '.join(re.findall(r'[a-z]+', lore))} "
    return any(f" {cue} " in words for cue in _SPEAKING_WORDS)


def derived_behaviour(row: Mapping[str, Any]) -> str:
    """How a creature fights, from its name and traits; ``fights`` when they say nothing of it."""
    lore = " ".join([_text(row.get("name")), *map(_text, row.get("traits") or ())]).casefold()
    words = f" {' '.join(re.findall(r'[a-z]+', lore))} "
    return next((behaviour for behaviour, cues in _BEHAVIOUR_WORDS if any(f" {cue} " in words for cue in cues)), "fights")


def bestiary_mechanics(revision: Any) -> dict[str, Any]:
    """The world's creatures as combat definitions: numbers by threat, its weakness stuns it for a turn, and it
    behaves as the world says (else as its lore tells, ``derived_behaviour``)."""

    canon = _mapping(getattr(revision, "canon", None))
    played = {entry.id: entry for entry in parse_play_sections(canon)[0].bestiary}
    creatures: dict[str, Any] = {}
    for row in lore_rows(canon, "bestiary"):
        creature_id = _text(row.get("id"))
        if not creature_id:
            continue
        threat = _text(row.get("threat")).casefold()
        stats = threat_stats(threat)
        play = played.get(creature_id)
        if play is not None and play.stats is not None:
            stats = play.stats.model_dump()
        weakness = _text(row.get("weakness"))
        aliases = [part.strip() for part in re.split(r",|\band\b|\bor\b", weakness) if part.strip()]
        creatures[creature_id] = {
            "definition_id": creature_id,
            "definition_revision": int(getattr(revision, "revision", 1) or 1),
            "name": _text(row.get("name")) or _label_from_id(creature_id),
            **stats,
            "armor": 0,
            "initiative_bonus": 1 if "fast" in " ".join(row.get("traits") or ()).casefold() else 0,
            "morale_threshold": 35,
            "tags": [_text(trait) for trait in row.get("traits") or () if _text(trait)],
            "budget_cost": stats["xp_value"],
            "vulnerabilities": (
                [{"trigger_tag": weakness, "aliases": aliases, "condition": "stunned", "duration_turns": 1, "magnitude": 1}]
                if weakness else []
            ),
            "behaviour": play.behaviour if play is not None and row.get("behaviour") else derived_behaviour(row),
            "threat": threat,
            "speaks": row["speaks"] is True if "speaks" in row else derived_speaks(row),
            "loot": [drop.model_dump() for drop in play.loot] if play is not None else [],
            "source": "published_world_bestiary",
        }
    return {"creatures": creatures} if creatures else {}


def companion_candidates(world_model: Mapping[str, Any]) -> dict[str, int]:
    """Characters who can join the party, with the trust each needs first."""
    candidates: dict[str, int] = {}
    for npc_id, npc in _mapping(world_model.get("npcs")).items():
        role = f"{_text(_mapping(npc).get('role'))}".casefold()
        trust = min((needed for word, needed in _COMPANION_WORDS if word in role), default=None)
        if trust is not None:
            candidates[str(npc_id)] = trust
    return candidates


def creator_setup(revision: Any, scenario: Any, world_model: Mapping[str, Any], world: Mapping[str, Any]) -> dict[str, Any]:
    """The creator setup the turn engine reads each turn, so it never fills in its built-in starter town."""

    canon = _mapping(getattr(revision, "canon", None))
    locations = _mapping(world_model.get("locations"))
    npcs = _mapping(world_model.get("npcs"))
    start = _text(world_model.get("start_location_id"))
    return {
        "title": _text(getattr(revision, "title", "")) or _text(world.get("title")),
        "genre": _text(world.get("genre")) or "fantasy",
        "setting": _text(canon.get("summary")) or _text(world.get("description")),
        "premise": _text(_mapping(canon.get("isekai_premise")).get("summary")) or _text(world.get("description")),
        "themes": [_text(theme) for theme in canon.get("themes") or () if _text(theme)],
        "locations": [
            {
                "location_id": location_id,
                "name": location["name"],
                "description": location["description"],
                "tags": ["published_world"] + (["deferred"] if location.get("deferred") else []),
                "metadata": {"region_id": location["region_id"], "region_name": location["region_name"],
                             "connected_location_ids": sorted(set(location["exits"].values()))},
            }
            for location_id, location in locations.items()
        ],
        "factions": [
            {
                "faction_id": _text(row.get("id")),
                "name": _text(row.get("name")),
                "description": _text(row.get("agenda") or row.get("description")),
                "goals": [_text(row.get("agenda"))] if _text(row.get("agenda")) else [],
                "relationships": {},
                "metadata": {},
            }
            for row in _rows(canon.get("factions"))
            if _text(row.get("id"))
        ],
        "npc_seeds": [
            {
                "npc_id": npc["id"],
                "name": npc["name"],
                "role": npc["role"],
                "description": npc["description"],
                "goals": [],
                "faction_id": None,
                "location_id": npc["location_id"] or None,
                "must_survive": False,
                "metadata": {"source": "published_world"},
            }
            for npc in npcs.values()
        ],
        "starting_location_id": start,
        "starting_npc_ids": [
            _text(npc_id) for npc_id in getattr(scenario, "initial_npc_ids", ()) or ()
            if _mapping(npcs.get(_text(npc_id))).get("location_id") == start
        ],
    }


def _canon_item(canon: Mapping[str, Any], item_id: str) -> dict[str, Any]:
    return next((row for row in lore_rows(canon, "items") if _text(row.get("id")) == item_id), {})


def opening_kit(
    revision: Any,
    scenario: Any,
    *,
    equipment: Iterable[Mapping[str, Any]],
    inventory: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """The opening's starting items and purse, keeping the build's equipped gear so the hero can still fight; an
    opening that equips the hero itself (``equipment``: slot and item) carries that gear instead."""

    canon = _mapping(getattr(revision, "canon", None))
    resources = _mapping(getattr(scenario, "starting_resources", None))
    authored = [_mapping(row) for row in resources.get("equipment") or () if _text(_mapping(row).get("id"))]
    equipped = {_text(item.get("name")).casefold() for item in equipment}
    items: list[dict[str, Any]] = [] if authored else [
        dict(item) for item in inventory if _text(item.get("name")).casefold() in equipped]
    worn: list[dict[str, str]] = []
    for row in authored:
        canon_item = _canon_item(canon, _text(row.get("id")))
        name = _text(canon_item.get("name")) or _label_from_id(_text(row.get("id")))
        worn.append({"slot": _text(row.get("slot")) or "Gear", "name": name})
        items.append({"id": _text(row.get("id")), "name": name, "quantity": 1,
                      "type": _text(canon_item.get("type")) or "misc",
                      "description": _text(canon_item.get("effect") or canon_item.get("description")),
                      "rarity": _text(canon_item.get("rarity"))})
    for raw in resources.get("inventory") or ():
        item_id = _text(raw if isinstance(raw, str) else _mapping(raw).get("id"))
        if not item_id:
            continue
        quantity = int(_mapping(raw).get("quantity") or 1) if isinstance(raw, Mapping) else 1
        existing = next((row for row in items if row.get("id") == item_id), None)
        if existing is not None:
            existing["quantity"] = int(existing.get("quantity") or 1) + quantity
            continue
        canon_item = _canon_item(canon, item_id)
        items.append({
            "id": item_id,
            "name": _text(canon_item.get("name")) or _label_from_id(item_id),
            "quantity": quantity,
            "type": _text(canon_item.get("type")) or "misc",
            "description": _text(canon_item.get("effect") or canon_item.get("description")),
            "rarity": _text(canon_item.get("rarity")),
        })
    currency = {"gold": 0, "silver": 0, "copper": 0}
    for coin, amount in _mapping(resources.get("currency")).items():
        if coin in currency:
            currency[coin] = max(0, int(amount or 0))
    stats = _mapping(resources.get("stats"))
    return {
        "inventory": items,
        "currency": currency,
        "equipment": worn,
        "health": int(stats.get("health") or 0),
        "aether": int(stats.get("aether") or stats.get("mana") or 0),
        "knowledge": [_text(value) for value in resources.get("knowledge") or () if _text(value)],
    }


def opening_quests(revision: Any, scenario: Any, *, lead_seed_id: str = "") -> list[dict[str, Any]]:
    """The quest log at the opening: the world's intro quests, then the quests the opening's story seeds lead to.

    ``lead_seed_id`` names the seed the player chose to start with (a classic new game's opening hook): its quest
    leads the log, and is the active one.
    """

    canon = _mapping(getattr(revision, "canon", None))
    quests = {_text(row.get("id")): row for row in _rows(canon.get("quests")) if _text(row.get("id"))}
    seeds = {_text(row.get("id")): row for row in getattr(revision, "adventure_seeds", ()) or () if isinstance(row, Mapping)}
    start = _text(getattr(scenario, "starting_location_id", ""))
    ordered: list[tuple[dict[str, Any], str]] = [
        (quest, "") for quest in quests.values()
        if _text(quest.get("tier")) == "intro" and start in (quest.get("locations") or ())
    ]
    seed_ids = [_text(seed_id) for seed_id in getattr(scenario, "opening_seed_ids", ()) or ()]
    if lead_seed_id in seeds:
        seed_ids = [lead_seed_id, *(seed_id for seed_id in seed_ids if seed_id != lead_seed_id)]
        lead = quests.get(_text(_mapping(seeds[lead_seed_id]).get("quest_id")))
        if lead is not None:
            ordered = [(quest, hook) for quest, hook in ordered if quest is not lead]
            ordered.insert(0, (lead, _text(_mapping(seeds[lead_seed_id]).get("hook"))))
    for seed_id in seed_ids:
        seed = _mapping(seeds.get(seed_id))
        quest = quests.get(_text(seed.get("quest_id")))
        if quest and all(quest is not existing for existing, _ in ordered):
            ordered.append((quest, _text(seed.get("hook"))))
    return [{**world_quest_row(quest, start, hook=hook), "status": "active" if index == 0 else "available"}
            for index, (quest, hook) in enumerate(ordered)]


def world_quest_row(quest: Mapping[str, Any], start: str, *, hook: str = "") -> dict[str, Any]:
    """A world's quest as a campaign's log keeps it (without its status): the opening's log, and a quest offered in
    play that the log does not have yet."""
    quest_id = _text(quest.get("id"))
    places = [_text(place) for place in quest.get("locations") or () if _text(place)]
    return {
        "id": quest_id,
        "quest_id": quest_id,
        "title": _to_the_hero(_text(quest.get("title"))) or _label_from_id(quest_id),
        "objective": _to_the_hero(_text(quest.get("objective"))),
        "hook": _to_the_hero(hook),
        "rewards": [_text(reward) for reward in quest.get("rewards") or () if _text(reward)],
        "locations": places,
        # The player starts at the opening's place, so a quest that names it has already been there.
        "visited_locations": [start] if start in places else [],
        # A quest of steps, its deadline and who gave it, and its kind (an intro, a finale), as the world wrote them.
        **{key: quest[key] for key in ("steps", "deadline_hours", "giver_id", "tier") if quest.get(key)},
        **({"objective": _to_the_hero(_text(_mapping(quest["steps"][0]).get("summary")) or _text(quest.get("objective")))}
           if quest.get("steps") else {}),
        "source": "published_world",
    }


def _to_the_hero(text: str) -> str:
    """A quest's words as the hero reads them: an author's "the protagonist" is the hero ("Repair the protagonist's
    phone" is "Repair your phone"). Only where the words read as written (a possessive, an object); a sentence that
    opens with it keeps it, its verb being the author's."""
    text = re.sub(r"\b[Tt]he protagonist's\b", lambda match: "Your" if match.group(0)[0] == "T" else "your", text)
    return re.sub(r"(?<=[a-z,;] )the protagonist\b", "you", text)


__all__ = [
    "WORLD_MODEL_SCHEMA",
    "bestiary_mechanics",
    "companion_candidates",
    "creator_setup",
    "location_label",
    "opening_kit",
    "opening_quests",
    "published_locations",
    "session_world_model",
    "world_quest_row",
]
