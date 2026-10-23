# RPG gameplay design pack (RQ-5.0)

Status: **approved for implementation, 2026-10-23.** The owner accepted the roadmap's gameplay decisions
(`docs/RPG_PRODUCTION_ROADMAP_2026-10-23.md` §7, Q-1); the numbers below are first values, tuned by the balance
simulation (RQ-5.3, RQ-5.5) and the owner playtest (RQ-9.2), and recorded here when they change.

Each gameplay package (RQ-5.1–5.7) has a one-page note in this folder written from the template below. A note says
what the player experiences, the rules that decide it, the state it changes, what the narrator is told, and the
playthrough scenarios that prove it. Implementation follows the roadmap's architecture: a resolver in the owning
mechanic (§4.3) returns `StateChange` values; the narrator only phrases the outcome.

| Note | Package | Required for G1 Strong |
|------|---------|------------------------|
| [stakes.md](stakes.md) | RQ-5.1 Stakes: defeat, injuries, fleeing | yes |
| [checks.md](checks.md) | RQ-5.2 Skill checks outside combat | yes |
| [progression.md](progression.md) | RQ-5.3 XP, levels, skills | yes |
| [quests.md](quests.md) | RQ-5.4 Multi-step, branching, failable quests | yes |
| [economy.md](economy.md) | RQ-5.5 Sinks, sources, prices that move | stretch |
| [encounters.md](encounters.md) | RQ-5.6 Creature behaviour, negotiation, stealth | stretch |
| [rewind.md](rewind.md) | RQ-5.7 Undo and save points | yes |

## Note template

```
# <Package>: <one-line promise to the player>

## What the player experiences
## Rules (deterministic; seeded rolls named by purpose)
## State it changes (StateChange types)
## What the narrator is told
## Balance bands (if any)
## Scenarios (RQ-0.3 suite)
## Out of scope
```

## Balance bands

The balance simulation (RQ-5.3) plays 500 scripted turns per world with a deterministic "reasonable player" policy
(rest when HP < 40%, buy food when hunger > 60, take every quest offered, fight what the world spawns, flee below
25% HP) and fails when a band is broken.

| Measure | Band after 100 turns | Band after 500 turns |
|---------|----------------------|----------------------|
| Player level | 2–4 | 5–9 |
| Purse (in copper; 1 silver = 10, 1 gold = 100) | 50–2,000 | 200–10,000 |
| Fights won / fights started | 0.55–0.90 | 0.55–0.90 |
| Defeats | ≤ 3 | ≤ 10 |
| Turns spent below 25% HP | ≤ 15% | ≤ 15% |
| Hunger ≥ 80 (starving) | ≤ 5% of turns | ≤ 5% of turns |
| Quests completed | ≥ 1 | ≥ 4 |

## Playtest rubric (RQ-9.2)

The owner scores each dimension 1–5 after a session; G1 Strong needs a mean ≥ 4 on stakes, choice and progression.

| Score | Stakes | Choice | Progression | Living world | Clarity | Speed |
|------:|--------|--------|-------------|--------------|---------|-------|
| 1 | Nothing I did could go wrong | Every turn had one sensible move | Nothing about me changed | The world stood still | I could not tell what happened | I waited and lost the thread |
| 3 | Some risks felt real | I weighed options now and then | I grew, but it did not change how I played | Things happened, mostly off to the side | I usually knew what changed | Waits were noticeable but bearable |
| 5 | Risk shaped my decisions | Meaningful forks most turns | Growth opened new ways to play | The world moved and I moved it | I always knew what changed and why | It felt immediate |
