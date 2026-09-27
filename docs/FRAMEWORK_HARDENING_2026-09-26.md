# Omnix framework hardening — 2026-09-26

This follow-up implements the remaining local rollout hardening. The deployment
is healthy; repository-wide Python validation still has unresolved failures.

## Changes deployed

- Memory suggestion processing now claims the specific PostgreSQL job, retains
  its original worker and lease token, renews during provider work, and fences
  late completion/failure after expiry, cancellation, or takeover. Derived
  candidates and successful completion commit in one transaction. Background
  callbacks no longer attempt transitions without an owned lease.
- Suggestion admission uses a durable identity scoped by workspace, principal,
  module, type, and idempotency key. Concurrent submissions preserve existing
  job results and logs instead of searching a bounded recent-job list.
- PostgreSQL job ownership uses the trusted user. Logical owners such as Chat
  session IDs remain in the compatibility contract, avoiding foreign-key errors.
- Gateway composition preserves an explicitly injected live TTS provider.
  Its warmed-provider default is installed only for the unconfigured shared
  lookup. Repeated factory calls previously replaced fake/alternate providers
  and could leave tests waiting indefinitely for audio from an unavailable model.
- Real-provider qualification found a Windows sharing violation while deleting
  a finished TTS priority marker. Cleanup now tolerates Windows errors 32/33
  after releasing the generation lock. A later scan reaps the unlocked marker;
  an unlocked marker does not become active solely because deletion raced.
  Other permission failures retain their original behavior. The TTS process was
  restarted to deploy this fix, preserving the other service PIDs during that
  restart; see [TTS restart](measurements/hardening-tts-restart-2026-09-26.json).
- Root web commands select the supported runtime via
  `scripts/web_toolchain.mjs`. Windows installation uses
  `python scripts/install_node_toolchain.py`, verifies the official archive
  SHA256, and installs into ignored `.tools`. `.node-version` pins **22.23.3**.
- Trading loads optional analysis, terminal, and side panels on selection.
  The chart engine has a separate cacheable chunk. Equivalent ISO timestamp
  spellings now merge by epoch time, fixing duplicate bars and indicator errors
  observed in the live browser.
- RPG timeline insertion uses the existing node identity index instead of
  scanning every root. Historical RPG report hooks are isolated between tests
  to prevent recursive report generation during broad validation.
- Five historical RPG test modules installed global import interceptors and
  replaced application modules with stubs. Their module maps, parent-package
  attributes, and import finders are now restored after collection and each
  test, including exceptional collection. Other tests retain real modules.
- The Chat atomic integration test imports its shared fixture by package name,
  allowing both normal and `importlib` pytest collection.

## Measurements

| Check | Result | Evidence |
| --- | --- | --- |
| Real-provider soak | 180.474 s; 3,089 successful reads; zero read errors | [Soak](measurements/gateway-soak-2026-09-26.json) |
| Read latency under soak | p50 15.34 ms; p95 42.79 ms; p99 51.57 ms; max 5,992.25 ms | Same soak |
| Real Chat | Two Codex jobs completed in 13.129 / 3.579 s; cross-replica idempotency passed; one persisted reply each | Same soak |
| Real voice | Qwen PCM → Nemotron/Parakeet transcription passed twice; first audio 1.790 / 1.474 s | Same soak |
| Real market reads | Binance BTC-USDT and Yahoo AAPL, 30 bars each, passed | Same soak |
| Deployment ownership | One worker, two API replicas, exactly one background advisory-lock owner; all ready | [Deployment](measurements/gateway-routed-deployment-2026-09-26.json) |
| Migrations | Schema `0097_chat_session_coordination`; no pending migrations or checksum drift | Same deployment |
| Controlled restart | Gateway ready after 16.798 s; web after 5.110 s; STT/TTS/Hermes/image PIDs preserved | [Restart](measurements/hardening-restart-2026-09-26.json) |
| Live memory lease | Created → claimed → running → completed; repeated admission preserved identity | [Lease](measurements/memory-live-lease-2026-09-26.json) |
| Trading initial chunks | Workspace 384.00 kB + chart engine 176.65 kB = 560.65 kB; previous workspace 864.87 kB, approximately 35% deferred | [Build sizes](measurements/hardening-trading-build-2026-09-26.json) |
| RPG independent root insertion | 20,000 events: 2.300028 s → 0.016577 s, 138.75× | [Scaling](measurements/timeline-root-scaling-2026-09-26.json) |

The Node archive SHA256 was
`2b0ff57b049cda1bbcea2240eec20467018713c1efe1f7360c2681859b90ed71`.
Trading payload figures are uncompressed JavaScript; shared app dependencies
are excluded from both figures. The RPG measurement covers independent root
insertion, not overall RPG throughput.

The final soak ran while the broad Python suite was active on the same machine.
Its 5.992 s slowest read is retained in the report; percentile results do not
imply that every request met a latency target. This is a shared-machine local
baseline, not an isolated capacity benchmark.

## Validation

- **Web:** all **1,532 tests across 423 files passed**. Final production build
  passed without unsupported-Node, circular-chunk, or oversized-chunk warnings.
- **Python:** the final combined run passed **92 distinct focused checks** in
  30.70 s using `importlib` collection and disposable PostgreSQL. It covers
  leases, Chat transactions and ownership, recovery, jobs, audiobook, privacy,
  maintenance, report-hook and import isolation, timeline insertion, and Node
  installer checksum/path validation, live voice PCM, startup latency, and
  explicit TTS provider composition, cross-process TTS priority, crash cleanup,
  and Windows sharing violations. See the
  [focused outcome](measurements/hardening-focused-tests-2026-09-26.json).
- Collecting the five historical stub modules alongside 20 real PostgreSQL
  lease/ownership tests now runs those PostgreSQL tests successfully. The
  combined diagnostic run had 304 passed, ten stale RPG assertion failures,
  and one retired RPG attribute collection error; see
  [isolation qualification](measurements/hardening-import-isolation-2026-09-26.json).
- The ten voice composition/transport tests passed independently after fixing
  the provider overwrite; see
  [voice qualification](measurements/hardening-voice-composition-2026-09-26.json).
- Five TTS priority checks passed, including generation completion despite a
  simulated Windows sharing violation and later stale-marker cleanup; see
  [priority checks](measurements/hardening-tts-priority-2026-09-26.json).
- A repeated real-provider soak initially had one TTS HTTP 500 with 3,026
  successful reads and no read errors. The traceback identified the Windows
  marker deletion race. The failure is preserved in
  [pre-fix soak](measurements/gateway-soak-windows-priority-failure-2026-09-26.json).
- The earlier timeline/EventBus group also passed 15 checks, including the
  bounded seen-ID case at 200,000 events.
- Changed Python runtime files and scripts passed Ruff and compilation under
  the deployed Python 3.10 runtime. `conftest.py` passed Ruff with its pre-existing
  path-bootstrap E402 exceptions excluded. Final diff whitespace checks passed.
- Browser inspection confirmed the optional Strategies panel finishes loading,
  its close control works, and live chart updates no longer show the observed
  duplicate-timestamp indicator error. No trading controls were exercised.
- The first repository-wide run had 9,505 passed, 4,925 failed, 442 skipped,
  and 360 errors in 664.42 s. Its global stub contamination caused unrelated
  tests to receive `MagicMock` values, including PostgreSQL user IDs. Those
  counts are not a reliable independent defect inventory. A fresh run after
  import isolation finished its test cases with **13,111 passed, 1,278 failed,
  442 skipped, and 358 errors** in 828.21 s. The 358 errors include 112 collection
  failures. See the [outcome inventory](measurements/hardening-full-python-isolated-2026-09-26.json).
  That broad run began before the final Windows cleanup fix; the final 92-check
  focused run validates that fix and the affected runtime contracts.

## Remaining qualification

- The broad Python suite has collection and execution failures beyond the nine
  failures repaired during the earlier framework work. Examples include imports
  of retired SQLite/Flask/RPG contracts, missing optional audio/async test
  dependencies, and stale persistence mocks. Failures require individual triage;
  they were not deleted, blanket-skipped, or treated as passing.
  Verified examples from the fresh run include 69 setup errors calling Flask's
  `test_client` on FastAPI, 53 using FastAPI's nonexistent `config` attribute,
  imports of removed RPG model classes, and tests reading retired static files.
  Other assertion and behavior failures remain unresolved; this inventory is
  not a claim that every failure is obsolete or harmless.
- Physical browser microphone capture, speaker playback, and interruption
  remain unverified pending the user's hands-on call. Generated speech passed
  through real TTS and STT; this does not establish physical device behavior.
- The three-minute soak and controlled restart establish a local baseline.
  They do not establish maximum capacity, long-duration stability, or multi-host
  failover. Recovery and fencing have PostgreSQL regression coverage; the restart
  deliberately waited for active Chat jobs to finish.
- Memory job leases fence individual attempts. This change does not add an
  autonomous replay loop for old queued memory jobs.
- Qualification covers read-only market data, not funded brokerage execution.
  Existing provider settings and trading/agent authority were preserved.

## Reproduce

```text
python scripts/install_node_toolchain.py
node scripts/web_toolchain.mjs --version
node scripts/web_toolchain.mjs test -- --run
node scripts/web_toolchain.mjs build
python scripts/measure_gateway_soak.py --model gpt-5.6-luna --duration-seconds 180 --workers 4 --output resources/artifacts/gateway-soak-check.json
```

PostgreSQL integration tests require `OMNIX_TEST_DATABASE_URL` pointing at a
disposable database. The suite includes schema reset/truncation tests. Never
point those tests at the deployed database.
