# Managed Finviz Top-5 SHADOW startup profile

Omnix automatically provisions one built-in Finviz research strategy when the
web gateway starts.

Managed strategy ID:

`finviz-learning-v2-shadow`

Managed paper account ID:

`omnix-finviz-shadow`

The profile starts in SHADOW and uses the exact morning cohort policy evaluated
in the Sep 2026 Finviz workflow. AUTO PAPER is available only after the existing
prospective qualification and explicit review path has authorized this exact
profile/evidence snapshot:

- capture time: 09:15 ET;
- discovery source: Finviz Top Gainers;
- source cohort size: first 5 ranked symbols;
- no pagination or replacement beyond those first five;
- if one of the source five cannot be enriched or fails downstream eligibility,
  Omnix does not substitute #6;
- deterministic V2 structure evaluation begins from 09:35 ET;
- intraday learning is enabled;
- 3-minute Stoch RSI trend capture is enabled;
- intraday LLM review is enabled for the top five at a 10-minute cadence;
- execution-cost SHADOW accounting remains enabled through the Stoch lifecycle;
- the four-arm SHADOW experiment runs the deterministic V2 baseline, Stoch trend capture,
  stateful AI on every completed 1-minute bar, and a separate event-driven AI policy over
  the same frozen Top-5 cohort.

## Startup behavior

On every production startup, Omnix:

1. checks the stable managed strategy ID;
2. if it was explicitly archived, does nothing;
3. otherwise ensures a durable paper account exists;
4. creates the strategy if missing;
5. restores the exact managed SHADOW configuration if it was merely edited,
   disabled, or switched off;
6. preserves an already-enabled AUTO PAPER mode that was previously promoted
   through the normal reviewed qualification path, while clearing any stale
   prior-session universe pointer so the current immutable morning archive is used;
7. leaves unrelated strategies untouched;
8. starts the normal strategy monitor only after provisioning finishes.

The default managed account starts with USD 1,000. Startup never grants AUTO PAPER
permission by itself. If a persisted AUTO PAPER promotion exists, the runtime
re-evaluates the V2 qualification evidence/profile fingerprint before each cycle
and fails closed when qualification or the current daily archive is not ready.
The AI experiment remains research-only and has no paper-account or broker-order
authority.

The provisioner is idempotent across repeated starts and converges safely when
multiple application workers start at the same time.

## Operator controls

Disable automatic provisioning:

`OMNIX_TRADING_FINVIZ_SHADOW_AUTOPROVISION=0`

Use an existing paper account instead of the managed account:

`OMNIX_TRADING_FINVIZ_SHADOW_ACCOUNT_ID=<existing-account-id>`

The override is fail-closed: the named account must already exist.

Change only the initial cash used when the managed account is first created:

`OMNIX_TRADING_FINVIZ_SHADOW_INITIAL_CASH=1000`

Changing the initial-cash environment variable later does not reset or mutate an
existing account.

For legacy-test persistence mode, provisioning remains off unless explicitly
opted in with:

`OMNIX_TRADING_FINVIZ_SHADOW_AUTOPROVISION_IN_TESTS=1`

## Operator opt-out

Archiving the managed strategy is treated as an explicit durable opt-out.
Startup will not resurrect it or create account-side effects after archive.
Simple OFF/disabled edits are not considered an opt-out and are restored on the
next startup.
