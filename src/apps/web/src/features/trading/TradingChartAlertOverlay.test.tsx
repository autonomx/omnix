import { describe, expect, it } from 'vitest';
import { editorDefaults } from './TradingChartAlertOverlay';

describe('Trading chart alert placement defaults', () => {
  it('keeps an RSI placement on the indicator scale', () => {
    const editor = editorDefaults({
      time: '2026-08-22T20:00:00.000Z',
      price: 73,
      x: 120,
      y: 240,
      source: 'context-menu',
      indicatorId: 'rsi',
      indicatorPeriod: 14,
    }, 77_286.18);

    expect(editor).toMatchObject({
      condition: 'indicator_above',
      indicator: 'rsi',
      period: '14',
      threshold: '73',
    });
  });

  it('keeps a main-chart placement as a price alert', () => {
    const editor = editorDefaults({
      time: '2026-08-22T20:00:00.000Z',
      price: 78_000,
      x: 120,
      y: 240,
      source: 'context-menu',
    }, 77_286.18);

    expect(editor.condition).toBe('price_above');
    expect(editor.indicator).toBe('rsi');
  });
});
