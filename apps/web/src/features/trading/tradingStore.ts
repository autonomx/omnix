import { create } from 'zustand';
import type { TradingChartType } from './chart/chartAdapter';
import type { DrawingTool } from './drawings/drawingCommands';
import type { CoreIndicatorId, CoreIndicatorInstance } from './indicators/coreIndicators';

export type TradingLayout = 'one' | 'four';
export type TradingChartState = {
  chartId: string;
  instrumentId: string;
  bindingId: string | null;
  interval: string;
  chartType: TradingChartType;
  indicators: CoreIndicatorInstance[];
};
export type TradingLinkState = {
  instrument: boolean;
  interval: boolean;
  crosshair: boolean;
  visibleRange: boolean;
};

type TradingWorkspaceState = {
  layout: TradingLayout;
  activeChartId: string;
  drawingTool: DrawingTool;
  charts: TradingChartState[];
  links: TradingLinkState;
  setLayout: (layout: TradingLayout) => void;
  setActiveChart: (chartId: string) => void;
  setDrawingTool: (tool: DrawingTool) => void;
  updateChart: (chartId: string, patch: Partial<Omit<TradingChartState, 'chartId'>>) => void;
  toggleIndicator: (chartId: string, id: CoreIndicatorId, period?: number) => void;
  setLink: (key: keyof TradingLinkState, enabled: boolean) => void;
};

const defaultInstrument = 'crypto:BINANCE:spot:BTC-USDT';
const indicators = (): CoreIndicatorInstance[] => [
  { id: 'sma', period: 20, enabled: true },
  { id: 'ema', period: 20, enabled: false },
  { id: 'rsi', period: 14, enabled: true },
];

export const useTradingStore = create<TradingWorkspaceState>((set) => ({
  layout: 'one',
  activeChartId: 'chart-1',
  drawingTool: 'cursor',
  charts: [
    { chartId: 'chart-1', instrumentId: defaultInstrument, bindingId: null, interval: '1m', chartType: 'candlestick', indicators: indicators() },
    { chartId: 'chart-2', instrumentId: 'crypto:BINANCE:spot:ETH-USDT', bindingId: null, interval: '5m', chartType: 'candlestick', indicators: indicators() },
    { chartId: 'chart-3', instrumentId: 'crypto:BINANCE:spot:SOL-USDT', bindingId: null, interval: '15m', chartType: 'candlestick', indicators: indicators() },
    { chartId: 'chart-4', instrumentId: defaultInstrument, bindingId: null, interval: '1h', chartType: 'line', indicators: indicators() },
  ],
  links: { instrument: false, interval: false, crosshair: true, visibleRange: true },
  setLayout: (layout) => set({ layout }),
  setActiveChart: (activeChartId) => set({ activeChartId }),
  setDrawingTool: (drawingTool) => set({ drawingTool }),
  updateChart: (chartId, patch) => set((state) => {
    const instrumentChanged = patch.instrumentId !== undefined;
    const linkedInstrument = instrumentChanged && state.links.instrument;
    const linkedInterval = patch.interval !== undefined && state.links.interval;
    return {
      charts: state.charts.map((chart) => {
        if (chart.chartId === chartId) {
          return {
            ...chart,
            ...patch,
            ...(instrumentChanged && patch.bindingId === undefined ? { bindingId: null } : {}),
          };
        }
        return {
          ...chart,
          ...(linkedInstrument ? { instrumentId: patch.instrumentId, bindingId: null } : {}),
          ...(linkedInterval ? { interval: patch.interval } : {}),
        };
      }),
    };
  }),
  toggleIndicator: (chartId, id, period) => set((state) => ({
    charts: state.charts.map((chart) => chart.chartId !== chartId ? chart : {
      ...chart,
      indicators: chart.indicators.map((indicator) => indicator.id !== id ? indicator : {
        ...indicator,
        enabled: !indicator.enabled,
        period: period ?? indicator.period,
      }),
    }),
  })),
  setLink: (key, enabled) => set((state) => ({ links: { ...state.links, [key]: enabled } })),
}));
