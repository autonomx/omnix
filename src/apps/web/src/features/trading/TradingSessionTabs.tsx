import { useTradingStore, type TradingTabState } from './tradingStore';

function isGeneratedTabName(name: string): boolean {
  return name === 'Main Session' || /^Session \d+$/.test(name);
}

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
  const renameTab = useTradingStore((state) => state.renameTab);

  const renameSession = (tab: TradingTabState, fallbackLabel: string) => {
    const currentName = isGeneratedTabName(tab.name) ? fallbackLabel : tab.name;
    const nextName = window.prompt('Rename chart session', currentName);
    if (nextName?.trim()) renameTab(tab.tabId, nextName);
  };

  return (
    <nav className="trading-session-tabs" aria-label="Trading chart sessions">
      <div className="trading-session-tabs-scroll" role="tablist" aria-label="Independent chart sessions">
        {tabs.map((tab, index) => {
          const fallbackLabel = getTabLabel(tab);
          const label = isGeneratedTabName(tab.name) ? fallbackLabel : tab.name;
          const title = label === fallbackLabel ? `${label} chart session` : `${label} · ${fallbackLabel}`;
          return (
          <div className={`trading-session-tab${tab.tabId === activeTabId ? ' active' : ''}`} key={tab.tabId}>
            <button
              type="button"
              role="tab"
              aria-selected={tab.tabId === activeTabId}
              aria-label={`Open ${label} chart session`}
              onClick={() => onSelect(tab.tabId)}
              onDoubleClick={() => renameSession(tab, fallbackLabel)}
              title={`${title} · Double-click to rename`}
            >
              <span className="trading-session-tab-dot" aria-hidden="true" />
              <span className="trading-session-tab-name">{label}</span>
              {tab.tabId === activeTabId ? <span className="trading-session-tab-state" aria-hidden="true" /> : null}
            </button>
            <button
              type="button"
              className="trading-session-tab-close trading-session-tab-rename"
              aria-label={`Rename ${label} chart session`}
              title="Rename chart session"
              onClick={() => renameSession(tab, fallbackLabel)}
            >
              ✎
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
