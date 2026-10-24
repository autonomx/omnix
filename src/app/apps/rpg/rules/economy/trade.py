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

COPPER = {"gold": 100, "silver": 10, "copper": 1}
UNTRADED_GOODS_COPPER = 5  # what a shop pays for goods it does not sell itself: a token
RELIEF = {"meal": ("hunger", -35), "drink": ("thirst", -30)}
_WORD = re.compile(r"[a-z0-9']+")
# Words that name what is wanted without naming an offer ("supplies"), and words for each kind of service.
_GENERIC = frozenset({"supplies", "goods", "wares", "something", "anything", "stuff", "things", "items"})
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
    world = _d(simulation.get("world_model"))
    location = _s(_d(simulation.get("player_state")).get("location_id"))
    present = set(_l(_d(simulation.get("present_npc_state")).get("present_npc_ids")))
    return [_d(provider) for provider_id, provider in _d(world.get("providers")).items()
            if _s(_d(provider).get("location_id")) == location and (not present or provider_id in present)]


def _named(providers: list[dict[str, Any]], words: set[str], text: str) -> list[dict[str, Any]]:
    lowered = text.casefold()
    return [provider for provider in providers
            if _s(provider.get("provider_name")).casefold() in lowered
            or words & {_s(alias).casefold() for alias in _l(provider.get("aliases")) if " " not in _s(alias)}]


def _offers(simulation: Mapping[str, Any], provider: Mapping[str, Any]) -> list[dict[str, Any]]:
    offers = _d(_d(simulation.get("world_model")).get("offers")).get(_s(provider.get("provider_id")))
    return [_d(offer) for offer in _l(offers)]


def _stock(simulation: Mapping[str, Any], offer: Mapping[str, Any]) -> int | None:
    if offer.get("stock") is None:
        return None  # unlimited
    kept = _d(_d(simulation.get("trade")).get("stock"))
    return int(kept.get(_s(offer.get("offer_id")), offer.get("stock")) or 0)


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
    player = _d(simulation.get("player_state"))
    return copper(_d(_d(player.get("inventory_state")).get("currency") or player.get("currency")))


def _listing(provider: Mapping[str, Any], offers: list[dict[str, Any]], *, unnamed: bool) -> str:
    listed = ", ".join(f"{_s(offer.get('label'))} ({coins(copper(_d(offer.get('price'))))})" for offer in offers)
    return f"{_s(provider.get('provider_name'))} offers: {listed}." + (" Nothing is sold until you name one." if unnamed else "")


def buy(simulation: Mapping[str, Any], text: str) -> TradeOutcome | None:
    """Buying what the player names from someone here who sells it; their offers when it names none of them."""
    if not _d(_d(simulation.get("world_model")).get("offers")):
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
            return TradeOutcome(lines=[_listing(candidates[0], _offers(simulation, candidates[0]), unnamed=True)],
                                kind="listed")
        return TradeOutcome(lines=["No one here sells that."], refused=True, kind="refused")
    _, _, provider, offer = ranked[0]
    name, label = _s(provider.get("provider_name")), _s(offer.get("label"))
    price = copper(_d(offer.get("price")))
    left = _stock(simulation, offer)
    if left is not None and left <= 0:
        return TradeOutcome(lines=[f"{label} is sold out."], refused=True, kind="refused")
    purse = _purse(simulation)
    if purse < price:
        return TradeOutcome(lines=[f"You cannot afford {label}: it costs {coins(price)} and you have {coins(purse)}."],
                            refused=True, kind="refused")
    kind = _s(offer.get("service_kind"))
    effects = _d(offer.get("effects"))
    changes: list[StateChange] = [PurseChanged(delta_copper=-price, reason=f"bought {label} from {name}")]
    lines = [f"You pay {coins(price)} to {name} for {label}. The transaction is complete."]
    for item in _l(effects.get("items_added")):
        item = _d(item)
        changes.append(ItemAdded(item_id=_s(item.get("item_id")), name=_s(item.get("name")) or label,
                                 quantity=max(1, int(item.get("quantity") or 1)), category=_s(item.get("type")),
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
        changes.append(StockTaken(offer_id=_s(offer.get("offer_id")), remaining=left - 1))
    changes.append(TradeRemembered(provider_id=_s(provider.get("provider_id")), provider_name=name, deal="bought",
                                   what=label, copper=price))
    return TradeOutcome(changes=changes, lines=lines, kind="bought")


def sell(simulation: Mapping[str, Any], text: str) -> TradeOutcome | None:
    """Selling one of something the hero carries to a shopkeeper here: half the price of goods they sell
    themselves, a token for other goods, and nothing for what a quest gave."""
    world = _d(simulation.get("world_model"))
    if not _d(world.get("providers")):
        return None
    lowered = text.casefold()
    store = _d(_d(simulation.get("player_state")).get("inventory_state"))
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
    rewards = {_s(reward) for quest in _l(_d(simulation.get("quest_state")).get("quests"))
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


__all__ = ["TradeOutcome", "buy", "coins", "copper", "sell"]
