import { useRouter, type AnyRouter } from '@tanstack/react-router';
import { useEffect, useState, type MouseEvent } from 'react';
import { fetchChatPriceBars, tradingChartHref, type ChatPriceBar } from '../../../../trading';
import { ChartBlockView } from './ChartBlockView';
import type { ChartBlock, PriceChartBlock } from '../schema';

const DAY = 86_400;
const INTERVAL_SECONDS: Record<PriceChartBlock['interval'], number> = {
  '1m': 60, '5m': 300, '15m': 900, '30m': 1_800, '1h': 3_600, '4h': 14_400, '1d': DAY, '1w': 7 * DAY,
};
const RANGE_SECONDS: Record<Exclude<PriceChartBlock['range'], 'YTD' | 'MAX'>, number> = {
  '1D': DAY, '5D': 5 * DAY, '1M': 31 * DAY, '3M': 92 * DAY, '6M': 183 * DAY, '1Y': 366 * DAY, '5Y': 5 * 366 * DAY,
};
const INTERVAL_LABEL: Record<PriceChartBlock['interval'], string> = {
  '1m': '1 min', '5m': '5 min', '15m': '15 min', '30m': '30 min', '1h': 'Hourly', '4h': '4 hour', '1d': 'Daily', '1w': 'Weekly',
};

/** The bar window a pinned chart shows: its range, ending at `as_of` (when the answer was written). */
export function priceChartWindow(block: PriceChartBlock, nowSeconds: number): { from: number | null; to: number; limit: number } {
  const to = Math.floor(Date.parse(block.as_of) / 1000);
  const from = block.range === 'MAX'
    ? null
    : block.range === 'YTD'
      ? Math.floor(Date.UTC(new Date(to * 1000).getUTCFullYear(), 0, 1) / 1000)
      : to - RANGE_SECONDS[block.range];
  const elapsed = Math.max(0, nowSeconds - to);
  const needed = from === null ? 5_000 : Math.ceil((to - from + elapsed) / INTERVAL_SECONDS[block.interval]) + 5;
  return { from, to, limit: Math.max(2, Math.min(5_000, needed)) };
}

/** Bars inside the window; later bars (after the answer was written) are left out. */
export function pinnedBars(bars: ChatPriceBar[], window: { from: number | null; to: number }): ChatPriceBar[] {
  return bars.filter((bar) => bar.time <= window.to && (window.from === null || bar.time >= window.from));
}

type Load = { status: 'loading' } | { status: 'ready'; bars: ChatPriceBar[] } | { status: 'error' };

/** Pinned, read-only market data: the chart shows what was true when the answer was written. */
export function PriceChartBlockView({ block, summary }: { block: PriceChartBlock; summary: string }) {
  const router = useRouter({ warn: false }) as AnyRouter | undefined;
  const [load, setLoad] = useState<Load>({ status: 'loading' });
  useEffect(() => {
    let cancelled = false;
    const window = priceChartWindow(block, Date.now() / 1000);
    setLoad({ status: 'loading' });
    fetchChatPriceBars(block.instrument_id, block.interval, window.limit)
      .then((bars) => { if (!cancelled) setLoad({ status: 'ready', bars: pinnedBars(bars, window) }); })
      .catch(() => { if (!cancelled) setLoad({ status: 'error' }); });
    return () => { cancelled = true; };
  }, [block]);

  const href = tradingChartHref(block.instrument_id);
  const openChart = (event: MouseEvent<HTMLAnchorElement>) => {
    if (!router || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    void router.navigate({ to: '/trading', search: { instrument: block.instrument_id } } as never);
  };
  const asOf = block.as_of.slice(0, 10);
  const title = block.title ?? `${block.symbol} · ${INTERVAL_LABEL[block.interval]} · ${block.range}`;
  const chart: ChartBlock | null = load.status === 'ready' && load.bars.length
    ? {
      type: 'chart', id: block.id, v: 1, kind: 'area', size: 'md', bindings: [], provenance: 'bound',
      x: { type: 'time' }, y: { format: 'number' },
      series: [{ name: `${block.symbol} close`, points: load.bars.map((bar) => [bar.time, bar.close] as [number, number]) }],
    }
    : null;
  return (
    <section className="gui-block gui-price-chart" aria-label={title}>
      <header className="gui-block-header">
        <h4>{title}</h4>
        <span className="gui-provenance"><span className="gui-provenance-market">Market data as of <time dateTime={block.as_of}>{asOf}</time></span></span>
        <a className="gui-link-button" href={href} onClick={openChart}>Open in chart</a>
      </header>
      {load.status === 'loading' ? <div className="gui-block-status" role="status">Loading market data…</div> : null}
      {load.status === 'error' ? <div className="gui-block-status" role="status">Market data is unavailable. {summary}</div> : null}
      {load.status === 'ready' && !chart ? <div className="gui-block-status" role="status">No market data for this period.</div> : null}
      {chart ? <ChartBlockView block={chart} summary={summary} /> : null}
    </section>
  );
}
