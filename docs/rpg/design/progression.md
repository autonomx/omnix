# RQ-5.3 Progression: growing stronger opens new ways to play

## What the player experiences

Experience comes from fights won, quests finished, checks passed and discoveries. Each level-up offers a choice:
+2 to one attribute, a new ability from the world's ability list, or +1 rank in two skills. Skills rise with use and
unlock better outcomes (a rank-3 climber attempts heroic climbs at +2).

## Rules

- One XP curve (replacing the two today: `loot_runtime` uses `xp_to_next_level` = 100 + 50 per level, and
  `player_progression_state` keeps `xp_to_next`): XP to reach level n+1 = `100 × n × (n + 1) / 2`
  (100, 300, 600, 1,000, 1,500, …).
- XP sources: creature `xp_value` (from the bestiary or its threat), quest rewards (as written, else 100 × quest
  steps), checks (10 / 20 / 35 for moderate / hard / heroic), the first visit to a named place (15).
- Level-up: the choice is presented as clarification options; until chosen, XP keeps accruing and the choice waits
  (it never blocks play).
- Skill ranks 0–5; skill XP to the next rank = 50 × (rank + 1); practising (the existing Practice action) gives 5 XP
  at most once per in-game hour per skill.
- Max HP grows by 5 + constitution modifier per level.

## State it changes

`XpGained`, `LevelGained`, `LevelChoicePending`/`LevelChoiceMade`, `AttributeChanged`, `AbilityLearned`,
`SkillXpGained`, `SkillRankGained`, `MaxHpChanged`.

## Balance bands

See the README (levels 2–4 after 100 turns, 5–9 after 500).

## Scenarios

A fight's XP levels the hero up and the choice is offered; choosing an ability makes it usable next turn; practice
is capped per hour; quest reward XP.

## As built (RQ-5.3 part 1)

`rules/player/progression.py`: `gain` is the one curve every source uses (fights, quests, checks, discovery);
`LevelReached` carries the choices waiting (`level_choices_pending`) and the health the levels add (5 + the
constitution modifier each, at least 1, healing by as much). Quests pay the experience their rewards name, else
50 for each of their places (tuned from 100 by the balance simulation); a check passed pays 5 / 10 / 20 / 35 by difficulty (easy, moderate, hard, heroic) to the
hero besides its skill experience; a first visit to a place pays 15. A level's choice is the player's words: "raise
strength" (+2), "learn <ability>" (one the tree has, the level allows and the prerequisites open), or "improve
<skill> and <skill>" (a rank each, to 5); `LevelChoiceMade`; with no choice waiting, those words are the older
path's. Skills: 50 x (rank + 1) to the next rank, 0 to 5; an hour's practice is 5. The balance simulation
(`scripts/rpg_balance_sim.py`, `test_balance.py`) plays 500 turns of Aurelia and the starter world: level, fights won,
defeats, time hurt and hunger stay inside their bands, since the pressures' side quests (RQ-5.4) the purse and the
quests completed, since creatures act like themselves (RQ-5.6) the win rate, and since the economy (RQ-5.5) the
purse late too: every one of Aurelia's; the starter world's win rate not yet, a strict expected failure (its bestiary
has little between levels 2 and 9, so a hero who grows wins nearly every fight there is). The hero's level and attributes count in a fight (combat.md), and since the third Aurelia playtest their skills too: a
blow is struck at + the rank of the weapon's skill (swordsmanship for a blade, archery for a bow, magic for a staff or
wand), and the defense skill's rank raises their defense (before, the skills a level's choice raised counted only in
checks). A companion fights with the numbers of their calling (a scout or a guard as a fighter, a guide as the hardy). On the play screen
the ability tree's Learn is the same choice (`unlock_ability`, a structured-action turn): only an ability the tree has,
the level allows and the prerequisites open, and only while a choice waits; abilities have no ranks to raise (the older
ability points and Upgrade are gone, RQ-2.4 part 3). Not yet: the choice as clarification options on the play screen
(RQ-7.3).

## Out of scope

Classes and multiclassing, respec.
