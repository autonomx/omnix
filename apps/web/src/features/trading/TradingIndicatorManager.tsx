import type { CoreIndicatorId, CoreIndicatorInstance } from './indicators/coreIndicators';

export function TradingIndicatorManager({
  indicators,
  onToggle,
}: {
  indicators: CoreIndicatorInstance[];
  onToggle: (id: CoreIndicatorId) => void;
}) {
  return (
    <div className="trading-indicator-manager" role="group" aria-label="Technical indicators">
      {indicators.map((indicator) => (
        <button
          key={indicator.id}
          type="button"
          className={indicator.enabled ? 'active' : undefined}
          aria-pressed={indicator.enabled}
          onClick={() => onToggle(indicator.id)}
        >
          {indicator.id.toUpperCase()} {indicator.period}
        </button>
      ))}
    </div>
  );
}
