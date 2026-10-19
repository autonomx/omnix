import { unwrapLabelled } from '../../api/http';
import { api } from './api/gateway';

/** One bar of a chat price chart: UTC seconds at the bar's start and its close. */
export type ChatPriceBar = { time: number; close: number };

/**
 * Read-only bars for chat's pinned price charts (chat generative UI, GUI-4.2).
 *
 * It calls the chart's bars endpoint and nothing else: no order, alert,
 * watchlist or strategy path is reachable from chat through this module.
 */
export async function fetchChatPriceBars(instrumentId: string, interval: string, limit: number): Promise<ChatPriceBar[]> {
  const response = await unwrapLabelled(
    api.GET('/api/trading/bars', { params: { query: { instrument_id: instrumentId, interval, limit: Math.max(1, Math.min(5_000, Math.round(limit))) } } }),
    'Trading',
  );
  return response.bars
    .map((bar) => ({ time: Math.floor(Date.parse(bar.start_time) / 1000), close: Number(bar.close) }))
    .filter((bar) => Number.isFinite(bar.time) && Number.isFinite(bar.close));
}

/** The trading chart showing an instrument (`?instrument=` is the chart's own link). */
export function tradingChartHref(instrumentId: string): string {
  return `/trading?instrument=${encodeURIComponent(instrumentId)}`;
}
