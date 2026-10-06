import type { MarketBar } from './tradingTypes';
import { tradingIntervalMinutes } from './tradingIntervals';

export function percentChangeFromBars(
  currentPrice: string | number | null | undefined,
  bars: readonly MarketBar[],
): number | null {
  const currentIntervalOpen = Number(bars.at(-1)?.open);
  const current = Number(currentPrice ?? bars.at(-1)?.close);
  if (!Number.isFinite(currentIntervalOpen) || currentIntervalOpen <= 0 || !Number.isFinite(current)) return null;
  return ((current - currentIntervalOpen) / currentIntervalOpen) * 100;
}

export function percentChangeFromLookback(
  currentPrice: string | number | null | undefined,
  bars: readonly MarketBar[],
  targetInterval: string,
): number | null {
  const targetMinutes = tradingIntervalMinutes(targetInterval);
  const latest = bars.at(-1);
  if (targetMinutes == null || !latest) return null;

  const latestStart = Date.parse(latest.start_time);
  if (!Number.isFinite(latestStart)) return null;
  const cutoff = latestStart - targetMinutes * 60_000;
  const reference = bars.find((bar) => Date.parse(bar.start_time) >= cutoff);
  const currentIntervalOpen = Number(reference?.open);
  const current = Number(currentPrice ?? latest.close);
  if (!Number.isFinite(currentIntervalOpen) || currentIntervalOpen <= 0 || !Number.isFinite(current)) return null;
  return ((current - currentIntervalOpen) / currentIntervalOpen) * 100;
}
