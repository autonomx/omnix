import { useEffect, useMemo, useState } from 'react';
import { tradingPaperApi } from './tradingPaperApi';
import { TRADING_STRATEGY_DEFINITIONS } from './tradingStrategyCatalog';
import { tradingStrategyApi } from './tradingStrategyApi';
import type {
  GapperCandidate,
  GapperUniverse,
  GapperUniverseFreezeInput,
  GapPullbackConfig,
  StrategyEvent,
  StrategyMode,
  StrategyProtection,
  StrategyResearchReview,
  TradingStrategyConfig,
} from './tradingStrategyTypes';
import './TradingStrategiesPanel.css';

const definition = TRADING_STRATEGY_DEFINITIONS.gap_pullback_v1;

const defaultStrategy = (accountId: string): TradingStrategyConfig => ({
  strategy_id: `gap-pullback-${Date.now()}`,
  account_id: accountId,
  strategy_kind: 'gap_pullback_v1',
  strategy_version: '1.1.0',
  mode: 'shadow',
  active_universe_id: null,
  enabled: true,
  revision: 1,
  config: {
    strategy_id: 'gap_pullback_v1',
    strategy_version: '1.1.0',
    minimum_gap_pct: '20',
    minimum_price: '0.50',
    maximum_price: '20',
    minimum_premarket_dollar_volume: '10000000',
    minimum_tod_rvol: '5',
    maximum_spread_bps: '150',
    preferred_float_min_shares: '2000000',
    preferred_float_max_shares: '30000000',
    float_preference_mode: 'score',
    require_catalyst_evidence: true,
    reject_dilution_flags: ['registered_offering', 'atm', 'warrants', 'convertible', 'equity_line'],
    opening_impulse_min_pct: '8',
    pullback_min_pct: '15',
    pullback_max_pct: '55',
    pullback_volume_max_ratio: '0.70',
    higher_low_buffer_bps: '20',
    breakout_volume_ratio: '1.25',
    pivot_left_bars: 2,
    pivot_right_bars: 2,
    volume_lookback_bars: 10,
    require_breakout_hold: true,
    breakout_hold_bars: 1,
    breakout_hold_tolerance_bps: '25',
    minimum_quality_score: 7,
    stop_buffer_bps: '15',
    reward_multiple: '2',
    entry_start_et: '09:35:00',
    last_entry_et: '11:30:00',
  },
  risk: {
    risk_per_trade_pct: '0.35',
    max_daily_loss_pct: '1.5',
    max_open_risk_pct: '1',
    max_positions: 3,
    max_trades_per_day: 5,
    max_trade_value: '25000',
    one_trade_per_symbol_per_day: true,
    max_spread_bps: '150',
    entry_start_et: '09:35:00',
    last_entry_et: '11:30:00',
    force_flat_et: '15:55:00',
    kill_switch: false,
  },
});

function eventTone(event: StrategyEvent): string {
  if (event.event_type === 'rejection' || event.state === 'rejected' || event.state === 'research_error') return 'rejected';
  if (event.event_type === 'entry_order_submitted' || event.state === 'entry_ready' || event.state === 'research_reviewed') return 'ready';
  return 'working';
}

function universeImport(raw: string, fallbackUniverseId: string | null): GapperUniverseFreezeInput {
  const parsed: unknown = JSON.parse(raw);
  const object: Record<string, unknown> | null = Array.isArray(parsed)
    ? { candidates: parsed }
    : parsed && typeof parsed === 'object'
      ? parsed as Record<string, unknown>
      : null;
  if (!object || !Array.isArray(object.candidates) || object.candidates.length === 0) {
    throw new Error('Universe JSON must be a candidate array or an object with a non-empty candidates array.');
  }
  const now = new Date();
  const today = now.toISOString().slice(0, 10);
  const universeId = typeof object.universe_id === 'string' && object.universe_id.trim()
    ? object.universe_id.trim()
    : fallbackUniverseId?.trim() || `gappers-${today}`;
  const discovery = typeof object.discovery_source === 'string' ? object.discovery_source : 'import';
  if (!['manual', 'import', 'scanner', 'provider'].includes(discovery)) {
    throw new Error('discovery_source must be manual, import, scanner, or provider.');
  }
  return {
    universe_id: universeId,
    session_date: typeof object.session_date === 'string' ? object.session_date : today,
    evaluation_time: typeof object.evaluation_time === 'string' ? object.evaluation_time : now.toISOString(),
    discovery_source: discovery as GapperUniverseFreezeInput['discovery_source'],
    candidates: object.candidates as GapperCandidate[],
  };
}

function numeric(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null;
  const next = Number(value);
  return Number.isFinite(next) ? next : null;
}

function compactNumber(value: string | number | null | undefined): string {
  const next = numeric(value);
  if (next === null) return '—';
  return Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 }).format(next);
}

function percent(value: string | number | null | undefined): string {
  const next = numeric(value);
  return next === null ? '—' : `${next.toFixed(next >= 10 ? 1 : 2)}%`;
}

function basisPoints(value: string | number | null | undefined): string {
  const next = numeric(value);
  return next === null ? '—' : `${next.toFixed(0)} bps`;
}

function latestEventMap(events: StrategyEvent[]): Map<string, StrategyEvent> {
  const output = new Map<string, StrategyEvent>();
  for (const event of events) {
    if (event.event_type === 'research_llm') continue;
    if (!output.has(event.instrument_id)) output.set(event.instrument_id, event);
  }
  return output;
}

function latestResearchMap(events: StrategyEvent[]): Map<string, StrategyEvent> {
  const output = new Map<string, StrategyEvent>();
  for (const event of events) {
    if (event.event_type !== 'research_llm') continue;
    if (!output.has(event.instrument_id)) output.set(event.instrument_id, event);
  }
  return output;
}

function qualityFromEvent(event?: StrategyEvent): number | null {
  const features = event?.payload?.features;
  if (!features || typeof features !== 'object') return null;
  const raw = (features as Record<string, unknown>).quality_score;
  const score = Number(raw);
  return Number.isFinite(score) ? score : null;
}

function classificationFromEvent(event?: StrategyEvent): Record<string, unknown> | null {
  const value = event?.payload?.classification;
  return value && typeof value === 'object' ? value as Record<string, unknown> : null;
}

function ConfigNumberField({
  label,
  value,
  onChange,
  step = 'any',
  suffix,
}: {
  label: string;
  value: string | number;
  onChange: (value: string) => void;
  step?: string;
  suffix?: string;
}) {
  return (
    <label>
      <span>{label}{suffix ? <small>{suffix}</small> : null}</span>
      <input type="number" step={step} value={String(value)} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

export function TradingStrategiesPanel() {
  const [strategies, setStrategies] = useState<TradingStrategyConfig[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [draft, setDraft] = useState<TradingStrategyConfig | null>(null);
  const [events, setEvents] = useState<StrategyEvent[]>([]);
  const [protections, setProtections] = useState<StrategyProtection[]>([]);
  const [universe, setUniverse] = useState<GapperUniverse | null>(null);
  const [selectedCandidates, setSelectedCandidates] = useState<Set<string>>(new Set());
  const [researchReviews, setResearchReviews] = useState<StrategyResearchReview[]>([]);
  const [llmModel, setLlmModel] = useState('');
  const [accounts, setAccounts] = useState<Array<{ account_id: string; name: string }>>([]);
  const [status, setStatus] = useState<'loading' | 'ready' | 'saving' | 'error'>('loading');
  const [universeJson, setUniverseJson] = useState('');
  const [freezingUniverse, setFreezingUniverse] = useState(false);
  const [discoveringUniverse, setDiscoveringUniverse] = useState(false);
  const [runningResearch, setRunningResearch] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const selected = useMemo(
    () => strategies.find((item) => item.strategy_id === selectedId) ?? null,
    [selectedId, strategies],
  );

  const latestStates = useMemo(() => latestEventMap(events), [events]);
  const latestResearch = useMemo(() => latestResearchMap(events), [events]);

  const loadUniverse = async (universeId: string | null) => {
    if (!universeId) {
      setUniverse(null);
      setSelectedCandidates(new Set());
      return;
    }
    const nextUniverse = await tradingStrategyApi.universe(universeId);
    setUniverse(nextUniverse);
    setUniverseJson(JSON.stringify(nextUniverse, null, 2));
    setSelectedCandidates(new Set(nextUniverse.candidates.map((candidate) => candidate.instrument_id)));
  };

  const refreshDetail = async (strategyId: string, universeId?: string | null) => {
    const [nextEvents, nextProtections] = await Promise.all([
      tradingStrategyApi.events(strategyId),
      tradingStrategyApi.protections(strategyId),
    ]);
    setEvents(nextEvents);
    setProtections(nextProtections);
    if (universeId !== undefined) await loadUniverse(universeId);
  };

  const refresh = async () => {
    setStatus('loading');
    try {
      const [nextStrategies, nextAccounts] = await Promise.all([
        tradingStrategyApi.list(),
        tradingPaperApi.accounts(),
      ]);
      setStrategies(nextStrategies);
      setAccounts(nextAccounts.map((item) => ({ account_id: item.account_id, name: item.name })));
      const nextId = nextStrategies.some((item) => item.strategy_id === selectedId)
        ? selectedId
        : nextStrategies[0]?.strategy_id ?? '';
      setSelectedId(nextId);
      const current = nextStrategies.find((item) => item.strategy_id === nextId) ?? null;
      setDraft(current ? structuredClone(current) : null);
      if (current) await refreshDetail(current.strategy_id, current.active_universe_id);
      else {
        setEvents([]);
        setProtections([]);
        setUniverse(null);
      }
      setStatus('ready');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
      setStatus('error');
    }
  };

  useEffect(() => { void refresh(); }, []);

  useEffect(() => {
    if (!selected) return;
    setDraft(structuredClone(selected));
    setResearchReviews([]);
    void refreshDetail(selected.strategy_id, selected.active_universe_id).catch((error) => {
      setNotice(error instanceof Error ? error.message : String(error));
    });
  }, [selected?.strategy_id, selected?.revision]);

  const startNew = () => {
    if (!accounts.length) {
      setNotice('Create a paper account before configuring an automated strategy.');
      return;
    }
    setSelectedId('');
    setEvents([]);
    setProtections([]);
    setUniverse(null);
    setSelectedCandidates(new Set());
    setResearchReviews([]);
    setDraft(defaultStrategy(accounts[0].account_id));
    setNotice(null);
  };

  const updateConfig = <K extends keyof GapPullbackConfig>(key: K, value: GapPullbackConfig[K]) => {
    setDraft((current) => current ? { ...current, config: { ...current.config, [key]: value } } : current);
  };

  const updateNumericConfig = (key: keyof GapPullbackConfig, value: string) => {
    updateConfig(key, value as never);
  };

  const save = async () => {
    if (!draft) return;
    if (!draft.account_id) {
      setNotice('A paper account is required.');
      return;
    }
    if (draft.mode === 'auto_paper' && !draft.active_universe_id) {
      setNotice('AUTO PAPER requires a frozen gapper universe id.');
      return;
    }
    setStatus('saving');
    try {
      const exists = strategies.some((item) => item.strategy_id === draft.strategy_id);
      const saved = exists ? await tradingStrategyApi.update(draft) : await tradingStrategyApi.create(draft);
      setStrategies((current) => [saved, ...current.filter((item) => item.strategy_id !== saved.strategy_id)]);
      setSelectedId(saved.strategy_id);
      setDraft(structuredClone(saved));
      setNotice(saved.mode === 'auto_paper'
        ? 'AUTO PAPER enabled. Orders remain paper-only; LLM research cannot authorize execution.'
        : saved.mode === 'shadow'
          ? 'Shadow mode saved. The complete pipeline is evaluated without placing orders.'
          : 'Strategy is off.');
      await refreshDetail(saved.strategy_id, saved.active_universe_id);
      setStatus('ready');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
      setStatus('error');
    }
  };

  const discoverYahooUniverse = async () => {
    if (!draft) return;
    setDiscoveringUniverse(true);
    try {
      const now = new Date();
      const timestamp = now.toISOString();
      const generatedId = `yahoo-gappers-${timestamp.slice(0, 10)}-${timestamp.slice(11, 16).replace(':', '')}`;
      const frozen = await tradingStrategyApi.discoverYahooUniverse({
        universe_id: generatedId,
        evaluation_time: timestamp,
        count: 50,
        minimum_gap_pct: draft.config.minimum_gap_pct,
        minimum_price: draft.config.minimum_price,
        maximum_price: draft.config.maximum_price,
      });
      setDraft((current) => current ? { ...current, active_universe_id: frozen.universe_id } : current);
      setUniverse(frozen);
      setUniverseJson(JSON.stringify(frozen, null, 2));
      setSelectedCandidates(new Set(frozen.candidates.map((candidate) => candidate.instrument_id)));
      setNotice(`Scan phase complete: froze ${frozen.candidates.length} point-in-time Yahoo candidates. Research/narrowing can now add catalyst and supply evidence.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
    } finally {
      setDiscoveringUniverse(false);
    }
  };

  const freezeUniverse = async () => {
    if (!draft) return;
    if (!universeJson.trim()) {
      setNotice('Paste or edit point-in-time candidate JSON before freezing a universe.');
      return;
    }
    setFreezingUniverse(true);
    try {
      const request = universeImport(universeJson, draft.active_universe_id);
      const uniqueId = universe?.source_fingerprint && request.universe_id === universe.universe_id
        ? `${request.universe_id}-research-${Date.now()}`
        : request.universe_id;
      const frozen = await tradingStrategyApi.freezeUniverse({ ...request, universe_id: uniqueId });
      setDraft((current) => current ? { ...current, active_universe_id: frozen.universe_id } : current);
      setUniverse(frozen);
      setUniverseJson(JSON.stringify(frozen, null, 2));
      setSelectedCandidates(new Set(frozen.candidates.map((candidate) => candidate.instrument_id)));
      setNotice(`Research snapshot frozen: ${frozen.candidates.length} candidates · ${frozen.universe_id}.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
    } finally {
      setFreezingUniverse(false);
    }
  };

  const freezeSelectedUniverse = async () => {
    if (!draft || !universe) return;
    const candidates = universe.candidates.filter((candidate) => selectedCandidates.has(candidate.instrument_id));
    if (!candidates.length) {
      setNotice('Select at least one candidate before freezing the narrowed universe.');
      return;
    }
    setFreezingUniverse(true);
    try {
      const now = new Date();
      const narrowed = await tradingStrategyApi.freezeUniverse({
        universe_id: `${universe.universe_id}-selected-${now.toISOString().slice(11, 16).replace(':', '')}`,
        session_date: universe.session_date,
        evaluation_time: now.toISOString(),
        discovery_source: 'import',
        candidates,
      });
      setDraft((current) => current ? { ...current, active_universe_id: narrowed.universe_id } : current);
      setUniverse(narrowed);
      setUniverseJson(JSON.stringify(narrowed, null, 2));
      setSelectedCandidates(new Set(narrowed.candidates.map((candidate) => candidate.instrument_id)));
      setNotice(`Narrowing phase complete: ${narrowed.candidates.length} selected candidates frozen and attached.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
    } finally {
      setFreezingUniverse(false);
    }
  };

  const runLlmResearch = async () => {
    if (!draft || !strategies.some((item) => item.strategy_id === draft.strategy_id)) {
      setNotice('Save the strategy and attach a frozen universe before running LLM research.');
      return;
    }
    if (!draft.active_universe_id) {
      setNotice('Attach a frozen universe before running LLM research.');
      return;
    }
    setRunningResearch(true);
    try {
      const response = await tradingStrategyApi.runLlmResearch(draft.strategy_id, llmModel);
      setResearchReviews(response.reviews);
      await refreshDetail(draft.strategy_id);
      const reviewed = response.reviews.filter((item) => item.status === 'reviewed').length;
      const missing = response.reviews.filter((item) => item.status === 'missing_evidence').length;
      setNotice(`LLM research complete: ${reviewed} reviewed, ${missing} missing timestamped evidence. Results remain shadow-only.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
    } finally {
      setRunningResearch(false);
    }
  };

  const applyLlmExclusions = () => {
    const reviewsBySymbol = new Map(researchReviews.map((review) => [review.instrument_id, review]));
    setSelectedCandidates((current) => {
      const next = new Set(current);
      for (const [instrumentId, review] of reviewsBySymbol) {
        const classification = review.classification;
        if (!classification) continue;
        if (classification.directional_bias === 'negative' || classification.dilution_risk === 'explicit') next.delete(instrumentId);
      }
      return next;
    });
    setNotice('Applied LLM research exclusions to the UI selection only. Freeze selected candidates to make the narrowing decision explicit and auditable.');
  };

  const setMode = (mode: StrategyMode) => setDraft((current) => current ? { ...current, mode } : current);

  const candidateRows = useMemo(() => {
    if (!universe) return [];
    return universe.candidates.map((candidate) => {
      const event = latestStates.get(candidate.instrument_id);
      const research = latestResearch.get(candidate.instrument_id);
      const localReview = researchReviews.find((item) => item.instrument_id === candidate.instrument_id);
      const classification = localReview?.classification
        ? localReview.classification as unknown as Record<string, unknown>
        : classificationFromEvent(research);
      return { candidate, event, research, classification, qualityScore: qualityFromEvent(event) };
    });
  }, [universe, latestStates, latestResearch, researchReviews]);

  const reviewedCount = candidateRows.filter((row) => row.research?.state === 'research_reviewed' || row.classification).length;
  const evidenceReadyCount = universe?.candidates.filter((candidate) => (candidate.catalyst_evidence_ids?.length ?? 0) > 0).length ?? 0;
  const entryReadyCount = candidateRows.filter((row) => row.event?.state === 'entry_ready').length;
  const submittedCount = events.filter((event) => event.event_type === 'entry_order_submitted').length;
  const rejectedCount = candidateRows.filter((row) => row.event?.state === 'rejected').length;

  const phaseStatus = (phaseId: string): { tone: string; text: string } => {
    if (phaseId === 'discover') return universe ? { tone: 'complete', text: `${universe.candidates.length} frozen` } : { tone: 'pending', text: 'Not started' };
    if (phaseId === 'research') {
      if (!universe) return { tone: 'pending', text: 'Waiting for scan' };
      if (evidenceReadyCount === universe.candidates.length) return { tone: 'complete', text: `${evidenceReadyCount}/${universe.candidates.length} evidence-ready` };
      return { tone: 'attention', text: `${evidenceReadyCount}/${universe.candidates.length} have catalyst evidence` };
    }
    if (phaseId === 'llm') {
      if (!universe) return { tone: 'pending', text: 'Waiting for research' };
      return reviewedCount ? { tone: 'complete', text: `${reviewedCount} reviewed` } : { tone: 'pending', text: 'Optional review not run' };
    }
    if (phaseId === 'deterministic') {
      const evaluated = candidateRows.filter((row) => row.event && row.event.event_type !== 'research_llm').length;
      return evaluated ? { tone: 'active', text: `${evaluated} evaluated · ${rejectedCount} rejected` } : { tone: 'pending', text: 'Waiting for market structure' };
    }
    if (phaseId === 'selection') return entryReadyCount ? { tone: 'complete', text: `${entryReadyCount} entry-ready` } : { tone: 'pending', text: `Score ≥ ${draft?.config.minimum_quality_score ?? 7} required` };
    return draft?.mode === 'auto_paper'
      ? { tone: submittedCount ? 'complete' : 'active', text: submittedCount ? `${submittedCount} orders submitted` : 'AUTO PAPER armed' }
      : draft?.mode === 'shadow'
        ? { tone: 'attention', text: 'Shadow only' }
        : { tone: 'pending', text: 'Off' };
  };

  return (
    <div className="trading-strategies-panel">
      <aside>
        <div className="trading-strategies-heading">
          <div><strong>Strategies</strong><small>Reusable strategy catalog</small></div>
          <button type="button" onClick={startNew}>New</button>
        </div>
        {strategies.length ? strategies.map((item) => (
          <button key={item.strategy_id} type="button" className={item.strategy_id === selectedId ? 'active' : undefined} onClick={() => setSelectedId(item.strategy_id)}>
            <strong>{item.strategy_id}</strong>
            <span>{item.strategy_kind} · {item.mode.replace('_', ' ')}</span>
          </button>
        )) : <p>No strategies configured.</p>}
        <div className="trading-strategy-safety"><strong>Execution boundary</strong><small>LLM/model output is research-only. AUTO PAPER requires deterministic gates + server risk + execution evidence.</small></div>
      </aside>

      <section>
        {!draft ? (
          <div className="trading-strategies-empty"><strong>{definition.label}</strong><p>{definition.thesis}</p><button type="button" onClick={startNew}>Create strategy</button></div>
        ) : (
          <>
            <header className="trading-strategy-editor-header">
              <div><strong>{draft.strategy_id}</strong><small>{definition.label} · v{draft.strategy_version} · revision {draft.revision}</small></div>
              <div className="trading-strategy-header-actions"><button type="button" onClick={() => void refresh()}>Refresh</button><button type="button" className="primary" onClick={() => void save()} disabled={status === 'saving'}>{status === 'saving' ? 'Saving…' : 'Save strategy'}</button></div>
            </header>

            {notice ? <div className="trading-strategy-notice" role="status">{notice}</div> : null}

            <section className="trading-strategy-overview">
              <div><strong>{definition.thesis}</strong><small>Hard structural gates cannot be compensated for by a high score.</small></div>
              <div className="trading-mode-switch" role="group" aria-label="Strategy mode">
                {(['off', 'shadow', 'auto_paper'] as StrategyMode[]).map((mode) => <button type="button" key={mode} className={draft.mode === mode ? 'active' : undefined} onClick={() => setMode(mode)}>{mode === 'auto_paper' ? 'Auto paper' : mode[0].toUpperCase() + mode.slice(1)}</button>)}
              </div>
            </section>

            <section className="trading-strategy-pipeline">
              <header><div><strong>Daily strategy pipeline</strong><small>Every phase is visible and auditable.</small></div></header>
              <div className="trading-strategy-phase-grid">
                {definition.phases.map((phase) => {
                  const phaseState = phaseStatus(phase.id);
                  return <article key={phase.id} data-tone={phaseState.tone}><header><strong>{phase.label}</strong><span>{phaseState.text}</span></header><p>{phase.description}</p>{phase.safety ? <small>{phase.safety}</small> : null}</article>;
                })}
              </div>
            </section>

            <details className="trading-strategy-config-section" open>
              <summary><strong>Strategy configuration</strong><span>All gap_pullback_v1 details</span></summary>
              <div className="trading-strategy-config-body">
                <div className="trading-config-block">
                  <header><strong>Identity & account</strong><small>Reusable strategy instance</small></header>
                  <div className="trading-strategy-grid">
                    <label><span>Strategy type</span><select value={draft.strategy_kind} disabled><option value="gap_pullback_v1">{definition.label}</option></select></label>
                    <label><span>Paper account</span><select value={draft.account_id} onChange={(event) => setDraft({ ...draft, account_id: event.target.value })}>{accounts.map((account) => <option key={account.account_id} value={account.account_id}>{account.name}</option>)}</select></label>
                    <label><span>Frozen universe id</span><input value={draft.active_universe_id ?? ''} onChange={(event) => setDraft({ ...draft, active_universe_id: event.target.value || null })} placeholder="yahoo-gappers-..." /></label>
                    <label className="toggle-field"><span>Enabled</span><input type="checkbox" checked={draft.enabled} onChange={(event) => setDraft({ ...draft, enabled: event.target.checked })} /></label>
                  </div>
                </div>

                <div className="trading-config-block">
                  <header><strong>1. Scanner & liquidity gates</strong><small>Starting universe</small></header>
                  <div className="trading-strategy-grid">
                    <ConfigNumberField label="Minimum gap" suffix="%" value={draft.config.minimum_gap_pct} onChange={(value) => updateNumericConfig('minimum_gap_pct', value)} step="0.5" />
                    <ConfigNumberField label="Minimum price" suffix="$" value={draft.config.minimum_price} onChange={(value) => updateNumericConfig('minimum_price', value)} step="0.01" />
                    <ConfigNumberField label="Maximum price" suffix="$" value={draft.config.maximum_price} onChange={(value) => updateNumericConfig('maximum_price', value)} step="0.01" />
                    <ConfigNumberField label="Premarket dollar volume" suffix="$" value={draft.config.minimum_premarket_dollar_volume} onChange={(value) => updateNumericConfig('minimum_premarket_dollar_volume', value)} step="1000000" />
                    <ConfigNumberField label="Minimum TOD RVOL" suffix="×" value={draft.config.minimum_tod_rvol} onChange={(value) => updateNumericConfig('minimum_tod_rvol', value)} step="0.5" />
                    <ConfigNumberField label="Maximum spread" suffix="bps" value={draft.config.maximum_spread_bps} onChange={(value) => updateNumericConfig('maximum_spread_bps', value)} step="10" />
                    <ConfigNumberField label="Preferred float min" suffix="shares" value={draft.config.preferred_float_min_shares} onChange={(value) => updateNumericConfig('preferred_float_min_shares', value)} step="100000" />
                    <ConfigNumberField label="Preferred float max" suffix="shares" value={draft.config.preferred_float_max_shares} onChange={(value) => updateNumericConfig('preferred_float_max_shares', value)} step="100000" />
                    <label><span>Float handling</span><select value={draft.config.float_preference_mode} onChange={(event) => updateConfig('float_preference_mode', event.target.value as GapPullbackConfig['float_preference_mode'])}><option value="ignore">Ignore</option><option value="score">Score preference</option><option value="require">Hard require</option></select></label>
                  </div>
                </div>

                <div className="trading-config-block">
                  <header><strong>2. Catalyst & supply research</strong><small>Timestamped evidence only</small></header>
                  <div className="trading-strategy-grid">
                    <label className="toggle-field"><span>Require catalyst evidence</span><input type="checkbox" checked={draft.config.require_catalyst_evidence} onChange={(event) => updateConfig('require_catalyst_evidence', event.target.checked)} /></label>
                    <label className="wide-field"><span>Rejected dilution / supply flags<small>comma separated</small></span><input value={draft.config.reject_dilution_flags.join(', ')} onChange={(event) => updateConfig('reject_dilution_flags', event.target.value.split(',').map((item) => item.trim()).filter(Boolean))} /></label>
                  </div>
                </div>

                <div className="trading-config-block">
                  <header><strong>3. Failed sell-off structure</strong><small>Mandatory causal gates</small></header>
                  <div className="trading-strategy-grid">
                    <ConfigNumberField label="Opening impulse minimum" suffix="%" value={draft.config.opening_impulse_min_pct} onChange={(value) => updateNumericConfig('opening_impulse_min_pct', value)} step="0.5" />
                    <ConfigNumberField label="Pullback depth minimum" suffix="%" value={draft.config.pullback_min_pct} onChange={(value) => updateNumericConfig('pullback_min_pct', value)} step="1" />
                    <ConfigNumberField label="Pullback depth maximum" suffix="%" value={draft.config.pullback_max_pct} onChange={(value) => updateNumericConfig('pullback_max_pct', value)} step="1" />
                    <ConfigNumberField label="Selling volume / impulse max" suffix="ratio" value={draft.config.pullback_volume_max_ratio} onChange={(value) => updateNumericConfig('pullback_volume_max_ratio', value)} step="0.05" />
                    <ConfigNumberField label="Higher-low buffer" suffix="bps" value={draft.config.higher_low_buffer_bps} onChange={(value) => updateNumericConfig('higher_low_buffer_bps', value)} step="5" />
                    <ConfigNumberField label="Breakout volume minimum" suffix="× recent" value={draft.config.breakout_volume_ratio} onChange={(value) => updateNumericConfig('breakout_volume_ratio', value)} step="0.05" />
                    <label><span>Pivot left bars</span><input type="number" min="1" max="10" value={draft.config.pivot_left_bars} onChange={(event) => updateConfig('pivot_left_bars', Number(event.target.value))} /></label>
                    <label><span>Pivot right bars</span><input type="number" min="1" max="10" value={draft.config.pivot_right_bars} onChange={(event) => updateConfig('pivot_right_bars', Number(event.target.value))} /></label>
                    <label><span>Volume lookback bars</span><input type="number" min="2" max="100" value={draft.config.volume_lookback_bars} onChange={(event) => updateConfig('volume_lookback_bars', Number(event.target.value))} /></label>
                  </div>
                </div>

                <div className="trading-config-block">
                  <header><strong>4. Confirmation & quality score</strong><small>Score 0–10; structure remains mandatory</small></header>
                  <div className="trading-strategy-grid">
                    <label className="toggle-field"><span>Require breakout hold / retest</span><input type="checkbox" checked={draft.config.require_breakout_hold} onChange={(event) => updateConfig('require_breakout_hold', event.target.checked)} /></label>
                    <label><span>Hold bars</span><input type="number" min="1" max="5" value={draft.config.breakout_hold_bars} onChange={(event) => updateConfig('breakout_hold_bars', Number(event.target.value))} /></label>
                    <ConfigNumberField label="Hold tolerance" suffix="bps below B1" value={draft.config.breakout_hold_tolerance_bps} onChange={(value) => updateNumericConfig('breakout_hold_tolerance_bps', value)} step="5" />
                    <label><span>Minimum quality score<small>/ 10</small></span><input type="number" min="0" max="10" value={draft.config.minimum_quality_score} onChange={(event) => updateConfig('minimum_quality_score', Number(event.target.value))} /></label>
                    <ConfigNumberField label="Stop buffer" suffix="bps below L2" value={draft.config.stop_buffer_bps} onChange={(value) => updateNumericConfig('stop_buffer_bps', value)} step="5" />
                    <ConfigNumberField label="Reward multiple" suffix="R" value={draft.config.reward_multiple} onChange={(value) => updateNumericConfig('reward_multiple', value)} step="0.25" />
                    <label><span>Entry starts ET</span><input type="time" step="1" value={draft.config.entry_start_et} onChange={(event) => updateConfig('entry_start_et', event.target.value)} /></label>
                    <label><span>Last entry ET</span><input type="time" step="1" value={draft.config.last_entry_et} onChange={(event) => updateConfig('last_entry_et', event.target.value)} /></label>
                  </div>
                  <div className="quality-score-explainer"><span><b>0–2</b> fresh catalyst</span><span><b>0–2</b> supply / float</span><span><b>0–2</b> opening structure</span><span><b>0–2</b> controlled pullback</span><span><b>0–2</b> VWAP + B1 break + hold</span></div>
                </div>

                <div className="trading-config-block">
                  <header><strong>5. Server risk & protection</strong><small>Authoritative paper risk</small></header>
                  <div className="trading-strategy-grid">
                    <ConfigNumberField label="Risk per trade" suffix="%" value={draft.risk.risk_per_trade_pct} onChange={(value) => setDraft({ ...draft, risk: { ...draft.risk, risk_per_trade_pct: value } })} step="0.05" />
                    <ConfigNumberField label="Max daily loss" suffix="%" value={draft.risk.max_daily_loss_pct} onChange={(value) => setDraft({ ...draft, risk: { ...draft.risk, max_daily_loss_pct: value } })} step="0.1" />
                    <ConfigNumberField label="Max open risk" suffix="%" value={draft.risk.max_open_risk_pct} onChange={(value) => setDraft({ ...draft, risk: { ...draft.risk, max_open_risk_pct: value } })} step="0.1" />
                    <label><span>Max positions</span><input type="number" min="1" max="50" value={draft.risk.max_positions} onChange={(event) => setDraft({ ...draft, risk: { ...draft.risk, max_positions: Number(event.target.value) } })} /></label>
                    <label><span>Max trades / day</span><input type="number" min="1" max="100" value={draft.risk.max_trades_per_day} onChange={(event) => setDraft({ ...draft, risk: { ...draft.risk, max_trades_per_day: Number(event.target.value) } })} /></label>
                    <ConfigNumberField label="Max trade value" suffix="$" value={draft.risk.max_trade_value} onChange={(value) => setDraft({ ...draft, risk: { ...draft.risk, max_trade_value: value } })} step="1000" />
                    <ConfigNumberField label="Risk max spread" suffix="bps" value={draft.risk.max_spread_bps} onChange={(value) => setDraft({ ...draft, risk: { ...draft.risk, max_spread_bps: value } })} step="10" />
                    <label className="toggle-field"><span>One trade / symbol / day</span><input type="checkbox" checked={draft.risk.one_trade_per_symbol_per_day} onChange={(event) => setDraft({ ...draft, risk: { ...draft.risk, one_trade_per_symbol_per_day: event.target.checked } })} /></label>
                    <label><span>Force flat ET</span><input type="time" step="1" value={draft.risk.force_flat_et} onChange={(event) => setDraft({ ...draft, risk: { ...draft.risk, force_flat_et: event.target.value } })} /></label>
                    <label className="toggle-field danger"><span>Kill switch</span><input type="checkbox" checked={draft.risk.kill_switch} onChange={(event) => setDraft({ ...draft, risk: { ...draft.risk, kill_switch: event.target.checked } })} /></label>
                  </div>
                </div>
              </div>
            </details>

            <section className="trading-research-workbench">
              <header><div><strong>Research & daily candidate workbench</strong><small>Scan → evidence → optional LLM review → explicit narrowing → deterministic monitoring.</small></div><div className="workbench-actions"><button type="button" onClick={() => void discoverYahooUniverse()} disabled={discoveringUniverse || freezingUniverse}>{discoveringUniverse ? 'Scanning…' : 'Scan Yahoo & freeze'}</button><button type="button" onClick={() => void freezeUniverse()} disabled={freezingUniverse || discoveringUniverse}>{freezingUniverse ? 'Freezing…' : 'Freeze edited JSON'}</button></div></header>

              <div className="llm-research-bar"><div><strong>LLM catalyst review</strong><small>Uses only attached timestamped evidence. It can help you review/narrow candidates but cannot authorize AUTO PAPER.</small></div><input value={llmModel} onChange={(event) => setLlmModel(event.target.value)} placeholder="Optional model override" /><button type="button" onClick={() => void runLlmResearch()} disabled={runningResearch}>{runningResearch ? 'Reviewing…' : 'Run LLM review'}</button><button type="button" onClick={applyLlmExclusions} disabled={!researchReviews.length}>Apply LLM exclusions</button></div>

              {universe ? (
                <>
                  <div className="candidate-toolbar"><div><strong>{universe.universe_id}</strong><small>{universe.session_date} · {universe.discovery_source} · {universe.candidates.length} candidates · selected {selectedCandidates.size}</small></div><div><button type="button" onClick={() => setSelectedCandidates(new Set(universe.candidates.map((candidate) => candidate.instrument_id)))}>Select all</button><button type="button" onClick={() => setSelectedCandidates(new Set())}>Select none</button><button type="button" className="primary" onClick={() => void freezeSelectedUniverse()} disabled={freezingUniverse || !selectedCandidates.size}>Freeze selected & attach</button></div></div>
                  <div className="candidate-table-wrap">
                    <table className="strategy-candidate-table">
                      <thead><tr><th>Use</th><th>Candidate</th><th>Gap</th><th>Price</th><th>RVOL</th><th>$ volume</th><th>Float</th><th>Spread</th><th>Catalyst</th><th>Supply</th><th>LLM</th><th>Deterministic state</th><th>Score</th></tr></thead>
                      <tbody>
                        {candidateRows.map(({ candidate, event, research, classification, qualityScore }) => (
                          <tr key={candidate.instrument_id} data-tone={event ? eventTone(event) : 'working'}>
                            <td><input type="checkbox" aria-label={`Use ${candidate.instrument_id}`} checked={selectedCandidates.has(candidate.instrument_id)} onChange={(change) => { setSelectedCandidates((current) => { const next = new Set(current); if (change.target.checked) next.add(candidate.instrument_id); else next.delete(candidate.instrument_id); return next; }); }} /></td>
                            <td><strong>{candidate.instrument_id.split(':').at(-1)}</strong><small>rank {candidate.discovery_rank ?? '—'}</small></td>
                            <td>{percent(candidate.gap_pct)}</td><td>${numeric(candidate.premarket_price)?.toFixed(2) ?? '—'}</td><td>{numeric(candidate.tod_rvol)?.toFixed(1) ?? '—'}×</td><td>${compactNumber(candidate.premarket_dollar_volume)}</td><td>{compactNumber(candidate.float_shares)}</td><td>{basisPoints(candidate.spread_bps)}</td>
                            <td><span className={(candidate.catalyst_evidence_ids?.length ?? 0) ? 'pass' : 'warn'}>{(candidate.catalyst_evidence_ids?.length ?? 0) ? `${candidate.catalyst_evidence_ids?.length} evidence` : 'missing'}</span></td>
                            <td>{candidate.dilution_flags?.length ? <span className="fail">{candidate.dilution_flags.join(', ')}</span> : <span className="pass">clean flags</span>}</td>
                            <td>{classification ? <span title={String(classification.rationale ?? '')}>{String(classification.directional_bias ?? classification.catalyst_class ?? 'reviewed')} · {Math.round(Number(classification.confidence ?? 0) * 100)}%</span> : research?.state === 'research_missing' ? <span className="warn">needs evidence</span> : '—'}</td>
                            <td><strong>{event?.state ?? 'not evaluated'}</strong><small>{event?.reason_code ?? ''}</small></td>
                            <td><span className={qualityScore !== null && qualityScore >= draft.config.minimum_quality_score ? 'score pass' : 'score'}>{qualityScore ?? '—'}/10</span></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              ) : <div className="workbench-empty">Run the Yahoo scan or attach a frozen point-in-time universe to begin today's research pipeline.</div>}

              <details className="universe-json-editor"><summary>Point-in-time universe JSON / evidence editor</summary><p>Add externally captured catalyst evidence IDs and deterministic dilution flags here, then freeze a new immutable research snapshot. Never overwrite an existing universe ID with changed evidence.</p><textarea aria-label="Gapper universe JSON" value={universeJson} onChange={(event) => setUniverseJson(event.target.value)} placeholder={'[{"instrument_id":"equity:NASDAQ:XYZ","previous_close":"1.00","premarket_price":"1.35","gap_pct":"35","premarket_dollar_volume":"15000000","tod_rvol":"8","float_shares":"8000000","catalyst_evidence_ids":["..."],"dilution_flags":[]}]'} /></details>
            </section>

            <section className="trading-strategy-monitoring">
              <section><header><div><strong>Live candidate states</strong><small>Latest deterministic evaluation/rejection evidence</small></div><span>{events.length} events</span></header><div className="strategy-event-list">{events.slice(0, 40).map((event) => <details key={`${event.event_id}-${event.observed_at}`} className={eventTone(event)}><summary><strong>{event.instrument_id.split(':').at(-1)}</strong><span>{event.event_type === 'research_llm' ? 'LLM research' : event.state}</span><small>{event.reason_code ?? '—'}</small><time>{new Date(event.observed_at).toLocaleTimeString()}</time></summary><pre>{JSON.stringify(event.payload, null, 2)}</pre></details>)}{!events.length ? <p>No strategy events yet.</p> : null}</div></section>
              <section><header><div><strong>Active protections</strong><small>Server-persisted stop / target state</small></div><span>{protections.length}</span></header><div className="strategy-protection-list">{protections.map((item) => <article key={item.protection_id}><strong>{item.instrument_id.split(':').at(-1)}</strong><span>{item.status}</span><small>qty {String(item.quantity)} · stop {String(item.stop_price)} · target {String(item.target_price)}</small></article>)}{!protections.length ? <p>No active strategy protections.</p> : null}</div></section>
            </section>
          </>
        )}
      </section>
    </div>
  );
}
