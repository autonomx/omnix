# Character Mode staged rollout and rollback guide

Status: repository implementation complete; deployment adoption pending.

Baseline: `cc42b5d18c02886ef3d51996f345cb74aea07058` or a later `main` commit containing it.

Character Mode must be enabled incrementally. Passing repository CI is necessary but does not replace a deployment-specific rehearsal with the actual model, TTS provider, voice assets, data stores, and retention configuration.

## Before Stage 1

1. Back up the configured Chat SQLite database, assistant-memory database, character database, shared asset manifest, cloned-voice audio, and any selected Hermes directory.
2. Confirm normal System Assistant text and voice Chat work with all Character flags disabled.
3. Confirm existing sessions load as `interaction_mode=system` and existing memory remains owned by `system/system-assistant`.
4. Review cloned-voice governance. Legacy voices should remain unverified until ownership, source, creator, consent, allowed uses, and source hash are recorded.
5. Use a non-production or explicitly selected test character for the first rollout.

## Stage 1 — Character identity without memory

Enable only:

```text
OMNIX_CHARACTER_MODE_ENABLED=1
OMNIX_CHARACTER_MEMORY_ENABLED=0
OMNIX_CHARACTER_SHARED_MEMORY_ENABLED=0
OMNIX_CHARACTER_HERMES_SYNC_ENABLED=0
```

Keep normal Chat-memory flags at their existing deployment values.

Verify:

- a character can be created, versioned, selected, and archived;
- the server—not the browser—resolves personality, greeting, identity policy, and effective identity hash;
- selecting a voice without Character Mode stays System Assistant mode;
- switching System Assistant -> character -> System Assistant creates clean context segments;
- changing only the renderer voice does not change character identity;
- Character Mode with memory off performs no character-memory reads or writes;
- a character without a linked voice can use the deployment's normal renderer voice.

Rollback: set `OMNIX_CHARACTER_MODE_ENABLED=0`. Profiles and versions remain stored but cannot become active interactions.

## Stage 2 — Character memory read-only pilot

Prerequisites:

```text
OMNIX_CHARACTER_MODE_ENABLED=1
OMNIX_CHARACTER_MEMORY_ENABLED=1
OMNIX_CHAT_MEMORY_ENABLED=1
```

Keep each pilot session at:

```text
read_memory=true
write_memory=false
shared_memory_access=none
```

Verify:

- only `character/<active-character-id>` records enter the prompt;
- System Assistant and other-character records are excluded before scope ranking;
- memory-off sessions start with no character snapshot;
- a read-only session cannot create pending suggestions or approved records;
- switching character or memory policy starts a new context segment and clears stale snapshots;
- forget and relationship reset remove the selected character's content without affecting other owners.

Rollback: turn off `OMNIX_CHARACTER_MEMORY_ENABLED` or return pilot sessions to `read_memory=false`. Existing records remain isolated and retained.

## Stage 3 — Explicit character-memory writes

Enable writes only for selected pilot sessions:

```text
read_memory=true
write_memory=true
```

Enable normal suggestion processing only when the deployment is ready to review pending candidates:

```text
OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED=1
```

Verify:

- inferred content becomes a pending suggestion, never prompt-eligible memory before approval;
- explicit user saves are written to the active character owner;
- write-only mode can start fresh, save new information, and still read no prior memory;
- rejected suggestions remain excluded;
- retries do not create duplicate candidates;
- first-token and first-audio latency do not wait for post-turn extraction.

Rollback: set session `write_memory=false`, disable memory suggestions, or disable `OMNIX_CHARACTER_MEMORY_ENABLED`. Previously approved character memory remains intact.

## Stage 4 — Read-only shared System Assistant memory

Enable:

```text
OMNIX_CHARACTER_SHARED_MEMORY_ENABLED=1
```

For each participating character, configure a server-owned policy such as:

```json
{
  "access": "read_only",
  "allowed_categories": ["preference", "fact"]
}
```

Set the session policy to:

```text
shared_memory_access=read_only
```

Verify:

- only allowlisted, normal-sensitivity System Assistant categories are included;
- session-scoped, sensitive, secret, and non-allowlisted records are excluded;
- the character cannot edit, approve, forget, or create System Assistant memory;
- shared records are clearly treated as read-only background context;
- turning shared access off removes the bridge without changing either owner.

Rollback: set `OMNIX_CHARACTER_SHARED_MEMORY_ENABLED=0` or `shared_memory_access=none`.

## Stage 5 — Governed cloned voice and live-call pilot

Before linking a cloned voice, record:

- voice subject or owner;
- source type and source reference;
- creator ID;
- granted consent and consent timestamp;
- source SHA-256;
- allowed uses including `character` and, for calls, `live_call`;
- active deletion state.

Verify:

- unverified, revoked, pending-deletion, deleted, provenance-incomplete, or unhashed voices cannot be linked;
- a voice allowed for `character` but not `live_call` cannot render a character call;
- the live-call runtime resolves the active profile version and effective identity hash;
- the character greeting is spoken once at call start;
- speech speed and bounded sampling controls apply without altering language identity;
- changing a voice override does not change the character;
- AI identity disclosure remains in the trusted server-owned identity instructions;
- first-audio diagnostics record preload timing without recording private prompt or memory content.

Rollback: unlink the voice, revoke consent, change its deletion state, or return the character to an approved renderer. Do not delete the character or memory as an implicit consequence.

## Stage 6 — Optional Character Hermes pilot

Keep this stage disabled unless an explicit compatibility pilot is required:

```text
OMNIX_CHARACTER_HERMES_SYNC_ENABLED=1
```

Ordinary System Assistant Hermes synchronization remains independently controlled by `OMNIX_HERMES_MEMORY_SYNC_ENABLED`.

Verify:

- each operation names an existing explicit character owner;
- each character uses its own `characters/<character-id>/CHARACTER.md` path and managed block;
- imports are screened and become pending character-owned suggestions;
- imports never become active without normal approval;
- exports contain only active, user-approved, normal-sensitivity, non-session, non-Hermes-origin records for that character;
- System Assistant and other-character memory never appears in the file;
- repeated import/export is idempotent and does not create feedback loops;
- unavailable Hermes storage does not affect native Character Mode.

Rollback: set `OMNIX_CHARACTER_HERMES_SYNC_ENABLED=0`. Native character profiles and memory remain authoritative and unchanged.

## Private-call release check

Before offering a user-facing private-call option, verify the deployment's complete retention path with `transcript_policy=none`:

- no curated-memory read;
- no history recall;
- no candidate extraction or approved-memory write;
- no retained Chat messages, segment summary, search-index entry, audio asset, or derived transcript after call termination;
- only content-free operational diagnostics remain;
- interrupted, failed, and browser-disconnected calls receive the same cleanup.

Treat failure of any item as a release blocker for the private-call label. Do not represent ordinary memory-off mode as a private or non-retained call.

## Production monitoring

Track content-free metrics by interaction mode and profile version:

- runtime preload latency;
- first token and first audio latency;
- TTS fallback rate;
- character resolution failures;
- voice-consent rejection counts;
- memory snapshot selection counts and owner-mismatch exclusions;
- context-segment switches;
- pending suggestion and approval counts;
- retention cleanup failures;
- Character Hermes disabled/offline/error status.

Do not include prompt text, memory text, transcript text, cloned-voice audio, or consent evidence contents in operational logs.

## Full rollback

To return to normal System Assistant operation without deleting Character data:

```text
OMNIX_CHARACTER_MODE_ENABLED=0
OMNIX_CHARACTER_MEMORY_ENABLED=0
OMNIX_CHARACTER_SHARED_MEMORY_ENABLED=0
OMNIX_CHARACTER_HERMES_SYNC_ENABLED=0
```

Then restart the relevant services and confirm:

- new sessions resolve as System Assistant;
- normal Chat memory remains available according to its own flags;
- selecting a voice remains renderer-only;
- existing character profiles, versions, records, transcripts, voice governance, and exports remain present but inactive;
- no Character Hermes reads or writes occur.

Destructive cleanup is a separate, explicitly confirmed operation and is not part of feature rollback.
