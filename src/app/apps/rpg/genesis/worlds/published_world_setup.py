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


def _regions(canon: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {_text(row.get("id")): row for row in _rows(canon.get("regions")) if _text(row.get("id"))}


def published_locations(
    canon: Mapping[str, Any],
    topology: Mapping[str, Any],
    manifest_location_ids: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """The world's places with their display name, region and a description (the region's, when they have none)."""
    regions = _regions(canon)
    rows = _rows(_mapping(topology).get("locations"))
    known = {row.get("id") for row in rows}
    rows += [{"id": location_id} for location_id in manifest_location_ids
             if isinstance(location_id, str) and location_id not in known]
    places: list[dict[str, Any]] = []
    for row in rows:
        location_id = _text(row.get("id"))
        if not location_id:
            continue
        region = regions.get(_text(row.get("region_id")), {})
        name = _text(row.get("name")) or _label_from_id(location_id)
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
        for item in _rows(canon.get("items")):
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


def session_world_model(revision: Any, scenario: Any, *, present_at_start: Iterable[str] = ()) -> dict[str, Any]:
    """The per-session world the location registry and travel graph read for a published campaign."""

    canon = _mapping(getattr(revision, "canon", None))
    locations = _locations(revision)
    start = _text(getattr(scenario, "starting_location_id", ""))
    characters = _rows(canon.get("characters"))
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
        }
    routes: list[dict[str, Any]] = []
    for route in _rows(_mapping(getattr(revision, "topology", None)).get("routes")):
        origin, target = _text(route.get("from")), _text(route.get("to"))
        if origin in by_id and target in by_id:
            routes.append({"id": _text(route.get("id")), "from": origin, "to": target,
                           "travel_time": _text(route.get("travel_time"))})
    world_locations: dict[str, dict[str, Any]] = {}
    for location_id, row in by_id.items():
        name = _text(row.get("name"))
        present = [
            {"id": npc["id"], "name": npc["name"], "role": npc["role"]}
            for npc in npcs.values()
            if npc["location_id"] == location_id
        ]
        services: list[str] = []
        for npc in present:
            services.extend(kind for kind in _role_services(npc["role"]) if kind not in services)
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
            "aliases": sorted({name.casefold(), _label_from_id(location_id).casefold()}),
            "description": row["description"],
            "region_id": row["region_id"],
            "region_name": row["region_name"],
            "map_id": _text(row.get("map_id")),
            "deferred": bool(row.get("deferred")),
            "present_npcs": present,
            "services": services,
            "exits": exits,
        }
    providers: dict[str, dict[str, Any]] = {}
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
    return {
        "schema_version": WORLD_MODEL_SCHEMA,
        "source": "published_world",
        "providers": providers,
        "items": [
            {"id": _text(item.get("id")), "name": _text(item.get("name")), "type": _text(item.get("type")),
             "effect": _text(item.get("effect") or item.get("description"))}
            for item in _rows(canon.get("items"))
            if _text(item.get("id"))
        ],
        "offers": {provider_id: _service_offers(canon, provider) for provider_id, provider in providers.items()},
        "world_id": _text(getattr(revision, "world_id", "")),
        "world_revision": int(getattr(revision, "revision", 0) or 0),
        "start_location_id": start,
        "locations": world_locations,
        "routes": routes,
        "npcs": npcs,
    }


# Who will travel with the player when asked, from the world's own words: a "guide and first companion" at
# once, a "reluctant protector" once trusted.
_COMPANION_WORDS = (("companion", 0), ("guide", 0), ("protector", 20), ("ally", 20), ("mercenary", 20))


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
    return next((row for row in _rows(canon.get("items")) if _text(row.get("id")) == item_id), {})


def opening_kit(
    revision: Any,
    scenario: Any,
    *,
    equipment: Iterable[Mapping[str, Any]],
    inventory: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """The opening's starting items and purse, keeping the build's equipped gear so the hero can still fight."""

    canon = _mapping(getattr(revision, "canon", None))
    resources = _mapping(getattr(scenario, "starting_resources", None))
    equipped = {_text(item.get("name")).casefold() for item in equipment}
    items: list[dict[str, Any]] = [dict(item) for item in inventory if _text(item.get("name")).casefold() in equipped]
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
        "health": int(stats.get("health") or 0),
        "aether": int(stats.get("aether") or stats.get("mana") or 0),
        "knowledge": [_text(value) for value in resources.get("knowledge") or () if _text(value)],
    }


def opening_quests(revision: Any, scenario: Any) -> list[dict[str, Any]]:
    """The quest log at the opening: the world's intro quests, then the quests the opening's story seeds lead to."""

    canon = _mapping(getattr(revision, "canon", None))
    quests = {_text(row.get("id")): row for row in _rows(canon.get("quests")) if _text(row.get("id"))}
    seeds = {_text(row.get("id")): row for row in getattr(revision, "adventure_seeds", ()) or () if isinstance(row, Mapping)}
    start = _text(getattr(scenario, "starting_location_id", ""))
    ordered: list[tuple[dict[str, Any], str]] = [
        (quest, "") for quest in quests.values()
        if _text(quest.get("tier")) == "intro" and start in (quest.get("locations") or ())
    ]
    for seed_id in getattr(scenario, "opening_seed_ids", ()) or ():
        seed = _mapping(seeds.get(_text(seed_id)))
        quest = quests.get(_text(seed.get("quest_id")))
        if quest and all(quest is not existing for existing, _ in ordered):
            ordered.append((quest, _text(seed.get("hook"))))
    log: list[dict[str, Any]] = []
    for index, (quest, hook) in enumerate(ordered):
        quest_id = _text(quest.get("id"))
        places = [_text(place) for place in quest.get("locations") or () if _text(place)]
        log.append({
            "id": quest_id,
            "quest_id": quest_id,
            "title": _text(quest.get("title")) or _label_from_id(quest_id),
            "status": "active" if index == 0 else "available",
            "objective": _text(quest.get("objective")),
            "hook": hook,
            "rewards": [_text(reward) for reward in quest.get("rewards") or () if _text(reward)],
            "locations": places,
            # The player starts at the opening's place, so a quest that names it has already been there.
            "visited_locations": [start] if start in places else [],
            "source": "published_world",
        })
    return log


__all__ = [
    "WORLD_MODEL_SCHEMA",
    "companion_candidates",
    "creator_setup",
    "location_label",
    "opening_kit",
    "opening_quests",
    "published_locations",
    "session_world_model",
]
