# RPG evolution roadmap (2026-10-29)

Status: **proposal, for review.** Nothing here is started. It follows the production roadmap
([RPG_PRODUCTION_ROADMAP_2026-10-23.md](RPG_PRODUCTION_ROADMAP_2026-10-23.md)). That roadmap made the game correct,
measured and maintainable. This one makes it deeper. Its evidence is the full Aurelia campaign
([playtest-aurelia-2026-10-26.md](rpg/playtest-aurelia-2026-10-26.md), session 3: 176 turns, all six quests,
level 7, the gate made a guarded bridge), the route autoplay runs, and the measured gates in
[current-state.md](rpg/current-state.md).

Section 7 lists the decisions the owner needs to make before any work package starts.

The game master (EV-0) sits above the other packages. A language-model game master directs the story: pacing,
consequences, events, people, and new content when the story needs it. Deterministic code keeps authority over what
is true and what it does. The other packages are the game master's tools as much as features of their own.

## 1. Main weaknesses

Ordered by how much each limits the game. Each names what the campaign showed and what the code does today.

### W-0. No one directs the story

- **Seen:** nothing in the campaign raised the stakes when play stalled, brought an earlier choice back, or answered
  something the author had not foreseen. The story moved only when the hero reached the next authored step.
- **In the code:** the model has two jobs: reading what the player means (intent) and phrasing what happened
  (narration and dialogue). Neither decides what should happen next.
  - The pieces a director would need exist but are unused for that: narration's typed proposals, folded in by the
    next turn and recorded so replay applies exactly the same set (production roadmap §4); a seeded event injector
    and agent scheduler (RQ-4.6); and Aurelia's `gm_guide` lore topic (opening beats, ending choices, tone
    controls), which nothing reads.
- **Why it matters:** W-1 and W-4 below are the symptoms. Authored content alone makes a story that is the same
  every time.

### W-1. Choices change little afterwards (the largest gap)

- **Seen:** Seraphine's engine was democratised. The step's telling was good, and dialogue remembered it. Nothing else
  changed: no faction standing, no prices, no one moved, no quest opened or closed, no greeting differed. The gate's
  fate was the same: one closing line, then the world went on as before.
- **In the code:** a way's `told` line (`rules/quest/progress.py`) is the whole of an outcome. There are 58 change
  types (`foundation/state/changes.py`), but none records a world fact or a group's standing. `RegardChanged` is per
  person only.
- **Why it matters:** a second campaign plays like the first. Choices are what make an RPG worth replaying.

### W-2. Combat is long and offers few choices

- **Seen:** the Hollow Archon (level 10, 120 health) took some 40 rounds of attacking and drinking potions (three).
  Ordinary fights had the same shape: trading blows until one side falls.
- **In the code:** the hero has abilities (`rules/ability_use.py`: an ability tree, cooldowns, a blow, a heal, a
  hinder), but few, and play rarely reaches for them. A creature's lore weakness is stored on its definition (Aurelia's
  "bells and contradictory commands", "name the oath it broke") but no fight reads it. Only a `recall_lore` check
  names it (`rules/checks.py`). Bosses are large health pools with no phases. The play section has no resistances.
- **Why it matters:** fights are most of the game's risk, and today they are a matter of patience, not decisions.

### W-3. Quest steps done by talking match words, not meaning

- **Seen:** "talk to Elyra about voice/phone/call/…" completes when one of those words is said. Phrasing it otherwise
  can miss the step. An unrelated line using a listed word can complete it.
- **In the code:** a `talk` condition's `about` list in the quests play section. The intent reading never proposes
  which step a line addresses.
- **Why it matters:** this is the most common kind of step in story quests. It is brittle for players, and authors
  have to guess word lists.

### W-4. People keep schedules but don't pursue their goals

- **Seen:** everyone keeps their day, but nothing they want ever moves forward. Rhea never exposes the traitor in
  the guard, and Brindle never finishes his radio to Earth. Nothing happens between two people unless the hero is
  involved.
- **In the code:** goals sit in each person's routine with a priority (`routines` play section) and shape what they
  talk about. No rule advances them. Pressures move the world as a whole (`rules/pressures.py`), but not its people.
- **Why it matters:** the world feels staged around the hero rather than alive.

### W-5. Response time

- **Measured:** arriving somewhere takes p50 6.5 s (target 6 s). A question's outcome takes p95 3.3 s (target 3.0 s).
  In route autoplay, travel is the most common and the slowest action, at p50 12-14 s.
- **Why it matters:** latency breaks the flow of play more than any single rule does.

### W-6. A world written only as lore plays thin

- **Seen:** Vesper-9, played from what launch infers, had one "Local news" offer, default numbers and no one to join
  the hero. Aurelia became good only after its own play data was written, and parts of that needed a script
  (`lore-additions.json`, this week).
- **In the code:** the world editor has no form for an item's slot and numbers, or for a character's home. World Forge
  drafts lore, but drafts play sections only partly (`draft_play_sections_from_lore`).
- **Why it matters:** the game's quality is capped by how hard a good world is to author.

### W-7. Money doesn't drive much

- **Seen:** until this week the only income was the first quest's 20 silver. Aether Shards as loot help now. There
  is still little to spend on mid-game: no upgrades, crafting, bribes, passage or property.
- **Why it matters:** loot, purse and gear should form a loop that rewards exploring and fighting.

### W-8. Smaller content and engine gaps

- Valecourt and Cinderhold have no maps.
- Orik's inn gives new arrivals "one free night" in its lore, but the economy charges for it. This needs W-1's facts.
- M2's target lower bound is 0.923 against 0.95. Most of the misses are label questions for the owner
  ([label review](measurements/rpg-intent-label-review-2026-10-26.md)).

## 2. Principles

The production roadmap's invariants hold for every work package here (AGENTS.md, RPG section):

- Every state change is a turn through the one pipeline, and a rule is pure.
- One owning rule per mechanic, registered in `PipelineMechanic`, `MECHANIC_OWNERS` and `CHANGE_WRITES`.
- Model output is a proposal; deterministic code decides.
- A change to the stored shape is a new document version, with its upgrade.
- No world's names in the engine. What a world does is data in its play sections.
- No unseeded randomness on the turn path.

Three more for this roadmap:

- **The game master proposes; code decides.** The game master chooses what should happen and why. Deterministic code
  checks that it can happen and works out what it does. The game master never writes state, rolls dice, or sets a
  reward or a blow directly. Its proposals are recorded, so a campaign replays to the same state (D1).

- **Data over code.** Each new mechanic is something an author writes in a play section, with a sensible derived
  default for a world that writes nothing.
- **Visible change.** A consequence that the player cannot see or feel does not count. Each package names what the
  player sees.

## 3. Work packages

Each package lists its problem, its design, what changes in the stored state, its gate and its rough size: S (days),
M (one to two weeks) or L (two weeks or more).

### EV-0. The game master (W-0, and through the others W-1, W-4, W-6) — L, in two parts

**Role.** A language-model game master that directs the campaign:

- **Pacing:** it notices a stall (turns without a meaningful event, a step not advanced) and adds a complication or an
  opportunity.
- **Consequences:** it brings a past choice back at the right moment, and decides how the world answers an action no
  author foresaw.
- **Events:** it moves people toward their goals, sets encounters, and spreads rumours.
- **Threads:** it keeps track of open threads (an unkept promise, a spared enemy, a companion's own goal) and gives
  each a turn in the spotlight.
- **Invention:** it creates new named people, places, items, creatures and quests when the story needs them
  (part 2).

**When it runs.** At scene boundaries, while travel resolves, on the daily world tick, and when play stalls; never
on every turn. A direction call is off the turn's critical path. Its proposals are folded into the next turn, as
narration's are today. That keeps the F3 target (at most one model call on 80% of turns) and does not add latency.

**What it reads.**

- the campaign's state;
- the world facts (EV-1);
- open threads;
- the people's goals and beats (EV-4);
- the world's `gm_guide` (opening beats, ending choices, tone controls);
- the author's play sections, as its palette and its limits.

World text is untrusted data in its prompt, and no speaker's secret is sent to it.

**What it may propose.** A closed set of typed proposals, each with the reason it gives:

- set a fact, or bring a consequence forward;
- advance a person's goal by a beat, or move a person;
- start an encounter from the bestiary, sized to the hero's level;
- spread a rumour, or add a complication to the current scene;
- offer a quest, from the canon or from templates;
- (part 2) invent a person, place, item, creature or quest.

**What code checks before a proposal is committed.**

- Every reference exists, and no fact the proposal sets contradicts one that holds.
- Danger and rewards stay inside the level's budgets.
- No secret is revealed.
- The daily limits hold: at most so many events a day, and at most one complication a scene.
- An invention follows the rules below.

A proposal that fails a check is dropped and logged, and shows in the measures.

**Part 1: direct and improvise** with what the world contains.

**Part 2: invent.** Owner decision (2026-10-29): the game master may invent, and each invention is added to the lore,
for a permanent record and a consistency review.

- An invention is a typed lore entry: a person, place, item, creature or quest, in the shape the lore topics already
  use. It carries its provenance: the campaign, the turn, and the game master's reason.
- **Checks before it is played:**
  - its id is new and its name does not clash with the canon's;
  - its references exist;
  - its numbers sit inside the level's budgets;
  - it contradicts no established fact;
  - a place joins the roads like any other.
- **The record.** On commit, the entry is added to the campaign's lore layer. It is played at once, kept with the
  campaign, and replays exactly. It is also filed with the world as a lore draft from the game master, which an
  author reviews.
- **The review.**
  - A model consistency check runs first. It compares the entry with the canon and reports its findings as
    evidence, not as a verdict.
  - The author then approves the entry into the world's lore, edits it, or rejects it.
  - An approved entry joins the world's lore for future campaigns, through the world library's publication like any
    edit.
  - A rejected one stays in the campaign that met it, and is never offered to another.
- The world editor gains a review queue for these drafts (with EV-6).

**State and versions.** Part 1 needs no new state beyond EV-1's facts and EV-4's beats; its proposals are a new
proposal kind. Part 2 adds a campaign lore layer, which is a new document version with its upgrade, and the world's
review queue, which is a migration.

**Gate.**

- Proposal measures over route autoplay and a judged run:
  - share of proposals accepted;
  - contradictions with established facts among accepted proposals: upper bound ≤ 1%;
  - turns between meaningful events: a ceiling, set from the rubric playtests;
  - direction calls per hour of play, and their cost.
- Part 2:
  - every invention is in the campaign's lore layer and in the review queue;
  - none clashes with the canon by id or name;
  - the consistency check's findings are calibrated on labelled examples, as the N1 judge is.
- The 1,000-turn replay stays identical with the game master on (D1).
- The owner's playtest rubric for stakes and choice.

**Model.** The direction calls use the reference model at a higher effort than narration's. The cost per hour of play
is measured and reported.

### EV-1. Consequences: facts the world remembers and rules read (W-1, W-8) — L

EV-1 is the record the game master writes to and reads from. Authored consequences are its palette.

**Design.**

- A campaign holds **world facts**: named values (`engine_fate = council`, `oathblade_borne = true`) in a new state
  section.
- One new change type, `FactSet(fact_id, value, source)`, owned by a new pure rule, `rules/consequences.py`.
- Facts are written by a quest step's way (an authored `sets: [{fact, value}]` beside its `told`), by an ending, and
  by a check or fight outcome where the author says so.
- A new play section, `consequences`, says what facts change. Each entry is a condition on facts plus one effect,
  read by the rule that already owns that mechanic:
  - **Prices:** a seller's or region's price modifier (`rules/economy/trade.py`). Orik's free first night is a
    one-time waiver while `new_arrival` holds.
  - **Group standing:** a group's standing with the hero moves. Dialogue's stance reads it alongside personal regard.
    Membership comes from the lore, or is declared by the author where the lore is silent.
  - **Whereabouts:** a person's routine is replaced or ended (`rules/routines.py`).
  - **Quests:** a quest opens or closes (`requires` / `forbids` facts).
  - **Places:** a line is added to a place's description, or a service opens or closes there.
  - **Pressures:** a pressure's lever is pushed (`rules/pressures.py`).
- **Endings get an epilogue:** a finale's way names the facts to tell. Deterministic code picks an authored line for
  each fact that holds, the narrator phrases them, and the claim checker holds the phrasing to them.
- **The player sees** a "What has changed" entry in the journal for each fact that holds, plus the effects
  themselves: a price, a greeting, a person who is gone, a quest offered.

**State:** a new document version (a `world_facts` section and a group-standing entry), with its upgrade.

**Aurelia:** facts and consequences for every decision step: the engine's fate, the vow kept, the memory restored,
the gate's fate. Plus Orik's free night.

**Gate:**
- A consequence playthrough: each of Aurelia's decisions produces three or more observable differences in the
  following 20 turns, asserted in the playthrough suite.
- The golden diff is explained.
- The 1,000-turn replay stays identical (D1).

### EV-2. Combat depth and pacing (W-2) — L

**Design.**

- **Weaknesses that work.** An action that uses a creature's weakness ("I ring the bell", "I strike with unpolished
  iron", "I name the oath it broke") triggers the stored vulnerability: a stun, a damage bonus or a morale break.
  The grammar reads the weakness's aliases, which are stored already.
- **Abilities by calling.** Each calling starts with two abilities and learns more at levels from the existing tree.
  The suggestions and the play screen surface abilities that are ready to use.
- **Defend and guard** become actions. A guarded companion takes the blow.
- **Companion orders in a fight:** "Liora, flank it", "Vael, guard me". This extends `CompanionOrdered`.
- **Creature resistances and boss phases** in the bestiary section: `resists` tags, and `phases` as health thresholds
  that change behaviour or numbers, call allies, or expose the weakness.
- **Pacing targets**, set in the balance simulation: an ordinary fight lasts 3-5 rounds and a boss 8-12; potions are
  used on fewer than a quarter of a boss fight's turns.

**State:** new change types for a phase entered and a guard set. Possibly no document version, if both stay inside the
combat section.

**Aurelia:** every creature's weakness made usable, the Archon in three phases, Echoes resisting plain steel.

**Gate:**
- Balance bands per world, including fight length.
- A scripted fight of each kind in the playthrough suite.
- The rubric's stakes and choice scores, at the owner's playtest.

### EV-3. Quest steps judged by meaning (W-3) — M

**Design.**

- The intent reading, which already runs on a spoken turn, may propose the open step a line addresses
  (`quest_id`, `step_id`).
- Deterministic code accepts the proposal only when four things hold:
  - the speaker is the step's subject;
  - the place fits;
  - the step is open;
  - the line names the step's subject or one of its `about` words' families.
- Without a proposal, today's word match still applies.
- A false completion is worse than a miss, so precision is gated higher than recall.

**Gate:**
- A new held-out set of about 200 lines per world, with labelled steps: precision ≥ 0.98, recall ≥ 0.90.
- The intent prompt's version is bumped, and M2 is rerun, since the prompt changes.

### EV-4. People who act on their goals (W-4) — L (needs EV-1)

Authored beats are the default, and the game master (EV-0) chooses which to advance and when. With the game master
off, the seeded daily tick advances them as below.

**Design.**

- A goal in the routines section may hold **beats**: ordered steps toward it, each with a chance per day, a
  condition (facts, a place, the time) and its effects (facts set, a move, a rumour).
  - Example: Rhea suspects the guard; then names the traitor; then the traitor flees to Cinderhold.
- The daily world tick, which is deterministic and seeded by purpose, advances at most a few beats a day.
- The hero hears of a beat through rumours (paid information), conversation and the journal. Where the author offers
  one, the hero can step in through a quest the beat opens.

**Gate:**
- A 200-turn run: at least eight beats seen, each told to the hero at least once.
- The W1 checks still pass.
- The 1,000-turn replay is identical.

### EV-5. Upgrades and crafting (W-7) — M

**Design.**

- A new service kind, `upgrade`: a seller improves an item the hero carries by one tier, for materials and coin.
- Recipes are authored in the economy section. Tiers are bounded and add to the item's stats.
- One new change type, `ItemImproved`.
- Then decide whether to go further with full recipes (owner question 7).

**Aurelia:** Hollis improves a blade or armour with Aether Shards. Brindle tunes the Arc Baton.

**Gate:** the balance simulation's purse and gear bands. The purse rises and is spent, and level-7 gear is better
than level-2 gear.

### EV-6. Authoring in the editor (W-6) — M

**Design.**

- **World editor forms:**
  - an item's gear (slot and numbers);
  - a character's home, aliases and group;
  - a quest's rewards and a way's `sets`;
  - the `consequences` section;
  - the bestiary's phases and resistances.
- A review queue for the game master's inventions (EV-0 part 2). Each shows its provenance and the consistency
  check's findings, with approve, edit and reject.
- World Forge drafts every play section from the lore, not only some: quests' steps, knowledge, the economy with
  gear, routines with beats.
- `lore-additions.json` becomes unnecessary for Aurelia: the same edits go through the editor's entity authoring
  (`entity_authoring.update_world_entity`).

**Needs:** the owner's permission to run the web typecheck. The LM Studio World Forge run belongs here.

**Gate:**
- A world authored only in the editor plays at Aurelia's depth: the playthrough suite's scenarios pass on it.
- The web build passes.
- The core-task UI checks pass.

### EV-7. Response time (W-5) — M

**Design.**

- Prepare the arrival scene's deterministic facts while travel resolves.
- Stream narration from the first sentence.
- Cache scene lore per place, time of day and canon revision.
- Make a long journey one turn with interruptions, not several.

**Gate:** F1 met in every class (arrive p50 ≤ 6 s, a question's outcome p95 ≤ 3.0 s), and travel p50 ≤ 8 s in route
autoplay.

### EV-8. Content (W-8) — S each

- Maps for Valecourt and Cinderhold.
- Orik's free night, once EV-1 exists.
- Vesper-9 given authored play sections, or retired as a showcase (owner question 9).

## 4. Order and lanes

| Phase | Lane A | Lane B | Ends when |
|------|--------|--------|-----------|
| 0 | Close the production roadmap: RQ-9.2-9.4, the M2/N1/F1/F2 reruns | — | The final scorecard is written |
| 1 | EV-1 Consequences | EV-2 Combat | Both gates pass on Aurelia |
| 2 | EV-0 part 1: the game master directs and improvises (on EV-1) | EV-3 Steps by meaning | Both gates pass; M2 rerun |
| 3 | EV-4 People's goals, driven by the game master | EV-0 part 2: invention and the lore record | Both gates pass; the review queue works end to end |
| 4 | EV-6 Authoring, with the review queue | EV-5 Upgrades, EV-7 Latency | A second world authored in the editor plays at Aurelia's depth |
| any | EV-8 content | | |

EV-0 comes after EV-1 because a game master with no facts to read or write can only narrate.

As in the production roadmap: two lanes in worktrees, review agents only (no development agents), a review loop
after each package, and every gate run locally on a scratch database.

## 5. New measures

| Measure | Target | Package |
|--------|--------|---------|
| Game master proposals that contradict established facts (accepted only) | upper ≤ 1% | EV-0 |
| Turns between meaningful events | a ceiling, set at the first rubric playtest | EV-0 |
| Direction calls per hour of play; cost per hour | measured and reported; F3 still met | EV-0 |
| Inventions recorded in the campaign's lore and in the review queue | 100% | EV-0 part 2 |
| Observable differences per decision, in the following 20 turns | ≥ 3 | EV-1 |
| Fight length, median rounds (ordinary / boss) | 3-5 / 8-12 | EV-2 |
| Potion turns in a boss fight | < 25% | EV-2 |
| Step proposal precision / recall | ≥ 0.98 / ≥ 0.90 | EV-3 |
| Goal beats seen in 200 turns | ≥ 8, each told | EV-4 |
| Gear at level 7 against level 2 (damage, armour) | strictly better, inside the bands | EV-5 |
| A world made only in the editor: playthrough scenarios | 100% | EV-6 |
| Travel p50 in route autoplay | ≤ 8 s | EV-7 |

The rubric's stakes, choice and progression scores (G1, at the owner's playtest) are the measure that matters most.
The table above is how we get there.

## 6. Risks

- **The game master drifts from the world.** Its inventions could pile up and blur the author's world. Mitigation:
  every invention is a lore entry with provenance; checks run before it is played; a consistency review runs after;
  and only the author's approval carries it to other campaigns.
- **The game master overdirects.** Too many events or complications would bury the player's own choices.
  Mitigation: daily and per-scene limits in code, and the rubric's choice score.
- **Direction cost.** A higher-effort model call at each scene boundary has a cost. Mitigation: it runs off the
  critical path, on a call budget per hour, measured from the first run.

- **Facts sprawl.** Many facts with few readers become noise. Mitigation: a fact with no reader is a publication
  finding, as unknown references are today.
- **Model proposals completing steps wrongly.** Mitigation: deterministic acceptance, and precision gated at 0.98.
- **Combat balance churn.** Every world's bands move. Mitigation: bands per world in the balance simulation, re-set
  once in EV-2.
- **Document versions.** EV-1 and possibly EV-2 change the stored shape. Mitigation: one version for both, if they
  land close together.
- **Latency work touching prompts.** EV-7 may change narration prompts, which triggers the model gates (narration
  and intent).

## 7. For the owner to decide

Decided (2026-10-29):

- **The game master may invent** new named people, places, items, creatures and quests. Each invention is added to
  the lore, for a permanent record and a review for lore consistency (EV-0 part 2).

Open:

1. **Scope and order:** EV-1 and EV-2 first, then EV-0, as in section 4? Or another order?
2. **Group standing on screen:** as a number, or in words ("respected by the Wayfarers")?
3. **"What has changed":** may the journal list the world's facts, or should the player only feel their effects?
4. **Boss fights:** is 8-12 rounds the right target? May the hero flee a boss?
5. **Steps by meaning:** accept a step the model proposed and the code checked, with no listed word said? (Proposed:
   yes, since the word list stays as the fallback.)
6. **People's goals:** may a person's goal fail, or the person leave or die, without the hero being involved?
   (Permanent consequences raise replay value, but can close content.)
7. **Crafting:** upgrades only, or full recipes?
8. **Timing:** start after the production roadmap's gates close (phase 0), or run phase 1 alongside them?
9. **Vesper-9:** give it authored play sections, or keep it as the example of a world played from its lore alone?
10. **Where an invention lives before review:** in the campaign that met it only, until an author approves it into
    the world's lore (proposed)? Or in the world's lore at once, flagged as unreviewed, so every new campaign sees it?
11. **The game master's reach:** may it end a person's life, or close a quest for good, without the hero being
    involved? This is question 6, asked of the game master rather than of authored beats. (Proposed: yes, within
    the daily limits, and never a quest's giver while the quest is open.)
12. **Can the player see the game master?** Proposed: no. Its work shows only as the world's events. A developer
    view lists its proposals, its reasons, and which were dropped.
