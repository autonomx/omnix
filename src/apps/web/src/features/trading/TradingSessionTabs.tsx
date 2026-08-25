import type { TradingTabState } from './tradingStore';

export function TradingSessionTabs({
  tabs,
  activeTabId,
  canAdd,
  getTabLabel,
  onSelect,
  onAdd,
  onClose,
}: {
  tabs: readonly TradingTabState[];
  activeTabId: string;
  canAdd: boolean;
  getTabLabel: (tab: TradingTabState) => string;
  onSelect: (tabId: string) => void;
  onAdd: () => void;
  onClose: (tab: TradingTabState) => void;
}) {
  return (
    <nav className="trading-session-tabs" aria-label="Trading chart sessions">
      <div className="trading-session-tabs-scroll" role="tablist" aria-label="Independent chart sessions">
        {tabs.map((tab, index) => {
          const label = getTabLabel(tab);
          return (
          <div className={`trading-session-tab${tab.tabId === activeTabId ? ' active' : ''}`} key={tab.tabId}>
            <button
              type="button"
              role="tab"
              aria-selected={tab.tabId === activeTabId}
              aria-label={`Open ${label} chart session`}
              onClick={() => onSelect(tab.tabId)}
              title={`${label} chart session`}
            >
              <span className="trading-session-tab-dot" aria-hidden="true" />
              <span className="trading-session-tab-name">{label}</span>
              {tab.tabId === activeTabId ? <span className="trading-session-tab-state" aria-hidden="true" /> : null}
            </button>
            <button
              type="button"
              className="trading-session-tab-close"
              aria-label={`Close ${label} chart session`}
              onClick={() => onClose(tab)}
              disabled={tabs.length <= 1}
            >
              ×
            </button>
            {index === 0 ? <span className="trading-session-tab-divider" aria-hidden="true" /> : null}
          </div>
          );
        })}
      </div>
      <button type="button" className="trading-session-tab-add" aria-label="Create chart session tab" onClick={onAdd} disabled={!canAdd}>+</button>
      <span className="trading-session-tab-hint">Each tab keeps its own chart layout, indicators, drawings, and settings</span>
    </nav>
  );
}
