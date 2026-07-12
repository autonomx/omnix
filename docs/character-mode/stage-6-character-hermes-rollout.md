# Character Mode Stage 6 - optional Character Hermes compatibility

Status: temporary-store preflight and isolated live restart rehearsal passed on 2026-07-09.

Character Hermes is an optional, owner-aware adapter. Native Omnix character memory remains authoritative. Ordinary System Assistant Hermes synchronization is controlled separately.

## Preflight

Run before enabling the live flag:

```bat
python scripts\character_mode_stage6_preflight.py
```

Expected result: `decision = pass`.

The preflight uses temporary files and SQLite state. It verifies disabled and missing-storage behavior, review-first idempotent import, owner binding, filtered idempotent export, unmanaged-text preservation, feedback-loop prevention, and non-destructive rollback. Its report contains no memory or file content.

## Controlled live pilot

Select a backed-up, explicitly isolated root and restart Omnix with:

```text
OMNIX_CHARACTER_HERMES_SYNC_ENABLED=1
OMNIX_CHARACTER_HERMES_MEMORY_DIR=<isolated-character-hermes-root>
```

Create `<root>/<character-id>/CHARACTER.md` with controlled unmanaged input, then run:

```bat
python scripts\character_mode_stage6_live.py prepare
```

Expected result: `decision = needs_review`.

Restart all Omnix services with the same root and flag, then run:

```bat
python scripts\character_mode_stage6_live.py verify-restart
```

Expected result: `decision = pass`.

The passing final run deletes its exact synthetic records, resolved candidate, sessions, and isolated rehearsal directory.

## Trust boundary

- Every operation names an existing explicit character owner.
- Imports ignore managed blocks and screen operational, injection-like, and secret-bearing lines.
- Imports become pending `source=hermes` character-owned candidates.
- Approval remains explicit and does not permit export feedback.
- Exports include only active, user-approved, normal-sensitivity, non-session, non-Hermes-origin records for that character.
- System Assistant and other-character records remain excluded.
- Unmanaged file content is preserved and managed-block replacement is atomic and idempotent.

## Rollback

Set `OMNIX_CHARACTER_HERMES_SYNC_ENABLED=0` and restart. Native profiles, character memory, shared read-only memory, governed voice behavior, and normal Chat remain available. Existing Hermes files are not changed by disabled import or export operations.
