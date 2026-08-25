import { useState } from 'react';
import { TradingAlertsPanel } from './TradingAlertsPanel';
import { TradingIndicatorPresets } from './TradingIndicatorPresets';
import { TradingLayoutPanel } from './TradingLayoutPanel';
import { TradingNewsPanel } from './TradingNewsPanel';
import { TradingPaperPanel } from './TradingPaperPanel';
import { TradingProspectiveEconomicPanel } from './TradingProspectiveEconomicPanel';
import { TradingSymbolIntelligence } from './TradingSymbolIntelligence';
import { TradingTradeJournal } from './TradingTradeJournal';
import { TradingWatchlist } from './TradingWatchlist';
import { TradingObjectPanel } from './TradingObjectPanel';
import { TradingPinePanel } from './TradingPinePanel';
import type { DrawingSnapMode } from './drawings/drawingCommands';
import type { CoreIndicatorId, CoreIndicatorInstance } from './indicators/coreIndicators';
import type { TradingLayout, TradingLinkState } from './tradingStore';
import type { CanonicalInstrument, ProviderBinding, TradingAlert } from './tradingTypes';

export type TradingSideTab = 'watchlist' | 'paper' | 'intelligence' | 'journal' | 'prospective' | 'indicators' | 'alerts' | 'news' | 'layout' | 'objects' | 'pine';

const tabs: Array<{ id: TradingSideTab; label: string }> = [
  { id: 'watchlist', label: 'Watchlist' },
  { id: 'paper', label: 'Trade' },
  { id: 'intelligence', label: 'Intel' },
  { id: 'journal', label: 'Journal' },
  { id: 'prospective', label: 'Evidence' },
  { id: 'indicators', label: 'Indicators' },
  { id: 'alerts', label: 'Alerts' },
  { id: 'news', label: 'News' },
  { id: 'layout', label: 'Layout' },
];

export function TradingSidePanel({
  sessionId,
  instruments,
  activeInstrumentId,
  bindingId,
  providerBindings,
  interval,
  selectedTab,
  onTabChange,
  paperAccountId,
  onPaperAccountChange,
  indicators,
  layout,
  chartCount,
  minimumChartCount,
  maximumChartCount,
  links,
  snapMode,
  onSelectInstrument,
  onSelectAlert,
  onSetIndicators,
  pineIndicatorId,
  onPineIndicatorChange,
  onOpenPineScript,
  onSetLayout,
  onSetChartCount,
  onAddChart,
  onRemoveChart,
  onSetLink,
  onSetSnapMode,
  onOpenResearch,
}: {
  sessionId?: string;
  instruments: CanonicalInstrument[];
  activeInstrumentId: string;
  bindingId: string | null;
  providerBindings?: readonly ProviderBinding[];
  interval: string;
  selectedTab?: TradingSideTab;
  onTabChange?: (tab: TradingSideTab) => void;
  paperAccountId?: string | null;
  onPaperAccountChange?: (accountId: string) => void;
  indicators: CoreIndicatorInstance[];
  layout: TradingLayout;
  chartCount: number;
  minimumChartCount: number;
  maximumChartCount: number;
  links: TradingLinkState;
  snapMode: DrawingSnapMode;
  onSelectInstrument: (instrumentId: string) => void;
  onSelectAlert: (alert: TradingAlert) => void;
  onSetIndicators: (indicators: CoreIndicatorInstance[]) => void;
  pineIndicatorId: CoreIndicatorId | null;
  onPineIndicatorChange: (id: CoreIndicatorId) => void;
  onOpenPineScript: (id: CoreIndicatorId) => void;
  onSetLayout: (layout: TradingLayout) => void;
  onSetChartCount: (count: number) => void;
  onAddChart: () => void;
  onRemoveChart: () => void;
  onSetLink: (key: keyof TradingLinkState, enabled: boolean) => void;
  onSetSnapMode: (mode: DrawingSnapMode) => void;
  onOpenResearch: () => void;
}) {
  const [internalTab, setInternalTab] = useState<TradingSideTab>('watchlist');
  const activeTab = selectedTab ?? internalTab;
  const setActiveTab = (tab: TradingSideTab) => {
    setInternalTab(tab);
    onTabChange?.(tab);
  };
  if (activeTab === 'objects') {
    return (
      <aside className="trading-side-panel trading-object-side-panel" aria-label="Trading object tree and data window">
        <TradingObjectPanel
          sessionId={sessionId}
          instruments={instruments}
          activeInstrumentId={activeInstrumentId}
          bindingId={bindingId}
          interval={interval}
          indicators={indicators}
          onSetIndicators={onSetIndicators}
          onOpenPineScript={onOpenPineScript}
        />
      </aside>
    );
  }
  if (activeTab === 'pine') {
    return (
      <aside className="trading-side-panel trading-object-side-panel trading-pine-side-panel" aria-label="Pine Editor">
        <TradingPinePanel
          indicators={indicators}
          activeIndicatorId={pineIndicatorId}
          onActiveIndicatorChange={onPineIndicatorChange}
        />
      </aside>
    );
  }
  return (
    <aside className="trading-side-panel" aria-label="Trading side panel">
      <nav role="tablist" aria-label="Trading side panel sections">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={`trading-tab-${tab.id}`}
            aria-selected={activeTab === tab.id}
            aria-controls={`trading-panel-${tab.id}`}
            className={activeTab === tab.id ? 'active' : undefined}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>
      <section
        role="tabpanel"
        id={`trading-panel-${activeTab}`}
        aria-labelledby={`trading-tab-${activeTab}`}
        className={activeTab === 'watchlist' ? 'trading-side-panel-watchlist' : undefined}
        tabIndex={0}
      >
        {activeTab === 'watchlist' ? (
          <TradingWatchlist
            instruments={instruments}
            activeInstrumentId={activeInstrumentId}
            interval={interval}
            providerBindings={providerBindings}
            onSelect={onSelectInstrument}
          />
        ) : null}
        {activeTab === 'paper' ? (
          <TradingPaperPanel
            instrumentId={activeInstrumentId}
            bindingId={bindingId}
            preferredAccountId={paperAccountId}
            onAccountChange={onPaperAccountChange}
          />
        ) : null}
        {activeTab === 'intelligence' ? (
          <TradingSymbolIntelligence
            instrumentId={activeInstrumentId}
            bindingId={bindingId}
            accountId={paperAccountId}
          />
        ) : null}
        {activeTab === 'journal' ? (
          <TradingTradeJournal
            accountId={paperAccountId}
            instrumentId={activeInstrumentId}
          />
        ) : null}
        {activeTab === 'prospective' ? <TradingProspectiveEconomicPanel /> : null}
        {activeTab === 'indicators' ? (
          <TradingIndicatorPresets indicators={indicators} onApply={onSetIndicators} />
        ) : null}
        {activeTab === 'alerts' ? (
          <TradingAlertsPanel
            instrumentId={activeInstrumentId}
            bindingId={bindingId}
            interval={interval}
            onSelectAlert={onSelectAlert}
          />
        ) : null}
        {activeTab === 'news' ? <TradingNewsPanel onOpenResearch={onOpenResearch} /> : null}
        {activeTab === 'layout' ? (
          <TradingLayoutPanel
            layout={layout}
            chartCount={chartCount}
            minimumChartCount={minimumChartCount}
            maximumChartCount={maximumChartCount}
            links={links}
            snapMode={snapMode}
            onSetLayout={onSetLayout}
            onSetChartCount={onSetChartCount}
            onAddChart={onAddChart}
            onRemoveChart={onRemoveChart}
            onSetLink={onSetLink}
            onSetSnapMode={onSetSnapMode}
          />
        ) : null}
      </section>
    </aside>
  );
}
