# RQ-4.1: an author writes how a world plays, and the next campaign plays it

## What the author experiences

In the world editor, **How It Plays** (Game Master) shows the world's six play sections: its economy (who sells
what, at what price and stock, and what they buy back), routines (where each person is through the day, and their
goals), knowledge (what each person knows, and on what terms they tell it), pressures (the forces the world's clock
moves, and what eases or worsens them), bestiary (how its creatures fight, and what they drop), and quests (what each
takes, step by step, and where it branches; quests.md). Each section is a list of rows edited as a form; people,
places, items, creatures, regions and quests are chosen from the world's own, a step's subject from what its
condition asks (a place to reach, a person to talk to, a check's kind).

**Draft empty sections from lore** asks World Forge for a first draft of each section the author has not written:
what launch would infer from the world's words, written out to read, correct and keep. **Save draft** keeps the
draft with the world; **Publish** publishes the world with it, and the world's openings launch from that revision.
A tab says, for each section, how many rows the draft has and whether the published world wrote it or takes it from
its lore. The campaign setup shows the same for the revision it launches ("Written: economy, routines · from lore:
…").

## Rules

- The sections are optional (RQ-2.0, `world_play_sections.py`). A section left empty is played from the lore: launch
  infers it (`published_world_setup`, `published_pressures`). Readiness says which: `authored` or `derived`.
- The draft is kept in the world's metadata (`play_sections`, a key only the editor writes). Before anything is saved
  the page shows what the latest revision carries. A save names the draft it replaces (`expected_content_hash`); a
  newer save made elsewhere refuses it (409), and a draft of the wrong shape is refused with each error named (422).
- References are the world's as launch reads them (`lore_sections.lore_rows`: the section the world wrote, else the
  entities of its kinds), so a world written as lore (Vesper-9) is checked against its entities. A draft naming a
  person, place, item, creature, lever or region the world lacks is saved and shown, and refused at publication.
- World Forge's draft (`play_section_generation.py`) is deterministic and asks no model: sellers by role with the
  world's own prices and only its own items; each person at their place all day with their goals; what they say
  openly (their public truth) and what they keep until trusted (their secrets, trust 50); the world's pressure
  entities, eased by the quests that name them, then the danger its creatures put on each region's roads; each
  creature's numbers by its threat and its behaviour as its lore tells. A section the world wrote is kept as written,
  and a quest's steps are left to the author (a quest without them is done by reaching its places).
- Publication writes the draft into the new revision's canon (`play_section_publication.py`) after the authored map
  blueprints, at both of the library's publications: a generation run's and the repair's. Publishing from the page
  repairs each opening at its starting place, so each is pinned to a revision with the draft; a world with nothing to
  recompile from (written by hand, or installed from a bundle) is republished as its latest revision stands, its map
  definitions issued again for the new revision, and needs no starter bubble. A later repair reuses a publication only
  when it carries the current draft (`authored_play_sections` in its provenance).
- The new revision's trust is attached as for any compile: a generated world's receipt is signed over the compiled
  canon, a hand-written world's ledger covers it.

## State it changes

The world's metadata (`play_sections`); on publication, a world revision and release (and the openings' scenario
revisions) whose canon carries the sections.

## Out of scope

Model-written sections (World Forge's draft is the lore's inference); the quality of what a model would write is
outside the roadmap (§9).

## What the editor writes since the evolution roadmap (EV-6)

The play-section form also writes a goal's beats (routines.md), the facts a way or a quest's completion sets and the
facts a quest requires or forbids (EV-1), a creature's resistances, no-escape, recovery and boss phases (combat.md),
upgrades and their recipes (economy.md), and the **Consequences** section (`fact_effects`: one effect a row, while
its facts hold). World Forge's draft now also gives each quest its steps (its places in order, then word with its
giver), each goal a first beat, and the world's gear to its first seller of goods. The **Inventions to Review** page
is the world's review queue: what the game master invented in campaigns on the world (EV-0 part 2), with where it
came from and the consistency check's findings, to approve into the next publication, reject or link. The entry
forms write an item's gear and a character's home, aliases and group, and a collection's heading adds an entry.

Entries are kept where their topic keeps them: a generated topic's `entities`, a bundle's `characters` or `items`
(`authoring_presentations.ENTRY_LISTS`; a new one goes in the topic's one list, `entity_authoring.entry_list_for`).
A generated world recompiles its canon from its topics when published. A world written by hand or installed from a
bundle has nothing to recompile from: its publication writes its editor's entries into the canon list of the same
name by id, the editor's fields over the canon's, a new one added to the entity manifest and the release's index
(`topic_entries.py`), and a launch reuses a published revision only while its canon holds them. Its topics keep the
draft revision they were installed at, so a write is taken at the world's draft or the topic's own.
