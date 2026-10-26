"""Trade (RQ-2.3; docs/rpg/design/economy.md): buying from and selling to the people who trade where the hero stands.

The world's economy section says who sells what, at what price and stock, and what each buys back (RQ-2.0). The
rule reads it with the campaign's stock and the hero's purse and pack, and says what happens as changes: coin paid
or earned, goods taken or handed over, a need eased, a room reserved, the stock left, and the trade remembered.
A world without an economy section (the starter town until RQ-2.8) has no trade here; ``trade`` returns ``None``.
"""
from __future__ import annotations

import re
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
from app.apps.rpg.rules.routines import MINUTES_PER_DAY
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
_WORD = re.compile(r"[a-z0-9']+")
# Words that name what is wanted without naming an offer ("supplies"), and words for each kind of service.
_GENERIC = frozenset({"supplies", "goods", "wares", "something", "anything", "stuff", "things", "items"})
MOST_AT_ONCE = 10  # goods bought in one go (the playtest: "two Healing Potions" bought one)
_COUNTS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
           "a couple of": 2, "a pair of": 2, "a few": 3, "several": 3}
_COUNT = re.compile(r"\b(\d+|" + "|".join(sorted(_COUNTS, key=len, reverse=True)) + r")\b(?!\s*(?:gold|silver|copper|coins?)\b)")


def wanted_count(text: str) -> int:
    """How many the words ask for: a number or a number's word, else one; at most ``MOST_AT_ONCE``."""
    match = _COUNT.search(text.casefold())
    if match is None:
        return 1
    word = match.group(1)
    return max(1, min(MOST_AT_ONCE, int(word) if word.isdigit() else _COUNTS[word]))
_KIND_WORDS = {
    "lodging": frozenset({"room", "rent", "lodging", "bed", "stay", "night", "sleep"}),
    "meal": frozenset({"meal", "food", "stew", "supper", "dinner", "breakfast", "lunch", "eat"}),
    "drink": frozenset({"drink", "ale", "wine", "beer", "mead"}),
}
_FILLER = frozenset("a an the some my one i buy purchase rent order get from to for of please".split())


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


def _words(text: str) -> set[str]:
    return {word for word in _WORD.findall(text.casefold()) if word not in _FILLER}


def _providers_here(simulation: Mapping[str, Any]) -> list[dict[str, Any]]:
    world = _d(_sections.world_model_of(simulation))
    location = _s(_d(_sections.player_state_of(simulation)).get("location_id"))
    present = set(_l(_d(_sections.present_npc_state_of(simulation)).get("present_npc_ids")))
    return [_d(provider) for provider_id, provider in _d(world.get("providers")).items()
            if _s(_d(provider).get("location_id")) == location and (not present or provider_id in present)]


def sellers_here(simulation: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The people here who sell something."""
    return [provider for provider in _providers_here(simulation) if _offers(simulation, provider)]


def _named(providers: list[dict[str, Any]], words: set[str], text: str) -> list[dict[str, Any]]:
    lowered = text.casefold()
    return [provider for provider in providers
            if _s(provider.get("provider_name")).casefold() in lowered
            or words & {_s(alias).casefold() for alias in _l(provider.get("aliases")) if " " not in _s(alias)}]


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
    """What ``offer`` costs now, in copper, and why it differs from its price (economy.md)."""
    price = copper(_d(offer.get("price")))
    factor, why = 1.0, []
    left, full = stock_left(simulation, offer), int(offer.get("stock") or 0)
    if left is not None and full and left <= full * SCARCE_SHARE:
        factor, why = factor * SCARCE_MARKUP, [*why, "it is nearly gone"]
    access = _trade_access(simulation, _s(provider.get("location_id")))
    if access is not None and access < CHOKED_TRADE:
        factor, why = factor * CHOKED_MARKUP, [*why, "the roads choke trade"]
    provider_id = _s(provider.get("provider_id"))
    if int(_d(_d(simulation.get("relationship_state")).get(provider_id)).get("trust") or 0) >= TRUSTED:
        factor, why = factor * TRUSTED_DISCOUNT, [*why, "you are trusted"]
    if haggled(simulation, provider_id):
        factor, why = factor * HAGGLE_DISCOUNT, [*why, "you haggled"]
    return (price if factor == 1.0 else max(1, round(price * factor))), why


def _score(offer: Mapping[str, Any], words: set[str]) -> int:
    label = _words(_s(offer.get("label")))
    score = 10 * len(words & label)
    if words & _KIND_WORDS.get(_s(offer.get("service_kind")), frozenset()):
        score += 6
    items = {_s(_d(item).get("item_id")).rsplit(":", 1)[-1] for item in _l(_d(offer.get("effects")).get("items_added"))}
    if any(word in item.split("-") or word in item.split("_") for word in words for item in items):
        score += 4
    return score


def _purse(simulation: Mapping[str, Any]) -> int:
    player = _d(_sections.player_state_of(simulation))
    return copper(_d(_d(_sections.inventory_state_of(player)).get("currency") or player.get("currency")))


def _listing(simulation: Mapping[str, Any], provider: Mapping[str, Any], offers: list[dict[str, Any]], *,
             unnamed: bool) -> str:
    listed = ", ".join(f"{_s(offer.get('label'))} ({coins(price_of(simulation, provider, offer)[0])})" for offer in offers)
    return f"{_s(provider.get('provider_name'))} offers: {listed}." + (" Nothing is sold until you name one." if unnamed else "")


def buy(simulation: Mapping[str, Any], text: str) -> TradeOutcome | None:
    """Buying what the player names from someone here who sells it; their offers when it names none of them."""
    if not _d(_d(_sections.world_model_of(simulation)).get("offers")):
        return None
    words = _words(text)
    here = _providers_here(simulation)
    sellers = [provider for provider in here if _offers(simulation, provider)]
    named = _named(sellers, words, text)
    candidates = named or sellers
    ranked = sorted(((_score(offer, words), index, provider, offer) for provider in candidates
                     for index, offer in enumerate(_offers(simulation, provider))), key=lambda row: (-row[0], row[1]))
    if not ranked or ranked[0][0] == 0 or words <= _GENERIC:
        if len(candidates) == 1:
            return TradeOutcome(lines=[_listing(simulation, candidates[0], _offers(simulation, candidates[0]),
                                                unnamed=True)],
                                kind="listed")
        return TradeOutcome(lines=["No one here sells that."], refused=True, kind="refused")
    _, _, provider, offer = ranked[0]
    name, label = _s(provider.get("provider_name")), _s(offer.get("label"))
    price, why = price_of(simulation, provider, offer)
    left = stock_left(simulation, offer)
    if left is not None and left <= 0:
        return TradeOutcome(lines=[f"{label} is sold out."], refused=True, kind="refused")
    purse = _purse(simulation)
    if purse < price:
        return TradeOutcome(lines=[f"You cannot afford {label}: it costs {coins(price)} and you have {coins(purse)}."],
                            refused=True, kind="refused")
    kind = _s(offer.get("service_kind"))
    effects = _d(offer.get("effects"))
    # Goods by the count asked, as many as are left and the purse covers; a room, a meal or a drink is one.
    asked = wanted_count(text) if kind == "shop_goods" else 1
    count = min(asked, left if left is not None else asked, purse // price)
    what = label if count == 1 else f"{count} × {label}"
    changes: list[StateChange] = [PurseChanged(delta_copper=-price * count, reason=f"bought {what} from {name}")]
    lines = [f"You pay {coins(price * count)} to {name} for {what}" + (f" ({', '.join(why)})" if why else "")
             + ". The transaction is complete."]
    if count < asked:
        lines.append(f"That is all {'there is' if left is not None and left < asked else 'you can afford'} of {label}.")
    for item in _l(effects.get("items_added")):
        item = _d(item)
        changes.append(ItemAdded(item_id=_s(item.get("item_id")), name=_s(item.get("name")) or label,
                                 quantity=max(1, int(item.get("quantity") or 1)) * count, category=_s(item.get("type")),
                                 fields={"description": _s(item.get("description"))} if item.get("description") else {}))
    if kind in RELIEF:
        need, delta = RELIEF[kind]
        changes.append(NeedsChanged(**{need: delta}))
        lines.append(f"It eases your {need}.")
    if kind == "lodging":
        changes.append(ServiceReserved(offer_id=_s(offer.get("offer_id")), service_kind=kind,
                                       provider_id=_s(provider.get("provider_id")), provider_name=name, label=label,
                                       duration=_s(effects.get("duration")) or "one_night"))
    if left is not None:
        changes.append(StockTaken(offer_id=_s(offer.get("offer_id")), remaining=left - count, day=_today(simulation)))
    changes.append(TradeRemembered(provider_id=_s(provider.get("provider_id")), provider_name=name, deal="bought",
                                   what=what, copper=price * count))
    return TradeOutcome(changes=changes, lines=lines, kind="bought")


def sell(simulation: Mapping[str, Any], text: str) -> TradeOutcome | None:
    """Selling one of something the hero carries to a shopkeeper here: half the price of goods they sell
    themselves, a token for other goods, and nothing for what a quest gave."""
    world = _d(_sections.world_model_of(simulation))
    if not _d(world.get("providers")):
        return None
    lowered = text.casefold()
    store = _d(_sections.inventory_state_of(_d(_sections.player_state_of(simulation))))
    carried = sorted((_d(item) for item in _l(store.get("items")) if _s(_d(item).get("name")).casefold() in lowered),
                     key=lambda item: len(_s(item.get("name"))), reverse=True)
    if not carried:
        return TradeOutcome(lines=["You carry nothing by that name to sell."], refused=True, kind="refused")
    item = carried[0]
    name = _s(item.get("name"))
    shops = [provider for provider in _providers_here(simulation) if "shop_goods" in _l(provider.get("service_kinds"))]
    shops = _named(shops, _words(text), text) or shops
    if len(shops) != 1:
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


__all__ = ["TradeOutcome", "buy", "coins", "copper", "haggled", "price_of", "sell", "sellers_here", "stock_left"]
