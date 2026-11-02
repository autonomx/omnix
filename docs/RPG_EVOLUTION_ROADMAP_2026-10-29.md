# RPG evolution roadmap (2026-10-29)

Status: **built, gates partly run** (owner's go-ahead, 2026-10-29; every package landed by 2026-10-30). Section 8
logs each package, and what of its gate is still to run. It follows the production roadmap
([RPG_PRODUCTION_ROADMAP_2026-10-23.md](RPG_PRODUCTION_ROADMAP_2026-10-23.md)). That roadmap made the game correct,
measured and maintainable. This one makes it deeper. Its evidence is the full Aurelia campaign
([playtest-aurelia-2026-10-26.md](rpg/playtest-aurelia-2026-10-26.md), session 3: 176 turns, all six quests,
level 7, the gate made a guarded bridge), the route autoplay runs, and the measured gates in
[current-state.md](rpg/current-state.md).

Section 7 records the owner's decisions (all answered on 2026-10-29).

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
  - Some pieces a director would need exist but are unused for that: a seeded event injector and agent scheduler
    (RQ-4.6), and Aurelia's `gm_guide` lore topic (opening beats, ending choices, tone controls), which nothing reads.
  - One piece is designed but was never built: typed proposals folded into a later turn, chosen at commit, marked
    consumed once, and recorded on the turn row so replay applies the same set (production roadmap §4.1). No
    proposal store, consumed marker or migration exists. EV-11 builds it.
- **Why it matters:** W-1 and W-4 below are the symptoms. Authored content alone makes a story that is the same
  every time.

### W-1. Choices change little afterwards (the largest gap)

- **Seen:** Seraphine's engine was democratised. The step's telling was good, and dialogue remembered it. Nothing else
  changed: no faction standing, no prices, no one moved, no quest opened or closed, no greeting differed. The gate's
  fate was the same: one closing line, then the world went on as before.
- **In the code:** a way's `told` line (`rules/quest/progress.py`) is the whole of an outcome. There are 56 change
  types in `StateChange` (`foundation/state/changes.py`), but none records a world fact or a group's standing. `RegardChanged` is per
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

- **Measured** (`rpg-latency-route-stream-sonnet-low-2026-10-29.json`, 20 runs a class):
  - arriving somewhere takes p50 7.2 s (target 6 s) and p95 10.3 s (target 10 s);
  - first narration p95 is 5.1 s on arriving, 3.4 s in a fight and 2.9 s on looking (target 2.5 s);
  - a question's outcome takes p95 3.2 s (target 3.0 s).

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
- M2's target lower bound is 0.943 against 0.95 (`rpg-intent-route-2026-10-29.json`). 11 of its 39 misses are a
  label question for the owner ([label review](measurements/rpg-intent-label-review-2026-10-26.md)).

### W-9. The game reads words, not meaning, before the model is asked

Added after the list above was ordered. It is worked on first (phase 0), because EV-2 and EV-3 build on how a line
is read.

- **Seen:** 33 lines were run through the command grammar and the planner on 2026-10-29: 32 idioms and remarks, and
  one real command. 16 of the idioms became game actions with no model call:
  - "give it a rest", "the rest of the money is yours" and "I'll sleep on it" rest the hero, and hours pass;
  - "can't wait to see the Forge" waits;
  - "look who's talking" and "I look forward to working with you" look around;
  - "I'd never threaten you" rolls intimidation, "he tried to trick me" rolls deception, and "climb the ranks of
    the guild" rolls a climb.
- **In the code:** the command grammar (`rules/intent/grammar.py`) reads every line first, with word lists. When it
  is confident, the turn runs and the model is never asked (`session/turn/run.py`, `plan_player_text`). That was
  17.6% of M2's held-out lines. Counting speech, which the grammar sends to the dialogue call with no intent call,
  at least 54.5% of the lines made no intent call: the run made 546 calls of every kind for 1,200 lines
  (`rpg-intent-route-2026-10-29.json`), and it does not record which were intent calls.
  - Some families commit with no confidence bar: skill checks, an attack on a named target, abilities, buying and
    selling, a level's choice and searching (`session/turn/planning.py`).
  - Word matching also runs after the reading:
    - the question and hypothetical filters (`session/turn/intent.py`);
    - a talk step's `about` words (W-3);
    - the resolvers, which read the raw text again (`session/turn/resolution.py`): how long to wait
      ("until evening"), what and how many to buy ("buy two"), how to rest, a companion's order, a level's choice,
      what to give;
    - the dialogue plan, which decides what a person reveals or offers by word overlap and patterns
      (`rules/dialogue/plan.py`).
  - The option cards send text that goes through the same grammar (`session/turn/suggestions.py`).
- **Measured:** in M2 (2026-10-26), 10.7% of the lines that meant to change something changed nothing, and the run
  does not record which lines they were. The held-out set has few idioms, negations or reported speech, so M2 does not
  measure this failure.
- **Why it matters:** players do not type commands. A word list cannot tell "give it a rest" from resting, and each
  new list (a creature's weakness, a companion's order) adds more of the same failure.

### W-10. Nothing new is found in play

- **Seen:** a campaign plays only what the world held when it was made. Play creates new copies of known things only:
  - a creature from the world's bestiary, when the hero attacks it, when one calls an ally, or as a road encounter
    while a region's danger is high (`rules/pressures.py`);
  - an item from the world's list, as loot, a purchase or a reward;
  - and people's whereabouts, time, weather and pressures.
- **In the code:** none of the change types (`foundation/state/changes.py`) adds a place, a person, a kind of
  creature or item, a quest or lore. "I search the hills for a cave" finds nothing: no cave is in the scene, so the
  turn is a free action, and the claim checker keeps the narrator from describing one. Only authored places have
  local maps, and map definitions belong to the world, not to a campaign.
- **Why it matters:** exploring is half of an RPG. A world that never grows past its author's list is used up in one
  campaign. EV-0 part 2 lets the game master invent, but only when it judges the story needs it. The player's own
  exploring finds nothing, and a dungeon is more than one lore entry.

### W-11. The story's names lead nowhere

Added at the owner's request (2026-10-29).

- **Seen:** the narration and people's lines name people, places, groups and events ("Bob the butcher", "the
  Skybridge"), but a name is plain text. To read about it, the player opens the lore tab and searches.
- **In the code:**
  - The campaign's lore is already readable by the player: the lore panel (`RpgLorePanel`, in the story tabs) and
    the route for one entry (`/api/rpg/sessions/{id}/lore/document`). Both leave out every secret (`public_canon`,
    `genesis/forge/campaign_lore_api.py`).
  - What the response text names is not marked. The narrative engine's evidence carries the entities it is about
    (`entity_refs`), but the text the player reads does not.
- **Why it matters:** a world's depth is in its lore, and the player meets the lore through the story. One click
  from a name to its entry makes that depth reachable.

### W-12. The story is silent

Added at the owner's request (2026-10-29).

- **Seen:** the narrator and the people speak only as text.
- **In the code:**
  - The RPG has a `tts` setting, off and unused in play (`declarations.py`).
  - Omnix has part of what a voiced game needs, and EV-13 lists what it lacks:
    - a voice library of cloned voices (`resources/voice_clones`), with no description, revision or eligibility
      flag;
    - a speech contract (`StreamingSpeechSynthesizer`) with a Qwen service adapter
      (`platform/live_speech/tts_adapters.py`);
    - in the audiobook app, casting a voice per speaker, pinned by revision, and a render cache keyed by the full
      render identity (`apps/audiobook/render_planner.py`, `render_keys.py`).
  - Each response entry already names its speaker (`speaker_id` in `rpgTurnEntries.ts`). The narrative engine
    projects its final blocks for speech, with a speaker on each (`tts_projection`).
- **Why it matters:** voices make people distinct and the world present, and let a player listen instead of read.

## 2. Principles

The production roadmap's invariants hold for every work package here (AGENTS.md, RPG section):

- Every state change is a turn through the one pipeline, and a rule is pure.
- One owning rule per mechanic, registered in `PipelineMechanic`, `MECHANIC_OWNERS` and `CHANGE_WRITES`.
- Model output is a proposal; deterministic code decides.
- A change to the stored shape is a new document version, with its upgrade.
- No world's names in the engine. What a world does is data in its play sections.
- No unseeded randomness on the turn path.

Four more for this roadmap:

- **Typed text is read by the model; only a card is a command.** Owner decision (2026-10-29). Code does not interpret
  the player's words. The model reads every typed line, and code checks the reading against the scene and the rules.
  A card the player clicks carries its action and target, and runs with no reading. No package adds a word list.
- **The game master proposes; code decides.** The game master chooses what should happen and why. Deterministic code
  checks that it can happen and works out what it does. The game master never writes state, rolls dice, or sets a
  reward or a blow directly. Its proposals are recorded, so a campaign replays to the same state (D1).
- **Work done off the turn enters through a turn.** A direction call, an area's filled-in detail or narration's side effects
  are proposals in the proposal record (EV-11). A later turn folds them in at commit, through the rules, and records
  which. Nothing written off the turn changes the campaign document directly (AL018, AL019).
- **Replay re-runs the rules.** D1 today rebuilds each turn's hash from its stored patch (`scripts/rpg_replay_audit.py`).
  That cannot catch a rule that depends on something unrecorded. From EV-11 on, D1 also re-executes each turn from
  its recorded inputs (the reading or card, the folded proposal set, the seed) and compares the hash.

- **Data over code.** Each new mechanic is something an author writes in a play section, with a sensible derived
  default for a world that writes nothing.
- **Visible change.** A consequence that the player cannot see or feel does not count. Each package names what the
  player sees.

## 3. Work packages

Each package lists its problem, its design, what changes in the stored state, its gate and its rough size: S (days),
M (one to two weeks) or L (two weeks or more).

### EV-0. The game master (W-0, and through the others W-1, W-4, W-6) — L, in two parts (needs EV-1, EV-11)

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

**When it runs.** As a job after a turn commits: at a scene boundary, after travel, after the daily world tick's
turn, and when play stalls; never on every turn. A direction call is off the turn's critical path. Its proposals go
into the proposal record (EV-11), and the next turn folds them in at commit. It does not count against a turn's calls
(F3) and does not add latency.

**What a stall is.** A meaningful event is a committed change of one of these kinds:
- a fact set;
- a quest offered, advanced or ended;
- a fight started;
- a goal's beat advanced;
- a person arriving or leaving where the hero is;
- an item or coin gained beyond a purchase.

"Turns between meaningful events" counts the hero's turns from one to the next.

**What it reads.**

- the campaign's state;
- the world facts (EV-1);
- open threads;
- the people's goals and beats (EV-4);
- the world's `gm_guide` (opening beats, ending choices, tone controls);
- the author's play sections, as its palette and its limits.

World text is untrusted data in its prompt. It reads the public canon only: no secret field (`SECRET_FIELDS`,
`public_canon`) reaches it, a lore entry's `hidden_truth` included. So:
- code checks a proposal against the secrets mechanically: no reference to a secret entry, and no text that names a
  secret (`names_a_secret`, `rules/secrets.py`);
- whether a proposal's meaning contradicts a secret is not something code can judge, and the game master cannot see
  the secrets. Its proposals get no such check in play. An invention's draft gets one in review, where the
  consistency check reads the secrets (question 14);
- an invention's own secrets go in its secret fields, so they stay out of every later prompt.

**What it may propose.** A closed set of typed proposals, each with the reason it gives:

- set a fact, or bring a consequence forward;
- advance a person's goal by a beat, or move a person;
- start an encounter from the bestiary, sized to the hero's level;
- spread a rumour, or add a complication to the current scene;
- offer a quest, from the canon or from templates;
- (part 2) invent a person, place, item, creature or quest;
- (EV-10) fill in a larger area's detail as the hero approaches it.

Each kind is accepted by the rule that owns what it changes. `MECHANIC_OWNERS` registers the owners of the player's
planned actions (`PipelineMechanic`) and `TICK_OWNERS` the world tick's, so proposals get a third registry,
`FOLD_IN_OWNERS`, with its own test beside them (`src/tests/unit/rpg/test_mechanic_owners.py`):

| Proposal | Accepting rule |
|---|---|
| a fact, a consequence brought forward | `rules/consequences.py` (EV-1) |
| a goal's beat, a person moved | `rules/routines.py` and its goals (EV-4) |
| an encounter | the combat rule (`rules/combat/`) |
| a rumour: something people in a place come to know and tell | `rules/rumours.py` (EV-4), writing `RumourSpread` |
| a quest offered | the quest rule (`QuestOffered`) |
| a complication | `rules/consequences.py`, as a fact with its effects |
| an invention | a new rule, `rules/inventions.py` (part 2) |
| an area's filled-in detail (`AreaDetailed`) | `rules/inventions.py`, which checks each entry; `rules/exploration.py` owns finding the hidden ones (EV-10) |

**The level's budgets.** EV-2 builds them, in phase 1 (see EV-2). EV-0 checks every proposal against them.

**What code checks before a proposal is committed.**

- Every reference exists, and no fact the proposal sets contradicts one that holds.
- Danger and rewards stay inside the level's budgets.
- No secret is revealed.
- The daily limits hold: at most so many events a day, and at most one complication a scene.
- No protected person fails, leaves or dies without the hero: a companion in the party, the giver of an open quest,
  anyone an open quest's step needs (questions 6 and 11). Every such event is told.
- An invention follows the rules below.

A proposal that fails a check is dropped and logged, and shows in the measures.

**Part 1: direct and improvise** with what the world contains.

**Talking to the game master** (owner decision, question 12; part 1). The player can see the game master and ask
it about the game, as at a table.
- **Where:** a game master panel on the play screen. The player asks in their own words:
  - "What is going on in Valecourt?"
  - "Why did Rhea leave?"
  - "What did I promise Orik?"
  - "What could I do next?"
- **What it reads.** Its prompt is built only from what the hero knows (EV-1's record of what the hero knows: the
  entries met, the facts learned, the places visited), and from the state the hero can see. That means:
  - no secret, and no hidden or unmet entry, is in its prompt;
  - from the proposal record (EV-11), only proposals already folded in whose effects the hero has met, with their
    reasons. A reason is the game master's own free text, so it passes the same check as an answer before it is
    admitted.
- **What it may tell:**
  - what has happened and why, including its own reasons for events the hero has met;
  - the situation now: open threads and quests, what the hero has learned, who is where as far as the hero knows;
  - options and hints, as a game master would.
- **What it never tells:**
  - a secret;
  - a fact the hero has not learned;
  - its plans: a proposal not yet folded in, a filled-in place not yet found (EV-10), a beat not yet reached.

  Code checks every answer before it is shown. No answer names a secret (`names_a_secret`), or an entry outside what
  the hero knows.
- **It changes nothing.** A question to it is not a turn: no time passes and no state changes. Asked to act ("give
  me a hundred silver"), it declines.
- **Wishes.** The player may tell it how they want the story to go: more danger, a slower pace, more of a person.
  - The panel's call may propose a wish, from a closed set: pace, danger, a person or thread to see more of, tone.
    Code checks it, and the panel offers it as a card to confirm ("Note: more danger?").
  - The card records it as a structured action with no time, `PreferenceNoted`. A new mechanic, `note_preference`,
    in `PipelineMechanic`, is owned by `rules/direction.py` and registered in `MECHANIC_OWNERS`.
  - The game master reads wishes when it directs. They never bind a rule: its proposals are checked as always.
- **Where it is kept.** Questions and answers are kept outside the campaign document, in the campaign's panel log
  (a migration), for the developer view and the gate. They change no state, so replay does not need them.
- **Model:** one call per question, the reference model, off the turn's path. Panel calls count against the
  player's model budget (RQ-8.2).
- **Developer view:** it still lists every proposal, its reason, and which were dropped.

**Part 2: invent.** Owner decision (2026-10-29): the game master may invent, and each invention is added to the lore,
for a permanent record and a consistency review.

- An invention is a typed lore entry: a person, place, item, creature or quest, in the shape the lore topics already
  use. It carries its provenance: the campaign, the turn, and the game master's reason.
- **An invention carries its play data with it.** A lore entry alone does not play. Its play data is what the play
  sections hold for an authored entry:
  - an item's slot, numbers and price (the economy's gear);
  - a creature's numbers, behaviour, weakness and resistances (the bestiary);
  - a person's home, routine and knowledge;
  - a quest's steps, ways and rewards;
  - a place's roads and services.

  Code checks the play data against the level's budgets as it checks the entry.
- **Checks before it is played**, all mechanical:
  - its id is new and its name does not clash with the canon's;
  - its references exist, and none is to a secret entry;
  - its numbers sit inside the level's budgets;
  - the facts it sets do not conflict, by id and value, with facts that hold;
  - its text names no secret (`names_a_secret`);
  - a place joins the roads like any other.

  Whether its prose contradicts the canon's meaning is the consistency check's to report, in review.
- **The record.** When a turn folds the invention in, the entry and its play data are added to the campaign's lore
  layer. It is played at once (a boss's new blade can be picked up, worn and sold), kept with the campaign, and
  replays exactly. Until an author approves it, other campaigns do not see it (question 10). It is also
  filed as a lore draft from the game master, which an author reviews.
- **How play reads it.** The rules read the campaign's world model: routines, presence, dialogue plans, knowledge and
  trade offers (`rules/routines.py`, `_schedules`, `present_now`). So the lore layer is merged into that view.
  - One function builds the effective world model: the pinned canon revision, then the campaign's lore layer.
  - A layer entry only adds. Its id is new, so it never overrides a canon entry, and lookup needs no precedence rule.
  - The merge is document assembly, so it keeps the JSONB key order (`foundation/persistence/document_parts.py`).
  - A filled-in person plays like an authored one: a home, a routine, presence by the hour, knowledge and a
    dialogue plan.
- **Ids.** An invention's id is the campaign's own (`gm:<campaign>:<name>`), so two campaigns never clash.
  - An approved entry gets a canon id in the world's next revision. The review links the draft to it.
  - A campaign that already holds its own copy keeps playing that copy, so it replays exactly. Later campaigns get
    the canon entry.
  - The review queue groups drafts with the same or a close name, so an author approves one and links the others.
- **Who reviews.** A draft goes to the world's owner, in the owner's tenant. On a world the player does not own (a
  bundled or community world, or a guest's campaign), the draft stays in the campaign unless the world's owner has
  asked for drafts; a guest's campaign never files one (question 15).
- **The review.**
  - A model consistency check runs first. It compares the entry with the canon and reports its findings as
    evidence, not as a verdict. It is an author's tool, and it reads the canon's secrets, as the author can. Its
    findings are shown only to the author (question 14).
  - The author then approves the entry into the world's lore, edits it, or rejects it. The review covers the entry
    and its play data together.
  - An approved entry joins the world's lore, and its play data joins the world's play sections, for future
    campaigns. Both go through the world library's publication like any edit. An entry never joins without its play
    data, so a later campaign never meets a named blade with no numbers.
  - A rejected one stays in the campaign that met it, and is never offered to another.
- The review queue's store and API come with part 2. Its screen in the world editor comes with EV-6.

**State and versions.** Part 1 adds the player's wishes to the game master (`PreferenceNoted`), a new document
version with its upgrade. Beyond that it uses EV-1's facts, EV-4's beats and EV-2's budget table, and its proposals
are new kinds in the proposal record (EV-11). Part 2 adds:
- a campaign lore layer, which is a new document version with its upgrade;
- the world's review queue, which is a migration.

**Gate.**

- Proposal measures over route autoplay and a judged run:
  - share of proposals accepted;
  - contradictions with established facts among accepted proposals: point estimate ≤ 1%, pooled over at least 400
    accepted proposals, with the upper bound reported (with no contradictions, 400 gives an upper bound near 1%);
  - turns between meaningful events: a ceiling, set from the rubric playtests;
  - direction calls per hour of play, and their cost.
- Part 2:
  - every invention is in the campaign's lore layer, and in the review queue where question 15 says it goes;
  - every invention carries its play data, inside the level's budgets;
  - an approved invention plays the same in a new campaign as in the one that met it;
  - none clashes with the canon by id or name;
  - the consistency check's findings are calibrated on labelled examples, as the N1 judge is.
- Talking to the game master:
  - a question set of at least 150 questions over an Aurelia campaign, asked at fixed points;
  - no answer reveals a secret, an unlearned fact, or a plan not yet played. This is checked by code, and by a
    judge on the rest. The target: none, with the upper bound reported. The judge sees the secrets and the plans to
    do this; it runs only in the evaluation, never in play (as question 14 allows for the consistency check);
  - a test asserts that no question changes the campaign;
  - the answers' usefulness is scored at the owner's playtest.
- The 1,000-turn replay, re-executed, stays identical with the game master on (D1).
- The owner's playtest rubric for stakes and choice.

**Model.** The direction calls use the reference model at a higher effort than narration's. The cost per hour of play
is measured and reported.

### EV-1. Consequences: facts the world remembers and rules read (W-1, W-8) — L

EV-1 is the record the game master writes to and reads from. Authored consequences are its palette.

**Design.**

- A campaign holds **world facts**: named values (`engine_fate = council`, `oathblade_borne = true`) in a new state
  section.
- Three new change types, all owned by a new pure rule, `rules/consequences.py`:
  - `FactSet(fact_id, value, source)`;
  - `FactLearned(fact_id, source)`: the hero comes to know a fact, by seeing it or being told;
  - `StandingChanged(group_id, delta, source)`, for a group's standing with the hero.
- A fact records whether the hero knows it. `FactSet` sets it when the hero sees the fact happen.
- **What the hero knows**, in one record: the entries the hero has met (people, creatures, items, quests heard of,
  lore told or read), the facts learned, and the places visited (today's `visited_location_ids`).
  - Today only places visited and what a person told the hero (`KnowledgeShared`) are kept.
  - A new pure rule, `rules/hero_knowledge.py`, judges after every turn what the hero met, from the turn's own
    changes and the scene the hero stood in, as quest progress is judged. It writes `EntryMet(entry_id, kind)`.
  - The journal, the game master's panel (EV-0), and "What has changed" read it.
- Facts are written by a quest step's way (an authored `sets: [{fact, value}]` beside its `told`), by an ending, and
  by a check or fight outcome where the author says so.
- A new play section, `fact_effects`, says what facts change. (It is not the `world` state section's existing
  `consequences` key.) Each entry is a condition on facts plus one effect,
  read by the rule that already owns that mechanic:
  - **Prices:** a seller's or region's price modifier (`rules/economy/trade.py`). Orik's free first night is a
    one-time waiver while `new_arrival` holds.
  - **Group standing:** a group's standing with the hero moves. Dialogue's stance reads it alongside personal regard.
    Membership comes from the lore, or is declared by the author where the lore is silent. The player sees it in
    words, in bands (hostile, wary, neutral, respected, trusted), and a change of band is told when it happens
    (question 2).
  - **Whereabouts:** a person's routine is replaced or ended (`rules/routines.py`).
  - **Quests:** a quest opens or closes (`requires` / `forbids` facts).
  - **Places:** a line is added to a place's description, or a service opens or closes there.
  - **Pressures:** a pressure's lever is pushed (`rules/pressures.py`).
- **Endings get an epilogue:** a finale's way names the facts to tell. Deterministic code picks an authored line for
  each fact that holds, the narrator phrases them, and the claim checker holds the phrasing to them.
- **The player sees** a "What has changed" entry in the journal for each fact that holds and that the hero knows,
  in the author's line for it (question 3), plus the effects themselves: a price, a greeting, a person who is gone, a
  quest offered.

**State:** a new document version, with its upgrade. It holds:
- a `world_facts` section, with each fact's value, its source and whether the hero knows it;
- a group-standing entry;
- the record of what the hero knows. Its upgrade seeds it from the places visited, the knowledge shared, the
  quests held and the people present at each turn's end.

**Aurelia:** facts and consequences for every decision step: the engine's fate, the vow kept, the memory restored,
the gate's fate. Plus Orik's free night (W-8).

**Gate:**
- A consequence playthrough: each of Aurelia's decisions produces three or more observable differences in the
  following 20 turns, asserted in the playthrough suite.
- The golden diff is explained.
- The 1,000-turn replay stays identical (D1), re-executed.

### EV-2. Combat depth and pacing (W-2) — L

**Design.**

- **Weaknesses that work.** An action that uses a creature's weakness ("I ring the bell", "I strike with unpolished
  iron", "I name the oath it broke") triggers the stored vulnerability: a stun, a damage bonus or a morale break.
  - The intent reading (EV-9) proposes the weakness used. Code accepts it when the creature is in the fight and the
    weakness is one it has.
  - The weakness's stored aliases go to the model as names. They are not words to match.
- **Abilities by calling.** Each calling starts with two abilities and learns more at levels from the existing tree.
  The suggestions and the play screen surface abilities that are ready to use.
- **Guarding another.** The hero already defends (`rules/combat/fight.py`, the "Defend" card). New: guarding a
  companion, or a companion guarding the hero. The guard takes the blow aimed at the one guarded.
- **Companion orders in a fight:** "Liora, flank it", "Vael, guard me". This extends `CompanionOrdered`. An order
  is a reading the model proposes and code checks (the companion is in the party and the fight). The fight's cards
  offer the common orders.
- **Creature resistances and boss phases** in the bestiary section: `resists` tags, and `phases` as health thresholds
  that change behaviour or numbers, call allies, or expose the weakness.
- **Leaving a boss** (question 4): the hero can still flee a boss, as today. A boss the hero leaves recovers part of
  its health, by a fixed share set in the bestiary, with a derived default.
- **No escape:** an author may mark a fight with no escape, such as a finale.
  - The mark is `no_escape` on the creature's bestiary entry. There is no authored encounter object, and quest steps
    do not start fights.
  - It is copied into the fight when the creature joins it, as its behaviour is today (`instantiate_campaign_creature`).
  - Breaking away is refused, and the cards offer no "Break away".
- **Pacing targets**, set in the balance simulation: an ordinary fight lasts 3-5 rounds and a boss 8-12; potions are
  used on fewer than a quarter of a boss fight's turns. The simulation plays structured actions, not typed lines,
  after EV-9.
- **The level's budgets.** Nothing in the code holds them yet: the balance simulation's bands are campaign-wide,
  after 100 and 500 turns (`scripts/rpg_balance_sim.py`). EV-2 adds a budget table per hero level, owned by a new
  pure rule, `rules/budgets.py`:
  - a creature's health, damage and defence, alone and in a group;
  - an item's numbers and price, by slot;
  - a quest's or a site's reward in coin, experience and items;
  - an encounter's total danger.

  The table is a play section with a derived default, and the balance simulation checks it. EV-2 sets fights by it;
  EV-0, EV-5 and EV-10 read it.
  - A new play section changes the world bundle's format: its format version moves (production roadmap §4.4).
  - A campaign already running, on a world with no table, reads the derived default.

**State:** new change types for a phase entered and a guard set. A fighter's phase, guard and `no_escape` are new
fields in the combat state: a new document version, with its upgrade (one with EV-1's, as phase 1's version).

**Aurelia:** every creature's weakness made usable, the Archon in three phases, Echoes resisting plain steel.

**Gate:**
- Balance bands per world, including fight length.
- A scripted fight of each kind in the playthrough suite.
- The rubric's stakes and choice scores, at the owner's playtest.

### EV-3. Quest steps judged by meaning (W-3) — M, built inside EV-9

EV-9 removes the talk step's word match, so it must bring this in the same change, or no talk step could complete.
EV-3 is listed on its own for its design and its gate. It lands with EV-9, in phase 0.

**Design.**

- The intent reading, which runs on every typed line after EV-9, may propose the open step a line addresses
  (`quest_id`, `step_id`).
- Deterministic code accepts the proposal only when three things hold:
  - the speaker is the step's subject;
  - the place fits;
  - the step is open.
- No word match remains (EV-9). A step's `about` list becomes a description of its subject, sent to the model.
- A false completion is worse than a miss, so precision is gated higher than recall.

**Gate:**
- A new held-out set of about 200 lines per world, with labelled steps, pooled over the worlds. At least 300 of the
  lines address a step, and at least 300 address none.
  - Precision, over the completions the game accepts: point estimate ≥ 0.98, with the lower bound reported.
  - Recall, over the lines that address a step: point estimate ≥ 0.90.
- The intent prompt's version is bumped, and M2 is rerun with EV-9's.

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
- A beat never makes a protected person fail, leave or die (question 6).
- One change type, `BeatAdvanced(person_id, goal_id, beat)`, owned by the routines rule.
- **Rumours, on the pipeline.**
  - A rumour is something the people of a place come to know and will tell. It is campaign state: authored
    knowledge lives in the world's revision, and this is learned in play.
  - A new pure rule, `rules/rumours.py`, owns it, with one change type, `RumourSpread(rumour_id, place_id, text_id,
    source)`. It writes the `world` section's existing `active_rumors` key, which nothing on the pipeline uses today.
  - Dialogue tells a rumour when a person of that place is asked. Paid information (trade) sells it.
  - The off-pipeline rumour system (`world/social/rumor_system.py`, `rumor_from_conversations.py`, used only by
    world creation's simulation) is retired from play. World creation keeps its own use, or moves to the rule.
  - Readers of `active_rumors` move to the new shape:
    - the sandbox outcome projection (`foundation/sandbox/outcome_projection.py`);
    - the world-scene narrator's prompt (`narration/ai/world_scene_narrator_prompts.py`);
    - World Forge's scene generator and presenters (`genesis/creator/`).

**State:** each goal's reached beat, in the people's goal state (`npc_goal_state`, in the `npcs` section), and
`active_rumors`'s entries in their new shape. One new document version, with its upgrade.

**Gate:**
- A 200-turn run: at least eight beats seen, each told to the hero at least once.
- The W1 checks still pass.
- The 1,000-turn replay is identical.

### EV-5. Upgrades and crafting (W-7) — M

**Design.**

- A new service kind, `upgrade`: a seller improves an item the hero carries by one tier, for materials and coin.
- Recipes are authored in the economy section. Tiers are bounded and add to the item's stats.
- One new change type, `ItemImproved`, owned by the trade rule's services.
- Tiers sit inside the budget table (EV-2).
- Full recipes are decided after the owner's playtest of upgrades (question 7).

**State:** a carried item gains its tier, which changes the inventory's stored shape: a new document version with its
upgrade.

**Aurelia:** Hollis improves a blade or armour with Aether Shards. Brindle tunes the Arc Baton.

**Gate:** the balance simulation's purse and gear bands. The purse rises and is spent, and level-7 gear is better
than level-2 gear.

### EV-6. Authoring in the editor (W-6) — M

**Design.**

- **World editor forms:**
  - an item's gear (slot and numbers);
  - a character's home, aliases and group;
  - a quest's rewards and a way's `sets`;
  - the `fact_effects` section;
  - the bestiary's phases and resistances.
- The screen for the review queue of the game master's inventions (its store and API come with EV-0 part 2). Each
  draft shows its provenance and the consistency check's findings, with approve, edit and reject.
- World Forge drafts every play section from the lore, not only some: quests' steps, knowledge, the economy with
  gear, routines with beats.
- `lore-additions.json` becomes unnecessary for Aurelia: the same edits go through the editor's entity authoring
  (`entity_authoring.update_world_entity`).

**Needs:** the owner's permission to run the web typecheck. The LM Studio World Forge run belongs here.

**Gate:**
- A world authored only in the editor plays at Aurelia's depth: the playthrough suite's scenarios pass on it.
- Vesper-9, lore-only, passes its three strict xfails from World Forge's drafted play sections: a companion, a shop
  and an inn (question 9).
- The web build passes.
- The core-task UI checks pass.

### EV-7. Response time (W-5) — M

**Design.**

- Prepare the arrival scene's deterministic facts while travel resolves.
- Stream narration from the first sentence.
- Cache scene lore per place, time of day and canon revision.
- Make a long journey one turn with interruptions, not several.

**Gate:** F1 met in every class (arrive p50 ≤ 6 s, a question's outcome p95 ≤ 3.0 s, and the speech-turn targets EV-9
sets), and travel p50 ≤ 8 s in route autoplay.

### EV-8. Content (W-8) — S each

- Maps for Valecourt and Cinderhold.
- Vesper-9 stays lore-only (question 9); EV-6 is what deepens it.

Orik's free night is EV-1's.

### EV-9. The model reads every typed line; cards are commands (W-9, W-3) — L, with EV-3

Owner decisions (2026-10-29): code stops interpreting the player's words; cards are the only deterministic commands;
speech takes two calls, run in parallel when safe; with no model, only the cards work.

**Design.**

- **Every typed line goes to the intent call** (`session/turn/intent.py`).
  - **Removed:** the grammar's reading and its word lists (`parse_command` and its tables in
    `rules/intent/grammar.py`), and `read_command`, `skip_reason` and the clarification table
    (`session/command_reading.py`).
  - **Kept, moved beside the intent call:**
    - the reading's type (`IntentCandidate`);
    - the scene (`SceneView`, `scene_view`);
    - what the scene knows of names, as data in the model's scene: people's other names and callings, the kinds of
      things carried, places' aliases.
  - **Harnesses that call the grammar** move to readings or structured actions: the intent eval
    (`scripts/rpg_intent_eval.py`) and the balance simulation (`scripts/rpg_balance_sim.py`).
- **The reading carries what the rules need, so no rule reads the raw text.** Besides family and target, it returns:
  - whether the line asks or supposes rather than does;
  - when the line is unclear, the question to ask;
  - for speech, whom it is addressed to, and the topics asked about. The topics are chosen from those the person may
    share, and none is secret;
  - typed slots:
    - a quantity;
    - how long to wait, or the hour to wait until;
    - the seller;
    - a level's choice;
    - a companion's order;
    - what to give, and to whom;
    - a check's kind;
  - the open step the line addresses (EV-3).
- **Removed with the word lists:**
  - the question and hypothetical filters on the reading;
  - the resolvers' reading of the raw text (`session/turn/resolution.py`): `wait_minutes`, `resolve_trade`'s names
    and counts, `rest`, `order`, `progression.choose`, `give_item`'s text;
  - the dialogue plan's word overlap and patterns for what a person reveals or offers (`rules/dialogue/plan.py`). It
    reads the reading's topics instead;
  - a talk step's `about` match (EV-3 replaces it, in the same change).
- **Code checks every reading, as today** (`valid_readings`, `decide`), and each slot:
  - the family is one the pipeline runs, aimed at a thing really in the scene, of a kind that family takes;
  - a quantity is no more than is on offer or carried;
  - a wait is within its limits;
  - the seller is present;
  - a choice is one the level offers;
  - a topic is one the person knows;
  - two close readings: the game asks which was meant;
  - none left: a free action, told, changing nothing.
- **Cards carry their action.**
  - A card is a `structured_action` turn, a kind the request already has (`session/turn/request.py`). It carries
    the campaign revision it was offered at, so a card from an older state is refused (RQ-8.9).
  - Its action is the family, the target and the same slots as a reading.
  - Every choice the game offers becomes a card action: the suggestions, the answers to a question ("Do you
    mean…?"), and a level's choices.
  - It is planned directly, with no reading and no model call. Its text stays, for the log.
  - Rest, Wait and Status cards are added. Items and abilities stay typed, or come from the existing panels.
- **Speech: two calls, in parallel when safe.**
  - **Under way** means the last turn left a dialogue focus on a person who is still present. Only then is a
    parallel reply safe.
  - A new speech turn (a first greeting, another person) reads the line, then runs the dialogue call: two calls in
    a row.
  - In a conversation under way, code first works out that person's plan from the turn's starting state, with no
    topics: stance, manner, and what they have already shared. What they reveal or offer depends on the reading's
    topics, so that part cannot be planned yet. The intent call and a dialogue call on that topic-free plan then
    start together.
  - The reply is held, not shown. It is used only when all three hold:
    - the reading is plain talk to that person: no check, no step, no other change;
    - the reading's topics add nothing to the plan: no new reveal or offer;
    - at commit, the plan rebuilt from the committed state matches the plan the reply was written for.

    Otherwise the reply is discarded, and the turn runs the reading's own path: the full plan with its topics, then
    its dialogue or narration call. Discarded replies are counted.
  - So the parallel reply serves small talk and follow-ups. A line that asks about something new runs in sequence.
    The discard share shows how often the parallel call pays. If most replies are discarded, the parallel path is
    dropped.
- **Model calls per turn.** F3 counts the calls whose output the turn uses. A discarded parallel reply is counted
  apart: at most one a turn, and reported.
  - A typed turn uses one intent call, then one narration or dialogue call.
  - Narration keeps its one revision (`_revise_with_feedback`, `narration/narrative_engine/validation.py`) when its
    first answer fails the check, on typed turns too (owner decision, 2026-10-29). That third call costs a few
    seconds, on the turns that need it. If the revision fails too, the deterministic prose is told, as today.
  - A card turn makes no intent call. Its narration, and its revision, are as today.
- **Every typed turn runs as a job,** as model turns do today (production roadmap §4.1). Only card turns can finish
  in the request.
- **With no model,** a typed turn says the storyteller is unavailable and offers the scene's cards. This replaces the
  grammar-only fallback (RQ-8.8).
- **Replay:** the reading and its slots are recorded with the turn, so a campaign replays, and re-executes, without
  the model (D1).

**State:** no document version. The structured action gains the card's action and slots, and the web's API contract
is regenerated with it.

**Targets revised (owner decision, 2026-10-29, restated here):**

- **F3:** no turn uses more than two model calls, plus narration's one revision when its first answer fails the
  check. A discarded parallel reply is counted apart. The "at least 80% of turns make at most one" target is
  dropped, because every typed turn now makes an intent call. Card turns and other deterministic structured turns
  make no intent call.
- **F1:**
  - These targets now apply to card and structured-action turns: deterministic ≤ 500 ms complete, an outcome
    p95 ≤ 300 ms for tactical moves and attacks, and ≤ 1.0 s for the rest. The latency harness plays those classes
    (status, wait, attack, tactical move) as cards. EV-9's gate holds them.
  - Typed turns keep their targets: an outcome p95 ≤ 3.0 s, complete p50 ≤ 6 s and p95 ≤ 10 s, first narration
    p95 ≤ 2.5 s. Several already miss with no intent call (W-5). EV-9 measures and reports them; EV-7's gate holds
    them.
  - Speech turns: targets set from the first measurement after this package.
- **Cost:** every typed line makes an intent call. On M2's held-out lines, at most 45.5% did before (546 calls of
  every kind for 1,200 lines). The cost per hour of play is measured and reported.

**Needs:** the owner's permission to run the web typecheck (as EV-6).

**Gate:**

- **A new idiom set**, held out, of about 300 lines per world, pooled over the worlds (at least 800 lines):
  - what it holds: idioms, negations, reported and quoted speech, figures of speech;
  - its seed is the 33-line probe of 2026-10-29 (W-9), committed with the set;
  - the target: no action committed by mistake, with a pooled upper bound ≤ 0.5%. With no mistakes, 800 lines
    give 0.48%.
- **Slots:** a labelled set of lines for each slot kind (quantity, wait, seller, a level's choice, order, give, check
  kind, topics), at least 75 lines a kind. Each kind read right: lower bound ≥ 0.95. With no mistakes, 75 lines give
  0.951.
- EV-3's gate.
- M2 rerun on the frozen held-out set, at its targets. The run records each failing line, missed stateful ones
  included, and each model call's role.
- **Cards:** every card turn plans its action with no intent call (100%), and every choice the game offers is a card.
- **Calls:**
  - no turn uses more than two model calls, besides narration's one revision;
  - the shares of turns with a revision, and of discarded parallel replies, are reported;
  - a test asserts that no reply is shown whose plan changed, by the reading's topics or by commit.
- F1 rerun: card and structured-action classes meet their restated targets; typed classes are measured and
  reported.
- With the model down, a typed turn offers the cards, and a card turn still runs.
- The playthrough suite and the published-world golden pass, with scripted readings or card actions in place of
  the grammar. The golden's diff is explained.
- **The web:** the component tests, the build, the typecheck (with the owner's permission), and the core-task UI
  checks at 360 and 1,440 px.
- The 1,000-turn replay, re-executed, stays identical (D1).

### EV-10. Areas filled in as the hero approaches: places, sites and dungeons (W-10) — L (needs EV-0 part 2, EV-11)

Owner decision (question 13): a world need not hold all its detail when it is made. When the hero heads for a larger
area, such as a region or a town, the game fills in what the area holds, from its lore.

**Design.**

- **What an area holds.** Each larger area has a detail budget: whatever an area of its kind and size should hold.
  The game master decides what fills it, from the area's lore. Code holds the limits: a table of how many of each
  kind an area holds, by its kind and size. It is not only places:
  - places: a town's buildings and districts (a market, a temple, a smithy, an inn); a region's sites (a cave, a
    ruin, a barrow, a dungeon), and its roads and landmarks;
  - people: those who live and work there, with their homes, days, knowledge and goals;
  - creatures: what lives in the wilds and the sites, from the bestiary or invented;
  - things: what is sold, found or guarded there, and loot;
  - services: lodging, trade, healing, passage, information;
  - stories: quests and hooks, rumours (EV-4), and local lore, such as its history, customs and dangers.
  - The limits are rows that EV-10 adds to EV-2's budget table (`rules/budgets.py`): counts per kind by area kind
    and size, with a derived default. The world's `gm_guide` palette may change the counts and name the kinds an area favours.
  - Authored detail counts toward it. Only what is missing is filled in.
  - Code checks counts and numbers against the table. Whether an entry fits the area's lore is the consistency
    check's to report, in review (EV-0 part 2).
  - World Forge may leave an area's detail open by design, so a world is made faster and grows where it is played.
- **Filled in one area ahead, off the turn.**
  - When the hero arrives in an area, the game master's run fills in the larger areas next to it that are still
    open. The lead time is the hero's whole stay, not one trip. At launch, a job fills in the starting area and its
    neighbours before the first turn.
  - Each entry (a place, a person, a creature, an item, a service, a quest, a rumour, a piece of lore) is a proposal
    in the proposal record (EV-11). It is written from the area's lore and checked like any invention before it is
    kept, with its play data.
  - Later turns fold it in at commit, through their changes (`AreaDetailed`). Nothing is written to the campaign
    off the turn.
  - One turn folds in at most a capped share, places first, then people, then the rest. The cap starts at 10 entries
    and 24 KB a turn, set from F2's measurement.
  - If an area is not ready when the hero arrives, the arrival shows what is authored, and the rest appears as
    later turns fold it in.
  - An area is filled in once a campaign. After that its detail is fixed, and replays exactly.
  - How long a fill-in takes, and its size, are reported.
- **Found by the player.**
  - What anyone would see (a town's market, its main street) shows on arrival.
  - What is hidden (a cave in the hills, a cellar under the inn) is found by exploring: a family the intent reading
    proposes (EV-9), such as "search the hills for a cave", "follow the river north", "go deeper".
  - A new mechanic, `explore`, in `PipelineMechanic`, owned by a new pure rule, `rules/exploration.py`. Code decides
    whether a hidden place is found here, by a seeded search check against its difficulty.
  - Found, it joins the roads like any place (`SiteFound`), and the hero can go there.
  - A room's encounter beaten, or its loot taken, is recorded (`RoomCleared`).
  - Exploring makes no generation call: if nothing has been filled in here yet, the search finds nothing this time.
- **A site has a fixed shape.** For a site such as a dungeon, the game master writes what is the model's to write:
  the theme, names, descriptions, and the hook that ties it to the story (a fact, a person's goal, an open thread).
  Code builds the rest:
  - rooms and the ways between them, from a seeded layout generator. It extends the settlement assembler
    (`world/map_settlement_assembler.py`) to interiors, and gives the site a local map;
  - an encounter per room, from the bestiary or an invented creature, sized to the hero's level;
  - loot inside the level's budget, from the world's items or an invented one with its play data;
  - a hazard or two, met by a check;
  - optionally a boss in phases (EV-2) and its reward.

  A town's new buildings get a place on the town's local map the same way.
- **Its inventions are recorded like any other.** A new place, its people, a boss and the blade it drops are entries
  with their play data in the campaign's lore layer, and drafts for review (EV-0 part 2, questions 10 and 15). An
  approved area's detail joins the world for future campaigns, its layout and contents with it.
- **The player sees** places on the map that were not there before, people and wares they had not met, work and
  rumours to hear about, a journal line for each place found, and a site cleared or left unfinished.

**State:**
- Filled-in places live in the campaign lore layer (EV-0 part 2). Found places and cleared rooms are new state, in
  the same document version if they land together.
- Change types `AreaDetailed`, `SiteFound` and `RoomCleared`, registered in `CHANGE_WRITES`.
- A new place's local map belongs to the campaign, but map definitions today belong to the world. Campaign-scoped
  map definitions are a migration.

**Aurelia:** a palette for the game master in `gm_guide`: what each of its five regions and its towns hold
(`region:starfall-march`, `region:meridian-heartland`, `region:cloudspine`, `region:ashen-east`,
`region:moonroot-deep`), written by the author from their lore. EV-8 authors the maps of Valecourt and Cinderhold;
EV-10 then fills in their open detail and places new buildings on those maps.

**Gate:**

- In a 200-turn route autoplay with exploring, every larger area the hero reaches has its detail filled in by the
  time the hero arrives, in at least 95% of arrivals, measured with real timing. A second run waits for each
  direction job, so its results do not depend on timing.
- Every area's filled-in counts sit inside its budget table. Every entry's numbers (encounters, loot, prices,
  rewards) sit inside the level's budgets. Fit with the lore is the consistency check's, in review.
- **Size and overhead (F2):**
  - a turn that folds in an area's detail stays inside F2 (player turn p95 ≤ 150 ms and ≤ 20 statements at 1 MB);
  - the document stays at or under 1 MB after every Aurelia area is filled in.

  If it does not, the lore layer becomes its own document part.
- No new entry clashes with the canon by id or name, or conflicts with a fact that holds.
- In the playthrough suite, with the area's detail given as a recorded proposal:
  - a scripted town filled in on arrival;
  - a scripted site, from finding it to its boss's reward.
- No turn makes a generation call (F3).
- The 1,000-turn replay, re-executed, stays identical with filling-in on (D1).

### EV-11. The proposal record (W-0) — M

Production roadmap §4.1 designed it; it was never built. EV-0 and EV-10 need it, and narration's side effects can
use it.

**Design**, as §4.1 has it:
- A proposal store: each proposal typed, with its source (narration, the game master), the turn it came after and
  its reason.
- The set to fold in is chosen at commit, inside the turn's re-check: every unconsumed proposal of an earlier turn
  whose source is final.
- A consumed marker per proposal, unique by its id, so two racing turns cannot both fold it in.
- The ids folded in are recorded on the turn row. Replay applies exactly that set.
- Each proposal passes through its owning rule (EV-0's table). A proposal a rule refuses is marked dropped, with its
  reason.
- Re-executing replay (§2): re-run each turn from its reading or card, its folded set and its seed, and compare the
  state hash. It needs EV-9: before EV-9 a turn's rules re-read its raw text, and its reading carries no slots.

**State:** a migration (the proposal store, the consumed markers, the ids on the turn row). No document version.

**Gate:**
- The race test from §4.1: two turns committing at once fold a proposal in exactly once.
- A proposal from the last turn before the player quits folds into the next session's first turn.
- Once EV-9 has landed: the re-executing replay of a 1,000-turn run made after it matches its stored hashes.
- PostgreSQL tests on a scratch database.

### EV-12. Names that open their lore (W-11) — M (needs EV-1's record of what the hero knows, EV-11)

Owner decision (2026-10-29): anything with lore that the response names can be clicked to open its lore.

**Design.**

- **What is linked:** every mention of an entry with lore, in narration, a person's line, the journal, the quest log
  or the game master's panel. That covers people, places, groups, creatures, items, quests, events and lore topics,
  authored or filled in (EV-10).
- **How a mention is found.**
  - The narrator and the dialogue call mark what they name, with the entry's id.
  - Code keeps a mark only when:
    - the id exists in the effective world model (canon and the campaign's lore layer);
    - the marked words are one of that entry's names (its name, aliases, callings, title);
    - the entry is not secret, and is not a hidden place still unfound (EV-10).

    Anything else is dropped, and the words stay plain text.
  - Deterministic prose (the fallback, the journal, the quest log) marks its own mentions from the entries it is
    built from.
- **Marks and streaming.** Narration drafts are shown while the writer works, and a draft that fails the claim check
  is revised or replaced by the deterministic prose. So:
  - every draft is shown with its marks stripped;
  - the spans (entry id, start, end) are computed only on the final, checked text, and travel beside it. The text
    itself is unchanged.
- **Hearing a name counts, through a proposal.** A kept mark of an entry the hero did not know yet means the hero has
  now heard of it.
  - The mark is the narrator's output, and narration is final only after the turn commits. So "heard of" is a
    narration proposal in the proposal record (EV-11).
  - The next turn folds it in as `EntryMet` (kind "heard of"), and replay applies the recorded set.
  - Until then, its link opens the entry's public lore.
- **What a click opens.** The lore panel opens beside the story, at that entry, without leaving the play screen. It
  shows:
  - the entry's public lore (`public_canon`): never a secret;
  - what the hero has learned of it: facts learned (EV-1), what people told the hero (`KnowledgeShared`), when the
    hero met or heard of it;
  - links onward, to the entries its lore names, under the same rule.
- **A new, read-only entry view.** Today's one-entry route (`/api/rpg/sessions/{id}/lore/document`) is not
  read-only.
  - It goes through `load_campaign_lore(..., ensure_current_location=True)`
    (`genesis/forge/campaign_lore_store.py`), which locks the campaign, may ask the model to write missing lore, and
    saves.
  - It also reads only the campaign's bible, not EV-10's filled-in entries.

  A click uses a new entry view over the effective world model, filtered by `public_canon` and the record of what
  the hero knows. It takes no lock, generates nothing and writes nothing.
- **What a click is not:** not a turn and not a model call. Nothing changes in the campaign.
- **The lore tab** keeps listing the public canon, as today. A link adds what the hero has learned.
- **Accessible:** a link is keyboard-reachable and readable by a screen reader, and works at 360 px (U1).

**State:** none in the document beyond EV-1's record. "Heard of" arrives through EV-11's proposals. The response's
spans are part of the final response, and the web's API contract is regenerated with them.

**Gate:**
- **Right target:** on a sample of 300 linked mentions over Aurelia's route, at least 98% open the entry meant, by
  point estimate, with the lower bound reported.
- **Coverage:** on a labelled sample of 100 responses, with every mention of an entry with lore labelled, at least 90%
  of those mentions are linked.
- **Nothing hidden:** no link opens a secret entry or an unfound hidden place, and no lore view shows a secret field.
  Both are asserted in tests.
- **No cost:** a test asserts that a click makes no model call and no database write.
- **Streaming:** a test asserts that no draft shows a mark, and that spans match the final text.
- **Heard of:** a test asserts that "heard of" arrives only through a folded proposal, and that replay applies it.
- **Narration:** the marks change the narrator's and the dialogue prompts, so N1 is rerun.
- **The web:** component tests, the build, and the core-task UI checks with a new task, "open a person's lore from
  the story", at 360 and 1,440 px, with axe at 0 serious.

### EV-13. Voices: every character and the narrator heard (W-12) — L (needs EV-12)

Owner decision (2026-10-29): each character, and the narrator, has a voice, chosen by the player or automatically.
Press to play by default; the player may switch on auto-play (questions 16 and 17).

**What the voice stack has, and lacks** (checked 2026-10-29):
- The voice library is the folder `resources/voice_clones`, served as is (`platform/voice/voice_library_routes.py`).
  A profile holds a name, a reference recording, its transcript and a language. It has no description to match a
  person on, no revision, and no flag saying who may use it.
- The library holds clones of identifiable real people, including the owner's own voice, and of characters from
  other games. Nothing marks them.
- Only audiobook castings pin a voice's revision (`apps/audiobook/render_planner.py`).
- The Qwen service adapter (`platform/live_speech/tts_adapters.py`) takes a voice name and returns one recording per
  call. It neither takes a profile's reference audio nor streams.
- The text splitter cuts at 160 characters on whitespace, not by sentence (`platform/live_speech/tts.py`).
- The narrative engine already projects its final blocks for speech, each with its speaker
  (`narration/narrative_engine/projections.py`, `tts_projection`).

**Design.**

- **The castable list.** EV-13 adds to each voice profile:
  - a description to cast by: voice, age, manner, accent;
  - a revision: a hash of its reference recording and transcript;
  - an eligibility flag.

  Only voices marked castable are cast automatically, or offered to other players. A clone of a real person, or of
  another work's character, is never castable by default. Its owner alone may choose it, for their own campaigns,
  after accepting its terms (`platform/voice/licence_acceptances.py`, or a new flag).
- **The cast.** The narrator and every person who speaks get a castable voice, pinned by its revision.
  - **Automatic:** code picks deterministically, seeded by the campaign and the person. It matches the voices'
    descriptions to the person's lore (calling, age, manner, origin), and avoids giving one voice to two people who
    meet in the same scene. A person heard for the first time, filled-in ones (EV-10) included, is cast then.
  - **By the author:** a world may name voices for its people and narrator in its bundle. Automatic casting
    respects them where they are castable.
  - **By the player:** a Voices panel lists the narrator and everyone who has spoken in the campaign, met or not,
    each with their voice, a preview, and a choice. The player's choice wins.
- **Where the cast is kept.** The cast is presentation, not the game's state. It is kept outside the campaign
  document, in the campaign's voice cast (a migration), so it changes no turn and does not touch replay.
- **What is spoken:** only the final, checked text, so a draft that is later revised or replaced is never heard.
  - Each response is spoken block by block from the narrative engine's speech projection (`tts_projection`), each
    block in its speaker's voice.
  - Quoted speech inside narration is its own block, spoken in the quoted person's voice.
    - The narrator marks each quote with its speaker as it writes it.
    - Code keeps the mark when the speaker is in the scene or has spoken before. Otherwise the quote is spoken in the
      narrator's voice.
  - A person's line from the dialogue call is spoken in that person's voice.
  - Nothing hidden reaches synthesis: only the text shown.
- **Synthesis.**
  - EV-13 makes voice-clone synthesis work through the RPG's path: a profile's reference recording and transcript go
    to the speech service.
  - Text is split by sentence (a new splitter beside today's). Each sentence is synthesized in order, so a long
    block starts playing after its first sentence.
  - Audio starts once the response is final, not while it streams. On a revised turn it starts later.
- **Playback.**
  - Each response has a play and stop button. Press to play is the default.
  - With auto-play switched on, each new response plays when it is final, in order, and a new turn stops what is
    playing.
  - Settings: voices on or off (the existing `tts` setting), and auto-play.
- **Cache.** Audio is cached by its full render identity, as audiobook's render keys are
  (`apps/audiobook/render_keys.py`): the text, provider, model and revision, language, parameters, and the reference
  recording's hash.
  - The cache is scoped to the player's tenant, so no one can probe another tenant's text.
  - A campaign's audio is deleted with the campaign, and follows the retention rules (RQ-8.10).
- **Failure.** When the speech service is down or slow, the text plays on, silent, and the play button says so.

**State:** none in the campaign document. Migrations for the campaign's voice cast, the voice profiles' fields and
the tenant-scoped audio cache. The web's API contract gains the cast and each entry's audio.

**Gate:**
- **Castable voices:** automatic casting never picks a voice that is not castable, and no player is offered a voice
  they may not use (tests).
- **Cast:**
  - every speaking block plays in its speaker's cast voice, and the narrator's in the narrator's (tests);
  - a quote inside narration plays in its speaker's voice. On a sample of 200 quotes over Aurelia's route, at least
    98% have the right speaker, by point estimate, with the lower bound reported;
  - auto-play is off until switched on (test);
  - automatic casting is the same for the same campaign, and no two people in one scene share a voice where the
    castable list has enough (tests).
- **Speed,** with the Qwen speech service, on the latency route:
  - the first audio of a response is heard p95 ≤ 1.5 s after its final text is shown. This is a starting target,
    confirmed or reset at the first measurement;
  - the turn's own numbers (F1) do not move.
- **Only final text:** a test asserts that no revised or replaced draft is ever synthesized.
- **Cache:** replaying a response plays from the cache, with no synthesis. Another tenant's request never hits it,
  and deleting a campaign deletes its audio (tests).
- **Failure:** with the speech service down, play goes on, silent, and no turn fails.
- **The web:** component tests, the build, and the core-task UI checks with a new task, "hear a person's line and
  change their voice", at 360 and 1,440 px, keyboard only, axe at 0 serious.
- **Real speech:** the desktop real-model check covers one voiced turn, with a cloned voice.
- **Narration:** the quote marks change the narrator's prompt, so N1 is rerun.

## 4. Order and lanes

| Phase | Lane A | Lane B | Ends when |
|------|--------|--------|-----------|
| 0 | Close the production roadmap's engineering (RQ-9.3; the N1 and F2 reruns), then EV-11 The proposal record | EV-9 The model reads every line; cards are commands, with EV-3 Steps by meaning | EV-9's, EV-3's and EV-11's gates pass (EV-11's replay gate after EV-9) |
| 1 | EV-1 Consequences; the owner's playtest (RQ-9.2), on the game after EV-9 | EV-2 Combat, with the budget table | Both gates pass on Aurelia; the production roadmap's final scorecard (RQ-9.4) is written, grading each area as it stands |
| 2 | EV-0 part 1: the game master directs and improvises (on EV-1, EV-11 and EV-2's budget table) | EV-4 People's goals: authored beats on the daily tick; the game master drives them once part 1 lands. Then EV-12 Names that open their lore | All three gates pass |
| 3 | EV-0 part 2: invention and the lore record, then EV-10 Areas filled in | EV-7 Latency, EV-5 Upgrades | All four gates pass; the review queue's store and API work end to end |
| 4 | EV-6 Authoring, with the review queue's screen | EV-13 Voices | A second world authored in the editor plays at Aurelia's depth; EV-13's gate passes |
| any | EV-8 content | | |

EV-0 comes after EV-1 because a game master with no facts to read or write can only narrate. It also needs EV-11,
because its proposals reach the campaign only through the proposal record.

EV-10 comes after EV-0 part 2 because a site is made of inventions, checked, recorded and reviewed the same way.

EV-13 sits in phase 4's free lane. Its quote marks use the marking EV-12 brings to narration, and its Voices panel
lists the people the hero knows (EV-1's record), so it comes after both. Casting and press-to-play for whole
entries need neither, and could ship earlier on their own.

EV-12 needs EV-1's record of what the hero knows, so it can come no earlier than phase 2. It touches narration and
dialogue prompts, so the narration gate (N1) is rerun with it.

EV-9 comes before EV-2 because a creature's weakness and a companion's order are read by the model, not by a word
list. EV-3 lands inside EV-9, because EV-9 removes the talk step's word match that EV-3 replaces. M2 and F1 are rerun
once, after EV-9, since it changes both (question 8).

EV-7 moves to phase 3 because EV-9 adds an intent call to every typed turn, and response time needs work sooner.

The final scorecard (RQ-9.4) closes phase 1 as a record, not a gate. It grades every area as it stands, and names
the owner of each area below Strong:
- F1's typed classes: EV-7;
- N1 (near-duplicates, the right speaker) and F2 (turn overhead): the production roadmap's open engineering work, as
  current-state lists it.

The M2 and F1 reruns belong to EV-9's gate, in phase 0.

As in the production roadmap: two lanes in worktrees, review agents only (no development agents), a review loop
after each package, and every gate run locally on a scratch database.

## 5. New measures

| Measure | Target | Package |
|--------|--------|---------|
| Game master proposals that contradict established facts (accepted only) | ≤ 1%, over ≥ 400 accepted; upper reported | EV-0 |
| Turns between meaningful events (as EV-0 defines them) | a ceiling, set at the first rubric playtest | EV-0 |
| Direction calls per hour of play; cost per hour | measured and reported; F3 still met | EV-0 |
| Inventions recorded in the campaign's lore and in the review queue | 100% | EV-0 part 2 |
| Observable differences per decision, in the following 20 turns | ≥ 3 | EV-1 |
| Fight length, median rounds (ordinary / boss) | 3-5 / 8-12 | EV-2 |
| Potion turns in a boss fight | < 25% | EV-2 |
| Step proposal precision / recall (point estimates; ≥ 300 lines each side, pooled) | ≥ 0.98 / ≥ 0.90 | EV-3 |
| Goal beats seen in 200 turns | ≥ 8, each told | EV-4 |
| Gear at level 7 against level 2 (damage, armour) | strictly better, inside the bands | EV-5 |
| A world made only in the editor: playthrough scenarios | 100% | EV-6 |
| Travel p50 in route autoplay | ≤ 8 s | EV-7 |
| Idiom set: actions committed by mistake (≥ 800 lines, pooled) | upper ≤ 0.5% | EV-9 |
| Slots read right (≥ 75 lines a slot kind) | lower ≥ 0.95, each kind | EV-9 |
| Card turns planned with no intent call | 100% | EV-9 |
| Model calls per turn (F3, revised) | none uses > 2, besides narration's one revision; card turns make no intent call | EV-9 |
| Parallel dialogue replies discarded | measured and reported | EV-9 |
| Proposals folded in exactly once; re-executing replay matches | 100% | EV-11 |
| Inventions carrying their play data, inside the level's budgets | 100% | EV-0 part 2 |
| Arrivals in a larger area with its detail already filled in (200-turn exploring run) | ≥ 95% | EV-10 |
| Turns that make a generation call | 0 | EV-10 |
| Linked mentions that open the entry meant (sample of 300) | ≥ 98%; lower reported | EV-12 |
| Mentions of known entries that are linked | ≥ 90% | EV-12 |
| Links to an entry the hero does not know; lore views showing a secret | 0 (tests) | EV-12 |
| First audio after a response's final text shows (Qwen speech service) | p95 ≤ 1.5 s (starting target) | EV-13 |
| Voices cast automatically that are not castable | 0 (tests) | EV-13 |
| Speaking entries played in their speaker's cast voice | 100% (tests) | EV-13 |
| Quotes in narration played in the right speaker's voice (sample of 200) | ≥ 98%; lower reported | EV-13 |
| Game master answers revealing a secret, an unlearned fact or a plan not yet played (≥ 150 questions) | 0; upper reported | EV-0 |

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
- **Document versions.** EV-1, EV-4, EV-5, EV-0 part 2 and EV-10 change the stored shape, and possibly EV-2.
  Mitigation: one version per phase, holding every shape change that lands in it, each with its upgrade.
- **Latency work touching prompts.** EV-7 may change narration prompts, which triggers the model gates (narration
  and intent).
- **Slower and costlier turns once the model reads every line.**
  - More than half of today's typed turns make no intent call; each now makes one.
  - A typed "status" or "wait" goes from about 100 ms to seconds.
  - A new speech turn makes two calls in a row.

  Mitigation: the parallel dialogue call in a conversation under way, cards for the common actions, EV-7 moved to
  phase 3, and F1's speech targets set from measurement.
- **A stale parallel reply.** A reply written for a plan that changes by commit could say the wrong thing. Mitigation:
  the reply is held until commit, and used only when the committed plan matches.
- **A third call on some typed turns.** Narration's revision, kept on typed turns, adds a few seconds when the first
  answer fails its check. Mitigation: the revision rate is reported, and N1's checks keep it rare.
- **No play without a model, except cards.** Accepted by the owner (2026-10-29).
- **Places that feel generated.** A site or a town's buildings built from a template can read as one kind repeated. Mitigation: the
  world's palette in `gm_guide`, a hook to the story for every site, and the rubric's playtest.
- **The game master gives the game away.** Talking to it, a player could learn a plan or a fact the hero has not met.
  Mitigation: nothing secret or unplayed is in its prompt for answers, code checks every answer, and the question set
  is gated at none revealed.
- **An area not ready on arrival.** A slow direction job leaves a town thin when the hero arrives. Mitigation: areas
  are filled in one area ahead, during the hero's stay next door; the rest appears on later turns; and the share
  ready on arrival is gated.
- **A filled-in world outgrows the document.** Many areas' people, places and lore could push a campaign past 1 MB.
  Mitigation: a capped fold-in per turn, F2's size check after Aurelia is filled in, and the lore layer as its own
  document part if needed.
- **A real person's voice on a character.** The voice library holds clones of real people and of other works'
  characters, unmarked. Automatic casting could put them on characters, and in other players' games. Mitigation:
  only voices marked castable are cast or offered. Those clones are never castable by default, and only their owner
  may choose them, for their own campaigns.
- **Speech competing with the model for the machine.** A local speech service beside a local model can starve
  both (the Fish model alone commits some 24 GB). Mitigation: the Qwen service as the default, voices off unless
  switched on, and failure that leaves play silent, not stopped.
- **An invention approved without its numbers.** A later campaign would meet a named item or creature that does not
  play. Mitigation: the review covers the entry and its play data together, and neither joins the world without the
  other.
- **Scripted tests lose the grammar.** The playthrough suite and the golden type commands today. Mitigation:
  scripted readings or card actions, and an explained golden diff.

## 7. For the owner to decide

Decided (2026-10-29):

- **The game master may invent** new named people, places, items, creatures and quests. Each invention is added to
  the lore, for a permanent record and a review for lore consistency (EV-0 part 2).
- **The model reads every typed line** (EV-9). Code no longer interprets the player's words. It checks the model's
  reading against the scene and the rules. The command grammar is removed.
- **Cards are the only deterministic commands.** A card carries its action and target and runs with no reading.
- **Speech takes two calls,** intent then dialogue. In a conversation under way they run in parallel, and the reply
  is used only when code confirms the line was plain talk to that person. F3 keeps "no turn makes more than two
  calls" and drops "at least 80% of turns make at most one".
- **Narration keeps its revision on typed turns:** a third call when the first narration fails its check, rather
  than the flat deterministic prose.
- **With no model, only the cards work.** A typed turn says the storyteller is unavailable.

The open questions, answered by the owner on 2026-10-29:

1. **Scope and order:** as in section 4. EV-9 with EV-3, and EV-11, come first in phase 0. EV-2 reads the player's
   words, and EV-0 needs EV-1's facts and EV-11's record.
2. **Group standing on screen:** in words, in a few bands: hostile, wary, neutral, respected, trusted. A change of
   band is told when it happens ("The Wayfarers think better of you"). The number shows only in the developer view.
3. **"What has changed":** the journal lists facts, as a line the author writes for each, never its id. Only facts
   the hero saw or was told are listed. A fact the hero has not learned shows only through its effects.
4. **Boss fights:** 8-12 rounds as the starting target, checked in the balance simulation and at the owner's
   playtest. Fleeing a boss stays possible, and a boss the hero leaves recovers part of its health. An author may mark
   a fight with no escape, such as a finale.
5. **Steps by meaning:** a step is completed by the model's proposal, checked by code, and no word list remains as a
   fallback (EV-9, EV-3).
6. **People's goals:** a person's goal may fail, and a person may leave or die, without the hero, with protections.
   These never fail, leave or die without the hero:
   - a companion in the party;
   - the giver of an open quest;
   - anyone an open quest's step needs.

   Every such beat is told: a rumour, a line in conversation, an entry in the journal.
7. **Crafting:** upgrades only, in EV-5. Recipes are decided after the owner's playtest of upgrades.
8. **Timing:**
   - EV-9 (with EV-3) and EV-11 are phase 0 engineering and start now.
   - The M2 and F1 reruns wait for EV-9, since it changes both. N1 and F2 rerun now.
   - The owner's RQ-9.2 playtest waits for EV-9, so it scores the game as players will meet it. It runs in phase 1,
     and the final scorecard (RQ-9.4) closes phase 1, grading each area as it stands.
   - Phase 1 starts when phase 0's gates pass. It does not wait on the playtest or the label review.
9. **Vesper-9:** kept lore-only, as the test of what World Forge drafts from lore (EV-6). Its three strict xfails
   become part of EV-6's gate.
10. **Where an invention lives before review:** in the campaign that met it only, until an author approves it into
    the world's lore.
11. **The game master's reach:** it may end a person's life or close a quest for good without the hero, within the
    daily limits and with question 6's protections. Each such event is told.
12. **The player can see the game master and talk to it,** to learn what is going on and why. It is a companion to
    play, not a player in it (EV-0, "Talking to the game master").
13. **Areas are filled in as the hero approaches them.** A world need not hold all its detail when it is made. When
    the hero heads for a larger area (a region, a town), the game fills in whatever the area should hold, from its
    lore: places, people, creatures, things, services, quests, rumours and local lore (EV-10). This replaces the earlier question about generating a site on the spot.
14. **The consistency check may read secrets,** for that check only, with its findings shown only to the author. The
    game master's own prompt stays public-canon only.
15. **Whose review queue:** a draft goes to the world's owner only if the owner has asked for drafts; otherwise it
    stays in the campaign. A guest's campaign never files one.

Added by the owner (2026-10-29):

- **Names open their lore.** Anything with lore that the response names (a person, a place, a group, an event) can
  be clicked to read its lore, as far as the hero knows it (EV-12).
- **Voices.** Each character and the narrator has a voice, cast by the player or automatically. A response plays by
  itself or from its play button (EV-13).

16. **Playback:** press to play by default. The player can switch auto-play on.
17. **Quoted speech inside narration** is spoken in the quoted person's voice. The narrator marks each quote with its
    speaker as it writes it.

Decided (2026-10-31):

18. **The gates' model: Claude Haiku 5.5 at low effort if it is as fast as Sonnet at low effort; it is not, so the
    reference stays Sonnet at low effort** (production roadmap Q-11). Measured on CLI 2.1.314 with the provider's
    flags: the CLI starts in about 0.5 s; on a short prompt Haiku's first text comes in 1.3-1.6 s and Sonnet's in
    2.2-2.9 s. On the game's own prompts (F1, 20 runs a class, streamed) Haiku still thinks on the narrative writer's:
    a look's first narration p50 11.0 s (Sonnet 4.1 s), an arrival's completion p50 16.2 s (Sonnet 9.3 s); the intent
    call alone is close (status p50 2.6 s, Sonnet 2.2 s). On M2's held-out set Haiku read worse (action family 0.821)
    than Sonnet did on its first 300 items (0.923).
    Revised (2026-11-01): the gates run on **Haiku 5.5 at low effort** from now on, Sonnet using too much of the
    account's tokens (a dev-split run on Sonnet hit its limit at item 556); the earlier gate numbers stay Sonnet's.

19. **F1 for typed turns, now that the model reads every line:** a narrated typed turn makes two calls in turn
    (the intent reading, then the writer), so its targets are first narration p95 ≤ 5 s and complete p50 ≤ 9 s,
    p95 ≤ 10 s. A card, the tactical route and the outcome keep theirs (deterministic ≤ 500 ms with no call; the
    outcome of a turn with an intent call p95 ≤ 3.0 s).
20. **The hourly model budget (production roadmap RQ-8.2) does not limit the install's owner.** It guards the owner's
    model account against guests, invited players and runaway scripts, at 600 turns and game-master questions an hour
    each (`session/turn_budget.is_install_owner`).

Decided (2026-11-01):

21. **M2's and N1's targets, now that the model reads every line on Haiku 5.5 at low effort:** action family and
    target entity lower bound ≥ 0.80, false stateful upper bound ≤ 1.5% (M2); correct speaker lower bound ≥ 0.95 (N1).
    The prompt rules tried for the misses left did not help on the dev split, and code reading the player's words is
    ruled out (EV-9); the targets are to be raised as the reading improves.
22. **F2's statements at p95 stay at 22** for a turn that queues game-master jobs or folds proposals in (p50 is 20).
    Merging the turn's durable-submission writes, which would bring it under 20, touches the turn's recovery
    protocol and is left for its own change.
23. **The sample sets are built and run** on Haiku 5.5 at low effort, model-written and pending the owner's spot check
    as the intent corpus is. As it went: all are built, the idiom set is run; the account's limit ended the rest
    (slots, steps, the lore links and quotes), which are not run (§8).
24. **A response's speech is streamed as live speech streams it** (EV-13): each sentence's PCM16 from the speech
    service's live-call stream on the CUDA-graph decode, heard as it arrives through the read-aloud player's audio
    worklet, and kept in the campaign's cache once whole. The live-call stream now carries the decode its caller asks
    for (it dropped `parity_mode`, so live speech over HTTP decoded in parity mode, slower than real time on a 4090,
    unless the stored settings said otherwise).

Open: none.

## 8. Status

| Package | What landed | Gate |
|---------|-------------|------|
| EV-11 The proposal record | Migration 0187: `omnix_rpg_proposals` (typed proposals by source, after a revision, with a reason) and `folded_proposals_jsonb` on turn rows. A turn folds the pending proposals of earlier revisions in at its load (`session/turn/proposals.py`), each through the rule that owns its kind (`FOLD_IN_OWNERS`, checked by `test_mechanic_owners.py`), so its plan sees them; a rewind leaves them for the turn after. The commit settles each proposal folded or dropped, only while it is still pending (`ProposalAlreadySettled` rolls the commit back), and records the folded set, payloads included, on the turn row. Pending proposals travel with a campaign's export. First kind: `heard_of` (EV-1). | Race, quit-and-return, a later revision waiting, dropped with a reason: `src/tests/rpg/playthrough/test_proposals.py` (PostgreSQL). Re-executing replay waits on EV-9. |
| EV-1 Consequences | Document version 12: `hero_knowledge` (each entry met, visited or heard of; seeded by the upgrade), `world_facts`, `group_standing`. Changes `EntryMet`, `FactSet`, `FactLearned`, `StandingChanged`. `rules/hero_knowledge.py` judges after every turn what the hero met. `rules/consequences.py`: a quest way's or an ending's `sets`, and the play sections `fact_effects` (price, an offer waived once, a seller closed, a place's line, a person's whereabouts, a group's standing, a quest opened or closed; a `fact:` pressure lever) and `group_members`, each read by the rule that owns the mechanic (trade, routines, look, dialogue stance, quest offers, pressures). The sheet shows "What has changed" and each group's standing in words (a journal tab). An ending's epilogue tells the known facts. Aurelia: facts and effects for the vow, the Loom's knights, the memory restored, the engine and the gate; Orik's first night free (W-8). | `test_consequences.py` (unit and playthrough: each engine way shows its line, the crown's standing, Valecourt's line and the smith's price). Golden diff: the new knowledge section and domain, document version 12, Orik's free night. |
| EV-9 The model reads every typed line; cards are commands (with EV-3) | The command grammar and its word lists are out of the engine: they are the scripted model's reader in tests (`tests/support/rpg_line_reader`). Every typed line goes to the intent call (`rpg.turn_intent.readings` v2), whose reading carries typed slots (`rules/intent/reading.ReadingSlots`: quantity, wait, rest, status topics, order, parting, a level's choice, topics, the quest step, a weakness), each checked against the scene and the rules; an unclear line gets the model's question; with no model, only the cards run. No rule reads the player's words: trade, items, waiting, rest, status, orders, a level's choice and the dialogue plan read ids and slots (the plan reads the topics a person may be asked of, `speaker_topics`). Every choice the game offers is a card (`Suggestion.action`), played as a `structured_action` with no model call and refused when offered before the last turn; Rest, Wait and Status cards are always offered. In a conversation under way the person's reply is written beside the intent call on their topic-free plan and used only when the turn's plan is the same (`parallel_reply`: used or discarded). EV-3: a talk step is done when the reading names it (`quest\|step\|way`) and the plan accepts it (`accepted_step`); `about` is the step's description sent to the model. EV-11's re-executing replay runs on the readings recorded. | Unit and playthrough suites, with the scripted reader. Re-executing replay: `test_reexecuting_replay.py` (a campaign re-run from its recorded readings, card, return and folded proposal hashes as it did). Gate run: the 1,000-turn re-executed replay (`scripts/rpg_living_world.py --turns 1000 --reexecute`, `docs/measurements/rpg-living-world-1000-reexecuted-2026-10-31.json`): a second campaign sent the first's 1,200 inputs (turns, returns, grid steps), its 961 intent calls answered by the readings the first was given and its turns folding in what the first's turn rows recorded (a name heard every 50 turns, 5 folded), hashes as the first after every input, answered and folded as recorded input by input, with no line read again; the patch replay verifies all 1,010 turn rows. Passes. Gate run, M2 (`docs/measurements/rpg-intent-route-2026-10-31.json`, held-out 1,200, Sonnet low): not met, family lower 0.868, target lower 0.867, false stateful upper 1.5%. The first run after EV-9 (2026-10-30) read 0.783 and 0.774; fixed from it (`session/turn/intent.py`, prompt v3): a line that asks or supposes with no reading that may be done is put to someone here who can answer (`answered`), a family aimed at nothing keeps its reading without the target the model gave it, and a refusal or a remark said aloud is talk; the eval scores a talk reading's target by the one asked or what they are asked about, and records why a turn fell back. Left: questions and remarks played as free actions, and travel asked back, for tuning on the dev split. On Haiku low, the gates' model since 2026-11-01 (`docs/measurements/rpg-intent-route-haiku-low-2026-11-01.json`): family lower 0.802, target lower 0.821, false stateful upper 1.1%, not met; a thing in the scene may now be what a question asks about (`ReadingSlots.topics`, and the person answers from its open kind and effect). Five prompt rules for what is left (a line that does two things, a gesture at someone, a journey however said, a question with no deed, a person by their calling) were measured on the dev split and dropped: no better (0.888 against 0.894 on the 555 items before the account's limit cut the run). The dev split also found a launch bug: a published world never kept the gear a player chose (the new game keeps it in its metadata; the launch looked on the hero's sheet), so the opening's kit replaced it and a world to come reskinned it (`test_chosen_gear.py`). F1 is the EV-7 row's. Gate run, the idiom set (`docs/measurements/rpg-idiom-set-haiku-low-2026-11-01.json`, 844 lines over three worlds, Haiku low, the prompt as it stands, v4): 11 lines acted on, 1.3%, upper bound 2.3%, **not met** (≤ 0.5%, which at 844 lines allows none): eight reports of what someone advised ("Bran said I should go to the market") and three figures of speech. A prompt rule for the reports brought it to 3 of 844 on this set but is not adopted: M2 could not be rerun on it before the account's limit, and M2 clears its target by little. Not yet run: the slot set (689 lines) and EV-3's held-out steps (630 lines); the sets and `scripts/rpg_reading_eval.py` are built, and no model has read them yet. |
| EV-2 Combat depth and pacing | A weakness the reading names (scene: each creature's weaknesses as names) stuns, hurts more or breaks a foe's nerve; `resists` blunts a weapon of that `material`; bosses fight in `phases` (harder, an ally called, the weakness laid bare); `no_escape` refuses breaking away and its cards offer none; a boss left keeps part of its wounds (`recovers`, half by default for a boss); one of the party guards another (`GuardSet`), and a companion ordered to guard or flank fights so (`PhaseEntered`, `GuardSet`; the orders allowed in a fight). Fight cards: a known weakness, the companions' orders, ready abilities. A calling starts with two abilities. `rules/budgets.py`: the level budget table (a `budgets` play section, derived by default; bundle format version 2, version 1 still imported), read by the road's encounters. The balance simulation measures fight length and a boss fight's potion share. Aurelia: every creature's weakness usable, the Hollow Archon in three phases with no escape, Echoes resisting plain steel, its weapons' materials. | `test_fight_depth.py` (each mechanic), `test_combat_depth.py` (Aurelia: an Echo Wolf flees contradictory commands; a companion stands guard). Pacing targets measured, not yet held. |
| EV-0 The game master, part 1 | Document version 13: the game master's bookkeeping (`direction`: the turn of the last meaningful event, the day's count of its events, a scene's complication, the player's wishes; `DirectionTracked`, `PreferenceNoted`, the mechanic `note_preference`). `rules/direction.py`: meaningful events, a stall after 8 turns, at most 3 of its events a day and 1 complication a scene, protected people. The direction call (`rpg.game_master.direction` v3), a job after a turn commits (`rpg.game_master`): on a scene's end, a return after time away, or a stall, it reads the public canon, the state, the facts, the wishes and the palette (creatures sized to the hero's level) and proposes from a closed set; code checks each proposal before it is stored (ids, no secret, no protected person moved), and the next turn folds it in through its owning rule (`gm_fact`, `gm_complication`, `gm_quest_offer`, `gm_move_person`, `gm_encounter`, and with EV-4 `gm_beat`, `gm_rumour`). The panel (migration 0188, `/api/rpg/sessions/{id}/game-master`, a "Game master" tab): a question answered from what the hero knows (`rpg.game_master.panel` v1), changing nothing, counted against the hourly budget, an answer that would tell a secret withheld, a wish offered as a card to confirm. | `test_game_master.py` (unit and playthrough: no question changes the campaign, a secret is withheld, a wish is a confirmed card, direction reaches the campaign only through the next turn). Gate run, the panel (`scripts/rpg_panel_eval.py`, `docs/measurements/rpg-game-master-panel-2026-10-31.json`, Sonnet low): the frozen set of 150 questions (`resources/benchmarks/rpg/game_master_panel/`, 30 at each of five points of an Aurelia campaign: secrets, unmet entries, plans, unlearned facts, fair questions, requests to act, attempts to break its rules) asked through the panel's route; no answer tells a secret, an unmet entry, an unlearned fact or a plan, by code or by a judge that sees them and what the hero has been shown (upper bound 2.5%); 149 shown, 1 withheld; no question changes the campaign. Found by it, and fixed: the panel withheld nearly every fair answer, because its check withheld any name the hero had not met, though its own view showed it (a quest's "Reach Starfall Village"); a name the hero has been shown, a road from where they stand, or one the player used in the question is theirs. Not yet run: the proposal measures over route autoplay and a judged run. |
| EV-4 People who act on their goals | A goal's `beats` (the routines section): ordered steps, each with a chance a day, a condition (facts, a place the hero has been, a day), the facts it sets, a move, and the word that goes about. On each day the clock crosses, the world tick advances each goal's next ready beat by a roll seeded by the campaign, the day and the beat, at most 3 a day (`rules/routines.daily_beats`); a beat never moves a protected person; the game master may bring one forward (`gm_beat`). `rules/rumours.py`: `RumourSpread` at the beat's places (or the game master's, `gm_rumour`), told by someone of the place asked for news (a "news" topic of the dialogue plan), sold by paid information, or heard by being there (`RumourHeard`, and the facts the beat set become known); the journal's "What has changed" lists the word heard. A fact a beat or a proposal sets now fires its world's `fact_effects` as a quest's does. Document version 14 (`npc_goal_state`, `active_rumors` in the new shape; older entries, read by nothing on the pipeline, dropped). World creation keeps its own rumour system (`world/social/rumor_system.py`); the sandbox projection reads both shapes. Aurelia: eleven beats over nine people. | `test_beats_and_rumours.py` (unit). Gate run: `test_goal_beats.py`, a 200-turn Aurelia run with at least eight beats reached and the word of each heard (passes). Gate run: the 1,000-turn re-executed replay (`scripts/rpg_living_world.py --turns 1000 --reexecute`, `docs/measurements/rpg-living-world-1000-reexecuted-2026-10-31.json`): a second campaign sent the first's 1,200 inputs (turns, returns, grid steps), its 961 intent calls answered by the readings the first was given and its turns folding in what the first's turn rows recorded (a name heard every 50 turns, 5 folded), hashes as the first after every input, answered and folded as recorded input by input, with no line read again; the patch replay verifies all 1,010 turn rows. Passes. |
| EV-12 Names that open their lore | `narration/lore_links.py`: the narrator marks what it names (`[[words\|id]]`, the writer's prompt v4); marks never reach the text (drafts strip them, the writer notes and strips them before its checks) and only settle which entry a shared name means. The links are worked out on the final text (`visible_response.links`: the narration's and each message's spans), from every name of an entry the hero may be shown, as written; a hidden or secret entry is never linked. A link of an entry the hero did not know is a `heard_of` narration proposal, folded in by the next turn. Read-only routes: `/lore/linkable` (the names a text may link) and `/lore/entries/{id}` (public lore, what the hero has learned, links onward; no lock, no model call, no write). Web: names in the story, the journal and the lore entry are buttons that open the entry beside the story (`rpgLoreLinks.tsx`, `RpgLoreEntryPanel.tsx`). The dialogue call's line is linked from its names (its prompt is not told ids). | `test_lore_links.py` (unit and playthrough: the right target, nothing hidden linked or shown, no draft shows a mark, no cost, heard of only through the next turn's fold). Gate run, N1 (`docs/measurements/rpg-narration-2026-10-31.json`, 900 judged turns, Sonnet low): contradictions upper 0.6% and near-duplicates 0.45%, met; correct speaker lower 0.961, not met (a line to someone read as a look, a person named by what they do read as no one or the wrong one: the intent reading's, with M2). Found by it: a look at someone away failed the turn with a server error (their lore is not the scene's); a person away is now told where their day has them (`resolution._not_here`, shared with talk) and a creature not here is no reading (`test_absent_people.py`). Not yet run: the 300-mention target sample and the 100-response coverage sample (`scripts/rpg_lore_voice_eval.py` is built; its one run met the account's limit and gave no result), and the 360/1,440 px UI checks. |
| EV-0 The game master, part 2: invention | `rules/inventions.py` (`gm_invent`): a person, place, item, creature or quest with its play data (a person's home, day and knowledge; a place's roads; an item's gear and where it lies or who sells it; a creature's numbers; a quest's steps and reward), checked before it is played (a campaign id, no clash with the canon's names, references the hero may be shown, the level's budgets, no contradicted fact, no secret). `InventionAdded` keeps it in the campaign's lore layer (document version 15) and adds it to the effective world model, where every rule reads it. The review queue (migration 0189, `/api/rpg/worlds/{id}/lore-review`): at the commit an invention is filed for its world's owner where question 15 says (a world the player owns, or one whose owner asked for drafts; never a guest's); a model consistency check reports findings to the author (`rpg.lore_review.consistency` v1); approve (with an edit), reject or link to an approved one; an approved entry gets a canon id and joins the world, with its play data, at its next publication (`genesis/worlds/approved_inventions.py`). | `test_inventions.py` (unit and playthrough: an invented person keeps her day, an invented blade lies where the hero can take it or is sold within the budget, refusals, filing, approval, the next revision's canon). The re-executed replay folds what turn rows recorded whatever their kind (the 1,000-turn run's are narration's); the game master's job is a model call the harness does not make. Not yet run: the consistency check's calibration, the proposal measures and the replay with the game master's own proposals. |
| EV-10 Areas filled in | Areas are regions. `rules/budgets.area_budget`: what an area holds, by size (a world's `gm_guide` may set it), authored places and people counted. The area call (`rpg.game_master.area` v1), a job once an area a campaign when the hero arrives next to it (and at the first turn), writes the area's entries as `gm_area` proposals; a turn folds at most 10 (and 24 KB), places first (`session/turn/proposals.py`), through `rules/inventions.fold_area_entry` (`AreaDetailed`; a rumour goes about, lore is kept). `rules/exploration.py`: the `explore` mechanic and intent family, a seeded search against a hidden place's difficulty (`SiteFound`, joining the roads); a site's fixed shape built by code (rooms in a line, an encounter in each sized to the hero's level, the last the boss's, the reward among the world's things); a room's encounter met on arrival and its clearing recorded (`RoomCleared`). Document version 16 (`area_detail`, `exploration`). Aurelia: a `gm_guide` palette for its five regions. Each room has its own grid, laid out by code from the site's seeded stream and kept in the lore layer; the commit stores it as the campaign's map definition (migration 0191: a definition may belong to a campaign, and goes with it), so the hero stands on it. Some rooms hold a hazard (a ledge, a tripwire, a pit), met once on arriving by a seeded check; failed, it hurts. | `test_areas_and_exploration.py` (unit), `test_areas.py` (playthrough: a scripted site from finding it to its reward, each room on its own grid, no generation call on the turn). F2 rerun (2026-10-31, `docs/measurements/rpg-turn-overhead-2026-10-31.json`, 200 turns a size): player turn p95 130.7 ms at 1 MB, inside 150 ms; statements p50 21, p95 24, past 20 (21 and 22 before this roadmap): the pending-proposals read was one a turn (EV-11), and each game-master job an arrival queues three (EV-0, the areas here). Since: a turn reads the proposals only when its launch gate's read finds one pending, and a job just made is not read back for logs it cannot have; the rerun reads p50 20 and p95 22 (132.0 ms at 1 MB): a turn that folds an area's detail in reads and settles its proposals, and one that queues jobs writes two statements each. Below 20 at p95 is the turn's own durable writes to merge (its submission's four statements, narration's three), a persistence change of its own. The timed autoplay's harness is `scripts/rpg_area_autoplay.py`: a worker thread runs the RPG's jobs beside the turns as the job worker does, and an arrival counts as filled in when the region's detail is there after its turn (`--wait` for the run that does not depend on timing). Found with it: a stall asked the game master on every turn past `STALL_TURNS` (53 of 60 turns, a model that could not move the hero); it asks once each stretch now. Gate run, timed (2026-10-31, `docs/measurements/rpg-area-autoplay-2026-10-31.json`, 200 turns, Sonnet low, the job worker's two LLM slots): every arrival filled in, 3 of 3 (Cloudspine 14 entries, Moonroot Deep 10, Ashen East 13); every area's entries inside its budget; all 38 jobs completed. Found on the way, and fixed: the areas next to the hero were those their place's roads reach, so an area was queued one step before the hero crossed into it (it is now every area a road from any of the area's places reaches, the hero's whole stay); nothing was queued at launch (now the launch routes queue the start's areas, `fill_areas_at_launch`); a fill waited behind the game master's direction jobs (fills now go first, the areas ahead before the one the hero stands in). The harness plays an explorer that stays five turns in an area and fights what it meets. The run that waits for each job (`docs/measurements/rpg-area-autoplay-wait-2026-10-31.json`): 4 of 4 arrivals filled in (Cloudspine 12 entries, Moonroot Deep 9, Ashen East 13, Meridian Heartland 20), inside the budgets, all 52 jobs completed. Both runs pass. |
| EV-7 Response time | A journey to a place further off is one turn by the shortest way, at most four roads, stopping where a quest's place is reached or the road is barred (`session/turn/travel.py`). The scene's lore evidence is built once for a scene at a canon (`genesis/forge/turn_grounding._scene_lore`, kept by both bible snapshots' hashes, the scene's entries, the place and the time of day). Narration already streams from its first sentence (EV-9's drafts). The arrival is prepared while travel resolves: as soon as a journey's destination is known, its local map (the campaign's instance, else its definition) is read beside the travel rule, and the turn finds it read (`session/turn/local_map.prepare_arrival`). | `test_turn_travel.py`, `test_scene_lore_cache.py`, `test_arrival_prepare.py`. Gate run (2026-10-31, `docs/measurements/rpg-latency-route-stream-sonnet-low-2026-10-31.json`, 20 runs a class, streamed): not met. Since EV-9 a narrated turn makes two model calls one after the other, the intent call (about 2 s; the CLI starts in 0.5 s of it) and then the writer: complete p50 7.5-9.3 s against 6 s, first narration p95 4.5-4.7 s against 2.5 s; the outcome is visible at p95 2.2-2.5 s, inside the intent turn's 3.0 s, and the tactical route takes 88 ms. Haiku at low effort is slower (question 18). F3, as the owner revised it, is met: no turn makes more than two calls but for one narration revision. Against the typed-turn targets the owner set (question 19: first narration p95 ≤ 5 s, complete p50 ≤ 9 s, p95 ≤ 10 s): first narration p95 4.5-4.7 s and complete p95 8.3-9.9 s are met in every class; complete p50 is met for look (7.5 s), buy (7.7) and fight (7.8), not for an arrival (9.3), whose narration is the longest (model time 9.1 s; the engine's 160 ms). With a fast local model (`liquid/lfm2.5-1.2b` through LM Studio, `OMNIX_RPG_GATE_PROVIDER=lmstudio`, `docs/measurements/rpg-latency-route-stream-lfm2.5-1.2b-2026-10-31.json`) a turn completes in 0.9-2.4 s and its outcome is visible at 170-380 ms; the game's own time outside the model is 120-180 ms a turn in every class (32 ms a tactical move), so the rest of a turn is the model's. That model's narration fails the writer's checks, so most turns asked the writer three times; its readings are not judged. Not yet run: travel p50 in route autoplay. |
| EV-5 Upgrades | The service kind `upgrade` and its `recipe` (the slots it improves, materials a tier, what a tier adds, the last tier) in the economy section; the trade rule's `improve` (`ItemImproved`) for materials and coin, priced by the tier, no further than the hero's level's budget for the slot. Document version 17 (carried gear has its tier). Aurelia: Hollis improves a blade or armour with Aether Shards; Brindle tunes a weapon. Gear is improved as it fights: a world's own weapon with no block of its own ("Iron Dagger") is improved as its kind, the block written (`ItemImproved.slot`), and an unnamed upgrade takes the piece the hero wears first. | `test_upgrades.py`. Gate run: the balance simulation's player now equips and buys better gear with coin to spare and has it improved where the trade rule would do it (`scripts/rpg_balance_sim.py`); in a finale, which has no breaking away, it drinks a potion or fights on. `test_balance.py` asserts EV-5's bands for Aurelia: coin spent rises from 100 turns to 500, and the worn gear's numbers are higher at 500 than at 100 (a run: gear 7 at 100 turns and 11 at 500, 264 and 964 copper spent, level 8, win rate 0.897, inside 0.55-0.90). Passes, with the starter world's pending win rate unchanged. |
| EV-6 Authoring in the editor | The play-section form: the economy's upgrades and recipes, a goal's beats, the facts a way or a quest's completion sets and the facts it requires or forbids, the bestiary's resistances, no-escape, recovery and phases, and a new "Consequences" section for `fact_effects`. The review queue's screen ("Inventions to Review": provenance, findings, check, approve, reject, link). World Forge drafts quests' steps (their places, then the giver), a first beat on every goal, and the world's gear for sale. The entity editor's form writes an item's gear (slot, numbers, material) and a character's home, aliases and group (`RpgEntityPlayFields.tsx`); play reads them (a character's aliases and group, and a person's group counts as membership). The collection's heading adds an entry (`RpgAddWorldEntity.tsx`; `POST /api/rpg/worlds/{world_id}/topics/{topic_id}/entities`, `genesis/worlds/entity_authoring.add_world_entity`, revision- and hash-checked), its id, kind and name, the rest then written in its editor. The entry functions work on every list of entries the editor shows (`authoring_presentations.ENTRY_LISTS`: a generated topic's `entities`, a bundle's `characters`, `items`, ...), an entry kept and added where its topic keeps them (`entry_list_for`). Found and fixed on the way: a world written by hand or installed from a bundle (no generation run) was republished as its canon stood, so nothing its editor changed reached play; its republication now writes the editor's entries into the canon by id (`genesis/worlds/topic_entries.py`; the editor's own marks left out), and a launch reuses a revision only while its canon holds them. Such a world's topics stay at the draft they were installed at while its draft advances, so every entry and topic edit was refused as a revision conflict; a write is taken at the world's draft or the topic's own, and the entry functions read the topics as the editor holds them. Adding an entry failed on the history table's check (migration 0193 allows `manual_add`). Aurelia's people, items, gear and quest rewards are its bundle's own topics; `lore-additions.json` keeps only the game master's palette and the maps. | `RpgWorldPlaySectionsPanel.test.tsx`, `RpgLoreReviewPanel.test.tsx`, `RpgEntityPlayFields.test.tsx`, `test_play_sections_authoring.py`, `test_rpg_world_entity_authoring_routes.py` (adding an entry), `test_rpg_world_entity_authoring.py` (entries in a bundle's lists; republication into canon), and `test_editor_entries_play.py` (PostgreSQL: Aurelia imported, a person added and a blade's gear changed through the entry functions, published, and both in a campaign launched after). The web typecheck (`tsc -b`, run with the owner's permission 2026-10-30) passes after two fixes: the play-sections readiness contract lists every section (`fact_effects`, `group_members`, `budgets`), and the upgrade recipe is `UpgradeRecipe` (its schema had taken the voice automation's `Recipe` name). Not yet run: a second world authored only in the editor, the core-task UI checks. |
| EV-13 Voices | The castable list (`resources/voice_clones/casting.json`; a voice not listed as castable is never cast or offered) with each voice's description and revision (`platform/voice/voice_casting.py`). The campaign's cast (migration 0190, outside the document): the narrator and everyone heard or met, cast deterministically by the campaign and the person among castable voices only, the author's castable choice kept, no voice shared in a scene while the list has enough; the player's choice wins (`/api/rpg/sessions/{id}/voices`). A final response is planned for speech from its shown text, block by block in its speakers' voices, by sentence (`/speech-plan`). A quote inside narration is spoken in its speaker's voice: the narrator marks it (`<<id\|"the quote">>`, the writer's prompt v5), the mark is kept for someone in the scene or who has spoken before, and the response carries `voices`. Each sentence's audio comes from the campaign's audio cache (migration 0192: by its full render identity, in the player's workspace, deleted with the campaign), else is streamed from the speech service's live-call stream on the CUDA-graph decode as it is synthesized, as PCM16, with live chat's token budget for its text, and kept once whole; a stream that breaks or runs out its budget is not kept, and a device busy for a moment is tried once more (`/speech-audio`, `tts_service.stream_audio_pcm16`). The page hears a response as one stream: each sentence pushed as it arrives into the read-aloud player's audio worklet (`rpgSpeechSink.ts`), the next asked for when the one before has arrived. Found by the speed gate (2026-11-01): `/speech-audio` posted to a `/tts` route the speech service does not have (only the in-process fake had answered it), then spoke in the parity decode (6–10 s a sentence); and the service's live-call stream dropped `parity_mode`, so every live stream over HTTP decoded in parity mode (1.3–1.6× slower than real time) unless the stored settings said otherwise: it now carries the decode its caller asks for (§7 decision 24). Web: a play button on each finished entry (none on a response still being written), a Voices tab with a preview and the choice, auto-play off until switched on; with the speech service down the text stands, silent, and the screen says so. Only two voices are castable: the library's clones are left off until their owner marks them. | `test_voice_cast.py`, `test_lore_links.py` (quotes), `test_voices.py` (playthrough: the cast, the speech plan, a sentence streamed once then played from the cache, a broken or runaway stream not kept, a busy device tried again, a service down silent), `test_tts_service_generation.py`, `test_tts_server_runtime.py` and `test_qwen_http_gateway.py` (the stream's decode reaches the engine), `RpgVoicesPanel.test.tsx`, `rpgVoices.test.ts` (sentences streamed into one sink as they arrive, a failure silent, a stop ending the request). Gate run, first audio (`docs/measurements/rpg-first-audio-2026-11-01.json`, `scripts/rpg_first_audio_eval.py`: 75 responses of Aurelia's prose over HTTP, Qwen3-TTS 0.6B on the owner's RTX 4090, both castable voices; from the final text to the player's start, the page's own audio set-up not in it): p50 250 ms, p95 313 ms, **met** (≤ 1.5 s); no runaway and no wait in simulated playback over 603 s of audio; from the cache p50 35 ms. Before the fixes: p50 9.8 s (parity, whole sentences), then p95 2.75 s (CUDA-graph, whole sentences). The live-call stream itself: first audio 0.18–0.25 s and 0.16–0.23× real time on the CUDA-graph decode, against 1.0–1.3 s and 1.3–1.6× in parity mode. Not yet run: the 200-quote speaker sample (with EV-12's, above), the desktop real-speech check, the UI checks, and speech heard in a real browser. RPG speech shares the realtime lane with live calls: during a call a sentence may be silent, and a call may be refused while a sentence is synthesized (from reading the code). |
| EV-8 Content | Orik's free night landed with EV-1; Vesper-9 stays lore-only (question 9). The maps of Valecourt (the city gate, Foundry Row, the palace workshops, the canal) and Cinderhold (the ash gate, the shrine court, the ward): square grids written in `lore-additions.json` and put into the source world by the author script (`with_maps`: a definition for every world revision, a blueprint, a binding in every release, the place's `map_id`), as grids without artwork yet. Aurelia now has seven maps. | `test_aurelia_maps.py` (playthrough: both places have maps, and a hero arriving in Valecourt stands on its grid); the bundle test's counts. |

**Review (2026-10-30).** Two review agents read the whole change, one the engine and state, one the edge, narration and
web. Fixed from it:
- an invented item's every number now sits in its slot's budget (a ring did damage; a blade's least damage passed
  its most), and its home, roads and places must be places;
- an invented quest's steps are written as the quest rule reads them;
- a fact already holding its value is not set again, so its one-time effects fire once;
- the game master sets no fact an authored quest or effect ties to the hero's deeds;
- a folded proposal's effects run even on a turn that does nothing in the world, and on a return after time away;
- a game master's move outlasts the person's own day; beats keep the time they happened;
- the game master's rumours get ids of their own;
- the author's guide is filtered for secrets before a game-master prompt;
- the scene-lore cache key holds the campaign, both canons' revisions and what is discovered;
- lore marks are cleared each turn, matched only as written, and an unclosed mark keeps its words;
- an area fill that fails is retried;
- a voice no longer castable is recast, the player's choice outranks the author's, and only someone who speaks can
  be given a voice;
- an approval must name only approved inventions, and can be withdrawn, and approvals are a reserved metadata key
  that joins the manifest;
- the review queue's read takes no lock, and a link stays within its world;
- auto-play plays only a final response after the page settles;
- link offsets are counted the page's way;
- the turn-path list now holds the new modules, read through accessors.

The three left open from it are now fixed too:
- `/lore/linkable` lists only what the hero knows, and the entry view opens an entry they know or one a response has
  just named (a pending `heard_of`), as far as they know it (`test_lore_links.py`);
- a rewind drops the undone timeline's pending proposals (`rpg_proposals.drop_undone`; `test_rewind.py`);
- the re-executing replay folds each turn in from the set its turn row recorded (`folded_proposals_jsonb`, through
  `proposals.replay_folded`), not the store, and checks the re-run records the same (`test_reexecuting_replay.py`).

A third review read the last round (EV-6, EV-7, EV-8, EV-10, EV-13). Fixed from it:
- a journey stops at each room that still holds its encounter or hazard, and a hazard never brings the hero down;
- an imported campaign has its rooms' grids rebuilt from its document before its map instances;
- deleting a campaign removes its own map definitions (a test proves it);
- auto-play waits for a campaign's history and for a response still being written, and skips notices; leaving a
  campaign stops its voices, and a stopped sentence lets its audio go;
- the speech cache keys on the voice's current revision and the speech service, and takes one sentence at a time;
- the aliases field keeps what is typed;
- the arrival's reads are locked, one journey a campaign;
- a group's own members outrank a person's lore;
- Valecourt's Foundry Row is on open ground;
- quote offsets are counted the page's way.

A fourth review (two agents, 2026-10-31) read what was built after the third: the gear upgrade fixes, the intent
reading's answer to a question, the editor's entries and their publication, migration 0193, the stall trigger, and the
gate harnesses. Fixed from it:
- a republished revision records the editor's entries it was made from, and a launch reuses a revision of a world
  with nothing to recompile from only while the editor holds the same (by that record, or by its canon for one made
  before it), whichever branch made it; an entry added or changed must name only what the world holds;
- a generated world's editor reads its draft's topics, and only a world with no generation run takes a write at its
  topic's own draft; a list's items that are not entries survive an edit; openings are read from either list;
- gear is read as it fights from its definition first, an unnamed upgrade takes a piece that can still be improved,
  and a block with no slot gets one;
- a line asks when its best reading does;
- the area gate's worker runs only its campaign's jobs, every write under the job's lease, and the run waits for
  every job and reads each one's final state; the re-executed replay must be answered and folded as recorded, input
  by input, and cannot read a line again; the intent eval credits a topic only for talk; F3 forgives one revision;
  the balance simulation counts only purchases as spent and only a potion drunk.

A fifth review (2026-10-31) read what came after the fourth. Fixed from it:
- a new game from the wizard (the genesis contract the web client sends) is filled in ahead at launch too, and at
  launch the starting area comes first (the first turns' searches read it);
- a check aimed at someone away (persuade, intimidate, deceive) is told where they are, as a look or talk is, with no
  roll and no change to their regard; a guard for creatures not here that could not fire (the scene offers every
  creature of the bestiary) is gone;
- the launch fill reads the campaign's revision through its accessor;
- the area gate's harness counts the game's own refusals and records every turn.

A sixth review (2026-11-01) read the speech streaming, and a seventh the branch against main before its merge: the
migrations on live data, what main's live portrait changed beside it, and what must not reach main. It found no
blocking defect (no database-backed test ran in it). Fixed from them:
- a sentence has live chat's token budget, and audio that ran out its budget is not kept: 13 of 60 sentences had run
  to the cap and would have been played from the cache for good;
- a cache write that fails no longer breaks a response already heard;
- the page: a failure leaves the text silent and lets the audio go, a stop ends the requests in flight, and a browser
  holding audio back is silent rather than waiting for ever;
- the live-call stream forwards only `parity_mode`: `non_streaming_mode` would have changed how text reaches the model
  for every live caller, which nobody decided;
- the first-audio harness counts the player's start and runaways, and rebuffers as the worklet does.

The live database was already at migration 0193 before the merge (applied 24-30 October), so merging left none
pending; the merge commit's message says otherwise and is wrong. Owner (2026-11-02): the 16 archived campaigns past
migration 0171's 30 days go at the next retention sweep. A backup taken first holds them, outside the repository.

