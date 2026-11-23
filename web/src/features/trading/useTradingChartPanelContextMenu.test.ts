import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useChartContextMenu, type ChartContextMenuInput } from './useTradingChartPanelContextMenu';
import { fixture } from '../../test/fixture';

function input(overrides: Partial<Record<keyof ChartContextMenuInput, unknown>> = {}) {
  const stage = document.createElement('div');
  const host = document.createElement('div');
  stage.appendChild(host);
  Object.defineProperty(stage, 'clientWidth', { value: 400 });
  Object.defineProperty(stage, 'clientHeight', { value: 500 });
  return fixture<ChartContextMenuInput>({
    active: false,
    adapterRef: { current: null },
    contextMenu: null,
    drawings: { removeAll: vi.fn() },
    hostRef: { current: host },
    indicators: [{ id: 'rsi', period: 14, enabled: true }],
    onActivate: vi.fn(),
    onClearIndicators: vi.fn(),
    onToggleIndicator: vi.fn(),
    paneIndicators: [],
    setAlertPlacement: vi.fn(),
    setContextMenu: vi.fn(),
    setSelectedIndicator: vi.fn(),
    ...overrides,
  });
}

const point = { time: '2026-08-05T12:00:00Z', price: 101, x: 390, y: 10, source: 'context-menu' as const };

describe('chart context menu', () => {
  it('opens on an inactive chart inside the stage, with the pane indicator it was opened on', () => {
    const ws = input();
    const { result } = renderHook(() => useChartContextMenu(ws));

    act(() => result.current.contextMenuActions.open(point, 'rsi'));

    expect(ws.onActivate).toHaveBeenCalledOnce();
    expect(ws.setSelectedIndicator).toHaveBeenCalledWith(null);
    expect(ws.setContextMenu).toHaveBeenCalledWith(expect.objectContaining({
      x: 114, y: 10, contextIndicatorId: 'rsi', chartIndicatorId: 'rsi', indicatorPeriod: 14,
    }));
  });

  it('the clean template clears indicators and drawings; momentum adds only the missing ones', () => {
    const ws = input();
    const { result } = renderHook(() => useChartContextMenu(ws));

    act(() => result.current.contextMenuActions.applyTemplate('clean'));
    expect(ws.onClearIndicators).toHaveBeenCalledOnce();
    expect(ws.drawings.removeAll).toHaveBeenCalledOnce();

    act(() => result.current.contextMenuActions.applyTemplate('momentum'));
    expect(ws.onToggleIndicator).toHaveBeenCalledTimes(1);
    expect(ws.onToggleIndicator).toHaveBeenCalledWith('macd');
  });

  it('adds an alert at the menu point, and does nothing without a menu', () => {
    const closed = input();
    renderHook(() => useChartContextMenu(closed)).result.current.contextMenuActions.addAlert();
    expect(closed.setAlertPlacement).not.toHaveBeenCalled();

    const open = input({ contextMenu: point });
    renderHook(() => useChartContextMenu(open)).result.current.contextMenuActions.addAlert();
    expect(open.setAlertPlacement).toHaveBeenCalledWith(point);
  });
});
