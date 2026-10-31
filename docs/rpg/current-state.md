# RPG: current state

As of 2026-10-29, branch `rpg-production` after `dfa6815f9e` (with Aurelia's gear and Valecourt content). This page holds only the latest state: each gate's
number, what is open and who it waits on. The history behind each line is in the roadmap's status log
([§11](../RPG_PRODUCTION_ROADMAP_2026-10-23.md#11-status)); the targets are its scorecard (§2).

## Where it stands

Every work package through RQ-9.1 has an entry in the status log. What remains is the production gate (RQ-9.2-9.4): the owner's
playtest, and the measured gates still short of their targets (M2, N1, F2, and two F1 classes). Engineering
playtests continue to find content and wiring problems, not missing systems
([playtest-aurelia-2026-10-26.md](playtest-aurelia-2026-10-26.md)).

## Gates

"Met (§11)" means taken from the status log, not re-run for this page.

| Area | Target (Strong) | Now | Status | Source |
|------|-----------------|-----|--------|--------|
| A1 Between contexts | AL017 = 0; contract-bypass imports only shrink | AL017 0; contract-bypass imports 614 (910 at baseline) | Met | `docs/measurements/rpg-scorecard-2026-10-26.json` |
| A2 Inside the turn | One pipeline; AL018, AL019, AL020 at 0; no string-key state reads on the turn path | All 0 | Met (§11) | RQ-1.5 done; A2 field reads |
| A3 Mechanic ownership | One owner per mechanic, checked by a registry test | `test_mechanic_owners.py` | Met (§11) | RQ-2.9 |
| A4 Content in code | No world's names in the engine (AL021) | 0 | Met (§11) | A4 part 2 |
| P1 Persistence | Crash-mid-turn test; versioned, pinned upgrades; newer documents refused | Built, and export/import (stretch) | Met (§11) | RQ-8.5, RQ-1.1, RQ-1.7, RQ-8.6 |
| M1 Mechanics | Playthrough suite 100% on three worlds; golden matches | Playthrough: 133 pass, 4 strict xfail (below). Golden: matches at `835946e514`. Route autoplay 3 x 150 turns, 0 findings | Open (the xfails) | Playthrough run 2026-10-26 on a working tree with uncommitted RPG changes; `rpg-autoplay-2026-10-26-route.json` |
| M2 Intent | Family and target lower ≥ 0.95; false stateful upper ≤ 1.0% | Since EV-9 the model reads every line: family lower 0.868, target lower 0.867, false stateful upper 1.5% (2026-10-31, Sonnet low; Haiku low 0.798, 0.809, 1.5%). The first EV-9 run read 0.783 and 0.774: a question none of whose readings could be done was a free action, and a status aimed at a quest lost its reading (both fixed) | Not met. Left: questions and remarks played as free actions, travel asked back; to be tuned on the dev split | `rpg-intent-route-2026-10-31.json`, `rpg-intent-route-haiku-low-2026-10-31.json` |
| G1 Gameplay depth | RQ-5.1-5.4 and 5.7 built; balance bands; rubric ≥ 4 on stakes, choice, progression | All built (5.5 and 5.6 too); rubric not scored | Waits on owner | [playtest-rq-9.2.md](playtest-rq-9.2.md) is blank |
| W1 Evolving world | The 200-turn Aurelia run's checks | All pass | Met | `rpg-living-world-2026-10-26.json` |
| D1 Determinism | AL013 = 0; 1,000-turn replay identical | Both, and re-executed (2026-10-31) | Met | `rpg-living-world-1000-reexecuted-2026-10-31.json` |
| F1 Latency | Typed turns (owner, 2026-10-31): first narration p95 ≤ 5 s, complete p50 ≤ 9 s, p95 ≤ 10 s; the outcome with an intent call p95 ≤ 3.0 s; cards and the tactical route ≤ 500 ms, no call | A narrated typed turn makes two calls in turn: first narration p95 4.5-4.7 s; complete p50 7.5-9.3 s, p95 8.3-9.9 s; outcome p95 2.2-2.5 s; the tactical route 88 ms (2026-10-31, Sonnet low; Haiku low is slower, its writer thinks) | Met but an arrival's complete p50 (9.3 s) | `rpg-latency-route-stream-sonnet-low-2026-10-31.json` |
| F2 Turn overhead | Player turn p95 ≤ 150 ms at 1 MB; ≤ 20 statements | 123.6 ms at 100 KB, 130.7 ms at 1 MB; statements p50 21, p95 24 (2026-10-31; 21 and 22 before the evolution roadmap). The evolution roadmap adds one every turn (the pending proposals, EV-11) and three for each game-master job an arrival queues (EV-0, EV-10) | Time met; statements not met | `rpg-turn-overhead-2026-10-31.json` |
| F3 Model calls | No turn more than two calls, but for one revision of its narration; cards and the tactical route none (owner decisions 2026-10-29) | Most two; four of 160 Haiku turns revised once; deterministic 0 (2026-10-31) | Met | the F1 runs above |
| U1 Play screen | Player-first layout; core tasks; axe 0 serious; 360 px; keyboard | 11 core tasks pass at 360 and 1,440 px, axe 0 | Met, except the owner's unaided run | `rpg-core-tasks-2026-10-25.json` |
| U2 Web code health | No RPG web file over 600 lines; one stylesheet per component | 0 files over 600 | Met (§11) | RQ-7.5 |
| N1 Narration | Contradictions upper ≤ 2.0%; speaker lower ≥ 0.985; grounded lower ≥ 0.93 (calibrated judge); near-duplicates ≤ 5% | 900 turns over three worlds (2026-10-31, Sonnet low): contradictions upper 0.6%; speaker lower 0.961 (19 of 744 wrong: a line to someone read as a look, a person named by what they do read as no one or the wrong one); near-duplicates 0.45%; grounded lower 0.84 by the uncalibrated judge. Four turns failed with a server error, a look at someone away (fixed, `test_absent_people.py`) | Contradictions and near-duplicates met; speaker not met | `rpg-narration-2026-10-31.json` |
| S1 Trust and safety | Injection corpus, SVG/CSP, model budget, tenant isolation, retention | All built | Met (§11) | RQ-3.4/8.1, 8.7, 8.2, 8.3, 8.10 |
| O1 Operability | Failure ≤ 0.5%; operations view; outage behaviour; crash mid-turn | Built; autoplay 0 failures | Met (§11) | RQ-8.4, 8.8, 8.5 |
| T1 Tests | Every §6 harness exists and is in the gate set | Yes | Met (§11) | §6 |

The four strict xfails in the playthrough suite:
- Vesper-9 is a lore-only world: no one written to join the hero, and no economy, so no shop or inn (3 scenarios).
- Aurelia: asking Miri Kestrel for work offers no quest (`test_an_npc_offers_a_quest_in_conversation`). This
  still fails after `02627d2e21`, which let people who hand out work offer quests: check whether the scenario or
  the rule is behind.

## Waiting on the owner

- The RQ-9.2 playtest: two hours, two worlds, scored on the rubric. G1 depends on it.
- The 150 calibration labels for the N1 judge (grounded is not gated until then).
- A spot check of the intent held-out set's labels: most of M2's remaining misses are label questions
  ([rpg-intent-label-review-2026-10-26.md](../measurements/rpg-intent-label-review-2026-10-26.md): 22 items).
- Permission to run the web typecheck.
- Publishing Aurelia's new bundle to the community world catalog.
- The LM Studio World Forge run, at the very end.

## Open engineering work

- Rerun F2 after `9f5c9e3b46` (one campaign read a turn) on a quiet machine; 1 MB p95 and statements are over.
- Rerun N1 after the eval fix; near-duplicates (35%) and the correct speaker are the gaps.
- Rerun M2 once the labels are checked (and for the lore-world reading in `46fb76145c`, not yet measured).
- F1: arrive p50 (6.5 s against 6 s) and a question's outcome (3.3 s against 3.0 s).
- Vesper-9's conversations copy its large bible three times a turn; the fix is one read-only view per canon
  revision (§11, F2 memo). Not done.
- RQ-9.3 documentation exists in `docs/rpg/`; RQ-9.4, the final scorecard, is not written.

## Content

Aurelia is the complete world: six stepped quests with ways and tellings, an authored economy (weapons and armour at
Captain Rhea's and at Hollis Brask's forge in Valecourt; the Ashen Oathblade as the bridge quest's reward; Aether
Shards dropped by Echoes and bought back), twelve people with days and knowledge (Valecourt has its foundry master
and engine warden by day), and the phone's voice named (the Unfinished Call). Its people and items are its bundle's topics, as the editor
edits them; its author files are `lore-additions.json` (the game master's palette and maps) and `play-sections.json`
([playtest-aurelia-2026-10-26.md](playtest-aurelia-2026-10-26.md#content-added-afterwards-2026-10-29)). Orik's "one free night" for new arrivals is now given (EV-1), and Valecourt and
Cinderhold have maps (EV-8).

## Proposed, not decided

Raised in review on 2026-10-26; none is a work package yet.

- **A shared rules core.** Attribute modifiers, rolls and condition penalties are computed separately in
  `rules/checks.py`, `rules/combat/fight.py` and `rules/player/progression.py`, and they disagree (a weak hero is
  penalized on a check but not on an attack). Also: party and quests have no rule module of their own
  (`rules/player/requests.py` holds both).
- **Travel time in play.** In route autoplay, travel is the most common action and the slowest: p50 12-14 s,
  against 6.5 s for "arrive" in the latency harness.

From the full Aurelia campaign (2026-10-29), in the order proposed. The plan, with its weaknesses, gates and the
owner's questions, is [RPG_EVOLUTION_ROADMAP_2026-10-29.md](../RPG_EVOLUTION_ROADMAP_2026-10-29.md); its section 8 logs
what landed and what of each gate is still to run. Every package is built (2026-10-30); the model-dependent gates
of all of them are not yet run. The campaign document is at version 17 (12: what the hero
knows; 13: the game master's bookkeeping; 14: goals' beats and rumours; 15: the lore layer; 16: areas and exploring;
17: gear tiers). Migrations 0187 to 0192 (proposals, the game master's panel, the lore review queue, the voice cast,
a campaign's own map definitions, the spoken-audio cache).

- **Consequences** (EV-1, built 2026-10-29). A decision writes facts other rules read (group standing, a person's
  whereabouts, prices, quests opened or closed, a place's line), and an ending's epilogue is told from them. The
  journal's "What has changed" tab shows them. Document version 12 adds the record of what the hero knows.
- **Combat depth and pacing** (EV-2, built 2026-10-29). Weaknesses usable in a fight, resistances, boss phases,
  no-escape finales, a boss left keeping part of its wounds, guarding another, companion orders, two starting
  abilities per calling, and the level budget table. Fight-length targets are measured, not yet held.
- **The model reads every typed line; cards are commands** (EV-9, built 2026-10-29). The command grammar is out of
  the engine (it is the scripted model's reader in tests); every typed line goes to the intent call, whose reading
  carries typed slots; no rule reads the player's words; every offered choice is a card. Speech takes two calls, the
  reply written beside the intent call in a conversation under way. With no model, only the cards work. Its
  model-dependent gates (idiom set, slots, M2, F1) are not yet run.
- **Steps judged by what was meant** (EV-3, built with EV-9). The reading names the step a line answers; code accepts
  it when the speaker and the open step fit. Its held-out gate is not yet run.
- **People who act on their goals** (EV-4, built 2026-10-30). Goals hold beats the daily tick advances, seeded
  (at most three a day); their word goes about as rumours, told when asked for news, sold as paid information, or
  heard by being there. Aurelia has eleven beats; the 200-turn gate run reaches at least eight and hears each.
- **Upgrades** (EV-5, built 2026-10-30). An `upgrade` service improves carried gear a tier for materials and coin,
  inside the level's budget: Hollis with Aether Shards, Brindle a weapon; a world's own weapon is improved as the
  kind it fights as. The balance simulation's player buys, wears and improves gear: Aurelia's coin spent rises and
  its gear at 500 turns beats its gear at 100 (gear 7 to 11, win rate 0.897); the bands pass.
- **Authoring in the editor** (EV-6, built 2026-10-30). The play-section form covers beats, facts set,
  consequences (`fact_effects`), combat depth and upgrades; the entity form an item's gear and a character's home,
  aliases and group; World Forge drafts quests' steps, beats and gear for sale; the review queue has its screen.
  a collection's heading adds an entry, kept where its topic keeps them. A world installed from a bundle now carries
  its editor's changes into play when published, and its entries can be edited at all (its topics' older draft was a
  conflict); adding one needed migration 0193. Aurelia's people and items are its bundle's topics; its
  `lore-additions.json` keeps the game master's palette and the maps. The web typecheck passes. Not run: a second
  world authored only in the editor.
- **Response time** (EV-7, built 2026-10-30). A long journey is one turn, stopping where a quest's place is reached
  or the road is barred; the scene's lore is built once per scene and canon; the arrival's local map is read while
  travel resolves. F1 is rerun: two calls in turn put every narrated class past it (the F1 row).
- **Content** (EV-8, built 2026-10-30). Valecourt and Cinderhold have maps (grids without artwork yet).
- **Areas filled in as the hero approaches** (EV-10, built 2026-10-30). Regions are filled in ahead, once a campaign,
  within a budget by size (a world's `gm_guide` palette; Aurelia has one for its five regions), a capped share a
  turn; `explore` finds hidden places by a seeded check; a site's rooms, encounters and reward are built by code and
  cleared in play; each room has its own grid (stored as the campaign's map definition) and some a hazard. The timed
  autoplay gate passes: every arrival of a 200-turn run found its area filled in (3 of 3), inside its budget; fills are
  queued at launch and for every area next to the hero's, ahead of the game master's direction.
- **The game master** (EV-0, built 2026-10-30). Part 1: it directs from a job after a turn (complications, facts, quest
  offers, moves, encounters, beats, rumours), each a proposal its owning rule folds in, within daily limits and never
  taking a protected person away; its panel answers from what the hero knows, changes nothing and withholds a secret.
  Part 2: it invents people, places, things, creatures and quests with their play data, played from the campaign's
  lore layer and filed for the world owner's review (question 15), approved into the next publication. Its proposal
  measures, the panel's question set and the consistency check's calibration are not run.
- **Names that open their lore** (EV-12, built 2026-10-30). Names in the story, the journal and a lore entry open
  the entry beside the story, read-only; the narrator marks what it names, the links are worked out on the final
  text, and a name the hero did not know is heard of by the next turn. The target and coverage samples and N1 are
  not rerun.
- **Voices** (EV-13, built 2026-10-30). The castable list (`resources/voice_clones/casting.json`; only two voices
  castable: the library's clones of real people and other works' characters are left off), a deterministic cast kept
  outside the document, the player's choice, quotes inside narration in their speaker's voice, a play button on each
  finished response, a Voices tab and auto-play off by default, spoken by sentence from a tenant-scoped audio cache.
  Not run: the speed, quote-sample and UI gates.
- **The proposal record** (EV-11, built 2026-10-29, migration 0187). Work done off the turn is a typed proposal; the
  next turn folds it in at its load through the rule that owns its kind, and its commit settles it exactly once and
  records it on the turn row. A rewind drops the undone timeline's pending proposals; the re-executing replay folds
  each turn in from its turn row's recorded set. The re-executing replay test passes.
