import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { newConditionDraft } from './alertConditionDrafts';
import { TradingAlertDialog, type TradingAlertEditorState } from './TradingAlertDialog';

afterEach(cleanup);

const editor = (overrides: Partial<TradingAlertEditorState> = {}): TradingAlertEditorState => ({
  mode: 'create', alertId: null, x: 0, y: 0, condition: 'price_above', threshold: '100', expiresAt: '', expiration: 'never',
  triggerPolicy: 'once', message: '', notifications: ['app'], indicator: 'rsi', period: '14', lookback: '1', ...overrides,
});

const dialog = (state: TradingAlertEditorState, onChange = vi.fn()) => render(
  <TradingAlertDialog editor={state} symbol="BTCUSDT" latestPrice={101} status="idle" onChange={onChange} onSubmit={vi.fn()} onClose={vi.fn()} />,
);

describe('alert dialog conditions (TVP-1.6)', () => {
  it("adds conditions after a price alert's own, up to five in all", () => {
    const onChange = vi.fn();
    dialog(editor(), onChange);
    fireEvent.click(screen.getByRole('button', { name: /Add condition/ }));
    expect(onChange).toHaveBeenCalledWith({ conditionDrafts: [expect.objectContaining({ source: 'close', value: '101' })] });
    cleanup();
    const four = Array.from({ length: 4 }, () => newConditionDraft('1'));
    const full = vi.fn();
    dialog(editor({ conditionDrafts: four }), full);
    expect(screen.getByLabelText('Condition 5 source')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Add condition/ }));
    expect(full).not.toHaveBeenCalled();
    expect(screen.getByRole('status').textContent).toMatch(/at most 5/);
  });

  it('keeps drawing alerts to one condition, saying why', () => {
    const onChange = vi.fn();
    dialog(editor({ condition: 'trendline_crossing', trendlinePoints: [{ time: 'a', price: 1 }, { time: 'b', price: 2 }] }), onChange);
    fireEvent.click(screen.getByRole('button', { name: /Add condition/ }));
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole('status').textContent).toMatch(/follow their drawing/);
  });
});
