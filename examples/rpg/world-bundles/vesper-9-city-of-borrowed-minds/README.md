# Vesper-9: City of Borrowed Minds

A ready-to-import cyberpunk authoring world for the Omnix RPG World Library. The setting is a drowned vertical megacity in 2099 where corporations own essential infrastructure, identity is a licensed service, memories can be repossessed, and an emergent intelligence may be trying to preserve every contradictory version of the people the city erased.

## Build the import file

```bash
python examples/rpg/world-bundles/vesper-9-city-of-borrowed-minds/materialize.py
```

This writes:

`examples/rpg/world-bundles/vesper-9-city-of-borrowed-minds.omnix-world.zip`

Bundle SHA-256: `41b3a7f7bdd17d38253034d07b50962f640545b1e920e329116a779ca55c89be`

Open **Worlds & Campaigns**, select **World bundle**, choose the generated ZIP, and import it. Leave the optional world ID empty to use `world:vesper-9-city-of-borrowed-minds`, or provide another ID to create a clone.

The import is an authoring world with all lore topics ready. It intentionally does not include compiled maps, releases, runtime scenarios, or image files; those can be produced in the normal World Forge workflow after import.

## Included content

The bundle contains all 18 Cyberpunk profile topics shown by the World Profile Preview:

1. World Overview and Setting Rules
2. History and Timeline
3. Megacities, Districts and Corporate Zones
4. Places, Facilities and Points of Interest
5. Corporations, Gangs, Governments and Institutions
6. Cultures and Subcultures
7. Actors and NPCs
8. Networks, Virtual Spaces and Artificial Intelligences
9. Technology and Augmentations
10. Weapons, Equipment, Vehicles and Commodities
11. Roles, Archetypes, Skills and Talents
12. Threats, Drones, Security Forces and Engineered Creatures
13. Economy, Services, Laws and Surveillance
14. Current Conflicts and Pressures
15. Quests, Jobs and Contracts
16. Encounter Seeds
17. Opening Threads
18. Opening Scenarios and One-Shots

Across those topics are 91 canonical entries: 5 historical eras, 5 districts, 7 locations, 6 factions, 4 cultures, 8 major NPCs, 4 networks and AI spaces, 6 augmentations, 8 equipment entries, 5 playable archetypes, 6 threat types, 4 economic and legal systems, 5 advancing world pressures, 6 contracts, 6 encounter seeds, 3 opening threads, and 2 launch scenarios.

Every topic has a three-paragraph overview. Every canonical entry has multi-paragraph lore covering its public role, ordinary lived detail, hidden truth, and consequences. NPCs include goals, dependencies, pressures, next actions, reaction conditions, knowledge limits, and speaking styles. Factions have resources, dependencies, internal divisions, current objectives, next actions, failure responses, and visible signs. Pressures include current state, next tick, escalation conditions, and observable evidence.

## Image prompts only

No image assets are generated or embedded. Every image-enabled entry includes:

- `image_role`, matching the profile role in the preview;
- `image_prompt`, written for grounded cinematic cyberpunk RPG art;
- a shared prohibition on rendered text, logos, watermarks, and UI overlays.

The bundle manifest therefore has an empty `assets` collection. Prompts remain attached to the lore entries so artwork can be generated and assigned manually.

## Core campaign

The campaign begins as residents suffer stolen or contradictory memories, the Red Knives Union prepares a general strike, the Tidebreak seawall begins to fail, Helix and Orison fight over corporate succession, and the emergent intelligence called **Moth** communicates through dreams, transit audio, and erased identities.

The central question is not merely whether Moth is alive. It is whether a city built on licensed identity can recognize any person—human, copied, composite, erased, or artificial—whose existence is inconvenient to its owners.

### Borrowed Night

A level-one opening at Black Rain Station. A dying courier with the player's face arrives carrying a sealed memory coldcase as Kestrel locks down the platforms and the twenty-year-lost ghost train approaches Platform Zero.

### Black Rain Rising

A strike-and-disaster opening at Tidebreak Docks. A contraband container holds stolen identities beside missing seawall pump controllers, forcing the party to balance worker solidarity, flood safety, evidence, and the lives stored inside the cargo.

## Source layout

The curated Python catalogue is compressed into reviewable Base64/zlib parts under `catalogue-parts/`, following the repository's existing sample-bundle approach and avoiding Git LFS. The materializer verifies the catalogue checksum, creates deterministic `manifest.json` and `world.json` entries, and writes a checksummed Omnix world ZIP with no binary assets.
