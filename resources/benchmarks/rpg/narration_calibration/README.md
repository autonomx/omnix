# RPG narration judge calibration (RQ-0.6)

`scripts/rpg_narration_eval.py --judge` grades each narrated turn on three criteria with a model judge. The judge
gates (roadmap N1, "grounded in canon") only once it agrees with a person: **agreement >= 0.90 and Cohen's kappa
>= 0.70 on each criterion, over 150 human-labelled items**. Until then the evaluation reports the rubric as
`uncalibrated`.

## `labels.jsonl`

150 narrated turns, sampled from a baseline run across the three worlds (`--calibration-template` writes the file
when it does not exist). Each row carries what the judge saw and the judge's answer; the `human` labels are `null`
until the owner fills them in:

```json
{"id": "cal-001", "world": "aurelia", "scene": "village", "input": "Orik, what do you know about the moonwell?",
 "present": ["npc:orik-stonewake", "..."], "applied_changes": [], "previous_narrations": ["..."],
 "narration": "...", "judge": {"grounded": true, "continuous": true, "varied": false, "note": "..."},
 "human": {"grounded": null, "continuous": null, "varied": null, "labeller": null, "note": null}}
```

To label: set each of `grounded`, `continuous` and `varied` to `true` or `false`, and `labeller` to your name. Judge
each criterion on its own, without looking at the judge's answer first:

- **grounded**: consistent with the scene (who is present, where), the applied changes, and the world's canon; it
  invents nothing that contradicts them.
- **continuous**: follows from the player's input and the previous narration.
- **varied**: not a near-repeat, in wording or structure, of the previous narrations.

The evaluation reads the labels on its next run and reports agreement and kappa per criterion.
