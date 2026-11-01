# Dialogue (RQ-2.2): rules decide, the model phrases

## What the player experiences

The person spoken to answers in their own voice, about what they would know: the innkeeper about the inn and the
roads, the guide about the grove. They share what they know freely, ask a price for some things, keep some until
they trust the hero, and never give away their secrets. Asked for work, someone who has it offers a quest. A
shopkeeper asked what they sell says, with prices. When the model cannot answer, the person still says something
true, in a line built from the same plan.

## Rules

- **Who answers.** The person the player names or addresses, if present; else the one they were talking to (the
  dialogue focus); else the turn takes the older path, where the model chooses among those present.
- **The plan** (`rules/dialogue/plan.py`, pure), built before the commit from the campaign:
  - the speaker's public canon (role, biography, personality, speech style, goals) and their secrets, which the
    line must not reveal;
  - their stance toward the hero: `friendly` (companion or trust ≥ 50), `wary` (trust < 0), else `neutral`;
  - knowledge facts that match the player's words (the world's knowledge section): `freely` shared; `for_price`
    offered for its price; `when_trusted` shared at the trust it needs, else held back; `never` withheld;
  - a quest hook: asked for work, help or a job, the first quest still available whose places include where the
    speaker is, offered by them;
  - their wares, when they sell and are asked what or for how much.
- **What it makes real** (changes, before the commit): `KnowledgeShared` for each fact shared, `QuestOffered`
  (the quest now names who offered it), `DialogueExchanged` (what was said, kept for continuity; the hero is now talking to them).
- **The line.** One model call writes the speaker's one or two sentences from the plan and the player's words.
  It is checked: a line that repeats a secret, or leaves out a ware asked about (prices are the game's), is
  replaced by the fallback. Sold-out goods are not offered. The older path's dialogue-quality rewrite (a word
  count, stock lines) does not apply to these turns.
- **Fallback line**, from the plan alone: the fact shared, the quest offered, the wares listed; with nothing to
  say, a neutral beat ("Orik Stonewake considers the question and says nothing useful.").
- Talking takes ten minutes and presses on needs as a standard turn.

## State it changes

`KnowledgeShared`, `QuestOffered`, `DialogueExchanged`, `TurnCounted`, `TimeAdvanced`, and the world tick (`WorldTicked`).

## What the narrator is told

The plan: who answers, their stance, what they reveal or offer and what they keep back. The narrator may not have
them reveal more.

## Scenarios

Ask someone present a question and get one short call; ask the innkeeper what he sells; ask the guild clerk for
work and be offered a quest; a person's secret never appears in their line; the model fails and the fallback line
says what the plan holds.

## Out of scope

Persuasion and intimidation checks (RQ-5.2), relationship changes from what is said (RQ-4.4), barter.
