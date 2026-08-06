import { useState } from 'react';
import { TradingAlertsPanel } from './TradingAlertsPanel';
import { TradingDiagnosticsPanel } from './TradingDiagnosticsPanel';
import { TradingIndicatorPresets } from './TradingIndicatorPresets';
import { TradingWatchlist } from './TradingWatchlist';
import type { CanonicalInstrument } from './tradingTypes';
import type { IndicatorId } from './indicators/indicatorRegistry';

type SideTab = 'watchlist' | 'indicators' | 'alerts' | 'data';

const tabs: Array<{ id: SideTab; label: string }> = [
  { id: 'watchlist', label: 'Watchlist' },
  { id: 'indicators', label: 'Indicators' },
  { id: 'alerts', label: 'Alerts' },
  { id: 'data', label: 'Data' },
];

export function TradingSidePanel({
  instruments,
  activeInstrumentId,
  bindingId,
  indicators,
  onSelectInstrument,
  onSetIndicators,
}: {
  instruments: CanonicalInstrument[];
  activeInstrumentId: string;
  bindingId: string | null;
  indicators: IndicatorId[];
  onSelectInstrument: (instrumentId: string) => void;
  onSetIndicators: (indicators: IndicatorId[]) => void;
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
        {activeTab === 'alerts' ? (
          <TradingAlertsPanel instrumentId={activeInstrumentId} bindingId={bindingId} />
        ) : null}
        {activeTab === 'data' ? <TradingDiagnosticsPanel /> : null}
      </section>
    </aside>
  );
}
