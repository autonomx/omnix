# EV-9's slot set

`slots.jsonl` holds 689 lines over the intent corpus's scenes, at least 75 for each slot kind the intent call reads:

| Kind | Lines | The slot |
|---|---|---|
| `quantity` | 84 | how many things a line buys ("buy three torches") |
| `wait` | 96 | how long to wait, or until when ("wait two hours", "wait until evening") |
| `seller` | 84 | whom a thing is bought from where more than one sells ("buy a potion from Brindle") |
| `choice` | 78 | a level's choice, with one waiting (`state: level`) ("raise my strength") |
| `order` | 75 | a companion's standing order, Liora in the party (`state: party`) ("Liora, keep watch") |
| `give` | 76 | the thing given and to whom ("give my lantern bread to Liora") |
| `check` | 96 | the kind of risky try ("I try to persuade Orik", "haggle with Bran") |
| `topics` | 100 | what a person is asked about ("ask Orik about Skybridge Pass") |

Each row names the reading expected (`expect`: its family and the slot's value). The gate (roadmap EV-9): each kind
read right with a Wilson lower bound ≥ 0.95 (`scripts/rpg_reading_eval.py --set slots`). Written by a model from the
scenes' contents, pending the owner's spot check. Frozen: change it only with a new file and a note here.
