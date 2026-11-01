# EV-9's idiom set

`idioms.jsonl` holds 844 lines over the intent corpus's scenes (`../intent_corpus/catalog.json`: Aurelia's grove,
village and guild, the starter town's market and tavern, Vesper-9's docks), pooled over the three worlds. Each line's
right handling commits no action: it is talk, a remark, a refusal or nothing at all, and the game must change nothing
(`stateful: false`).

| Tag | Lines | What |
|---|---|---|
| `idiom` | 380 | idioms and set phrases ("give it a rest", "break a leg", "I'll cross that bridge when I come to it") |
| `negation` | 145 | a deed refused ("I don't attack Liora", "I won't buy anything right now") |
| `reported` | 100 | what someone said, read or dreamt ("Orik said I should go to Skybridge Pass") |
| `quoted` | 108 | a deed inside quoted speech or a story ("I tell Bran, 'Someday I'll buy you a drink.'") |
| `figure` | 111 | figures of speech ("my purse is crying", "I could eat a horse") |

The seed is the probe of 2026-10-29 (roadmap W-9), tagged `probe-2026-10-29`: the idioms and remarks the command
grammar turned into actions ("give it a rest" rested the hero, "climb the ranks of the guild" rolled a climb).

The gate (roadmap EV-9): no action committed by mistake, the false stateful rate's pooled upper bound ≤ 0.5%
(`scripts/rpg_intent_eval.py --corpus resources/benchmarks/rpg/idiom_set/idioms.jsonl`). The family labels are a
guide only. Written by a model from the scenes' contents, pending the owner's spot check, like the intent corpus.
Frozen: change it only with a new file and a note here.
