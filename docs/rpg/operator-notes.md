# RPG operator notes

What someone running Omnix needs to know about the RPG: where its state lives, what keeps it healthy, the settings
that matter, and how to check it. Install-wide operations (backups, restores, releases) are in
[`docs/OPERATIONS.md`](../OPERATIONS.md) and [`docs/operations/`](../operations/).

## Where the state lives

PostgreSQL is the authority. A campaign is one document (`omnix_rpg_campaigns`) changed only by turns. Each turn
commits, in one transaction, the new document and revision, a turn row with the state's patch, the interaction, the
canonical narration, the submission's response and a metrics row. A full snapshot is kept every
`OMNIX_RPG_SNAPSHOT_EVERY` revisions (20). Worlds, their revisions, releases, maps and scenarios are in the
`omnix_rpg_world*`, `omnix_rpg_map*` and `omnix_rpg_scenario*` tables.

A turn is exactly once per submission id: a client that retries sends the same id and gets the recorded response.
A turn that crashes before its commit leaves nothing behind, and its retry runs it. One turn of a campaign runs at a
time; a second waits (up to `OMNIX_RPG_TURN_WAIT_SECONDS`, 120) and then runs on the state the first left.

## Retention

The retention job:

- purges archived campaigns after 30 days, with all their rows;
- keeps the newest 1,000 turns of a campaign past 5,000 revisions, behind a pinned snapshot;
- keeps turn metrics for 90 days.

Pinned revisions (save points, upgrade backups) are never purged.

## Settings

| Setting | Default | What it does |
|---|---|---|
| `OMNIX_RPG_TURNS_PER_HOUR` | 600 | Turns a user may take per hour; over it, 429 with `Retry-After`. 0 turns the limit off. |
| `OMNIX_RPG_TURN_WAIT_SECONDS` | 120 | How long a turn waits for another turn of its campaign |
| `OMNIX_RPG_SUBMISSION_WAIT_SECONDS` / `_LEASE_SECONDS` | 120 / 30 | How long a retry waits for a submission in flight; how long an unstarted claim holds |
| `OMNIX_RPG_SNAPSHOT_EVERY` | 20 | Revisions between full snapshots |
| `OMNIX_RPG_NARRATIVE_PROVIDER`, `_MODEL`, `_BASE_URL`, `_TIMEOUT_SECONDS` | the app's model, 90 s | The storyteller's model |
| `OMNIX_RPG_WORLD_FORGE_PROVIDER`, `_MODEL`, `_BASE_URL` | the app's model | The model World Forge generates worlds with (an LM Studio server, for example) |
| `OMNIX_RPG_WORLD_GENERATION_WORKERS` | 2 (at most 2) | World Forge's parallel generation workers |
| `OMNIX_RPG_WORLD_CATALOG_REPO` | `autonomx/omnix-worlds` | The community world catalog |
| `OMNIX_RPG_DEBUG_LOGS`, `OMNIX_RPG_LOG_RETENTION_DAYS` | on, 14 days | Per-turn debug logs and how long they are kept |
| `OMNIX_RPG_SLOW_SPAN_MS` | 500 | A pipeline step slower than this is logged as a warning |

## When the storyteller is down

A turn never waits on a failed model past its deadline. The rules still decide the turn; people answer with a line
built from what they know; the player sees that the storyteller is unavailable. Failed model calls are counted
apart from successful ones.

## Checking health

- **Operations view** (Developer tools in the RPG, or `GET /api/rpg/operations?days=7`): each day's failure and
  degraded rates, latency per turn class (p50, p95), and model calls a turn.
- **Replay audit** (`scripts/rpg_replay_audit.py`, read-only): replays each campaign's turns from its snapshots and
  reports any turn that does not reproduce its stored state.
- **Core tasks** (`scripts/rpg_core_tasks.py`): plays starting, trading, travelling, equipping, questing, resting,
  undo, a fight on the grid and coming back after time away in a real browser, at phone and desktop sizes, with
  accessibility and overflow checks. Run it against a running app after an upgrade.
- **Turn overhead** (`python -m tests.rehearsal.rpg.turn_overhead`, on a disposable database): the time and
  statements a turn costs without model time. The budget is p95 150 ms and 20 statements at a 1 MB campaign.
- **Screenshots** (`scripts/rpg_play_screenshots.py`): the play screen at 360, 768 and 1,440 px in light and dark,
  and a pixel comparison of two sets.

## Upgrades

An older campaign document is upgraded the first time it is opened, as a system turn with a pinned backup. A
campaign or save package from a newer Omnix is refused (`rpg_campaign_requires_newer_omnix`) rather than opened.
Schema changes ship as forward migrations under `src/app/persistence/migrations`; run
`python -m app.persistence migrate` before starting a new version.
