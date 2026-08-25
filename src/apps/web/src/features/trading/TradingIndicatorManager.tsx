import { createPortal } from 'react-dom';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { CoreIndicatorId, CoreIndicatorInstance } from './indicators/coreIndicators';
import { AUTO_CHART_PATTERN_DEFINITIONS, isAutoChartPatternId } from './indicators/autoPatterns';
import {
  TRADINGVIEW_BUILTIN_DEFINITIONS,
  tradingViewBuiltInDefaultPeriod,
} from './indicators/tradingViewBuiltIns';

type PickerTab = 'indicators' | 'strategies' | 'profiles' | 'patterns';
type PickerSection = 'favorites' | 'my-scripts' | 'technicals' | 'fundamentals' | 'top' | 'trending';

type IndicatorDefinition = {
  id: CoreIndicatorId;
  name: string;
  author: string;
  boosts: string;
  section: 'technicals';
  kind: 'indicator' | 'profile' | 'pattern';
  available: boolean;
  requirement?: string;
};

const omnixIndicatorDefinitions: IndicatorDefinition[] = [
  { id: 'bull-market-band', name: 'Bull Market Support Band (20w SMA, 21w EMA)', author: 'zkdev', boosts: '5.3 K', section: 'technicals', kind: 'indicator', available: true },
  { id: 'death-cross', name: 'Death Cross - 200 MA / 50 Cross Checker', author: 'MexPayne', boosts: '879', section: 'technicals', kind: 'indicator', available: true },
  { id: 'ema-stack', name: 'EMA 9, 21, 50, 200', author: 'edufelarcon', boosts: '756', section: 'technicals', kind: 'indicator', available: true },
  { id: 'fair-value-gap', name: 'Fair Value Gap [LuxAlgo]', author: 'LuxAlgo', boosts: '24.5 K', section: 'technicals', kind: 'indicator', available: true },
  { id: 'golden-cross', name: 'Golden Cross', author: 'MichMexTrade', boosts: '229', section: 'technicals', kind: 'indicator', available: true },
  { id: 'ideal-bb', name: 'IDEAL BB with MA (With Alerts)', author: 'rautadarsh123', boosts: '9.9 K', section: 'technicals', kind: 'indicator', available: true },
  { id: 'log-macd', name: 'Logarithmic Moving Average Convergence Divergence', author: 'chemmist', boosts: '882', section: 'technicals', kind: 'indicator', available: true },
  { id: 'macd-dema', name: 'MACD DEMA', author: 'ToFFF', boosts: '6.5 K', section: 'technicals', kind: 'indicator', available: true },
  { id: 'swing-liquidity', name: 'Swing Levels and Liquidity - By Leviathan', author: 'LeviathanCapital', boosts: '11.2 K', section: 'technicals', kind: 'indicator', available: true },
  { id: 'volume-profile', name: 'Volume Profile', author: 'kv4coins', boosts: '23.3 K', section: 'technicals', kind: 'profile', available: true },
];

const tradingViewIndicatorDefinitions: IndicatorDefinition[] = TRADINGVIEW_BUILTIN_DEFINITIONS.map((definition) => ({
  id: definition.id as CoreIndicatorId,
  name: definition.name,
  author: 'TradingView built-in',
  boosts: definition.available ? 'Built-in' : 'Needs data',
  section: 'technicals',
  kind: 'indicator',
  available: definition.available,
  requirement: definition.requirement,
}));

const patternDefinitions: IndicatorDefinition[] = AUTO_CHART_PATTERN_DEFINITIONS.map((definition) => ({
  id: definition.id,
  name: definition.name,
  author: 'Omnix',
  boosts: 'Built-in',
  section: 'technicals',
  kind: 'pattern',
  available: true,
}));

const indicatorDefinitions: IndicatorDefinition[] = [
  ...tradingViewIndicatorDefinitions,
  ...omnixIndicatorDefinitions,
  ...patternDefinitions,
];

const sectionGroups: Array<{ label: string; sections: Array<{ id: PickerSection; label: string; icon: string }> }> = [
  {
    label: 'PERSONAL',
    sections: [
      { id: 'favorites', label: 'Favorites', icon: '★' },
      { id: 'my-scripts', label: 'My scripts', icon: '♙' },
    ],
  },
  {
    label: 'BUILT-IN',
    sections: [
      { id: 'technicals', label: 'Technicals', icon: '⌁' },
      { id: 'fundamentals', label: 'Fundamentals', icon: '▥' },
    ],
  },
  {
    label: 'COMMUNITY',
    sections: [
      { id: 'top', label: 'Top', icon: '↗' },
      { id: 'trending', label: 'Trending', icon: '♨' },
    ],
  },
];

function indicatorPeriod(indicators: readonly CoreIndicatorInstance[], id: CoreIndicatorId): number {
  const configured = indicators.find((indicator) => indicator.id === id)?.period;
  if (configured !== undefined) return configured;
  const tradingViewDefault = tradingViewBuiltInDefaultPeriod(id);
  if (tradingViewDefault !== null) return tradingViewDefault;
  return isAutoChartPatternId(id) ? 3
    : id === 'rsi' || id === 'atr' || id === 'rsi-divergence' || id === 'stochastic-rsi' ? 14
      : id === 'macd' || id === 'log-macd' || id === 'macd-dema' ? 9
        : id === 'death-cross' || id === 'golden-cross' ? 50
          : id === 'ema-stack' ? 9
            : id === 'volume-profile' ? 100
              : id === 'swing-liquidity' ? 5
                : id === 'fair-value-gap' ? 3
                  : id === 'ideal-bb' ? 120
                    : 20;
}

export function TradingIndicatorManager({
  indicators,
  onToggle,
}: {
  indicators: CoreIndicatorInstance[];
  onToggle: (id: CoreIndicatorId) => void;
}) {
  const enabledCount = indicators.filter((indicator) => indicator.enabled).length;
  const triggerRef = useRef<HTMLButtonElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [tab, setTab] = useState<PickerTab>('indicators');
  const [section, setSection] = useState<PickerSection>('technicals');
  const [favoriteIds, setFavoriteIds] = useState<Set<CoreIndicatorId>>(
    () => new Set(indicatorDefinitions.map((definition) => definition.id)),
  );

  useEffect(() => {
    if (!open) return undefined;
    const frame = window.requestAnimationFrame(() => searchRef.current?.focus());
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setOpen(false);
      triggerRef.current?.focus();
    };
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [open]);

  const enabledById = useMemo(
    () => new Map(indicators.map((indicator) => [indicator.id, indicator.enabled])),
    [indicators],
  );
  const filteredDefinitions = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return indicatorDefinitions.filter((definition) => {
      if (tab === 'strategies') return false;
      if (tab === 'patterns' && definition.kind !== 'pattern') return false;
      if (tab === 'profiles' && definition.kind !== 'profile') return false;
      // Preserve the existing one-click Volume Profile path while also exposing
      // the dedicated Profiles tab. Pattern studies stay isolated in Patterns.
      if (tab === 'indicators' && definition.kind === 'pattern') return false;
      if (section === 'favorites' && !favoriteIds.has(definition.id)) return false;
      if (section !== 'favorites' && section !== 'technicals') return false;
      return !normalizedQuery || definition.name.toLowerCase().includes(normalizedQuery);
    });
  }, [favoriteIds, query, section, tab]);

  const toggleFavorite = (id: CoreIndicatorId) => {
    setFavoriteIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectIndicator = (definition: IndicatorDefinition) => {
    if (!definition.available) return;
    onToggle(definition.id);
    setOpen(false);
    triggerRef.current?.focus();
  };

  const emptyCopy = tab === 'strategies'
    ? ['No strategies available yet', 'Strategy templates will appear here as they are added.']
    : tab === 'profiles'
      ? ['No profiles found', 'Try another search or category.']
      : tab === 'patterns'
        ? ['No chart patterns found', 'Try another search or category.']
        : ['No indicators found', 'Try another search or category.'];

  const picker = open && typeof document !== 'undefined' ? createPortal(
    <div className="trading-indicator-picker-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false); }}>
      <section className="trading-indicator-picker" role="dialog" aria-modal="true" aria-labelledby="trading-indicator-picker-title">
        <header className="trading-indicator-picker-header">
          <h2 id="trading-indicator-picker-title">Indicators, metrics, and strategies</h2>
          <button type="button" className="trading-indicator-picker-close" aria-label="Close indicators" onClick={() => { setOpen(false); triggerRef.current?.focus(); }}>×</button>
        </header>

        <label className="trading-indicator-picker-search">
          <span className="trading-indicator-search-icon" aria-hidden="true" />
          <input ref={searchRef} type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search" aria-label="Search indicators" />
        </label>

        <div className="trading-indicator-picker-body">
          <aside className="trading-indicator-picker-sidebar" aria-label="Indicator categories">
            {sectionGroups.map((group) => (
              <div key={group.label} className="trading-indicator-picker-sidebar-group">
                <span className="trading-indicator-picker-sidebar-heading">{group.label}</span>
                {group.sections.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={section === item.id ? 'active' : undefined}
                    aria-pressed={section === item.id}
                    onClick={() => setSection(item.id)}
                  >
                    <span className="trading-indicator-picker-sidebar-icon" aria-hidden="true">{item.icon}</span>
                    <span>{item.label}</span>
                  </button>
                ))}
              </div>
            ))}
          </aside>

          <main className="trading-indicator-picker-results">
            <div className="trading-indicator-picker-tabs" role="tablist" aria-label="Indicator types">
              {(['indicators', 'strategies', 'profiles', 'patterns'] as PickerTab[]).map((item) => (
                <button key={item} type="button" role="tab" aria-selected={tab === item} className={tab === item ? 'active' : undefined} onClick={() => setTab(item)}>
                  {item[0].toUpperCase() + item.slice(1)}
                </button>
              ))}
            </div>
            <div className="trading-indicator-picker-columns" aria-hidden="true"><span>NAME</span><span>AUTHOR</span><span>BOOSTS</span></div>
            <div className="trading-indicator-picker-list" role="group" aria-label={tab === 'patterns' ? 'Auto chart patterns' : 'Technical indicators'}>
              {filteredDefinitions.map((definition) => {
                const period = indicatorPeriod(indicators, definition.id);
                const enabled = enabledById.get(definition.id) ?? false;
                const buttonLabel = ['atr', 'bollinger', 'ema', 'macd', 'rsi', 'sma', 'vwap'].includes(definition.id)
                  ? `${definition.id.toUpperCase()} ${period}`
                  : definition.name;
                return (
                  <div key={`${definition.kind}:${definition.id}:${definition.name}`} className={`trading-indicator-picker-row${enabled ? ' active' : ''}${definition.available ? '' : ' unavailable'}`} title={definition.requirement}>
                    <button type="button" className="trading-indicator-picker-star" aria-label={`${favoriteIds.has(definition.id) ? 'Remove' : 'Add'} ${definition.name} favorite`} aria-pressed={favoriteIds.has(definition.id)} onClick={() => toggleFavorite(definition.id)}>★</button>
                    <button type="button" className="trading-indicator-picker-item" aria-label={buttonLabel} aria-pressed={enabled} disabled={!definition.available} onClick={() => selectIndicator(definition)}>
                      <span className="trading-indicator-picker-name">
                        {definition.name}
                        {enabled ? <small>ACTIVE</small> : !definition.available ? <small>DATA REQUIRED</small> : null}
                      </span>
                      <span className="trading-indicator-picker-author">{definition.author}</span>
                      <span className="trading-indicator-picker-boosts">{definition.boosts}</span>
                    </button>
                  </div>
                );
              })}
              {filteredDefinitions.length === 0 ? (
                <div className="trading-indicator-picker-empty">
                  <strong>{emptyCopy[0]}</strong>
                  <span>{emptyCopy[1]}</span>
                </div>
              ) : null}
            </div>
          </main>
        </div>
      </section>
    </div>,
    document.body,
  ) : null;

  return (
    <div className={`trading-indicator-manager${enabledCount > 0 ? ' has-active' : ''}`}>
      <button
        ref={triggerRef}
        type="button"
        aria-label="Indicators"
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => setOpen((current) => !current)}
      >
        <span className="trading-indicator-glyph" aria-hidden="true"><i /><i /><i /></span>
        <span>Indicators</span>
        <span className="trading-menu-caret" aria-hidden="true">⌄</span>
      </button>
      {picker}
    </div>
  );
}
