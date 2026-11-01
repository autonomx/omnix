# Playtest: Aurelia, played as a player (2026-10-26)

An engineering playtest: the RPG's play routes on a scratch database, the narrator and every model call on Claude
Sonnet at low effort (the Claude CLI), and turns written as a player writes them. It looks for what is broken,
incoherent or out of the world's lore, and fixes it as it goes. It does not replace the owner's playtest (RQ-9.2),
which judges whether the game is fun.

Aurelia was chosen over Vesper-9: its author wrote how it plays (economy, routines, knowledge, pressures, bestiary)
and it has six quest arcs to an ending; Vesper-9 is lore-only and is worth a shorter session of its own.

## Session 1: Starfall Grove to the Wayfarers' Guild (turns 1-20)

What worked: Liora, Brindle, Miri and Seraphine each spoke in their own voice and from their lore (Seraphine on the
royal Meridian engine and the Cataclysm, Brindle's radio to Earth). Asking Liora to travel along made her a
companion. Arriving in Starfall Village advanced both quests and paid a first visit's experience; the guild finished
the first quest (20 silver, a Wayfarer Sigil, level 2) and eased the roads' pressure. The level's choice ("improve
swordsmanship and defense") ranked both skills with no model call.

Found and fixed:

| What the player met | Cause | Fix |
|---|---|---|
| "Liora, where am I? I woke up here..." was answered by the narrator, as a look | a question counted only when the whole text ended in "?"; "where am I" then matched the look rule before the name was read | a first sentence ending in "?" is a question; a name and a comma first is speech to that person |
| Liora joined the party; the play screen's party panel stayed empty | the reducer wrote the simulation's party only, never the sheet's `state.party` the screen reads | joining, leaving and a companion's health now project the sheet's party |
| Asked what to do first, Liora said only "stick close"; asked how to mend the phone, Brindle wanted "aether-coil wire" (an errand the game does not have) | the dialogue plan knew nothing of the hero's quests | the plan carries the hero's quests the speaker bears on (theirs, at their place, naming them, or any for a companion), each with where the game says it goes on, and those done; the line points there and invents no task, item or requirement |
| "the plan holds no posted contracts" | the line writer was told of "the PLAN" and said so | it is told never to speak of the plan itself |
| The Wayfarers' Guild's registrar had no contract to offer | a quest was offered only by its giver or at its place | someone whose role hands out work (a registrar, a quartermaster, a bounty clerk) offers a quest no one gave, wherever it is |
| A newcomer asking for work was offered the finale (The Hollow Meridian) | offers were ranked by the words asked, then the speaker's goals | a finale is the last thing offered for work in general |
| Three of Aurelia's six quests (the bridge, the burned memory, the princess's engine) could never be offered | only the opening's quests were in the campaign's log | the world model carries every quest the world has; one not in the log can be offered, and joins it |
| Level 2 was reached and nothing said a choice waited | the level's choice was neither offered nor in the status answer | a waiting choice leads the suggestions ("raise strength", "improve <the two skills practised most>") and the status names it and how to choose |
| A hero of Aurelia (high fantasy) had firearms and hacking | one skill list for every world | a new hero's skills are those of their world's kind (fantasy: magic and archery; a future: firearms and hacking) |
| "your task is to repair the protagonist's phone" | the author writes "the protagonist" for the hero | a quest's title, objective and hook are put to the hero ("Repair your phone"; "recruit you") |
| Liora's lines kept coming back to "before the Grove gets ideas" | the line writer was told not to repeat recent exchanges, but kept their images | it is told not to reuse a phrase, image or saying of its own recent lines |

Noted, not changed:

- The first quest finishes on reaching the guild, before the hero registers or chooses a companion: the author wrote
  it as places only, with no steps.
- The outcome card said "+2 gold" where the narration said "20 silver" (the same sum).
- A plain "look around" took 6-16 s and two model calls on the CLI route.

## Session 2: a fresh campaign, the wolf contract, a night at the inn (turns 1-55)

The fixes of session 1 held on a fresh campaign: Liora answered the first line herself and pointed to the village
and the guild, the party panel listed her, the quest log read "Repair your phone". Captain Rhea offered the echo-wolf
contract on arrival, the hunt at Skybridge Pass took three fights (one wolf fled, as the bestiary has it), the
contract asked to be reported to the captain, her routine had her at the pass by night and at the village gate on
watch, and reporting it paid its reward. Level 3 came with its choices, each made with no model call.

Found and fixed:

| What the player met | Cause | Fix |
|---|---|---|
| "I hunt for echo wolves along the pass" came to nothing, while "I attack an echo wolf" found one | seeking a creature by name was read as a free action | hunting, tracking or looking for a creature the world has is how its fight begins, where it is met |
| Asked where the wolves were, the captain named Valecourt and Cinderhold, far-off capitals | a hunt with no place of its own was pointed at the world's first places no one lives in | the nearest such places by road (Skybridge Pass) |
| Brindle, asked "what do you have for sale?", had nothing priced | "sale" was not one of the words that bring a seller's wares into the plan | sale, shop and merchandise are |
| Brindle said a potion was 3 silver; the counter took 3 silver 6 copper | the plan quoted the offer's list price, the trade rule charges the roads' fifth | the plan quotes the price the trade rule charges now |
| "Your 'Voices in the Phone' task" | the line writer quoted quest titles | it says where a quest goes on in the speaker's own words, never quoting a title |
| "I accept the quest The Hollow Meridian." was suggested on every screen | the first quest on offer was suggested | one someone offered first, a finale last |
| "Orik, I'd like a room for the night" was talk, and "I sleep until morning" was then refused | a name and a comma made the turn speech, whatever the words after it did; "I'd like" was no purchase | the words after a name are read as a command of their own: a deed is the turn (a room bought from Orik), a remark or a look is said to them; "I'd like", "I want", "can I get" something on sale buys it; "give me a room" asks for one |
| "Orik Stonewake offers A night's lodging" | an offer's label opens with a capitalised article | inside a sentence it reads "a night's lodging" |
| "Word comes: The Memory Loom stirs grows worse" | the pressure was named as a sentence (this roadmap's own authoring, Q-10) | renamed "Restlessness in the Memory Loom" in Aurelia's play sections, the bundle regenerated through the library's lifecycle |
| A room taken at 20:36 was slept in for eight hours; the hero woke at 04:36 to a village asleep, the narration saying "by morning" | a night's sleep was eight hours whenever it began | it lasts until the next 08:00 when that is within 12 hours, never less than eight hours |
| The captain's contract was finished and her regard did not move | a quest failed cost its giver 10; one done earned nothing | one done earns its giver 10; the last step is told by the quest's completion, not echoed before it |
| "at this hour, Princess is at Valecourt" | two copies of the name-in-passing helper, neither knowing Princess, Archon or Saint | one helper (`foundation/state/people.called`) with the world's ranks and stations |

Noted, not changed:

- A narrated turn on the CLI route records a "provider" call besides the narrative writer's (two per turn); the
  scripted golden records one. To trace.
- Fights at level 1 run five to seven rounds against a 10-health wolf (hits of 1-5); fights took 5-16 s a round.
- Two replies came back without their outcome section ("planned None" in the playtest client); the play screen
  reads the same reply. To trace.
- Some dialogue turns made four calls.

## Session 3: the whole campaign, to the gate's fate (turns 1-176)

A fresh campaign played to its end: every one of Aurelia's six quests, the roads contract, level 7, Liora and Vael in
the party. Before it could be played, two things had to change. Every quest was places only, so each, the finale too,
was done on arriving (Seraphine's engine was "decided" by reaching Valecourt). And the world's four roads never reached
Valecourt, Cinderhold or the Hollow Meridian, so the finale could not be reached at all.

The run: Liora joined in the grove; the first night ended at the guild with Miri's registry and a companion chosen;
Seraphine's summons led to Valecourt, where she holds court each evening, and to the choice (democratized, which she
remembered afterwards); Orik's daughter's memory was won back past the Loom's Rootbound Knights (a level-6 knight
fought once, then the knights' broken oath named, the other way through) and paid the Moonroot Key; the phone's voice
was followed to the ruins and named by Elyra; Vael's vow was witnessed, the pass crossed and the gale kept faith with
by a climb; then, with the key, the descent, Malrec confronted ("the harvest of what Earth's children never knew they
could spare"), the Hollow Archon (level 10, 120 health) fought for some 40 rounds with three potions, Vael striking the
last blow, and the gate made a guarded bridge.

Found and fixed:

| What the player met | Cause | Fix |
|---|---|---|
| Every quest done on arriving; the finale with no fight and no choice | Aurelia's quests were authored as places only | a quest's steps are a play section (steps of ways of conditions, a giver, a deadline; How It Plays edits them); Aurelia's author wrote all six |
| "Choose a first companion" could not be a step | no condition said it | a `companion` condition (someone named, or anyone) |
| No road to Valecourt, Cinderhold or the Hollow Meridian | the world's four roads left three places unreached | a place no road reaches is joined to the roads, from its region's capital |
| A grown hero won nearly every fight there was | the bestiary topped at level 3 below a level-8 boss | Aurelia's author wrote its creatures' numbers: mantas 4, wights 5, the Loom's knights 6, the Archon 10 |
| "Liora, will you come with me to the village?" asked Captain Rhea | one word of a calling ("village" of the "village guard captain") named her | a calling matches whole; an invitation after a name goes to that person |
| Asked "tell me about the engine", the game called the model to read whom the question was for | a question after a name kept its 0.6 confidence | asked of the one named, it is theirs at 0.85 |
| "I wait until evening" waited half an hour, and the princess who holds court each evening never came | a wait was always a while | a wait lasts as its words say (until evening, for three hours), at most twelve hours |
| Told what should become of the engine, in Valecourt, Seraphine said "come to Valecourt and tell me" | the plan said the quest went on at its unvisited places, and not that the words did the step | the plan says what the hero's words do now, and where a step goes on ("here") |
| Orik called Wren (they/them) "lass" | the line writer was not told who the hero is | it is told the hero's name and pronouns, and to use no gendered address they do not call for |
| Asked about his daughter, Orik offered nothing | "his daughter's memory" kept the possessive, and "daughter" never met it | a possessive's "'s" is no part of the word |
| "I accept the quest The Memory That Burned" before Orik offered it: "you do so; a few minutes pass" | a quest no one offered was no quest the grammar knew | it is refused by name, and never another taken in its place |
| "I buy two Healing Potions" bought one | a purchase was always one | goods by the count asked, as far as stock and purse go |
| Seventeen rounds against one knight; swordsmanship, chosen at each level, counted for nothing | a fight read the hero's level and attributes, not their skills; a companion fought at +0 | the weapon's skill adds to the hero's blows and the defense skill to their defense; a companion fights as their calling (a guide hardy, a general a fighter) |
| Eight rounds read as eight misses | the card told only the hero's wounds | the card shows each foe's health, once, as the turn leaves it |
| Every other fight round took twice as long | the writer's "down to 4 of its 10 health" was judged an invented claim, and the turn written again | a foe's health, as its blows give it, may be said |
| Paid for the roads contract, the captain asked for the next in the same breath | the next waited a day from the last's offer | a day from when it ended |
| Asked what vow he would have witnessed, Vael never offered his quest | a quest was offered for work words or a goal | a giver offers the quest the words ask about; "anything you need of me" asks for work |
| At the Hollow Meridian the Archon's fight was not suggested, nor Valecourt's road | suggestions knew the scene, not the quests | what the hero's quests ask now leads them |
| "I drink a Healing Potion", the last gone: "you are in a fight" | a use of nothing carried read as a deed refused | "you carry nothing like that to use" |
| A whole campaign together, and Liora's regard moved only when a quest ended | nothing else moved a companion's | a fight won together brings each companion still standing closer |
| The finale's choice ended on "Quest complete" | a branch taken told nothing | a way may tell what came of it; Aurelia's gate, engine, knights and gale tell theirs |

Noted, not changed:

- (Since added, below.) Valecourt, a capital, has no one in it by day (its princess holds court there only from 19:00); its lore names no one
  else there. A place someone's day brings them to is still wild, or the pass, where Captain Rhea checks the barricades
  by night, would have no wolves.
- Aurelia sells no weapons or armour: its lore has six items, its one weapon Vael's legendary Oathblade. Gear does not
  grow with the hero there; a world's author would write its shops' goods.
- Elyra could not name the voice from Earth: the world's lore never does.
- Orik's inn gives "new arrivals one free night", in its lore; the economy charges six silver.

### Content added afterwards (2026-10-29)

The first three were content, and Aurelia's author files now write them (`lore-additions.json`, `play-sections.json`):

- Gear. Aurelia has an authored economy now, keeping every offer launch used to infer. Captain Rhea sells the watch's
  spare Gatewarden Shortswords, Watch Leathers and Ward-glass Bucklers. Brindle sells his Arc Baton. In Valecourt,
  Hollis Brask, foundry master, sells an Aether-forged Longsword and Foundry Half-plate. Each item says its slot and
  numbers. The Ashen Oathblade (5-10, +3) is now the reward for the Bridge of One Thousand Promises. Echoes drop
  Aether Shards, which Brindle and Hollis buy back, so fights pay for the better gear.
- Valecourt by day. Hollis Brask works his forge there from 06:00 to 20:00. Cassia Venn, warden of the royal gate
  engine, keeps its hall. Seeing the engine is now a talk with her, not just arriving in the city.
- The voice. Elyra names it as the hero's own: the call they were making when the blackout took them, caught in the
  Memory Loom. She calls it the Unfinished Call. Brindle's radio catches it in storms, from Moonroot.

The engine changed to carry this. A world item's `equipment` now reaches the pack whether it is bought, given as a
reward or looted, and the pack honours its slot. A seller's buy-back types are now enforced (they were saved but never
read). An unnamed sale goes to the one seller who deals in the thing, or the hero is asked which seller.

## A short Vesper-9 session (turns 1-5)

Vesper-9 is lore-only: a world compiled from lore topics, played from what launch infers from them.

| What the player met | Cause | Fix |
|---|---|---|
| A cyberpunk hero set out with a travel cloak and an iron dagger, and no coin | the build's default kit is a fantasy one, and the opening names no purse | a hero of a world to come carries its kind of gear (a utility knife, a rain cloak, ration bars, a flashlight); an opening that names no purse keeps the build's |
| The opening quest, "Black Rain Rising", showed no objective | the opening scenario's quest kept its beats as `next_step` only | it says what it asks now |

Noted, not changed: its opening quest is the scenario's beats, with no steps or places the rules can judge, so it can
never be completed; Mara Vey's calling reads "encountered at this station" and Juno knows nothing of the black rain her
city is named for. A lore-only world plays as well as launch's inference of it; its author (or World Forge) would write
its quests' steps and its people's knowledge.
