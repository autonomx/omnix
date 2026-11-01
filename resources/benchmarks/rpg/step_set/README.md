# EV-3's step set

`steps.jsonl` holds 630 lines spoken to someone who holds a quest step the hero may answer: 300 address the step,
330 address none. The scenes hold three steps: Miri Kestrel's "Register with Miri Kestrel at the Wayfarers' Guild"
(Aurelia's guild) and Bran's and Mira's "Ask Bran or Mira which rumor is true" (the starter town's tavern), so each is
said in many ways; the lines that address none ask the same people other things.

Each row: the person spoken to and the step's address the line answers (`step`, or null). The gate (roadmap EV-3):
precision over the steps the reading names ≥ 0.98 and recall over the lines that address one ≥ 0.90
(`scripts/rpg_reading_eval.py --set steps`). Written by a model, pending the owner's spot check. Frozen: change it only
with a new file and a note here.
