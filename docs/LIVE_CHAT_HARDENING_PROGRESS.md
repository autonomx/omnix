# Live Chat Hardening Implementation Progress

Source roadmap: issue #1326  
Original implementation: PR #1327, merged at `7b18c335676dbc43a4bd5f53f8d3a2d7b1f7110b`  
Completion branch: `agent/live-chat-completion`  
Completion PR: #1328

## Phase status

| Phase | Status | Scope | Validation |
|---:|---|---|---|
| 9 | complete | target-runtime release evidence and v2 evaluator | original phase gate passed; completion aggregation gate pending final head |
| 10 | complete | calibration-backed automatic duplex | original phase gate passed; live waveform/current-device gate passed `535f2ea6121cdac04f5eb11a07d87bf8f5b5964b` |
| 11 | complete | authoritative browser conversation store | original phase gate passed; policy-consumption gate passed `a36913750c149c2e296d1bc10e6bab3621d347f7` |
| 12 | complete | durable Voice Session evaluation and preset tuning | original phase gate passed; completion evidence gate pending final head |

## Post-implementation review completion

The completion branch closes the repository gaps found after PR #1327:

1. **Combined release evidence** — the v2 gate accepts multiple System Assistant and Character evidence bundles and includes the original latency boundaries.
2. **Durable gate integration** — Voice Session records reproduce the aggregate gate, persist its status, and expose missing scenarios and failures in Voice Sessions.
3. **Runtime presence policies** — active versioned policies feed initiative timing, cooldown, response onset, target turn length, listener-backchannel cadence, and interruption sensitivity.
4. **Live acoustic evidence** — Automatic duplex is bound to the current input/output pair and barge-in uses a bounded playback reference plus delay-tolerant waveform similarity.
5. **Authoritative ownership** — speech over playback remains a candidate until classification; likely echo does not steal the user floor; policy decisions do not read visible DOM state.
6. **Trustworthy content-free metrics** — assistant text is summarized at the diagnostics privacy boundary into counts, a topic hash, and an obligation flag; raw text is discarded before persistence or upload.
7. **Runtime identity and tuning safety** — durable evidence carries browser/OS identity, and policy candidates are server-validated for count, existence, preset match, labels, runtime identity, and non-failed evidence.

## Repository completion gate

The final completion head must pass:

- RPG Phase 0 architecture compliance;
- RPG deterministic PR gates;
- Live Chat hardening gates;
- combined release aggregation and durable-store regressions;
- authoritative-state and privacy source guards;
- Web TypeScript and full unit suite;
- representative deterministic RPG smoke.

## Operational evidence boundary

Repository completion does not manufacture physical runtime evidence. Issue #1326 remains open until the required Windows/Chrome microphone, headphones/speakers, room-echo, background-noise, distance, interruption, initiative, backchannel, failure, rapid-interruption, and sustained-call scenarios are collected.

Until those labelled observations are sufficient, the machine-readable release gate must return `insufficient`, never `pass`. The final operator step is to obtain a real `pass` report and rehearse rollback to safe half-duplex plus conservative presence settings.
