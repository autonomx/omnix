import { expect, test } from 'vitest';
import { cfgState } from './cfgState';
import { createPairBadgeSummary } from './pairBadgeSummary';
import { pairSummaryText } from './pairSummaryText';

test('local flow carries neutral summary text', () => {
  const cfg = cfgState();
  const summary = createPairBadgeSummary({ text: 'Ready', reviewVisible: true, rpgVisible: true });

  expect(cfg.active).toBe(false);
  expect(summary.readOnly).toBe(true);
  expect(pairSummaryText(summary)).toBe('2/2 Ready');
});
