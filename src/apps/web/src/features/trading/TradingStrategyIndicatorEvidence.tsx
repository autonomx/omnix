import type { StrategyEvent } from './tradingStrategyTypes';
import './TradingStrategyIndicatorEvidence.css';

export type IndicatorSnapshotEvidence = {
  close: string | null;
  ema9: string | null;
  ema20: string | null;
  macd: string | null;
  macdSignal: string | null;
  macdHistogram: string | null;
  stochasticRsiK: string | null;
  stochasticRsiD: string | null;
};

export type ProspectiveIndicatorEvidence = {
  eventId: string;
  instrumentId: string;
  observedAt: string;
  cutoff: string | null;
  source: string | null;
  partialMarket: boolean;
  barCount: number;
  fullWarmup: boolean;
  confirmed: boolean | null;
  reasonCodes: string[];
  error: string | null;
  oneMinute: IndicatorSnapshotEvidence;
  fiveMinute: IndicatorSnapshotEvidence;
};

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function text(value: unknown): string | null {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return null;
}

function booleanValue(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null;
}

function numberValue(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return 0;
}

function snapshot(value: unknown): IndicatorSnapshotEvidence {
  const item = record(value);
  return {
    close: text(item?.close),
    ema9: text(item?.ema9),
    ema20: text(item?.ema20),
    macd: text(item?.macd),
    macdSignal: text(item?.macd_signal),
    macdHistogram: text(item?.macd_histogram),
    stochasticRsiK: text(item?.stochastic_rsi_k),
    stochasticRsiD: text(item?.stochastic_rsi_d),
  };
}

export function collectProspectiveIndicatorEvidence(
  events: StrategyEvent[],
  limit = 12,
): ProspectiveIndicatorEvidence[] {
  const output: ProspectiveIndicatorEvidence[] = [];
  for (const event of events) {
    if (event.event_type !== 'shadow_execution') continue;
    const execution = record(event.payload.execution);
    if (!execution || !('indicator_entry_confirmed' in execution)) continue;
    const context = record(execution.indicator_context);
    const reasons = Array.isArray(execution.indicator_entry_reason_codes)
      ? execution.indicator_entry_reason_codes.filter((value): value is string => typeof value === 'string')
      : [];
    output.push({
      eventId: event.event_id,
      instrumentId: event.instrument_id,
      observedAt: event.observed_at,
      cutoff: text(execution.indicator_context_cutoff),
      source: text(execution.indicator_context_source),
      partialMarket: booleanValue(execution.indicator_context_partial_market) === true,
      barCount: numberValue(execution.indicator_context_bar_count),
      fullWarmup: booleanValue(execution.indicator_context_full_warmup) === true,
      confirmed: booleanValue(execution.indicator_entry_confirmed),
      reasonCodes: reasons,
      error: text(execution.indicator_context_error),
      oneMinute: snapshot(context?.one_minute),
      fiveMinute: snapshot(context?.five_minute),
    });
    if (output.length >= Math.max(0, limit)) break;
  }
  return output;
}

function compactDecimal(value: string | null): string {
  if (value === null) return '—';
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return value;
  const magnitude = Math.abs(parsed);
  if (magnitude >= 100) return parsed.toFixed(2);
  if (magnitude >= 1) return parsed.toFixed(3);
  return parsed.toFixed(4);
}

function statusLabel(item: ProspectiveIndicatorEvidence): string {
  if (item.confirmed === true) return 'CONFIRMED';
  if (item.confirmed === false) return 'VETOED';
  return 'UNAVAILABLE';
}

function statusTone(item: ProspectiveIndicatorEvidence): string {
  if (item.confirmed === true) return 'confirmed';
  if (item.confirmed === false) return 'vetoed';
  return 'unavailable';
}

function IndicatorValues({ label, value }: { label: string; value: IndicatorSnapshotEvidence }) {
  return (
    <div className="indicator-evidence-timeframe">
      <strong>{label}</strong>
      <span>Close <b>{compactDecimal(value.close)}</b></span>
      <span>EMA9 <b>{compactDecimal(value.ema9)}</b></span>
      <span>EMA20 <b>{compactDecimal(value.ema20)}</b></span>
      <span>MACD <b>{compactDecimal(value.macd)}</b></span>
      <span>Signal <b>{compactDecimal(value.macdSignal)}</b></span>
      <span>Hist <b>{compactDecimal(value.macdHistogram)}</b></span>
      <span>Stoch K <b>{compactDecimal(value.stochasticRsiK)}</b></span>
      <span>Stoch D <b>{compactDecimal(value.stochasticRsiD)}</b></span>
    </div>
  );
}

export function TradingStrategyIndicatorEvidence({
  events,
  visible,
  loadError = null,
}: {
  events: StrategyEvent[];
  visible: boolean;
  loadError?: string | null;
}) {
  if (!visible) return null;
  const evidence = collectProspectiveIndicatorEvidence(events);
  return (
    <section className="trading-indicator-evidence" aria-label="Prospective indicator entry evidence">
      <header>
        <div>
          <strong>Prospective indicator entry evidence</strong>
          <small>Research only · frozen entry rule · no AUTO PAPER authority · Alpaca IEX partial-market evidence</small>
        </div>
        <span>{evidence.length} signals</span>
      </header>
      {evidence.length ? (
        <div className="indicator-evidence-list">
          {evidence.map((item) => (
            <article key={item.eventId} data-status={statusTone(item)}>
              <header>
                <div>
                  <strong>{item.instrumentId.split(':').at(-1) ?? item.instrumentId}</strong>
                  <small>{new Date(item.observedAt).toLocaleTimeString()} · cutoff {item.cutoff ? new Date(item.cutoff).toLocaleTimeString() : '—'}</small>
                </div>
                <span className="indicator-evidence-status">{statusLabel(item)}</span>
              </header>
              <div className="indicator-evidence-meta">
                <span className={item.fullWarmup ? 'pass' : 'warn'}>{item.fullWarmup ? 'Full 1m/5m warm-up' : 'Partial warm-up'}</span>
                <span>{item.barCount} finalized 1m bars</span>
                <span>{item.source ?? 'unknown source'}{item.partialMarket ? ' · partial market' : ''}</span>
              </div>
              {item.error ? <p className="indicator-evidence-error">{item.error}</p> : null}
              {!item.error && item.reasonCodes.length ? (
                <p className="indicator-evidence-reasons">Veto: {item.reasonCodes.join(' · ')}</p>
              ) : null}
              <div className="indicator-evidence-timeframes">
                <IndicatorValues label="1 minute" value={item.oneMinute} />
                <IndicatorValues label="5 minute" value={item.fiveMinute} />
              </div>
            </article>
          ))}
        </div>
      ) : loadError ? (
        <p className="indicator-evidence-error">Could not load persisted SHADOW indicator evidence: {loadError}</p>
      ) : (
        <p className="indicator-evidence-empty">Waiting for prospective Aug 24+ V2 SHADOW structural signals. No indicator result is inferred before a signal exists.</p>
      )}
    </section>
  );
}
