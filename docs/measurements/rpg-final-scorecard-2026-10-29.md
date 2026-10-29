# RPG production scorecard: final (RQ-9.4), 2026-10-29

This is the production roadmap's closing scorecard
([RPG_PRODUCTION_ROADMAP_2026-10-23.md](../RPG_PRODUCTION_ROADMAP_2026-10-23.md) §2 for the targets, §6 for the
gates). Each area is graded as §2 defines:

- **Weak:** known defects in normal play.
- **Fair:** works on the tested path.
- **Strong:** meets every measurable target, gated.
- **Excellent:** Strong, plus the stretch target.

Every number below was measured on 2026-10-29 unless it says otherwise. The code measured is `rpg-production` at the
revision each row names; the static counts are at `e9c958f90d`.

**Result.** Twelve of the nineteen areas are Strong or Excellent; seven are Fair. RQ-9.4's bar, every area Strong
or better, is not met. Of the seven:

- **Waiting only on the owner:** G1 (the rubric), U1 (the unaided run), M2 (the 11 disputed labels are its whole
  false-stateful rate; every other M2 target is met), and M1 (whether Vesper-9's three scenarios apply to a world
  written only as lore).
- **N1:** correct speaker is short of its bound. Its main cause is fixed in `e9c958f90d`; the next narration run
  measures it.
- **F2:** 22 statements per turn against 20; the time targets are met.
- **F1:** model time. Evolution roadmap EV-7 carries it, and EV-9 (the model reads every line) resets its speech-turn
  targets.

## By area

| # | Area | Grade | Evidence | What keeps it from the next grade |
|---|------|-------|----------|-----------------------------------|
| A1 | Between contexts | Strong | AL017 0; contract-bypass imports 614, against 929 at the roadmap's start (the ratchet); the 2026-10-29 rise to 623 was undone the same day (`97b262c215`). `rpg-scorecard-2026-10-29.json` | Contract-only imports are not enforced for every context (stretch) |
| A2 | Inside the turn | Strong | One pipeline; AL018, AL019 and AL020 at 0; architecture lint: no RPG findings at `c87fa4bd90` | — |
| A3 | Mechanic ownership | Strong | `test_mechanic_owners.py` passes in the full suite | — |
| A4 | Content in code | Strong | World-specific names in the engine: 0 (AL021; scorecard `rpg_world_specific_names` 0) | — |
| P1 | Persistence | Excellent | Crash mid-turn test; versioned, pinned upgrades (document version 11, `session/upgrades/hidden_truths.py`); newer documents refused; campaign export and import (stretch). Persistence suites pass | — |
| M1 | Mechanics | Fair | Full RPG suite passes at `e9c958f90d`. Playthrough suite: every scenario passes except Vesper-9's three strict xfails (no economy and no one to join the hero in a world written only as lore). Published-world golden matches; every diff today was document hashes only, explained in its commit. Aurelia played to its end by hand (176 turns) | The three Vesper-9 xfails. Either Vesper-9 gets authored play sections, or those scenarios are declared not to apply to a lore-only world (evolution roadmap §7, question 9) |
| M2 | Intent | Fair | Frozen held-out set, 1,200 items, at `e9c958f90d`: action family 0.975, lower 0.965 (met); target entity 0.980, lower 0.969 (met); false stateful 1.22%, upper 2.17%. `rpg-intent-route-2026-10-29b.json` (at `9818f0e5e9` the target lower was 0.943: `rpg-intent-route-2026-10-29.json`) | False stateful upper 1.0%. All 11 false-stateful items are labels for the owner: deeds labelled not stateful ([label review](rpg-intent-label-review-2026-10-26.md)). With them relabelled, the rate is 0 |
| G1 | Gameplay depth | Fair | RQ-5.1-5.4 and 5.7 built, and 5.5 and 5.6 too; the balance simulation inside its bands (Aurelia since its bestiary numbers); stepped quests, gear, loot and an authored economy in Aurelia | The owner's rubric (RQ-9.2): [playtest-rq-9.2.md](../rpg/playtest-rq-9.2.md) is blank |
| W1 | Evolving world | Strong | The 200-turn Aurelia run's checks all pass (`rpg-living-world-2026-10-26.json`) | Measured 2026-10-26; Aurelia's content has grown since (two people with routines), so a rerun would confirm it |
| D1 | Determinism | Strong | AL013 0 on the turn path; the 1,000-turn replay identical (`rpg-living-world-1000-2026-10-26.json`) | Measured 2026-10-26, before document version 11 |
| F1 | Latency | Fair | Deterministic turns (status, wait, tactical moves) complete at p95 ≤ 230 ms with no model call (met). Turns with a model call: complete p50 6.1-7.7 s, p95 8.2-10.6 s; first narration p95 5.0-6.1 s; a question's outcome p95 8.2 s. `rpg-latency-route-stream-sonnet-low-2026-10-29.json` at `e3a277655d` | Model time. First narration p95 was 2.2-2.3 s at `8d90136347` with the same model, and the narration gate's dialogue turns are about 1 s slower at the median than on 2026-10-26. That is either the service's variance or the dialogue prompt's growth since (common knowledge, the hero's quests); these runs cannot tell the two apart. Another Claude Code session was running during the measurement. Evolution roadmap EV-7 |
| F2 | Turn overhead | Fair | 200 player turns per size on a quiet machine at `e9c958f90d`: p95 146.5 ms at 100 KB and 148.1 ms at 1 MB (met; 189.4 ms at 1 MB on 2026-10-26); world-tick turns p95 101 ms (return) and 162 ms (a 24-hour wait), against 500 ms. `rpg-turn-overhead-2026-10-29.json` | Statements per player turn p95 22, against 20. By command (40 turns at 100 KB): talk and travel 20, a wait 20-21, a look and a buy 22. A narrated look or buy checks its scene lore is current (one statement) and then reads the whole campaign bible again for the narrator's evidence (a second). The fix is to build the evidence from the bible the check already confirmed; it changes which copy the evidence is drawn from, so it needs the narration golden's explained diff |
| F3 | Model calls | Strong | 99.4% of turns make at most one call; deterministic turns none; none over two (latency file above) | — |
| U1 | Play screen | Fair | Eleven core tasks pass at 360 and 1,440 px, axe 0 serious or critical (`rpg-core-tasks-2026-10-25.json`) | The owner completing every core task unaided |
| U2 | Web code health | Strong | No RPG web file over 600 lines (scorecard `rpg_web_files_over_600_lines` 0) | — |
| N1 | Narration | Fair | 900 narrated turns, judged, run begun at `9818f0e5e9`: state contradictions upper 0.63% (stretch met); near-duplicates 0.2%; private canon leaks 0; correct speaker 0.942, lower 0.922. `rpg-narration-2026-10-29.json` | Correct speaker lower 0.985. Most misses were a question put to someone by name first, answered by another; fixed in `e9c958f90d`, not yet re-measured. Grounded (judge lower 0.82) is not gated until the owner's 150 calibration labels |
| S1 | Trust and safety | Strong | Injection corpus, SVG and CSP, model budget, tenant isolation and retention, all built and tested. 2026-10-29: one filter keeps every world secret out of what is shown or sent (`rules/secrets.py`); no private canon leaks in N1 | — |
| O1 | Operability | Strong | Operations view, outage behaviour and crash mid-turn built (§11). Route autoplay: 0 failures (2026-10-26) | The narration gate had 5 failed turns of 900 (0.56%), all one cause, fixed in `e9c958f90d` |
| T1 | Tests | Strong | Every §6 harness exists and ran for this scorecard. Full RPG suite passes at `e9c958f90d` | — |

## Since the roadmap began

| Area | Baseline (2026-10-23) | Now |
|------|-----------------------|-----|
| A2 | Weak: 132 + 144 untyped state keys read by string; three nested turn layers | Strong: one pipeline, a reducer, lints at 0 |
| A3 | Weak: three combat paths, two inventories | Strong: one owner per mechanic |
| A4 | Weak: "Bran" in 46 engine files | Strong: 0 |
| M1 | Fair: bugs found only in live play | Fair: a playthrough suite, a golden, autoplay; three xfails left |
| M2 | Weak: 83 word lists, substring defects | Fair: family lower 0.965, target lower 0.969; false stateful only the owner's labels |
| G1 | Weak: quests advanced by reaching places only | Fair: stepped quests, checks, gear, economy, companions; the rubric unscored |
| W1 | Weak: no routines or pressures in published worlds | Strong |
| F2 | 296 ms p95 at 100 KB, 352 ms at 1 MB, 44 statements | 146.5 ms at 100 KB, 148.1 ms at 1 MB, 22 statements |
| N1 | Not measured | Fair: contradictions upper 0.63%, near-duplicates 0.2% |

## Waiting on the owner

- The RQ-9.2 playtest: two hours, two worlds, scored on the rubric (G1, U1).
- The 150 calibration labels for the N1 judge.
- The 22 disputed intent labels ([label review](rpg-intent-label-review-2026-10-26.md)): M2's false-stateful rate and
  11 of its target misses.
- Whether Vesper-9's three scenarios apply to a world written only as lore (M1).
- Permission to run the web typecheck.
