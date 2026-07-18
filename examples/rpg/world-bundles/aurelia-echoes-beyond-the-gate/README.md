# Aurelia: Echoes Beyond the Gate

A ready-to-import fantasy isekai world for the Omnix RPG World Library.

## Build the import file

The original checksummed world data remains stored as nine reviewable Base64-compressed parts so the repository does not depend on Git LFS. Eleven production WebP artworks are committed beside the materializer under `artwork/`.

```bash
python examples/rpg/world-bundles/aurelia-echoes-beyond-the-gate/materialize.py
```

This writes:

`examples/rpg/world-bundles/aurelia-echoes-beyond-the-gate.omnix-world.zip`

Bundle SHA-256: `7b4b4d2868af5b96070f3f40a6f27983576dfda50bb5c9d2972424db64e45eb6`

Open **Worlds & Campaigns**, select **World bundle**, choose the generated ZIP, and import it. Leave the optional world ID empty to use `world:aurelia-echoes-beyond-the-gate`, or enter another ID to create a clone.

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
