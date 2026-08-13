import { useState } from 'react';
import { TradingIndicatorPresets } from './TradingIndicatorPresets';
import { TradingLayoutPanel } from './TradingLayoutPanel';
import { TradingNewsPanel } from './TradingNewsPanel';
import { TradingWatchlist } from './TradingWatchlist';
import type { DrawingSnapMode } from './drawings/drawingCommands';
import type { CoreIndicatorInstance } from './indicators/coreIndicators';
import type { TradingLayout, TradingLinkState } from './tradingStore';
import type { CanonicalInstrument } from './tradingTypes';

type SideTab = 'watchlist' | 'indicators' | 'news' | 'layout';

const tabs: Array<{ id: SideTab; label: string }> = [
  { id: 'watchlist', label: 'Watchlist' },
  { id: 'indicators', label: 'Indicators' },
  { id: 'news', label: 'News' },
  { id: 'layout', label: 'Layout' },
];

export function TradingSidePanel({
  instruments,
  activeInstrumentId,
  indicators,
  layout,
  chartCount,
  minimumChartCount,
  maximumChartCount,
  links,
  snapMode,
  onSelectInstrument,
  onSetIndicators,
  onSetLayout,
  onSetChartCount,
  onAddChart,
  onRemoveChart,
  onSetLink,
  onSetSnapMode,
  onOpenResearch,
}: {
  instruments: CanonicalInstrument[];
  activeInstrumentId: string;
  indicators: CoreIndicatorInstance[];
  layout: TradingLayout;
  chartCount: number;
  minimumChartCount: number;
  maximumChartCount: number;
  links: TradingLinkState;
  snapMode: DrawingSnapMode;
  onSelectInstrument: (instrumentId: string) => void;
  onSetIndicators: (indicators: CoreIndicatorInstance[]) => void;
  onSetLayout: (layout: TradingLayout) => void;
  onSetChartCount: (count: number) => void;
  onAddChart: () => void;
  onRemoveChart: () => void;
  onSetLink: (key: keyof TradingLinkState, enabled: boolean) => void;
  onSetSnapMode: (mode: DrawingSnapMode) => void;
  onOpenResearch: () => void;
}) {
  const [activeTab, setActiveTab] = useState<SideTab>('watchlist');
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
        tabIndex={0}
      >
        {activeTab === 'watchlist' ? (
          <TradingWatchlist
            instruments={instruments}
            activeInstrumentId={activeInstrumentId}
            onSelect={onSelectInstrument}
          />
        ) : null}
        {activeTab === 'indicators' ? (
          <TradingIndicatorPresets indicators={indicators} onApply={onSetIndicators} />
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
