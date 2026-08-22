import { useMemo, useState } from 'react';
import type { CoreIndicatorId, CoreIndicatorInstance } from './indicators/coreIndicators';
import { indicatorPineSource, indicatorPineTitle } from './indicators/indicatorPine';
import './TradingPinePanel.css';

function indicatorLabel(indicator: CoreIndicatorInstance): string {
  return `${indicatorPineTitle(indicator.id)} ${indicator.period}`;
}

export function TradingPinePanel({
  indicators,
  activeIndicatorId,
  onActiveIndicatorChange,
}: {
  indicators: CoreIndicatorInstance[];
  activeIndicatorId: CoreIndicatorId | null;
  onActiveIndicatorChange: (id: CoreIndicatorId) => void;
}) {
  const [copied, setCopied] = useState(false);
  const enabledIndicators = indicators.filter((indicator) => indicator.enabled);
  const selected = enabledIndicators.find((indicator) => indicator.id === activeIndicatorId) ?? enabledIndicators[0] ?? null;
  const source = useMemo(() => selected ? indicatorPineSource(selected) : '', [selected]);
  const lines = source.split('\n');

  const copySource = async () => {
    if (!source || !navigator.clipboard) return;
    await navigator.clipboard.writeText(source);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1_500);
  };

  if (!selected) {
    return <div className="trading-pine-panel trading-pine-empty">Add an indicator to view its Pine Script.</div>;
  }

  return (
    <div className="trading-pine-panel" aria-label="Pine Editor">
      <header className="trading-pine-header">
        <div className="trading-pine-heading"><span className="trading-pine-glyph" aria-hidden="true">{'{}'}</span><strong>Pine Editor</strong></div>
        <span className="trading-pine-readonly">Read-only</span>
      </header>
      <div className="trading-pine-toolbar">
        <label>
          <span>Indicator</span>
          <select
            aria-label="Pine indicator"
            value={selected.id}
            onChange={(event) => onActiveIndicatorChange(event.target.value as CoreIndicatorId)}
          >
            {enabledIndicators.map((indicator) => <option key={indicator.id} value={indicator.id}>{indicatorLabel(indicator)}</option>)}
          </select>
        </label>
        <button type="button" className="trading-pine-copy" onClick={() => void copySource()}>{copied ? 'Copied' : 'Copy script'}</button>
      </div>
      <div className="trading-pine-script-title">
        <strong>{indicatorPineTitle(selected.id)}</strong>
        <span>{selected.id.toUpperCase()} · {selected.period} · Pine v6</span>
      </div>
      <div className="trading-pine-notice"><span aria-hidden="true">!</span><strong>This script is read-only.</strong><span>Use Copy script to create an editable version.</span></div>
      <div className="trading-pine-code" role="textbox" aria-label="Pine Script source" aria-readonly="true" tabIndex={0}>
        {lines.map((line, index) => (
          <div className="trading-pine-code-line" key={`${index}-${line}`}>
            <span aria-hidden="true">{index + 1}</span>
            <code>{line || ' '}</code>
          </div>
        ))}
      </div>
    </div>
  );
}
