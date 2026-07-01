import type { PairBadgeSummary } from './pairBadgeSummary';
import { pairCountText } from './pairCountText';

export function pairSummaryText(summary: PairBadgeSummary): string {
  return pairCountText(summary.visibleCount, summary.text);
}
