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
| M2 Intent | Family and target lower ≥ 0.95; false stateful upper ≤ 1.0% | Family lower 0.975; target lower 0.943 (39 misses of 919, 11 of them the Mira label question); false stateful upper 2.17% (all 11 label questions) | Family met; target and false stateful not met. The target misses' classes are fixed since (rerun pending) | `rpg-intent-route-2026-10-29.json` (at `9818f0e5e9`); [label review](../measurements/rpg-intent-label-review-2026-10-26.md) |
| G1 Gameplay depth | RQ-5.1-5.4 and 5.7 built; balance bands; rubric ≥ 4 on stakes, choice, progression | All built (5.5 and 5.6 too); rubric not scored | Waits on owner | [playtest-rq-9.2.md](playtest-rq-9.2.md) is blank |
| W1 Evolving world | The 200-turn Aurelia run's checks | All pass | Met | `rpg-living-world-2026-10-26.json` |
| D1 Determinism | AL013 = 0; 1,000-turn replay identical | Both | Met | `rpg-living-world-1000-2026-10-26.json` |
| F1 Latency | Complete p50 ≤ 6 s, p95 ≤ 10 s; first narration p95 ≤ 2.5 s; intent turn outcome p95 ≤ 3.0 s; deterministic ≤ 500 ms | p95 5.7-7.2 s; first narration 2.2-2.3 s; deterministic ≤ 105 ms; arrive p50 6.5 s; question 3.3 s | Two misses: arrive p50, question | `rpg-latency-route-stream-sonnet-low-2026-10-26.json` (at `8d90136347`) |
| F2 Turn overhead | Player turn p95 ≤ 150 ms at 1 MB; ≤ 20 statements | 146.8 ms at 100 KB, 189.4 ms at 1 MB; statements p95 22 | Not met; rerun pending | `rpg-turn-overhead-2026-10-26.json` (at `340299b33a`, before F2 part 3) |
| F3 Model calls | ≥ 80% of turns ≤ 1 call; deterministic 0; none > 2 | 100% ≤ 1; deterministic 0; max 1 | Met | latency file above |
| U1 Play screen | Player-first layout; core tasks; axe 0 serious; 360 px; keyboard | 11 core tasks pass at 360 and 1,440 px, axe 0 | Met, except the owner's unaided run | `rpg-core-tasks-2026-10-25.json` |
| U2 Web code health | No RPG web file over 600 lines; one stylesheet per component | 0 files over 600 | Met (§11) | RQ-7.5 |
| N1 Narration | Contradictions upper ≤ 2.0%; speaker lower ≥ 0.985; grounded lower ≥ 0.93 (calibrated judge); near-duplicates ≤ 5% | Contradictions 0.6%; speaker 0.871; near-duplicates 35%; judge not calibrated | Not met; rerun pending | `rpg-narration-2026-10-26.json` (at `6797790065`, before the eval fix in `cb70b4792d`) |
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
and engine warden by day), and the phone's voice named (the Unfinished Call). Its author files are
`lore-additions.json` and `play-sections.json`
([playtest-aurelia-2026-10-26.md](playtest-aurelia-2026-10-26.md#content-added-afterwards-2026-10-29)). Still open
there: Orik's "one free night" for new arrivals is charged; Valecourt and Cinderhold have no maps.

## Proposed, not decided

Raised in review on 2026-10-26; none is a work package yet.

- **A shared rules core.** Attribute modifiers, rolls and condition penalties are computed separately in
  `rules/checks.py`, `rules/combat/fight.py` and `rules/player/progression.py`, and they disagree (a weak hero is
  penalized on a check but not on an attack). Also: party and quests have no rule module of their own
  (`rules/player/requests.py` holds both).
- **Travel time in play.** In route autoplay, travel is the most common action and the slowest: p50 12-14 s,
  against 6.5 s for "arrive" in the latency harness.

From the full Aurelia campaign (2026-10-29), in the order proposed. The plan, with its weaknesses, gates and the
owner's questions, is [RPG_EVOLUTION_ROADMAP_2026-10-29.md](../RPG_EVOLUTION_ROADMAP_2026-10-29.md), for review:

- **Consequences.** A decision writes facts other rules read (faction standing, a person's attitude or place,
  prices, quests opened or closed, a place changed), and an ending's epilogue is told from them. Today a choice ends
  in its telling and a remembered fact.
- **Combat depth and pacing.** Abilities by calling, resistances and the lore's weaknesses usable in a fight,
  companion commands, boss phases. The Hollow Archon took some 40 rounds of attack-and-drink.
- **The model reads every typed line; cards are commands** (EV-9, owner decision 2026-10-29, phase 0). The command
  grammar turns idioms into actions ("give it a rest" rests the hero; 16 of 32 idioms tried). It is removed. Cards
  carry their action. Speech takes two calls, in parallel in a conversation under way. With no model, only the cards
  work.
- **Steps judged by what was meant.** A talk step matches its `about` words; the reading should propose which step a
  line addresses, and deterministic code accept it when speaker, place and step fit.
- **People who act on their goals.** A few deterministic goal events a day, told as rumours and written as facts.
- **Crafting.** Shards and a smith make better gear: loot, purse and progression tied together.
- **Authoring in the editor.** Forms for an item's gear and for characters with a home; World Forge drafting play
  sections, not only lore.
- **Sites to discover** (EV-10). Play adds no place, person, kind of creature or item, quest or lore today. The game
  master prepares hidden sites ahead (a cave, a ruin, a dungeon), exploring finds them by a seeded check, and code
  builds their rooms, encounters and loot inside the level's budgets. Every invention carries its play data; it joins
  the campaign's lore at once and the world's only on the author's approval.
