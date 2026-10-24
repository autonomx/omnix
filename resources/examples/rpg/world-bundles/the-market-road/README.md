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

- 11 places in 5 regions, joined by 11 roads with travel times, from the Rusty Flagon up the trade road to
  Glimmerdeep Pass and the snowbound north beyond it; each place says how it is met (climate, weather at an
  opening, indoors or out) and the names players call it by;
- 10 people with biographies, voices, goals, secrets and relationships: in town Bran the innkeeper, Mira (who will
  travel with the hero), Elara the merchant, Captain Aldric of the watch and Tomas the porter; in the north Thorin
  Ironfist, Elandra and Kael (the demo's party), Captain Bryn of the Northern Watch and Marta of the Frosted Flagon;
- how the world plays (RQ-2.0 sections): three sellers with prices, stock, restock and buy-back; a daily routine
  and goals for each person; what each knows and on what terms; three pressures; a bestiary with fighting numbers,
  behaviour and loot;
- 10 quests and the story seeds that lead to them, the town's naming the opening hook a new game can choose;
- 11 square-grid maps, with spawn points, zones and portals along the roads;
- 6 openings: one per starting place the new-game screen offers (`metadata.starting_place_key`), and the demo
  (`metadata.preset_id`), a campaign already under way: a level 14 ranger with her party, kit, quests, standing
  and journal at Glimmerdeep Pass (`starting_resources`).
