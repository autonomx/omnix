# Aurelia: Echoes Beyond the Gate

A ready-to-import fantasy isekai world for the Omnix RPG World Library.

## Build the import file

The checksummed bundle is stored as nine reviewable Base64-compressed parts so the repository does not depend on Git LFS for this sample binary.

```bash
python examples/rpg/world-bundles/aurelia-echoes-beyond-the-gate/materialize.py
```

This writes:

`examples/rpg/world-bundles/aurelia-echoes-beyond-the-gate.omnix-world.zip`

Bundle SHA-256: `9582c2ee7aecfb1d0890210bcd198baedfe4d1ef4ddfbadd6b5086a35f6eb944`

Open **Worlds & Campaigns**, select **World bundle**, choose the generated ZIP, and import it. Leave the optional world ID empty to use `world:aurelia-echoes-beyond-the-gate`, or enter another ID to create a clone.

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
- 10 checksummed SVG illustrations, including the world map, four character portraits, and five location scenes.

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

The deterministic regression reconstructs the bundle, validates its SHA-256 through the production archive parser, and checks its lore, character, faction, map, scenario, release, and artwork counts.
