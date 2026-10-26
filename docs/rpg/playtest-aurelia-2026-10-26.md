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
