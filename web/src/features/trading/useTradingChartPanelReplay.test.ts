import { act, renderHook } from '@testing-library/react';
import type React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useTradingReplayStore } from './tradingReplayStore';
import { useChartReplayActions, type ChartReplayInput } from './useTradingChartPanelReplay';
import { fixture } from '../../test/fixture';

const bars = [
  { start_time: '2026-08-05T12:00:00Z', end_time: '2026-08-05T12:05:00Z' },
  { start_time: '2026-08-05T12:05:00Z', end_time: '2026-08-05T12:10:00Z' },
];

function adapter() {
  return {
    isPriceScaleCoordinate: vi.fn(() => false),
    barIndexAtCoordinate: vi.fn(() => 1),
    barTimeToCoordinate: vi.fn(() => 50),
    timeToCoordinate: vi.fn(() => 50),
    indicatorPlotWidth: vi.fn(() => 200),
    onViewportChange: vi.fn(() => () => undefined),
  };
}

function input(overrides: Partial<Record<keyof ChartReplayInput, unknown>> = {}) {
  const chart = adapter();
  return fixture<ChartReplayInput>({
    active: true,
    adapter: chart,
    adapterRef: { current: chart },
    allBarsRef: { current: bars },
    chartQuery: { data: undefined },
    hostRef: { current: null },
    replayChoosingStart: false,
    replayMode: true,
    replaySelectionIndex: null,
    replayStartTime: null,
    setReplayMarkerX: vi.fn(),
    setReplayMode: vi.fn(),
    setReplaySelectionIndex: vi.fn(),
    setReplaySelectionX: vi.fn(),
    ...overrides,
  });
}

function stageClick() {
  const target = document.createElement('div');
  return fixture<React.MouseEvent<HTMLDivElement>>({
    target,
    clientX: 120,
    currentTarget: { getBoundingClientRect: () => ({ left: 20 }) },
  });
}

const original = useTradingReplayStore.getState();
let chooseStart: ReturnType<typeof vi.fn<(time: number) => void>>;
let stepForward: ReturnType<typeof vi.fn<(steps?: number) => boolean>>;

beforeEach(() => {
  chooseStart = vi.fn<(time: number) => void>();
  stepForward = vi.fn<(steps?: number) => boolean>(() => true);
  useTradingReplayStore.setState({ chooseStart, stepForward });
});

afterEach(() => {
  useTradingReplayStore.setState({ chooseStart: original.chooseStart, stepForward: original.stepForward });
});

describe('chart replay actions', () => {
  it('a chart click during a running replay does not restart it', () => {
    const { result } = renderHook(() => useChartReplayActions(input()));

    act(() => result.current.replay.handleStageClick(stageClick()));

    expect(chooseStart).not.toHaveBeenCalled();
  });

  it('a chart click while choosing a start sets the shared clock to the clicked bar close', () => {
    const ws = input({ replayChoosingStart: true, replaySelectionIndex: 1 });
    const { result } = renderHook(() => useChartReplayActions(ws));

    act(() => result.current.replay.handleStageClick(stageClick()));

    expect(ws.setReplaySelectionIndex).toHaveBeenCalledWith(1);
    expect(chooseStart).toHaveBeenCalledWith(Date.parse('2026-08-05T12:10:00Z'));
  });

  it('steps the shared clock and leaves replay through the slice', () => {
    const ws = input();
    const { result } = renderHook(() => useChartReplayActions(ws));

    act(() => { result.current.replay.nextBar(); result.current.replay.exit(); });

    expect(stepForward).toHaveBeenCalledOnce();
    expect(ws.setReplayMode).toHaveBeenCalledWith(false);
  });
});
