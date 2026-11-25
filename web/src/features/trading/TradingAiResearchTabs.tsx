import { lazy, Suspense, useState } from 'react';
import { TradingCopilotPanel } from './TradingCopilotPanel';
import { drawingScopeId } from './drawings/drawingToolSettings';
import { useTradingDrawings } from './drawings/useTradingDrawings';
import type { CoreIndicatorInstance } from './indicators/coreIndicators';
import { useTradingStore } from './tradingStore';
import type { ProviderBinding } from './tradingTypes';
import './TradingAiResearch.css';

const TradingFilingsPanel = lazy(() => import('./TradingFilingsPanel').then((module) => ({ default: module.TradingFilingsPanel })));
const TradingResearchPanel = lazy(() => import('./TradingResearchPanel').then((module) => ({ default: module.TradingResearchPanel })));

type ResearchView = 'copilot' | 'filings' | 'report';

const VIEWS: Array<{ id: ResearchView; label: string }> = [
  { id: 'copilot', label: 'Copilot' },
  { id: 'filings', label: 'Filings' },
  { id: 'report', label: 'Report' },
];

export type TradingAiResearchProps = {
  sessionId?: string;
  instrumentId: string;
  bindingId: string | null;
  interval: string;
  providerBindings?: readonly ProviderBinding[];
  indicators: CoreIndicatorInstance[];
  onSetIndicators: (indicators: CoreIndicatorInstance[]) => void;
};

/** The Research side tab: Copilot (chart chat), Filings (SEC summaries) and Report (the market research form). */
export function TradingAiResearchTabs(props: TradingAiResearchProps) {
  const [view, setView] = useState<ResearchView>('copilot');
  return (
    <div className="trading-ai-research">
      <div className="trading-ai-research-tabs" role="tablist" aria-label="Research views">
        {VIEWS.map((option) => (
          <button
            key={option.id}
            type="button"
            role="tab"
            aria-selected={view === option.id}
            className={view === option.id ? 'active' : undefined}
            onClick={() => setView(option.id)}
          >
            {option.label}
          </button>
        ))}
      </div>
      <Suspense fallback={<p role="status">Loading research…</p>}>
        {/* Keyed by instrument: a conversation or summary belongs to the symbol it was about. */}
        {view === 'copilot' ? <CopilotForChart key={props.instrumentId} {...props} /> : null}
        {view === 'filings' ? <TradingFilingsPanel key={props.instrumentId} instrumentId={props.instrumentId} /> : null}
        {view === 'report' ? <TradingResearchPanel instrumentId={props.instrumentId} bindingId={props.bindingId} interval={props.interval} /> : null}
      </Suspense>
    </div>
  );
}

function CopilotForChart({ sessionId, providerBindings, ...chart }: TradingAiResearchProps) {
  const activeChartId = useTradingStore((state) => state.activeChartId);
  const updateChart = useTradingStore((state) => state.updateChart);
  const syncDrawings = useTradingStore((state) => state.drawingToolSettings.syncDrawings);
  // The active chart's drawings, as the object tree reads them (TVP-3.8).
  const drawings = useTradingDrawings(chart.instrumentId, drawingScopeId(sessionId, activeChartId, syncDrawings));
  // The intervals the chart's binding serves: Omnix offers only a switch the chart can make.
  const supportedIntervals = providerBindings?.find((binding) => binding.binding_id === chart.bindingId)?.supported_intervals ?? [];
  return (
    <TradingCopilotPanel
      chart={{ ...chart, supportedIntervals, onSetInterval: (interval) => updateChart(activeChartId, { interval }) }}
      addDrawing={drawings.add}
    />
  );
}
