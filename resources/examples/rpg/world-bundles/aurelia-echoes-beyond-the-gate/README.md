# Aurelia: Echoes Beyond the Gate

A ready-to-import fantasy isekai world for the Omnix RPG World Library.

## Build the import file

The original checksummed world data remains stored as nine reviewable Base64-compressed parts so the repository does not depend on Git LFS. Eleven production WebP artworks are committed beside the materializer under `artwork/`.

```bash
python resources/examples/rpg/world-bundles/aurelia-echoes-beyond-the-gate/materialize.py
```

This writes:

`resources/examples/rpg/world-bundles/aurelia-echoes-beyond-the-gate.omnix-world.zip`

Bundle SHA-256: `a22a456f00329708f2b0cfb3f366aaf0d18e80317f864c6d873621814a833289`

Open **Worlds & Campaigns**, select **World bundle**, choose the generated ZIP, and import it. Leave the optional world ID empty to use `world:aurelia-echoes-beyond-the-gate`, or enter another ID to create a clone.

## How it plays

Aurelia's author wrote its people's days (`play-sections.json`): where each of the ten is, hour by hour, and their goals. By day everyone keeps their place (Liora in the grove, Miri and Seraphine at the guild, Orik, Brindle and Rhea in the village); evenings and nights differ (Liora by the inn's hearth, Brindle pitching at the guild, Rhea checking the pass's barricades, Naia at the grove at dawn).

The author also wrote its pressures, how its creatures fight (the deeper the place, the stronger what lives there: the pass's Sky Mantas at level 4, the ashen Glass Wights at 5, the Loom's Rootbound Knights at 6, the Hollow Archon at 10), and every quest's steps: the first night ends with a companion chosen, the phone is mended and its voice followed and named, Orik's daughter's memory is won back past the Loom's knights (and pays the Moonroot Key), and the finale needs that key, the descent, Malrec, the Archon, and a choice of the gate's fate. Its economy and knowledge are still played from its lore. Its four roads leave Valecourt, Cinderhold and the Hollow Meridian unreached; a launch joins each to them (`lore_sections.joined_routes`).

The sections are written in the way a world author writes them, by the world library's own lifecycle: `author_play_sections.py` imports the bundle into a disposable database, saves and publishes the sections (a new world revision, each opening pinned to it), exports the world, and writes its `world.json` into the source parts, the checksum above and this README.

```bash
OMNIX_DATABASE_URL=postgresql://...@127.0.0.1:16432/<disposable db> \
    python resources/examples/rpg/world-bundles/aurelia-echoes-beyond-the-gate/author_play_sections.py --allow-database <disposable db>
```

## Production artwork

The materializer replaces the earlier lightweight SVG placeholders while preserving the existing asset IDs referenced by maps and characters. The import contains:

- dedicated Aurelia cover art for the world-card catalog;
- Starfall Grove arrival art;
- portraits for Liora Fen, Archon Malrec, Princess Seraphine Valecourt, and Vael Ardyn;
- illustrated Starfall Village and Moonroot Ruins maps;
- Skybridge Pass and Wayfarers' Guild location art;
- an illustrated Aurelia world map.

The images are optimized for world cards, map/location previews, and character codex portraits while remaining embedded in the portable world bundle.

## Premise

During a citywide blackout on modern Earth, the protagonist is pulled through a broken Meridian Gate and awakens in Starfall Grove. Aurelia is a luminous high-fantasy world where memory, conviction, and unrealized possibility become magic. Earthborn arrivals can manifest remembered concepts as temporary powers, but overuse can erase the memories that made those powers possible.

The central campaign asks whether the way home should be closed, opened, or transformed into a guarded bridge between worlds.

## Included content

- 11 complete lore topics with append-only topic history;
- 10 named characters with biographies, goals, secrets, relationships, and speaking styles;
- 6 political factions;
- 5 regions and a connected travel topology;
- 5 certified square-grid maps with portals, spawn points, zones, objects, and hazards;
- 3 published launch scenarios;
- 6 main quest arcs plus supporting adventure seeds;
- a Resonance magic system with five schools and Earthborn Echo abilities;
- economy, services, items, bestiary, religions, history, cosmology, and GM guidance;
- 11 checksummed production WebP artworks.

## Playable maps

1. **Starfall Grove** — the canonical arrival point beneath the broken gate.
2. **Starfall Village** — frontier market, inn, moonwell, and public quest board.
3. **Wayfarers' Guild** — registration, contracts, party formation, and training.
4. **Skybridge Pass** — a tactical mountain crossing above the cloud sea.
5. **Moonroot Ruins** — a memory-haunted dungeon containing the ancient Memory Loom.

## Launch scenarios

### Gateborn: First Light

The primary level-one isekai opening. Meet Liora Fen, survive an unstable rift, investigate a dead smartphone that rings without power, and reach the guild.

### Wayfarer Initiation

Begin after registration, form a party, choose a first contract, and investigate a Glass Synod infiltrator.

### The Moonroot Expedition

A level 3–5 opening for an established party entering the ruins to recover stolen memories before the Hollow Meridian wakes.

## Major characters

- **Liora Fen** — foxkin gatewarden, guide, and first companion.
- **Princess Seraphine Valecourt** — reformist princess-engineer rebuilding ancient gateworks.
- **Vael Ardyn** — exiled Ashen general seeking atonement.
- **Miri Kestrel** — hyper-competent Wayfarers' Guild registrar.
- **Orik Stonewake** — innkeeper and retired portal mason.
- **Naia of the Open Hand** — an Earthborn saint who arrived eighty years ago and has not aged.
- **Archon Malrec** — leader of the Glass Synod and keeper of the Hollow Meridian.
- **Brindle Gearwing** — kobold relic mechanic who builds impossible devices from Earth electronics.
- **Elyra Moonroot** — dryad memory archivist and guardian of the ruins.
- **Captain Rhea Sunward** — commander of Starfall Village's guard.

## Verification

The deterministic regression reconstructs the bundle, validates its SHA-256 through the production archive parser, verifies every artwork's stable asset ID, WebP MIME type, archive extension, and byte-size floor, and checks the lore, character, faction, map, scenario, and release counts.
