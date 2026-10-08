# RPG bounded contexts (Track R)

Status: **R-1, R-2 and R-3 done (2026-10-08). Each context is a package under
`app/apps/rpg` and no context imports a context above it: the AL017 baseline is
0.** See "R-3: inverting the upward imports" below. Date: 2026-10-08.

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

Imports within a context are not checked.

## The original baseline: 60 upward imports (now 0)

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

Most of them came from two foundation modules, `core` and `persistence`, that
reached up into the contexts they serve. The baseline only shrinks: a new
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

**Done: inverting the upward imports (2026-10-08, AL017 60 -> 0).** Three kinds
of change, each checked against a simulation of AL017 before it was made:

- **Moves to the owning context** (pure `git mv` plus the rewrite). Repositories
  live with the types they store: `narration/persistence`, `world/persistence`,
  `genesis/persistence` and `session/persistence` (which also composes every
  context's repositories). Modules that served a higher context moved up (the
  foreground turn record, the narrative provider, the action intelligence
  prompts); dependency-light modules that lower contexts needed moved down (the
  location registry, ambient intent and pending interactions to `rules`; the
  LLM gateway adapter, the semantic packet contract, dynamic NPC profiles and
  `NarrativeEvent` to `foundation`; the memory prompt chain, the dialogue
  runtime and the LLM orchestration state to `narration`).
- **Ports**, in a context's `contracts` module, where a lower context has to
  call a higher one. `world.contracts.ConversationHooks`: the world
  conversation tick asks for model-written lines and ambient narration, and
  the session supplies them (`session/conversation_hooks.py`).
  `genesis.contracts.CampaignSessions`: the World Forge loads, saves, archives
  and creates campaign sessions through the store its callers pass
  (`SessionCampaignSessions` in `session/service.py`), as it already received its database and
  LLM gateway. Ports are passed explicitly, never registered in module state.
- **Small extractions**: the narrator's scene grounding
  (`narration.scene_grounding`), the traced JSON response (edge), the party
  view (narration presentation), the creation progress builders
  (`genesis.creation_progress`), and a frozen copy of the v6 companion
  normalization inside the v5 -> v6 save migration.

Moving the legacy game loop out of `foundation.core` showed that it and 116
modules reachable only through it (19,700 lines), and later the simulation
sandbox (`world.simulation`), were never reached by a production entry point;
they were deleted with the tests that only exercised them (owner decision).
Production boot imports fell from 2,073 to 1,965 modules.

**Not done:** contract-only imports. Only `world` and `genesis` have a
`contracts` module, holding the ports above; other cross-context imports still
name the module they need. Routing every cross-context import through a
contracts module is a separate, much larger change and is not enforced.

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
   then go through contracts only. (As built: contexts are packages and AL017
   is 0, but only `world` and `genesis` have a `contracts` module, for their
   ports; contract-only imports are not enforced. See "Not done" above.)

Acceptance (from the roadmap): RPG has 15 or fewer top-level entries, the
`rpg-production-turn` golden and the 50-turn replay are unchanged, and the
AL017 baseline is 0.
