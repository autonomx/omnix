"""Trade (RQ-2.3; docs/rpg/design/economy.md): buying from and selling to the people who trade where the hero stands.

The world's economy section says who sells what, at what price and stock, and what each buys back (RQ-2.0). The
rule reads it with the campaign's stock and the hero's purse and pack, and says what happens as changes: coin paid
or earned, goods taken or handed over, a need eased, a room reserved, the stock left, and the trade remembered.
A world without an economy section (the starter town until RQ-2.8) has no trade here; ``trade`` returns ``None``.

What is bought or sold, from or to whom, and how many is the reading's (evolution roadmap EV-9): an offer or a thing,
by id, and a seller or buyer, by id. No word of the line is read here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state.changes import (
    ItemAdded,
    ItemRemoved,
    NeedsChanged,
    PurseChanged,
    ServiceReserved,
    StateChange,
    StockTaken,
    TradeRemembered,
)
from app.apps.rpg.rules import routines
from app.apps.rpg.rules.consequences import closed_providers, price_factor, waived
from app.apps.rpg.rules.routines import MINUTES_PER_DAY
from app.apps.rpg.rules.wording import in_sentence
from app.apps.rpg.foundation.state import access as _sections

COPPER = {"gold": 100, "silver": 10, "copper": 1}
# What moves a price (economy.md): an offer nearly gone, a region whose trade the roads choke, a seller who trusts the
# hero, and a haggle won with them today.
SCARCE_SHARE, SCARCE_MARKUP = 0.2, 1.25
CHOKED_TRADE, CHOKED_MARKUP = 40.0, 1.20
TRUSTED, TRUSTED_DISCOUNT = 50, 0.90
HAGGLE_DISCOUNT = 0.90
UNTRADED_GOODS_COPPER = 5  # what a shop pays for goods it does not sell itself: a token
RELIEF = {"meal": ("hunger", -35), "drink": ("thirst", -30)}
MOST_AT_ONCE = 10  # goods bought in one go (the playtest: "two Healing Potions" bought one)


def copper(price: Mapping[str, Any]) -> int:
    return sum(int(price.get(coin) or 0) * value for coin, value in COPPER.items())


def coins(total: int) -> str:
    """A sum as the play screen says it: "1 gold, 2 silver", "8 copper"."""
    parts = [(total // 100, "gold"), (total // 10 % 10, "silver"), (total % 10, "copper")]
    return ", ".join(f"{amount} {coin}" for amount, coin in parts if amount) or "nothing"


@dataclass(frozen=True)
class TradeOutcome:
    """What the player's trade did: its changes, how to say it, and whether it was refused."""

    changes: list[StateChange] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    refused: bool = False
    kind: str = ""  # bought, sold, listed, refused


def _providers_here(simulation: Mapping[str, Any]) -> list[dict[str, Any]]:
    world = _d(_sections.world_model_of(simulation))
    location = _s(_d(_sections.player_state_of(simulation)).get("location_id"))
    present = set(_l(_d(_sections.present_npc_state_of(simulation)).get("present_npc_ids")))
    closed = closed_providers(simulation)  # a seller the world's facts closed (rules/consequences.py)
    return [_d(provider) for provider_id, provider in _d(world.get("providers")).items()
            if _s(_d(provider).get("location_id")) == location and (not present or provider_id in present)
            and provider_id not in closed]


def sellers_here(simulation: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The people here who sell something."""
    return [provider for provider in _providers_here(simulation) if _offers(simulation, provider)]


def _offers(simulation: Mapping[str, Any], provider: Mapping[str, Any]) -> list[dict[str, Any]]:
    offers = _d(_d(_sections.world_model_of(simulation)).get("offers")).get(_s(provider.get("provider_id")))
    return [_d(offer) for offer in _l(offers)]


def _today(simulation: Mapping[str, Any]) -> int:
    return routines.clock(simulation) // MINUTES_PER_DAY


def stock_left(simulation: Mapping[str, Any], offer: Mapping[str, Any]) -> int | None:
    """How many of ``offer`` its seller has left; ``None`` when the world does not count it.

    What a sale left grows back by the offer's ``restock_per_day`` for each day since, up to its stock; an offer the
    world gives no rate is stocked afresh each day (an inn's rooms, the day's meals: economy.md)."""
    if offer.get("stock") is None:
        return None  # unlimited
    full = int(offer.get("stock") or 0)
    kept = _d(_d(simulation.get("trade")).get("stock")).get(_s(offer.get("offer_id")))
    if kept is None:
        return full
    sale = _d(kept) if isinstance(kept, Mapping) else {"remaining": kept, "day": 0}  # an older campaign's count
    rate = full if offer.get("restock_per_day") is None else int(offer.get("restock_per_day") or 0)
    days = max(0, _today(simulation) - int(sale.get("day") or 0))
    return min(full, int(sale.get("remaining") or 0) + rate * days)


def _trade_access(simulation: Mapping[str, Any], location_id: str) -> float | None:
    """The causal runtime's trade access of the region a place is in; ``None`` where it keeps none."""
    region = _s(_d(_d(_d(_sections.world_model_of(simulation)).get("locations")).get(location_id)).get("region_id"))
    cell = _d(_d(_d(_d(simulation.get("causal_world_runtime")).get("state")).get("cells")).get(region))
    value = _d(cell.get("values")).get("trade_access")
    return float(value) if isinstance(value, (int, float)) else None


def haggled(simulation: Mapping[str, Any], provider_id: str) -> bool:
    """Whether a haggle with this seller was won today."""
    today = _today(simulation)
    return any(_s(_d(row).get("kind")) == "haggle" and _s(_d(row).get("target_id")) == provider_id
               and _s(_d(row).get("band")) != "failure" and int(_d(row).get("minute") or -1) // MINUTES_PER_DAY == today
               for row in _l(_d(simulation.get("checks")).get("history")))


def price_of(simulation: Mapping[str, Any], provider: Mapping[str, Any], offer: Mapping[str, Any]) -> tuple[int, list[str]]:
    """What ``offer`` costs now, in copper, and why it differs from its price (economy.md), and the world's facts
    (``rules/consequences.py``: a seller's or region's prices moved, an offer given free once)."""
    provider_id = _s(provider.get("provider_id"))
    free = waived(simulation, provider_id, _s(offer.get("offer_key")) or _s(offer.get("offer_id")).rsplit(":", 1)[-1])
    if free:
        return 0, [free]
    price = copper(_d(offer.get("price")))
    factor, why = price_factor(simulation, provider_id, _s(provider.get("location_id")))
    left, full = stock_left(simulation, offer), int(offer.get("stock") or 0)
    if left is not None and full and left <= full * SCARCE_SHARE:
        factor, why = factor * SCARCE_MARKUP, [*why, "it is nearly gone"]
    access = _trade_access(simulation, _s(provider.get("location_id")))
    if access is not None and access < CHOKED_TRADE:
        factor, why = factor * CHOKED_MARKUP, [*why, "the roads choke trade"]
    if int(_d(_d(simulation.get("relationship_state")).get(provider_id)).get("trust") or 0) >= TRUSTED:
        factor, why = factor * TRUSTED_DISCOUNT, [*why, "you are trusted"]
    if haggled(simulation, provider_id):
        factor, why = factor * HAGGLE_DISCOUNT, [*why, "you haggled"]
    return (price if factor == 1.0 else max(1, round(price * factor))), why


def _purse(simulation: Mapping[str, Any]) -> int:
    player = _d(_sections.player_state_of(simulation))
    return copper(_d(_d(_sections.inventory_state_of(player)).get("currency") or player.get("currency")))


def _listing(simulation: Mapping[str, Any], provider: Mapping[str, Any], offers: list[dict[str, Any]], *,
             unnamed: bool) -> str:
    listed = ", ".join(f"{_s(offer.get('label'))} ({coins(price_of(simulation, provider, offer)[0])})" for offer in offers)
    return f"{_s(provider.get('provider_name'))} offers: {listed}." + (" Nothing is sold until you name one." if unnamed else "")


def buy(simulation: Mapping[str, Any], target_id: str = "", seller_id: str = "",
        quantity: int | None = None, item_id: str = "") -> TradeOutcome | None:
    """Buying what the reading names (an offer, or a thing on offer, by id) from someone here who sells it (the
    seller it names, else any here); a seller's offers when it names none of them."""
    if not _d(_d(_sections.world_model_of(simulation)).get("offers")):
        return None
    sellers = [provider for provider in _providers_here(simulation) if _offers(simulation, provider)]
    candidates = [provider for provider in sellers if _s(provider.get("provider_id")) == seller_id] if seller_id else sellers
    if seller_id and not candidates:
        return TradeOutcome(lines=["No one here by that name sells anything."], refused=True, kind="refused")
    matches = [(provider, offer) for provider in candidates for offer in _offers(simulation, provider)
               if target_id and (_s(offer.get("offer_id")) == target_id or target_id in {
                   _s(_d(item).get("item_id")) for item in _l(_d(offer.get("effects")).get("items_added"))})]
    if not matches and target_id in _carried(simulation):  # gear named: the one here who improves it (EV-5)
        matches = [(provider, offer) for provider in candidates for offer in _offers(simulation, provider)
                   if _s(offer.get("service_kind")) == "upgrade"
                   and _slot(_carried(simulation)[target_id]) in _l(_d(offer.get("recipe")).get("slots"))]
        item_id = target_id
    if not matches:
        if len(candidates) == 1:
            return TradeOutcome(lines=[_listing(simulation, candidates[0], _offers(simulation, candidates[0]),
                                                unnamed=True)],
                                kind="listed")
        return TradeOutcome(lines=["No one here sells that."], refused=True, kind="refused")
    provider, offer = matches[0]
    name, label = _s(provider.get("provider_name")), _s(offer.get("label"))
    price, why = price_of(simulation, provider, offer)
    left = stock_left(simulation, offer)
    if left is not None and left <= 0:
        return TradeOutcome(lines=[f"{label} is sold out."], refused=True, kind="refused")
    kind = _s(offer.get("service_kind"))
    if kind == "upgrade":  # a carried piece of gear improved by a tier (EV-5)
        return improve(simulation, provider, offer, item_id=item_id)
    told: tuple[list[StateChange], list[str]] = ([], [])
    if kind == "paid_information":  # what is going about here, for a price (EV-4, ``rules/rumours.py``)
        from app.apps.rpg.rules.rumours import news_here, tell

        told = tell(simulation, news_here(simulation, routines.hero_location(simulation)),
                    source=_s(provider.get("provider_id")))
        if not told[1]:
            return TradeOutcome(lines=[f"{name} has nothing new to tell you."], refused=True, kind="refused")
    purse = _purse(simulation)
    if purse < price:
        return TradeOutcome(lines=[f"You cannot afford {label}: it costs {coins(price)} and you have {coins(purse)}."],
                            refused=True, kind="refused")
    effects = _d(offer.get("effects"))
    # Goods by the count asked, as many as are left and the purse covers; a room, a meal or a drink is one.
    asked = max(1, min(MOST_AT_ONCE, quantity or 1)) if kind == "shop_goods" else 1
    count = min(asked, left if left is not None else asked, purse // price if price else asked)
    what = label if count == 1 else f"{count} × {label}"
    changes: list[StateChange] = ([PurseChanged(delta_copper=-price * count, reason=f"bought {what} from {name}")]
                                  if price else [])
    lines = ([f"You pay {coins(price * count)} to {name} for {what}" + (f" ({', '.join(why)})" if why else "")
              + ". The transaction is complete."] if price else
             [f"{name} gives you {in_sentence(what)} for nothing" + (f" ({', '.join(why)})" if why else "") + "."])
    if count < asked:
        lines.append(f"That is all {'there is' if left is not None and left < asked else 'you can afford'} of {label}.")
    for item in _l(effects.get("items_added")):
        item = _d(item)
        changes.append(ItemAdded(item_id=_s(item.get("item_id")), name=_s(item.get("name")) or label,
                                 quantity=max(1, int(item.get("quantity") or 1)) * count, category=_s(item.get("type")),
                                 fields={**({"description": _s(item.get("description"))} if item.get("description") else {}),
                                         **({"equipment": _d(item.get("equipment"))} if _d(item.get("equipment")) else {})}))
    if kind in RELIEF:
        need, delta = RELIEF[kind]
        changes.append(NeedsChanged.model_validate({need: delta}))
        lines.append(f"It eases your {need}.")
    if told[1]:
        changes += told[0]
        lines += [f"{name} tells you: {line}" for line in told[1]]
    if kind == "lodging":
        changes.append(ServiceReserved(offer_id=_s(offer.get("offer_id")), service_kind=kind,
                                       provider_id=_s(provider.get("provider_id")), provider_name=name, label=label,
                                       duration=_s(effects.get("duration")) or "one_night"))
    if left is not None:
        changes.append(StockTaken(offer_id=_s(offer.get("offer_id")), remaining=left - count, day=_today(simulation)))
    changes.append(TradeRemembered(provider_id=_s(provider.get("provider_id")), provider_name=name, deal="bought",
                                   what=what, copper=price * count))
    return TradeOutcome(changes=changes, lines=lines, kind="bought")


def _deals_in(simulation: Mapping[str, Any], shop: Mapping[str, Any], name: str) -> bool:
    return any(_s(offer.get("label")).casefold() == name.casefold() for offer in _offers(simulation, shop))


def _buys(simulation: Mapping[str, Any], shop: Mapping[str, Any], item: Mapping[str, Any]) -> bool:
    """A shop buys back what it sells, and the kinds of things its buy-back names; anything, where it names none."""
    kinds = {_s(kind).casefold() for kind in _l(_d(shop.get("buys")).get("item_types")) if _s(kind)}
    return (not kinds or _deals_in(simulation, shop, _s(item.get("name")))
            or _s(item.get("category") or item.get("type")).casefold() in kinds)


def _carried(simulation: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    player = _d(_sections.player_state_of(simulation))
    return {_s(_d(row).get("item_id")): _d(row) for row in _l(_d(_sections.inventory_state_of(player)).get("items"))
            if _s(_d(row).get("item_id"))}


def _equipment(item: Mapping[str, Any]) -> dict[str, Any]:
    """A carried piece's equipment as it fights (``equipment_runtime.project_equipment_stats``): its own block, or its
    definition's, else its kind's by its name ("Iron Dagger": a dagger)."""
    from app.apps.rpg.rules.interactions.equipment_runtime import item_equipment
    from app.apps.rpg.rules.interactions.item_model import normalize_item_instance

    return _d(item_equipment(normalize_item_instance(dict(item))))


def _slot(item: Mapping[str, Any]) -> str:
    return _s(_equipment(item).get("slot"))


def improve(simulation: Mapping[str, Any], provider: Mapping[str, Any], offer: Mapping[str, Any], *,
            item_id: str = "") -> TradeOutcome:
    """A seller improves a piece of gear the hero carries by one tier (EV-5): the one named, else the first worn or
    carried that the recipe covers; for its materials and the offer's price, by the tier; up to the recipe's last
    tier, and no further than the hero's level's budget for its slot (``rules/budgets.py``)."""
    from app.apps.rpg.foundation.state.changes import ItemImproved, ItemRemoved
    from app.apps.rpg.rules.budgets import budget

    name, label = _s(provider.get("provider_name")), _s(offer.get("label"))
    recipe = _d(offer.get("recipe"))
    carried = _carried(simulation)
    covered = [item for item in carried.values() if _slot(item) in _l(recipe.get("slots"))]
    worn = set(_d(_d(_sections.inventory_state_of(_d(_sections.player_state_of(simulation)))).get("equipment")).values())
    last = int(recipe.get("max_tier") or 3)
    # Unnamed: a piece that can still be improved before one at its last tier, and what is worn before what is carried.
    item = carried.get(item_id) if item_id else next(iter(sorted(
        covered, key=lambda row: (int(row.get("tier") or 0) >= last, row.get("item_id") not in worn))), None)
    if item is None or _slot(item) not in _l(recipe.get("slots")):
        return TradeOutcome(lines=[f"{name} has nothing of yours to improve that way."], refused=True, kind="refused")
    item_name = _s(item.get("name")) or _s(item.get("item_id"))
    tier = int(item.get("tier") or 0)
    if tier >= int(recipe.get("max_tier") or 3):
        return TradeOutcome(lines=[f"The {item_name} can be improved no further."], refused=True, kind="refused")
    level = int(_d(_sections.player_state_of(simulation)).get("level") or 1)
    bounds = budget(simulation, level).items.get(_slot(item))
    stats = {key: int(value) for key, value in _d(_equipment(item).get("stats")).items()
             if isinstance(value, (int, float))}
    improved = {key: stats[key] + int(step) for key, step in _d(recipe.get("per_tier")).items() if key in stats}
    if not improved:
        return TradeOutcome(lines=[f"{name} cannot improve the {item_name}."], refused=True, kind="refused")
    for key, band in (("damage_max", getattr(bounds, "damage_max", None)), ("armor", getattr(bounds, "armor", None))):
        if band is not None and key in improved and improved[key] > band.high:
            return TradeOutcome(lines=[f"The {item_name} is as good as a hero of your level can make use of."],
                                refused=True, kind="refused")
    needed = [_d(row) for row in _l(recipe.get("materials"))]
    for row in needed:
        stack = _d(carried.get(_s(row.get("item_id"))))
        held = int(stack.get("qty") or stack.get("quantity") or 0)
        if held < int(row.get("quantity") or 1):
            material = _s(_d(carried.get(_s(row.get("item_id")))).get("name")) or _s(row.get("item_id"))
            return TradeOutcome(lines=[f"{name} needs {int(row.get('quantity') or 1)} × {material} for that."],
                                refused=True, kind="refused")
    price = price_of(simulation, provider, offer)[0] * (tier + 1)
    if _purse(simulation) < price:
        return TradeOutcome(lines=[f"You cannot afford {label}: it costs {coins(price)}."], refused=True, kind="refused")
    changes: list[StateChange] = [PurseChanged(delta_copper=-price, reason=f"{label} from {name}")] if price else []
    changes += [ItemRemoved(item_id=_s(row.get("item_id")), quantity=int(row.get("quantity") or 1)) for row in needed]
    changes.append(ItemImproved(item_id=_s(item.get("item_id")), tier=tier + 1, stats={**stats, **improved},
                                slot=_slot(item)))
    changes.append(TradeRemembered(provider_id=_s(provider.get("provider_id")), provider_name=name, deal="bought",
                                   what=f"{label}: {item_name}", copper=price))
    gains = ", ".join(f"{key.replace('_', ' ')} {stats[key]} to {value}" for key, value in improved.items())
    return TradeOutcome(changes=changes, kind="bought", lines=[
        f"{name} works on your {item_name} for {coins(price)}: it is tier {tier + 1} now ({gains})."])


def sell(simulation: Mapping[str, Any], item_id: str = "", buyer_id: str = "") -> TradeOutcome | None:
    """Selling one of something the hero carries (by id) to a shopkeeper here (the buyer the reading names, else the
    one here who deals in it): half the price of goods they sell themselves, a token for other goods, and nothing
    for what a quest gave."""
    world = _d(_sections.world_model_of(simulation))
    if not _d(world.get("providers")):
        return None
    store = _d(_sections.inventory_state_of(_d(_sections.player_state_of(simulation))))
    item = next((_d(row) for row in _l(store.get("items"))
                 if item_id and _s(_d(row).get("item_id") or _d(row).get("id")) == item_id), None)
    if item is None:
        return TradeOutcome(lines=["You carry nothing by that name to sell."], refused=True, kind="refused")
    name = _s(item.get("name"))
    shops = [provider for provider in _providers_here(simulation) if "shop_goods" in _l(provider.get("service_kinds"))]
    named = [shop for shop in shops if buyer_id and _s(shop.get("provider_id")) == buyer_id]
    if buyer_id and not named:
        # Someone here it is sold to who keeps no shop that buys ("sell the bread to Orik"): theirs to refuse, not
        # another's to buy (the review: the sale went to Brindle).
        present = set(_l(_d(_sections.present_npc_state_of(simulation)).get("present_npc_ids")))
        other = _s(_d(_d(world.get("npcs")).get(buyer_id)).get("name")) if buyer_id in present else ""
        if other:
            return TradeOutcome(lines=[f"{other} does not buy the {name}."], refused=True, kind="refused")
    if len(named) == 1 and not _buys(simulation, named[0], item):
        return TradeOutcome(lines=[f"{_s(named[0].get('provider_name'))} does not buy the {name}."], refused=True,
                            kind="refused")
    shops = [shop for shop in shops if _buys(simulation, shop, item)]
    # Unnamed, the one shop here that deals in it (Brindle buys back his shards; the guard captain does not).
    dealing = [shop for shop in shops if _deals_in(simulation, shop, name)]
    shops = named or (dealing if len(dealing) == 1 else shops)
    if len(shops) > 1:
        buyers = " or ".join(_s(shop.get("provider_name")) for shop in shops)
        return TradeOutcome(lines=[f"To whom do you sell the {name}: {buyers}?"], refused=True, kind="refused")
    if not shops:
        return TradeOutcome(lines=[f"No one here trades in goods to buy the {name}."], refused=True, kind="refused")
    shop = shops[0]
    buyer = _s(shop.get("provider_name"))
    rewards = {_s(reward) for quest in _l(_d(_sections.quest_state_of(simulation)).get("quests"))
               for reward in _l(_d(quest).get("rewards"))}
    item_id = _s(item.get("item_id") or item.get("id"))
    if item_id in rewards:
        return TradeOutcome(lines=[f"{buyer} will not buy the {name}: it was earned, not bought."], refused=True,
                            kind="refused")
    own = next((offer for offer in _offers(simulation, shop) if _s(offer.get("label")).casefold() == name.casefold()), {})
    fraction = float(_d(shop.get("buys")).get("price_fraction") or 0.5)
    paid = max(1, int(copper(_d(own.get("price"))) * fraction)) if own else UNTRADED_GOODS_COPPER
    return TradeOutcome(changes=[
        ItemRemoved(item_id=item_id, quantity=1),
        PurseChanged(delta_copper=paid, reason=f"sold {name} to {buyer}"),
        TradeRemembered(provider_id=_s(shop.get("provider_id")), provider_name=buyer, deal="sold", what=name, copper=paid),
    ], lines=[f"You sell the {name} to {buyer} for {coins(paid)}."], kind="sold")


__all__ = ["MOST_AT_ONCE", "TradeOutcome", "buy", "coins", "copper", "haggled", "price_of", "sell", "sellers_here",
           "stock_left"]
