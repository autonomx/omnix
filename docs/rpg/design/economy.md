# RQ-5.5 Economy (stretch): money matters, and prices answer the world

## What the player experiences

Coin comes in from quests, loot and selling; it goes out on lodging, food, repairs, potions and information. Prices
move: a shop sold out of potions restocks over days; when the roads are dangerous, goods from elsewhere cost more;
haggling (a persuade check) shaves a price.

## Rules

- Stock decreases on purchase and restocks by `restock_per_day` (authored, RQ-2.0) per in-game day.
- Price modifiers: scarcity (stock ≤ 20% of authored stock: +25%), a pressure on the region's `trade_access` below
  40 (+20%), relationship trusted (−10%), a successful haggle (−10%, once per offer per day).
- Selling: authored `buys.price_fraction` (default 0.5) of the shop's price for kinds it sells; quest items are not
  for sale.
- Sinks are sized so the balance simulation's purse stays within its band (README).

## State it changes

`StockChanged`, `PriceModifierApplied`, `CoinChanged`.

## Scenarios

Buy out a shop's potions; they restock after a day; prices rise while the road pressure is high and fall when it is
resolved; haggling once.

## Out of scope

Player-run shops, inflation, multiple currencies' exchange.
