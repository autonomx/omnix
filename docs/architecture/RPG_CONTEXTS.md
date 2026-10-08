# RPG bounded contexts (Track R)

Status: **R-1 and R-2 done (lint rule AL017 with a recorded baseline). R-3 moves
done (2026-10-08): each context is a package under `app/apps/rpg`; the upward
imports are not yet inverted (AL017 baseline still 60).** Date: 2026-10-08.

RPG is about 285,000 lines in 1,208 files under `src/app/apps/rpg`, with 129
top-level entries. Measured at any import scope, 32 of those entries form a
single import cycle, with `session` at its centre: `session` (78,000 lines)
imports 36 other entries and 14 import it. This map splits RPG into seven
contexts that may only depend downward. It is the map the lint enforces
(`[rpg_contexts]` in `resources/architecture/layers.toml`, rule AL017).

## The contexts, lowest first

| # | Context | What it holds | Files | Lines |
|---:|---|---|---:|---:|
| 1 | **foundation** | RPG's own kernel: core types, persistence, provider access and priorities, tracing, safe values, foreground turn records | 98 | 17,529 |
| 2 | **rules** | Deterministic game rules: actions, items, economy, combat, interactions, encounters, party, player, survival, quests, choices, validation | 131 | 27,852 |
| 3 | **world** | The simulated world: world state, locations, maps and grids, spatial and tactical layers, NPCs and their agency, social state, memory | 194 | 38,033 |
| 4 | **narration** | Everything that writes prose: AI calls, narrative engine, narration, dialogue, response generation, presentation, coherence, journal and story arcs | 210 | 49,971 |
| 5 | **genesis** | Making worlds and campaigns: the World Forge (`worlds/` and `session/genesis/`), creator, profiles, packs, migrations, modding | 254 | 74,341 |
| 6 | **session** | The turn pipeline: session, orchestration, runtime, execution, control, jobs, recovery | 229 | 63,792 |
| 7 | **edge** | What faces outward: HTTP API, the RPG Hermes feature, replay, the feature declaration, release gates and quality fixtures | 92 | 13,333 |

The full entry lists are in `layers.toml`. An entry may name a subpackage, and
the longest match wins: `session.genesis` belongs to genesis although the rest
of `session` does not.

**Why this order.** Rules must not know how they are narrated, and the world
must not know which turn is running. Narration reads rules and the world.
Genesis builds worlds and campaigns from all of those. The session pipeline
runs a turn through everything below it. The edge serves it.

**The main finding.** The World Forge lives inside `session` as
`session/genesis/`, and `worlds/` (40,000 lines) depends on it. That is why
`worlds` appeared to depend on the turn pipeline 54 times. Assigned to genesis,
those imports are within one context.

## What AL017 checks

- An import at any scope from one context into the same or a higher one is a
  violation, fingerprinted as `<from>-><to>:<entry>`.
- Importing a submodule does not also count as importing its parent package.
- An entry that belongs to no context is a violation
  (`rpg_entry_without_context:<entry>`), so a new top-level entry must be
  placed on the map.

Imports within a context are not checked. Contract-only imports between
contexts arrive in R-3, when each context becomes a package with a `contracts`
module.

## Baseline: 60 upward imports

| From → to | Imports |
|---|---:|
| foundation → narration | 14 |
| narration → session | 10 |
| foundation → world | 8 |
| genesis → session | 7 |
| foundation → genesis | 5 |
| foundation → session | 4 |
| rules → world | 3 |
| foundation → rules | 2 |
| world → session | 2 |
| rules → session, rules → genesis, rules → narration, world → narration, world → genesis | 1 each |

Most of them come from two foundation modules, `core` and `persistence`, that
still reach up into the contexts they serve. The baseline only shrinks: a new
upward import fails the lint.

## R-3: moving RPG into its contexts

**Done: the moves (2026-10-08).** RPG now has nine top-level entries: the seven
context packages, plus `feature.py`, `declarations.py` and `migrations/`, which
must stay together at the package root (migration and declaration discovery
find them next to `feature.py`). `world`, `narration` and `session` are both
an old entry and a context root; every other entry moved inside its context
(`app.apps.rpg.<context>.<entry>`), and the World Forge moved from
`session/genesis` to `genesis/forge`. The move was a pure `git mv` plus
`scripts/rewrite_imports.py`; cross-entry relative imports were made absolute
first. Five top-level modules that were shadowed by same-named packages (never
importable) were deleted. AL013 keeps its scope through `[rpg_core].exclude`.

**Still to do:** invert the 60 upward imports (the baseline below, now under the
new paths) and add each context's `contracts` module.

The original plan:

R-3 waits for WP-8.6 to close, because moving files would collide with the RPG
work still landing. One context per pull request series: a pure `git mv`, then
an import rewrite (`scripts/rewrite_imports.py`), then a baseline shrink.

1. **genesis first.** Move `session/genesis/` next to `worlds/`. That removes
   the World Forge from the turn pipeline and most genesis → session imports.
2. **foundation.** Move the session state types that `core` and `persistence`
   reach for into foundation, and invert the remaining upward calls through
   ports.
3. **Then rules, world, narration, session and edge**, each under
   `app/apps/rpg/<context>/` with a `contracts` module. Cross-context imports
   then go through contracts only.

Acceptance (from the roadmap): RPG has 15 or fewer top-level entries, the
`rpg-production-turn` golden and the 50-turn replay are unchanged, and the
AL017 baseline is 0.
