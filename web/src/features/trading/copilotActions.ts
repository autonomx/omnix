import type { TradingDrawing } from './drawings/drawingCommands';
import { AI_RANGE_TOOL_ID } from './drawings/tools/definitions/aiRange';
import type { CoreIndicatorId, CoreIndicatorInstance } from './indicators/coreIndicators';
import type { CopilotAction } from './researchTypes';
import { newIndicatorInstance } from './tradingStore';

/** What a Copilot proposal may change: the active chart's interval, indicators and drawings. Nothing else. */
export type CopilotChartControls = {
  instrumentId: string;
  indicators: CoreIndicatorInstance[];
  onSetInterval: (interval: string) => void;
  onSetIndicators: (indicators: CoreIndicatorInstance[]) => void;
  addDrawing: (drawing: TradingDrawing) => void;
};

/** The indicators with `id` on (its period when given), added with its defaults when the chart lacks it. */
export function indicatorsWith(indicators: CoreIndicatorInstance[], id: CoreIndicatorId, period: number | null | undefined): CoreIndicatorInstance[] {
  if (!indicators.some((indicator) => indicator.id === id)) return [...indicators, newIndicatorInstance(id, period ?? undefined)];
  return indicators.map((indicator) => (indicator.id === id ? { ...indicator, enabled: true, visible: true, period: period ?? indicator.period } : indicator));
}

/** The indicators with `id` off; what read it as a source reads the close again (as the toolbar toggle does). */
export function indicatorsWithout(indicators: CoreIndicatorInstance[], id: string): CoreIndicatorInstance[] {
  return indicators.map((indicator) => {
    if (indicator.id === id) return { ...indicator, enabled: false, visible: false };
    return indicator.source?.indicatorId === id ? { ...indicator, source: null } : indicator;
  });
}

function drawing(instrumentId: string, toolType: TradingDrawing['toolType'], points: TradingDrawing['points'], text = ''): TradingDrawing {
  return { drawingId: crypto.randomUUID(), instrumentId, toolType, points, selected: true, revision: 1, locked: false, hidden: false, text };
}

/**
 * Applies one proposal the person chose. `referencePrice` anchors a marked range's points (its band spans the chart's
 * height, so the price only places the anchors). Returns whether the chart changed.
 */
export function applyCopilotAction(action: CopilotAction, controls: CopilotChartControls, referencePrice: number): boolean {
  switch (action.kind) {
    case 'set_interval':
      if (!action.interval) return false;
      controls.onSetInterval(action.interval);
      return true;
    case 'add_indicator':
      if (!action.indicator) return false;
      controls.onSetIndicators(indicatorsWith(controls.indicators, action.indicator as CoreIndicatorId, action.period));
      return true;
    case 'remove_indicator':
      if (!action.indicator) return false;
      controls.onSetIndicators(indicatorsWithout(controls.indicators, action.indicator));
      return true;
    case 'draw_level': {
      const price = Number(action.price);
      if (!action.time || !Number.isFinite(price)) return false;
      controls.addDrawing(drawing(controls.instrumentId, 'horizontal-line', [{ time: action.time, price }], action.note ?? ''));
      return true;
    }
    case 'mark_range':
      if (!action.start || !action.end || !Number.isFinite(referencePrice)) return false;
      controls.addDrawing(drawing(controls.instrumentId, AI_RANGE_TOOL_ID, [{ time: action.start, price: referencePrice }, { time: action.end, price: referencePrice }]));
      return true;
    default:
      return false;
  }
}
