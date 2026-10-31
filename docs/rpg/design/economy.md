# RQ-5.5 Economy (stretch): money matters, and prices answer the world

## What the player experiences

Coin comes in from quests, loot and selling; it goes out on lodging, food, repairs, potions and information. Prices
move: a shop sold out of potions restocks over days; when the roads are dangerous, goods from elsewhere cost more;
haggling (a persuade check) shaves a price.

## Rules

- Stock decreases on purchase and restocks by `restock_per_day` (authored, RQ-2.0) per in-game day.
- Price modifiers: scarcity (stock ≤ 20% of authored stock: +25%), a pressure on the region's `trade_access` below
  40 (+20%), relationship trusted (−10%), a successful haggle (−10%, once per offer per day).
- Selling: authored `buys.price_fraction` (default 0.5) of the shop's price for kinds it sells, a token for others;
  quest items are not for sale. A shop with `buys.item_types` buys only those types and its own goods. Unnamed, a
  sale goes to the one shop here that sells the thing, else to the one that would buy it; with two, the hero is asked.
- Sinks are sized so the balance simulation's purse stays within its band (README).

## State it changes

`StockChanged`, `PriceModifierApplied`, `CoinChanged`.

## Scenarios

Buy out a shop's potions; they restock after a day; prices rise while the road pressure is high and fall when it is
resolved; haggling once.

## Out of scope

Player-run shops, inflation, multiple currencies' exchange.

## As built (restocking, with RQ-5.6 part 1)

A sale records what the offer has left and the campaign day (`StockTaken.day`); `rules/economy/trade.py`
`stock_left` grows it back by the offer's `restock_per_day` for each day since, up to its stock, so restocking needs
no tick of its own. An offer the world gives no rate (a derived inn's rooms, the day's meals) is stocked afresh each
day; an authored `restock_per_day` of 0 never restocks. Before this nothing restocked: an inn let six nights and was
sold out for the rest of the campaign (the balance simulation's player, hurt and with coin, asked for a room until
the end).

## As built (RQ-5.5)

`rules/economy/trade.py` `price_of`: an offer's price, then +25% when what is left is a fifth of its stock or less,
+20% when the trade access of the seller's region (the causal runtime's) is below 40, -10% from a seller who trusts
the hero (50 or more), and -10% for the rest of the day after a haggle won with them; the purchase line says why
("You pay 3 silver, 6 copper to Brindle Gearwing for Healing Potion (the roads choke trade, you haggled)"), and a
seller's listing shows the prices as they stand. A haggle is a check of its own (`checks.py` kind `haggle`:
persuasion and charisma, the seller's difficulty, else moderate; "haggle", "bargain with", "a better price"; with no
one named, the one seller here); a failure costs a little of the seller's regard. A check now records the minute
of the campaign clock it was made at, so the haggle holds for its day. Selling pays the shop's authored
`buys.price_fraction` (0.5 by default) of its list price, as RQ-2.3 built it. The sources: the world's pressures now
raise a side quest from anywhere once the hero's region is safe, one at a time and at most one a day (quests.md),
and a felled creature pushes back only its own region's pressure (a wolf killed in one march no longer made every
region's roads safe at once, which left nothing to pay for the rest of the campaign). With these the balance
simulation's purse is inside its band in both worlds. Haggles are once a day per seller, not per offer.

## Information and upgrades (evolution roadmap EV-4, EV-5)

Paid information sells the word going about where the hero stands (`rules/rumours.py`): the seller tells what has
not been heard, and refuses the price when there is nothing new. An `upgrade` offer improves a carried piece of gear
by one tier (`rules/economy/trade.improve`, `ItemImproved`): its recipe names the slots it improves, the materials a
tier takes, what a tier adds and the last tier; the price is the offer's by the tier, and no tier goes past the
hero's level's budget for the slot (`rules/budgets.py`). Gear is improved as it fights: unnamed, the piece the hero
wears comes first, and a world's own weapon with no equipment of its own ("Iron Dagger") is improved as its kind, its
block then written on the carried row. Aurelia: Hollis improves a blade or armour with two Aether
Shards a tier, up to three; Brindle tunes a weapon with one, up to two. Scenario: `test_upgrades.py`.
