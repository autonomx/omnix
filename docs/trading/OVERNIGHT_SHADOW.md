# Overnight trading strategy (SHADOW)

`overnight-trading-strategy-shadow` is a research group, separate from
`interday-trading-strategy-shadow`, that asks one question: do stocks picked
near the close gap up by the next open? It is **SHADOW only**. The kind
`overnight_shadow_v1` is registered with modes `off` and `shadow`; the
registry rejects `auto_paper` (`overnight_shadow_is_shadow_only`). Nothing
places, sizes or routes an order.

## Daily cycle

| Time (ET) | Step |
|---|---|
| 15:50 (`decision_et`) | Full-market scan of common stocks (Alpaca SIP). Features come from regular-session 30-minute bars that ended by 15:30 (`data_cutoff_et`), because the free SIP feed withholds the most recent 15 minutes. Each enabled arm records up to 5 picks (`overnight_pick`), plus the baseline population (`overnight_population`) and a scan marker (`overnight_scan`). |
| 15:55 (`entry_et`) | Shadow entry price: the open of the 15:55 one-minute bar (labelled later). |
| Next session 10:05 (`label_after_et`) | One-minute SIP bars label each pick: entry, the last premarket trade before 08:00, the 09:30 open (primary exit) and the 09:45 open. Writes `overnight_outcome` per pick and one `overnight_scorecard` per entry session. |

**Splits.** The scan's daily history (prior close, ADV, trend) is
split-adjusted, so a split taking effect on the decision day or in the trend
window is not read as a move; at decision time only splits through that day
exist, so this stays point-in-time. One-minute bars stay raw: before
labelling, Alpaca corporate actions are checked for a split taking effect
after the entry session and by the exit session, and its factor
(`split_factor`, 0.1 for a 1-for-10 reverse split) converts next-session
prices for the returns. Recorded prices stay as traded. A failed lookup
fails the cycle, so the session is labelled on a later tick rather than
with a fake gap.

Early-close sessions have no 15:55 bar, so no picks are recorded. A session
that is not labelled in time (Omnix offline) is labelled on a later morning;
the monitor looks back five sessions.

## Arms (config `arms`)

| Arm | Change vs prior close | Volume ÷ 20-day ADV | Close location in day range |
|---|---|---|---|
| `day2-runner` | ≥ +30% | ≥ 5× | ≥ 0.80 |
| `strong-close` | +10% to < +30% | ≥ 3× | ≥ 0.90 |

Both require a price of $1–$20 and rank by dollar volume. The scorecard also
scores the **baseline population**: every in-band stock up ≥ 10% at decision
time, with no other rules. An arm is only interesting if it beats that
baseline after costs (half-spread per side: 1.5% under $3, 1% under $10,
0.5% above).

## Market context (research only)

Each scan and scorecard also records the broad market through SPY, QQQ, IWM
and DIA (`OVERNIGHT_BENCHMARKS`). No arm reads it; it is collected so a
market-regime rule can be pre-registered and tested on sessions nobody has
looked at.

- `overnight_scan.market`: per ETF, the price at the data cutoff (last
  30-minute bar ended by 15:30) and its change vs the prior close
  (`change`), plus the prior session's own change (`prior_change`). Known at
  decision time. A failed fetch leaves `market` empty, sets `market_error`,
  and never blocks the picks.
- `overnight_scorecard.market`: per ETF, the return over the picks' holding
  window (15:55 one-minute open to the next 09:30 open, no costs), for
  market-adjusted scoring. This is an outcome, not a decision input.
- Trend, on every pick and population candidate: `prior_return_5d` (prior
  close vs the close five daily bars earlier) and `prior_up_days_5d` (up
  closes among those five), and `prior_return_20d` (vs the close 20 daily
  bars earlier), from split-adjusted daily bars before the decision day.
  `null` with too few prior daily bars, and on events recorded before these
  fields existed. Population stocks also get `off_52w_high`: prior close vs
  the highest daily high of up to 250 prior split-adjusted bars (`null` with
  fewer than 200, or if that extra fetch fails).
- `overnight_scan.social`: Reddit mention counts from ApeWisdom's public
  `all-stocks` list (rolling 24 hours, no API key), fetched page by page at
  the scan and kept only for population stocks. `ranked` is how many tickers
  the list held: a population stock missing from a successful fetch had no
  ranked mentions. A failed fetch sets `error` and never blocks the picks.
- `overnight_scan.news`: Alpaca (Benzinga) headlines known at the decision,
  from the prior session's 16:00 ET to the 15:30 data cutoff. Every
  population stock gets a context (`articles`, `categories`, newest five
  headlines), so `articles: 0` means no headline; a failed fetch sets
  `error` with no contexts (news unknown, not absent). The categories
  (`NEWS_CATEGORIES`: offering, reverse_split, fda_clinical, deal, earnings,
  theme) are frozen: the prospective test PREREG_OVERNIGHT4 (research cache)
  uses them by name, so changing them needs a new pre-registration.
- `overnight_mid_population`: the mid-cap research population for
  PREREG_OVERNIGHT5 (research cache): candidates priced $5-$50 with a
  20-session average dollar volume of $5M-$50M (`adv_dollars`), up at least
  5% at the data cutoff, with the same features as the small-cap population.
  The scan adds these stocks to its intraday read; the small-cap population
  and arms are unchanged by them. Their headlines are in
  `overnight_scan.news` (one request covers both populations). No arm reads
  them; outcomes are computed later from daily bars.
- `overnight_filings` (one event per scan, written after the scan marker so
  EDGAR's slower reads never delay or block the picks): per population
  stock, from SEC EDGAR, only filings accepted by the decision time:
  `filings_today` (form, 8-K items), `last_earnings` and the estimated
  `next_earnings_estimate` (8-K item 2.02, 52 weeks after its match),
  dilution signals (`shelf_last`: S-3/F-3 family within 3 years;
  `registration_last`: S-1/F-1/S-11 family within 180 days;
  `prospectus_count`/`prospectus_last`: 424B* within 90 days),
  `schedule_13d_count` (13D with the stock as subject, 30 days) and
  `insider` (Form 4 open-market purchases, code P, from the newest five
  Form 4s within 30 days). `cik: null` means not an SEC filer. The reads stop
  after 120 seconds (`truncated`); a failure for one company sets its
  `error`, and a missing SEC contact email or EDGAR outage sets the event's
  `error`. Windows look only at EDGAR's recent-filings list (at least a year
  or 1,000 filings).

## Operations

- Provisioned at startup by `strategy_overnight_monitor.provision_overnight_shadow_strategy`
  with its own evidence account `omnix-overnight-shadow`. Existing
  configurations, operator edits and archives are never overwritten.
- Switches: `OMNIX_TRADING_OVERNIGHT_SHADOW_MONITOR`,
  `OMNIX_TRADING_OVERNIGHT_SHADOW_AUTOPROVISION` (both default on; `_IN_TESTS`
  variants default off).
- A cycle may run up to 10 minutes (the scan takes about a minute when the
  process is idle). A timed-out cycle is retried on the next tick rather than
  stopping the monitor, and only one scan runs at a time: a cancelled cycle's
  scan thread finishes on its own and logs `overnight_shadow_monitor_error`
  if it fails.
- The strategy monitor skips kinds it does not own (registry `owner`), and the
  universe archiver skips kinds without a daily gapper universe.
- The Trading → Strategies panel shows the group read-only: schedule, arm
  rules, latest picks and scorecards.

## Prospective test (OVERNIGHT-4)

A forward test of a filtered POP10 rule (move under +23%, close within 4% of
the high, positive 20-session trend, no headline by 15:30; closing-auction
entry, opening-auction exit, 0.30% per side) was pre-registered on
2026-10-19, before any qualifying session existed. It runs on the first 250
sessions whose scan records `news`, with one futility look at 125. The
document lives in the research cache (`research/PREREG_OVERNIGHT4.md`,
gitignored); its SHA-256, recorded here so the text cannot change unnoticed:

`361d4a9f5d26c4fd331069d0be992286c2f4a177138083d9f94f2d524dd2ed69`

`FREEZE_OVERNIGHT4.txt` beside it pins the source files that define the
recorded fields. Changing the rule, costs, sessions or pass criteria needs a
new pre-registration, and so does changing `NEWS_CATEGORIES`.

## Mid-cap test (OVERNIGHT-5)

Two small-cap findings carried over to mid caps (price $5-$50, dollar ADV
$5M-$50M, up at least 5%): H1, a long overnight hold of moderate,
strong-closing, uptrending stocks with no headline; H2, a five-session short of
stocks that moved on headlines and closed weak. Pre-registered on 2026-10-19
with costs taken from SIP quotes and auction prints (mid-cap half-spread
about 0.06%, closing auctions of about $4M), then evaluated once on the
untouched 2022-03 to 2023-02 period; a hypothesis that passes is confirmed
forward on `overnight_mid_population`. Document: `research/PREREG_OVERNIGHT5.md`
(research cache), SHA-256:

`cdbd74082b350ae45ea8867fdbfdba8bd8649194d41014488d1e542274e5b0c2`

Result (evaluated once, 2026-10-19): both failed. H1 beat its population but
lost money (-0.26% net per trade); H2 earned +0.53% net per trade but no more,
reliably, than shorting every mid-cap mover in the 2022 bear market. The live
`overnight_mid_population` recording continues as data only.

A pre-registered historical test of the same arms (point-in-time universe,
March 2025 – October 2026) accompanies this strategy as research; its result
decides whether any arm deserves further work.
