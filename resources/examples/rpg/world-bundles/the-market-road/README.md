# The Market Road

The starter world: the classic new game is one of its openings (roadmap §4.4, RQ-2.8). A rain-soaked market town
on the old trade road, with the Rusty Flagon and its regulars, a market square, a road watched by bandits, an
abandoned mill, and an old quarry where a light burns that should have gone out years ago.

## Build the import file

The world is authored in `world.source.json`. Omnix compiles it (`genesis/worlds/world_source.py`) with the same
compilers a published world goes through (world revision, certified release, map definitions, one scenario per
opening). To write the bundle to a file, for importing by hand or sharing:

```bash
python resources/examples/rpg/world-bundles/the-market-road/materialize.py
```

This writes `resources/examples/rpg/world-bundles/the-market-road.omnix-world.zip` (not committed). The build is
deterministic.

Omnix installs the bundle into a workspace's library the first time a classic new game starts
(`genesis/worlds/builtin_worlds.py`), under an id that names the bundle's content, so an edited source installs
beside the older world and existing campaigns keep theirs.

## Included content

- 7 places in 4 regions, joined by 7 roads with travel times; each place says how it is met (climate, weather at
  an opening, indoors or out);
- 5 people with biographies, voices, goals, secrets and relationships: Bran the innkeeper, Mira (who will travel
  with the hero), Elara the merchant, Captain Aldric of the watch, and Tomas the porter;
- how the world plays (RQ-2.0 sections): two sellers with prices, stock, restock and buy-back; a daily routine and
  goals for each person; what each knows and on what terms; two pressures; a bestiary with fighting numbers,
  behaviour and loot;
- 7 quests and the story seeds that lead to them, each naming the opening hook a new game can choose;
- 7 square-grid maps, with spawn points, zones and portals along the roads;
- 5 openings, one per starting place the new-game screen offers (`metadata.starting_place_key`).
