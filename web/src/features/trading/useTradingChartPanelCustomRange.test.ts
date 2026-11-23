import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useChartCustomRange, type ChartCustomRangeInput } from './useTradingChartPanelCustomRange';
import { fixture } from '../../test/fixture';

function input(bars: { start_time: string; end_time: string }[]) {
  return fixture<ChartCustomRangeInput>({
    adapterRef: { current: null },
    barsRef: { current: bars },
    interval: '1d',
    rightOffset: 0,
    selectedRangeRef: { current: undefined },
    selectedTimezone: 'UTC',
    setSelectedRangeLabel: vi.fn(),
    setTimezoneMenuOpen: vi.fn(),
  });
}

const loaded = [
  { start_time: '2026-08-03T00:00:00Z', end_time: '2026-08-04T00:00:00Z' },
  { start_time: '2026-08-10T00:00:00Z', end_time: '2026-08-11T00:00:00Z' },
];

describe('chart custom range', () => {
  it('opens on the loaded history and closes the timezone menu', () => {
    const ws = input(loaded);
    const { result } = renderHook(() => useChartCustomRange(ws));

    act(() => result.current.customRange.toggle());

    expect(result.current.customRange).toMatchObject({ open: true, start: '2026-08-03', end: '2026-08-11', error: null });
    expect(ws.setTimezoneMenuOpen).toHaveBeenCalledWith(false);
  });

  it('refuses dates out of order or outside the loaded history, and shows dates inside it', () => {
    const ws = input(loaded);
    const { result } = renderHook(() => useChartCustomRange(ws));
    act(() => result.current.customRange.toggle());

    act(() => { result.current.customRange.setStart('2026-08-09'); result.current.customRange.setEnd('2026-08-05'); });
    act(() => result.current.customRange.apply());
    expect(result.current.customRange.error).toBe('The start date must be before the end date.');

    act(() => result.current.customRange.setStart('2026-07-01'));
    act(() => result.current.customRange.setEnd('2026-08-05'));
    act(() => result.current.customRange.apply());
    expect(result.current.customRange.error).toMatch(/^Requested dates are outside loaded history/);
    expect(ws.selectedRangeRef.current).toBeUndefined();

    act(() => result.current.customRange.setStart('2026-08-04'));
    act(() => result.current.customRange.apply());
    expect(result.current.customRange).toMatchObject({ open: false, error: null });
    expect(ws.selectedRangeRef.current).toEqual({ from: '2026-08-04', to: '2026-08-05' });
    expect(ws.setSelectedRangeLabel).toHaveBeenCalledWith('Custom');
  });

  it('closes on a press outside its popover but not inside it', () => {
    const { result } = renderHook(() => useChartCustomRange(input(loaded)));
    const inside = document.createElement('div');
    document.body.append(inside);
    result.current.customRange.ref.current = inside;
    act(() => result.current.customRange.toggle());

    act(() => { inside.dispatchEvent(new Event('pointerdown', { bubbles: true })); });
    expect(result.current.customRange.open).toBe(true);
    act(() => { document.body.dispatchEvent(new Event('pointerdown', { bubbles: true })); });
    expect(result.current.customRange.open).toBe(false);
    inside.remove();
  });
});
