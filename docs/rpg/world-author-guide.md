# Writing worlds

Every campaign plays in a world. A world is its lore (places, people, groups, creatures, items, quests and history),
its maps and openings, and, optionally, how it plays: who sells what, where people are through the day, what they
know, the troubles its clock moves, and how its creatures fight. Omnix infers what a world does not say from its
lore. Writing it down makes the world play the way you mean it to.

Worlds live in the library: **RPG → Worlds & Campaigns**.

## Making a world

- **Generate one.** Create a world, describe it and approve its genre profile; **World Generation** writes its lore
  topic by topic with the configured model (World Forge). Review the candidates, accept them, and publish. A
  campaign started from the New Campaign wizard with World Forge on goes through these same steps itself.
- **Import one.** A world bundle (`.omnix-world.zip`) carries a whole world, its maps and openings. Import it from
  the library, or adopt one from the community catalog (`autonomx/omnix-worlds`). An imported world from someone
  else is adopted before it can be launched.
- **Write one by hand.** The bundled worlds are written as readable sources: The Market Road's is
  `resources/examples/rpg/world-bundles/the-market-road/world.source.json`, compiled into a bundle by its
  `materialize.py`. Copying it is the quickest way to start a world of your own in a file.

## The world editor

Open a world from the library. Its sections:

| Section | What it holds |
|---|---|
| Overview | The world's title, summary, genre and tone |
| World Generation | Each lore topic's generation, review and publication |
| Images | Portraits, place and item art |
| World / Lore topics | Regions, places, people, groups, creatures, items, history and the rest, entity by entity |
| Map | The world map and its places |
| Scenarios | Openings: where a campaign starts, who is there, what the hero carries |
| How It Plays | Economy, routines, knowledge, pressures and bestiary (below) |
| Map Blueprints | The grid maps of places, for fights and moving around |
| Validation, Releases, Revision History | What publication checked, each certified release, earlier revisions |

A campaign plays from a published, certified release of the world. Editing the world changes its draft, and
campaigns started later play the new release. Campaigns already under way keep the release they started with.

## How It Plays

Each of the five sections is optional. A section you leave empty is inferred from the lore when a campaign starts,
and the editor's tabs and the campaign setup say which sections the world wrote ("Written") and which come from its
lore ("From lore").

Start with **Draft empty sections from lore**: World Forge writes each empty section from what the lore says (sellers
by their roles, people at their places, what they say openly and what they keep, the world's pressures, creature
numbers by threat). Read it, correct it, then **Save draft**. The draft is kept with the world; **Publish** writes it
into a new revision and pins the world's openings to it.

People, places, items, creatures, regions and quests are chosen from the world's own. A draft that names something
the world does not have is saved, and listed in red ("Routines names a person the world does not have"), but it
cannot be published until that is fixed.

### Economy

Each **seller** is a person of the world, at a place (by default, where they are found). Each **offer** has a name,
a service (goods, lodging, a meal, a drink, repair or information), a price in gold, silver and copper (never free),
and optionally a stock and how many it restocks each day. Goods name the item sold. **Buys back** lists the item
types the seller buys and the share of the price paid (0.5 is half).

### Routines

Each person's **day** is a list of hours: from which hour to which (0 to 24), where, and doing what. Between those
hours they are elsewhere. **Goals** are what they are after, each with a priority (5 leads), the topics that touch it
and, if it takes them somewhere, the place. A goal leads what they say and what they offer.

### Knowledge

What each person knows, as **facts**: the text, how they share it (freely, for a price, when trusted, or never), the
price or the trust it needs (0 to 100), and its topics. Asked about a topic, they tell what they would; a secret
("never") is not given away.

### Pressures

The troubles the world's clock moves: a name, a description, where it bears (a region or a place), what it wears
down (who governs, trade, resources, or the people), its severity (0 to 100) and trend, and the levels at which it
boils over or counts as resolved. **Levers** are what the hero can do about it: defeating a creature
(`defeat:<creature>`, for each one felled) or finishing a quest (`quest:<quest>`), each easing or worsening it by an
amount. A pressure that runs high makes travel in its region dangerous and raises side quests.

### Bestiary

For each creature: its **numbers** (level, health, defense, damage range, accuracy, experience), its **behaviour**
(fights, flees when hurt, calls allies, guards, ambushes; or as its lore tells), and its **drops** (an item, the
chance from 0 to 1, how many). A creature without numbers fights at the numbers its threat rating gives it.

## Quests

A quest's **steps** are done in order. Each step is a set of conditions that must all hold, or `any_of` branches
where either way completes it. A condition is `reach` a place, `talk` to someone (optionally `about` topics),
`hold` an item, `defeat` a creature (with a `count`), or pass a `check`. A quest with `deadline_hours` fails when
that much time passes after it is taken up, and its giver trusts the hero less. For example, from The Market Road:

```json
{
  "id": "quest:market-road:tavern-rumor",
  "title": "Rumor at the Rusty Flagon",
  "giver_id": "npc:bran",
  "steps": [
    {"id": "ask", "summary": "Ask Bran or Mira which rumor is true",
     "any_of": [{"talk": "npc:bran", "about": ["rumor", "story"]},
                {"talk": "npc:mira", "about": ["rumor", "story"]}]}
  ]
}
```

A quest without steps advances as the hero reaches its places.

## In a world source file

A hand-written source carries the same sections in its canon: `economy.providers`, `routines`, `knowledge`,
`pressures`, and `bestiary` rows with `stats`, `behaviour` and `loot` beside their lore, using the same fields as the
editor's forms. Publication checks them; `the-market-road/world.source.json` uses every one of them.

## Sharing

Export a world as a bundle from the library to give it to someone. A bundle carries the world's published
revisions, maps, openings and images; publish your How It Plays draft before exporting, so the sections travel in
the revision.
