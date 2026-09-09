import { useEffect, useMemo, useState } from 'react';
import { tradingStrategyApi } from './tradingStrategyApi';
import {
  tradingStrategyOperationsApi,
  type SolanaAIDecisionEvent,
  type SolanaAIStrategyRecord,
  type TradingOperationalHealth,
  type TradingStrategyOperationsStatus,
} from './tradingStrategyOperationsApi';
import type { TradingStrategyConfig } from './tradingStrategyTypes';
import './TradingCommandCenter.css';

function number(value: string | number | null | undefined, digits = 2): string {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed.toLocaleString(undefined, { maximumFractionDigits: digits }) : '—';
}

function money(value: string | number | null | undefined, currency: string, signed = false): string {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return '—';
  const sign = signed && parsed > 0 ? '+' : parsed < 0 ? '-' : '';
  return `${sign}${Math.abs(parsed).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
}

function pct(value: string | number | null | undefined, digits = 2): string {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? `${parsed.toFixed(digits)}%` : '—';
}

function time(value: string | null | undefined): string {
  if (!value) return 'Never';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function reasonLabel(value: string): string {
  return value.toLowerCase().replaceAll('_', ' ');
}

function StatusDot({ state }: { state: 'healthy' | 'degraded' | 'blocked' | 'unknown' }) {
  return <span className={`command-center-status-dot state-${state}`} aria-hidden="true" />;
}

function Card({
  label,
  value,
  detail,
  state,
}: {
  label: string;
  value: string;
  detail: string;
  state?: 'healthy' | 'degraded' | 'blocked' | 'unknown';
}) {
  return (
    <article className="command-center-card" data-health-state={state ?? 'unknown'}>
      <header>{state ? <StatusDot state={state} /> : null}<small>{label}</small></header>
      <strong>{value}</strong>
      <span>{detail}</span>
    </article>
  );
}

export function TradingCommandCenter({
  accountId,
  strategyId,
  currency,
}: {
  accountId: string;
  strategyId: string | null;
  currency: string;
}) {
  const [health, setHealth] = useState<TradingOperationalHealth | null>(null);
  const [runtime, setRuntime] = useState<TradingStrategyOperationsStatus | null>(null);
  const [strategy, setStrategy] = useState<TradingStrategyConfig | null>(null);
  const [solanaStrategy, setSolanaStrategy] = useState<SolanaAIStrategyRecord | null>(null);
  const [solanaDecisions, setSolanaDecisions] = useState<SolanaAIDecisionEvent[]>([]);
  const [solanaControlPending, setSolanaControlPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    let timer: number | null = null;
    const refresh = async () => {
      try {
        const [nextHealth, nextRuntime, nextStrategy, nextSolanaStrategy, nextSolanaDecisions] = await Promise.all([
          tradingStrategyOperationsApi.health(accountId),
          tradingStrategyOperationsApi.status(),
          strategyId ? tradingStrategyApi.get(strategyId) : Promise.resolve(null),
          tradingStrategyOperationsApi.solanaStrategy(),
          tradingStrategyOperationsApi.solanaDecisions(10),
        ]);
        if (!alive) return;
        setHealth(nextHealth);
        setRuntime(nextRuntime);
        setStrategy(nextStrategy);
        setSolanaStrategy(nextSolanaStrategy);
        setSolanaDecisions(nextSolanaDecisions);
        setError(null);
      } catch (reason) {
        if (!alive) return;
        setError(reason instanceof Error ? reason.message : String(reason));
      }
    };
    void refresh();
    timer = window.setInterval(() => void refresh(), 5_000);
    return () => {
      alive = false;
      if (timer !== null) window.clearInterval(timer);
    };
  }, [accountId, strategyId]);

  const paperMonitor = runtime?.paper_monitor;
  const strategyMonitor = runtime?.strategy_monitor;
  const operatingLabel = useMemo(() => {
    if (!strategy) return 'Account view';
    if (strategy.archived_at) return 'Archived';
    if (!strategy.enabled || strategy.mode === 'off') return 'Off';
    return strategy.mode === 'auto_paper' ? 'AUTO PAPER' : 'SHADOW';
  }, [strategy]);
  const monitorState = paperMonitor?.running
    ? 'healthy'
    : paperMonitor?.configured_enabled && paperMonitor?.registered
      ? 'degraded'
      : 'blocked';
  const risk = health?.risk;
  const execution = health?.execution;
  const healthState = health?.state ?? 'unknown';
  const riskReasons = risk?.reason_codes ?? [];
  const systemReasons = health?.reason_codes.filter((reason) => reason !== 'INSTRUMENT_NOT_SELECTED') ?? [];
  const latestSolanaDecision = solanaDecisions[0];
  const latestSolanaPayload = latestSolanaDecision?.payload?.decision;
  const latestSolanaAction = latestSolanaPayload && typeof latestSolanaPayload === 'object'
    ? String((latestSolanaPayload as Record<string, unknown>).action ?? latestSolanaDecision.state)
    : latestSolanaDecision?.state;

  const toggleSolana = async () => {
    if (!solanaStrategy || solanaControlPending) return;
    setSolanaControlPending(true);
    try {
      if (solanaStrategy.running) await tradingStrategyOperationsApi.stopSolana();
      else await tradingStrategyOperationsApi.startSolana();
      const [nextStrategy, nextDecisions] = await Promise.all([
        tradingStrategyOperationsApi.solanaStrategy(),
        tradingStrategyOperationsApi.solanaDecisions(10),
      ]);
      setSolanaStrategy(nextStrategy);
      setSolanaDecisions(nextDecisions);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSolanaControlPending(false);
    }
  };

  return (
    <section className="trading-command-center" aria-label="Daily trading command center" data-health-state={healthState}>
      <header className="command-center-header">
        <div>
          <strong>Daily Command Center</strong>
          <small>Server-authoritative account risk, paper execution runtime and today&apos;s operating state</small>
        </div>
        <span className={`command-center-overall state-${healthState}`}>
          <StatusDot state={healthState} />
          {healthState === 'unknown' ? 'Loading health' : healthState.toUpperCase()}
        </span>
      </header>

      <div className="command-center-grid">
        <Card
          label="Today realized P&L"
          value={money(risk?.daily_realized_pnl, currency, true)}
          detail={`Loss headroom ${money(risk?.daily_loss_remaining, currency)}`}
          state={risk?.state ?? 'unknown'}
        />
        <Card
          label="Open risk at stop"
          value={`${money(risk?.open_risk_dollars, currency)} · ${pct(risk?.open_risk_pct)}`}
          detail={`Server limit ${pct(risk?.max_open_risk_pct)} · ${risk?.policy_source === 'active_strategy' ? 'strategy policy' : 'paper policy'}`}
          state={risk?.state ?? 'unknown'}
        />
        <Card
          label="Buying power"
          value={money(risk?.buying_power, currency)}
          detail={`Equity ${money(risk?.equity, currency)}`}
        />
        <Card
          label="Exposure"
          value={`${risk?.position_count ?? 0} positions · ${risk?.open_order_count ?? 0} orders`}
          detail={`${risk?.active_protection_count ?? 0} protections · ${risk?.unprotected_exposure_count ?? 0} unprotected`}
          state={(risk?.unprotected_exposure_count ?? 0) > 0 ? 'blocked' : risk?.state ?? 'unknown'}
        />
        <Card
          label="Paper execution dispatcher"
          value={paperMonitor?.running ? 'Running' : paperMonitor?.registered ? 'Stopped' : 'Not registered'}
          detail={`${paperMonitor?.interval_seconds == null ? '—' : `${number(paperMonitor.interval_seconds, 2)}s`} cadence · last ${time(paperMonitor?.last_run_at)}`}
          state={monitorState}
        />
        <Card
          label="Strategy runtime"
          value={operatingLabel}
          detail={strategy ? `v${strategy.strategy_version} · rev ${strategy.revision}${strategy.risk.kill_switch ? ' · kill switch ON' : ''}` : strategyId ? 'Loading selected strategy' : 'All strategies'}
          state={strategy?.risk.kill_switch ? 'blocked' : strategyMonitor?.running || strategy?.mode !== 'auto_paper' ? 'healthy' : 'degraded'}
        />
        <Card
          label="Execution market check"
          value={execution?.instrument_id ? execution.state.toUpperCase() : 'Symbol context pending'}
          detail={execution?.instrument_id
            ? `${execution.provider ?? 'provider —'} · ${execution.spread_bps == null ? 'spread —' : `${number(execution.spread_bps)} bps`} · ${execution.freshness_mode ?? 'freshness —'}`
            : 'Account health is live; symbol execution eligibility is evaluated when a symbol is selected'}
          state={execution?.instrument_id ? execution.state : 'unknown'}
        />
        <Card
          label="Safety authority"
          value="Paper only"
          detail="Live broker OFF · AI order placement OFF · server risk authority ON"
          state="healthy"
        />
        <Card
          label="Solana AI 1m shadow"
          value={solanaStrategy?.running ? 'Running' : solanaStrategy ? 'Stopped' : 'Loading'}
          detail={`${solanaStrategy?.decision_count ?? 0} decisions · latest ${latestSolanaAction ?? 'none'}`}
          state={solanaStrategy?.running ? 'healthy' : solanaStrategy?.configured_enabled ? 'degraded' : 'blocked'}
        />
      </div>

      {solanaStrategy ? (
        <div className="command-center-attention" aria-label="Solana AI strategy history">
          <strong>{solanaStrategy.display_name}</strong>
          <span>
            {solanaStrategy.instrument_id} · {solanaStrategy.chart_interval} · research-only · no execution authority
          </span>
          <button type="button" disabled={solanaControlPending} onClick={() => void toggleSolana()}>
            {solanaControlPending ? 'Updating…' : solanaStrategy.running ? 'Stop shadow monitor' : 'Start shadow monitor'}
          </button>
          <span>
            {solanaDecisions.length
              ? solanaDecisions.slice(0, 5).map((item) => `${time(item.observed_at)} ${item.state}`).join(' · ')
              : 'No persisted Solana decisions yet.'}
          </span>
        </div>
      ) : null}

      {(systemReasons.length > 0 || riskReasons.length > 0 || paperMonitor?.last_error) ? (
        <div className="command-center-attention" role="status">
          <strong>Needs attention</strong>
          <span>{[
            ...new Set([...systemReasons, ...riskReasons]),
          ].map(reasonLabel).join(' · ') || paperMonitor?.last_error}</span>
        </div>
      ) : (
        <div className="command-center-clear" role="status">
          <strong>Account checks clear</strong>
          <span>Risk limits are within policy. Symbol-level execution eligibility remains fail-closed at order time.</span>
        </div>
      )}

      {error ? <div className="command-center-error" role="alert">Command Center refresh failed: {error}</div> : null}
    </section>
  );
}
