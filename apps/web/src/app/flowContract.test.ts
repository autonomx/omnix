import { expect, test } from 'vitest';
import { cfgLine } from './cfgLine';
import { cfgState } from './cfgState';
import { createPairBadgeSummary } from './pairBadgeSummary';
import { pairSummaryText } from './pairSummaryText';

test('local flow carries neutral summary text', () => {
  const cfg = cfgState();
  const summary = createPairBadgeSummary({ text: cfgLine(cfg), reviewVisible: true, rpgVisible: true });

  expect(cfg.active).toBe(false);
  expect(cfg.ready).toBe(false);
  expect(cfg.readOnly).toBe(true);
  expect(cfg.passive).toBe(true);
  expect(summary.readOnly).toBe(true);
  expect(pairSummaryText(summary)).toBe('2/2 Waiting');
});

test('local flow carries ready text only from ready state', () => {
  const cfg = cfgState(true, true);
  const summary = createPairBadgeSummary({ text: cfgLine(cfg), reviewVisible: true, rpgVisible: true });

  expect(cfg.ready).toBe(true);
  expect(pairSummaryText(summary)).toBe('2/2 Ready');
});
