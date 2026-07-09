# Character Mode repository release evidence

Status: implementation complete through CHAR-11 on `main`.

Release date: 2026-07-09.

Current repository baseline after CHAR-11: `cc42b5d18c02886ef3d51996f345cb74aea07058`.

This document records repository implementation and merge-gate evidence. It does not claim that Character Mode, character memory, shared System Assistant memory, or Character Hermes synchronization is enabled in a production deployment.

## Verification contract

CHAR-1 through CHAR-11 were squash-merged only after both required GitHub Actions workflows completed successfully on the exact pull-request head:

- `RPG Phase 0 architecture compliance`
- `RPG deterministic PR gates`

Each merge used the exact verified head SHA.

CHAR-0 is the documented bootstrap exception: its purpose included expanding the workflow branch filters to cover `main`, so the pull-request checks could not run against `main` before that bootstrap was merged. All subsequent phases used the required exact-head contract.

## Implementation evidence

| Phase | Pull request | Exact implementation head | Squash merge SHA | Gate evidence |
|---|---:|---|---|---|
| CHAR-0 | #1282 | `13d12da98553173373796f7e4cc0a70092ee2a8d` | `3be0913a3b42d5f6a50b38474599df7c61d9204f` | Bootstrap exception described above |
| CHAR-1 | #1283 | `5003e6e5ea59401aae18e0483e755e2f9e8dc6dc` | `77ce42d9789cb0adc3cd809b4745119216076912` | Both required workflows passed |
| CHAR-2 | #1284 | `cdd198d0f65d55bb9ca98354e6447fe01215aacf` | `64be01ac02f2ccad108350c798c3084b92ccac23` | Both required workflows passed |
| CHAR-3 | #1285 | `9b5ca114133fd4be499e222da72fb27a3cdbd157` | `07290da229fa63f603314b6250319b00056605ab` | Both required workflows passed |
| CHAR-4 | #1286 | `d98294e554010012af17f99df9807dfbc74b5b65` | `71e1dae0d97563e5f43b6d2f80d4c6a25241114b` | Both required workflows passed |
| CHAR-5 | #1287 | `b1ef4b4b182cd4600695b50c61d84f198a3dfb17` | `58bb21f5c8a32a1b0c34d28cea188ccecf77b53a` | Both required workflows passed |
| CHAR-6 | #1288 | `7001d48d42750c3e800cf5ce44d6b2495553ead9` | `f897d4db947206fed429c17fce23bb4585523f5c` | Both required workflows passed |
| CHAR-7 | #1289 | `fd09e1611fc0e2c877fb81d7a53892dc3c4e868d` | `32517044c260e303aa6e82c8601d51fdd55a5421` | Both required workflows passed |
| CHAR-8 | #1290 | `5a93c0e1e340d38968d5c2143c2c35fda64c3355` | `e882c7482a5b3cdae69c3ef2ed0ca4be648ba5bd` | Both required workflows passed |
| CHAR-9 | #1291 | `f26cb9242ee1c1362edefae2c44aa6e0c77e54d7` | `2670e3cd00832097626f46383c4ab4ab714c33de` | Both required workflows passed |
| CHAR-10 | #1292 | `6ab7865aa7a1074758ba43d525845ba9909f9a05` | `a4d27e4f7cda358918010785bfb6fb5d7dfa5d6d` | Both required workflows passed |
| CHAR-11 | #1293 | `32407d7b39220a661a7794881032113d3eaba49d` | `cc42b5d18c02886ef3d51996f345cb74aea07058` | Both required workflows passed |

## Delivered boundaries

The merged implementation includes:

- server-owned, versioned character profiles and effective identity hashes;
- voice assets kept separate from character identity;
- clean context segments when identity or privacy policy changes;
- independent character-memory read and write permissions;
- strict System Assistant versus character memory ownership;
- read-only, category-limited sharing of selected System Assistant memory;
- character-aware live-call greeting, voice, speech delivery, and preload diagnostics;
- profile, memory, transcript, export, reset, archive, and unlink management controls;
- cloned-voice ownership, consent, allowed-use, hash, provenance, revocation, and deletion-state enforcement;
- hard server-owned AI identity disclosure policy;
- optional, review-first, owner-aware Character Hermes compatibility that remains separate from ordinary System Assistant Hermes synchronization.

## Default operational posture

The Character feature flags remain off unless a deployment intentionally enables a rollout stage:

```text
OMNIX_CHARACTER_MODE_ENABLED=0
OMNIX_CHARACTER_MEMORY_ENABLED=0
OMNIX_CHARACTER_SHARED_MEMORY_ENABLED=0
OMNIX_CHARACTER_HERMES_SYNC_ENABLED=0
```

Normal Chat memory remains independently controlled, including `OMNIX_CHAT_MEMORY_ENABLED` and the existing suggestion, history, compaction, and ordinary Hermes settings.

## Rollback posture

- Disabling Character Mode stops new character interactions without deleting profiles, versions, memories, transcripts, voice governance, or exports.
- Disabling character memory stops character-memory reads and writes while retaining existing owner-isolated records.
- Disabling shared memory removes the read-only System Assistant-memory bridge without changing either memory owner.
- Disabling Character Hermes stops its adapter without affecting native Character Mode or ordinary System Assistant Hermes synchronization.
- Voice revocation or deletion state prevents future character linking and live-call use; it does not silently delete the character profile or its memories.
- Destructive profile, memory, transcript, and voice actions remain explicit and independent.

## Repository conclusion

CHAR-0 through CHAR-11 are complete on `main`. The repository now contains the implementation, migrations, APIs, UI, adversarial coverage, feature gates, ownership boundaries, consent controls, and exact-head merge evidence. Production adoption remains an operational decision and should follow `character-mode-rollout.md` stage by stage.
