import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { TradingDrawing } from './drawings/drawingCommands';
import type { DrawingAlertLevel } from './drawings/tools/types';
import type { TradingAlert } from './tradingTypes';

const state = vi.hoisted(() => ({ alerts: [] as unknown[] }));
const api = vi.hoisted(() => ({ updateAlert: vi.fn() }));
const replace = vi.hoisted(() => vi.fn());
vi.mock('./useTradingAlerts', () => ({ useTradingAlerts: () => ({ data: state.alerts }), useTradingAlertMutations: () => ({ replace }) }));
vi.mock('./tradingApi', () => ({ tradingApi: api }));
vi.mock('./drawings/TradingDrawingOverlay', () => ({
  drawingMenuEntries: (drawing: TradingDrawing) => ({
    drawingAlertLevels: [
      { key: 'upper', label: 'Upper', anchors: [drawing.points[0], drawing.points[1]], extend: 'right', interpolation: 'bars' },
      { key: 'lower', label: 'Lower', anchors: [{ ...drawing.points[0], price: drawing.points[0].price - 5 }, { ...drawing.points[1], price: drawing.points[1].price - 5 }], extend: 'right', interpolation: 'bars' },
    ] satisfies DrawingAlertLevel[],
  }),
}));
vi.mock('./drawings/drawingFrame', () => ({ chartAccessFor: () => ({}) }));

import { DRAWING_ALERT_SETTLE_MS, DrawingAlertSync, drawingAlertUpdates } from './DrawingAlertSync';

const T0 = '2026-10-09T14:00:00.000Z';
const T1 = '2026-10-09T15:00:00.000Z';
const instrument = { tickSize: null, pointValue: 1 };
const channel = (price: number): TradingDrawing => ({
  drawingId: 'ch', instrumentId: 'btc', toolType: 'parallel-channel', points: [{ time: T0, price }, { time: T1, price: price + 10 }], selected: false, revision: 1,
}) as TradingDrawing;
const alert = (level: string, points: Array<{ time: string; price: string }>) => ({
  alert_id: `a-${level}`, instrument_id: 'btc', condition_type: 'trendline_crossing', threshold: '0', enabled: true, revision: 1,
  parameters: { drawing_id: 'ch', drawing_level: level, trendline_points: points }, evaluation_policy: {},
}) as unknown as TradingAlert;
const adapter = { drawingBarIndexMatchesBars: () => true } as never;

beforeEach(() => {
  api.updateAlert.mockImplementation(async (item: TradingAlert) => item);
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe('drawing alerts follow their drawing (TVP-1.4)', () => {
  it('works out which alerts moved, on their own level', () => {
    const levels = (drawing: TradingDrawing): DrawingAlertLevel[] => [
      { key: 'upper', label: 'Upper', anchors: [drawing.points[0], drawing.points[1]], extend: 'right', interpolation: 'bars' },
    ];
    const still = alert('upper', [{ time: T0, price: '100' }, { time: T1, price: '110' }]);
    expect(drawingAlertUpdates([still], [channel(100)], levels)).toEqual([]);
    expect(drawingAlertUpdates([still], [channel(102)], levels)[0].points).toEqual([{ time: T0, price: 102 }, { time: T1, price: 112 }]);
    // A level the drawing no longer has, or a drawing not on this chart, changes nothing.
    expect(drawingAlertUpdates([alert('middle', [])], [channel(102)], levels)).toEqual([]);
    expect(drawingAlertUpdates([still], [], levels)).toEqual([]);
  });

  it('moves the alert line once the drawing settles', async () => {
    vi.useFakeTimers();
    state.alerts = [alert('lower', [{ time: T0, price: '95' }, { time: T1, price: '105' }])];
    const view = render(<DrawingAlertSync adapter={adapter} instrumentId="btc" instrument={instrument} drawings={[channel(100)]} />);
    view.rerender(<DrawingAlertSync adapter={adapter} instrumentId="btc" instrument={instrument} drawings={[channel(120)]} />);
    expect(api.updateAlert).not.toHaveBeenCalled();
    await act(async () => { await vi.advanceTimersByTimeAsync(DRAWING_ALERT_SETTLE_MS); });
    expect(api.updateAlert).toHaveBeenCalledTimes(1);
    expect(api.updateAlert.mock.calls[0][1].parameters.trendline_points).toEqual([{ time: T0, price: '115' }, { time: T1, price: '125' }]);
  });

  it('offers to disable the alerts of a drawing deleted here', async () => {
    state.alerts = [alert('upper', [{ time: T0, price: '100' }, { time: T1, price: '110' }])];
    const view = render(<DrawingAlertSync adapter={null} instrumentId="btc" instrument={instrument} drawings={[channel(100)]} />);
    expect(screen.queryByRole('alertdialog')).toBeNull();
    view.rerender(<DrawingAlertSync adapter={null} instrumentId="btc" instrument={instrument} drawings={[]} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Disable' }));
    await waitFor(() => expect(api.updateAlert).toHaveBeenCalledWith(expect.objectContaining({ alert_id: 'a-upper' }), expect.objectContaining({ enabled: false })));
  });

  it('never prompts for a drawing it never saw, such as one on another chart', () => {
    state.alerts = [alert('upper', [])];
    render(<DrawingAlertSync adapter={null} instrumentId="btc" instrument={instrument} drawings={[]} />);
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });
});
