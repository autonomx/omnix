# Trading V3 research hypothesis — delayed base acceptance continuation

Status: **REJECTED on development gate; not selectable; no execution authority**.

This hypothesis was frozen after the cached 2025-10-01 through 2026-02-27 winner/loser attribution and before any March 2026 holdout access.

## Why this is a different hypothesis

The rejected post-V2 experiment tried to buy the first causal failed-selloff / L1 → B1 → higher-L2 continuation. The extended attribution did not support rescuing that entry with more thresholds.

The only effects that were both large enough to be interesting and directionally stable across every leave-one-month-out and leave-one-symbol-out recomputation in both the 1.5x and 0x variants were:

- later entry time;
- longer setup maturation (L1 → B1 elapsed time in the rejected model).

The new hypothesis therefore removes L1/B1 ownership entirely and asks a different question: **after the opening auction has had time to settle, does a stock that accepts above VWAP and breaks a mature rolling base with expanding volume have continuation edge?**

## Frozen research state machine

Universe inputs remain the same causal reconstructed candidate envelope used by the 103-session development cache. Historical point-in-time catalyst/supply facts are not invented.

1. **Opening observation — 09:30–10:00 ET**
   - No entries.
   - Build the 30-minute opening range from finalized 1-minute bars.

2. **Post-open base — minimum 15 finalized minutes entirely after 10:00 ET**
   - Use the immediately preceding 15 finalized 1-minute bars as the base.
   - Base range must be narrower than the 30-minute opening range. This is a structural compression relation, not a fitted numeric percentage.

3. **Acceptance / breakout trigger**
   - Current finalized close is above the prior 15-minute base high.
   - Current finalized close is above current regular-session VWAP.
   - Current bar volume is greater than the mean volume of the prior 15 base bars.
   - Only the first causal qualifying trigger for the symbol is used.
   - Last trigger remains 11:30 ET.

4. **Execution / risk**
   - Enter on the next eligible 1-minute bar using the existing deterministic paper execution model.
   - Initial stop is 15 bps below the prior 15-minute base low.
   - Reuse frozen V2 management only for risk/exit comparability: 1.5R target, 0.75R profit-protection arm, +0.25R protected stop, 60-minute maximum hold.
   - One trade per symbol/day; existing portfolio/risk sizing remains authoritative.

## Development gate before March can be opened

The full October-February block is development data because it was used to formulate this hypothesis. A cache-only development replay may reject the hypothesis, but cannot validate it.

March 2026 remains unopened unless the exact frozen state machine above achieves all of:

- at least **15 trades**;
- expectancy **>= +0.20R/trade**;
- one-sided 90% lower confidence bound **> 0R**;
- maximum drawdown **<= 5R**.

If the development gate fails, March remains sealed and this hypothesis is rejected without threshold rescue. If it passes, March may be used exactly once as a separately declared holdout with no intervening changes.

## Development result

The exact frozen hypothesis was replayed cache-only over all **103/103 sessions** from 2025-10-01 through 2026-02-27.

- Candidates: **447**
- Triggers/trades: **35**
- Winners/losses: **19 / 16**
- Expectancy: **+0.11724R/trade**
- One-sided 90% lower confidence bound: **-0.11687R**
- Maximum drawdown: **3.51698R**
- P&L from $100,000 initial cash under the existing deterministic paper model: **+$702.08**

The hypothesis passed the sample-size and drawdown floors but failed both the **+0.20R expectancy** floor and the **positive 90% lower-bound** requirement. Therefore:

- **development gate: FAILED**;
- **March 2026 holdout: remains sealed / was not loaded**;
- **no threshold/window rescue is permitted for this hypothesis**;
- the result supports the descriptive idea that later maturation is preferable to immediate opening entries, but does not establish a tradable edge by itself.

## Known data limitations

- Reconstruction uses current listings and Alpaca IEX partial-market bars, so survivorship/listing bias remains.
- The 103-session regular-session datasets do not contain premarket bar structure for the analyzed trades.
- Point-in-time catalyst evidence and dilution/supply flags were absent in the analyzed reconstructed trade snapshots; no hindsight web/SEC reconstruction is permitted.
- No authoritative historical halt feed is present. Missing/bar-gap patterns are not treated as confirmed halts.

Frozen `gap_pullback_v1 2.0.0` and its prospective qualification experiment remain unchanged.