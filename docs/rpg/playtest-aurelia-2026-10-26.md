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
