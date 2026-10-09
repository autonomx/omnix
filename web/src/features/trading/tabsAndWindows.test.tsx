import { act, cleanup, fireEvent, render, renderHook, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { emitOmnixEvent } from '../../events/bus';
import { useChartTimeSync } from './chartTimeSync';
import { tradingDraftRecovery } from './persistence/draftRecovery';
import { parseTradingWorkspace, serializeTradingWorkspace } from './persistence/workspaceDocument';
import { useTradingWorkspacePersistence } from './persistence/useTradingWorkspacePersistence';
import { tradingApi } from './tradingApi';
import { TradingSessionTabs } from './TradingSessionTabs';
import { useTradingStore } from './tradingStore';
import type { TradingDocument } from './tradingTypes';
import { TradingWindowPresence, requestedTradingWindow, tradingWindowPresence, tradingWindowUrl } from './windowPresence';

const initialStore = useTradingStore.getState();

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  useTradingStore.setState(initialStore, true);
  window.history.replaceState(null, '', '/');
});

/** Two presences joined by an in-memory channel. */
function pairedWindows() {
  const peers: TradingWindowPresence[] = [];
  const channel = (index: number) => ({
    postMessage: (message: unknown) => peers.forEach((peer, at) => at !== index && peer.receive(message as never)),
    onmessage: null,
  }) as unknown as BroadcastChannel;
  peers.push(new TradingWindowPresence(channel(0)));
  peers.push(new TradingWindowPresence(channel(1)));
  return peers;
}

describe('trading windows (TVP-4.3)', () => {
  it('rings alerts in the most recently focused window only, and in the next one when it leaves', () => {
    const [first, second] = pairedWindows();
    first.focus(100);
    second.focus(200);
    expect([first.isAlertWindow(), second.isAlertWindow()]).toEqual([false, true]);
    first.focus(300);
    expect([first.isAlertWindow(), second.isAlertWindow()]).toEqual([true, false]);
    first.leave();
    expect(second.isAlertWindow()).toBe(true);
    expect(new TradingWindowPresence(null).isAlertWindow()).toBe(true);
  });

  it('tells the other windows when a document was saved', () => {
    const [first, second] = pairedWindows();
    const heard = vi.fn();
    const own = vi.fn();
    second.onOtherWindowSaved(heard);
    first.onOtherWindowSaved(own);
    first.announceSaved('watchlist', 'default', 7);
    expect(heard).toHaveBeenCalledWith('watchlist', 'default', 7);
    expect(own).not.toHaveBeenCalled();
  });

  it('opens a workspace and tab by URL', () => {
    const url = tradingWindowUrl('swing-1a2b', 'tab-3', { origin: 'https://omnix.test', pathname: '/trading' });
    expect(url).toBe('https://omnix.test/trading?workspace=swing-1a2b&tab=tab-3');
    expect(requestedTradingWindow('?workspace=swing-1a2b&tab=tab-3')).toEqual({ workspaceId: 'swing-1a2b', tabId: 'tab-3' });
    expect(requestedTradingWindow('')).toEqual({ workspaceId: null, tabId: null });
  });
});

describe('tab management (TVP-4.4)', () => {
  it('duplicates a tab next to it with new chart ids, and adds a blank tab', () => {
    const store = useTradingStore.getState();
    store.updateChart(store.activeChartId, { interval: '15m' });
    const original = useTradingStore.getState().tabs[0];
    const copyId = useTradingStore.getState().duplicateTab(original.tabId)!;
    const state = useTradingStore.getState();
    expect(state.tabs.map((tab) => tab.tabId)).toEqual([original.tabId, copyId]);
    const copy = state.tabs[1];
    expect(copy.name).toBe(`${original.name} copy`);
    expect(copy.charts[0].interval).toBe('15m');
    expect(copy.charts[0].chartId).not.toBe(original.charts[0].chartId);
    expect(state.activeTabId).toBe(copyId);
    const blankId = useTradingStore.getState().addBlankTab()!;
    const blank = useTradingStore.getState().tabs.find((tab) => tab.tabId === blankId)!;
    expect(blank.charts).toHaveLength(1);
    expect(blank.charts[0].interval).toBe('1h');
  });

  it('offers new, duplicate, reopen, a new window, saved layouts and tools from +', () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null);
    const onSelectWorkspace = vi.fn();
    const onOpenTool = vi.fn();
    const ui = () => {
      const state = useTradingStore.getState();
      return (
        <TradingSessionTabs
          tabs={state.tabs}
          activeTabId={state.activeTabId}
          canAdd
          getTabLabel={(tab) => tab.name}
          onSelect={state.setActiveTab}
          onClose={(tab) => state.removeTab(tab.tabId)}
          workspaceId="main"
          workspaces={[{ workspaceId: 'main', name: 'Main' }, { workspaceId: 'swing', name: 'Swing' }]}
          onSelectWorkspace={onSelectWorkspace}
          onOpenTool={onOpenTool}
        />
      );
    };
    const view = render(ui());
    fireEvent.click(screen.getByRole('button', { name: 'Create chart session tab' }));
    const launcher = screen.getByRole('menu', { name: 'New tab' });
    expect(within(launcher).getByRole('menuitem', { name: 'Reopen closed tab' })).toBeDisabled();
    expect(within(launcher).getByRole('menuitem', { name: 'Main (open)' })).toBeDisabled();
    fireEvent.click(within(launcher).getByRole('menuitem', { name: 'New chart tab' }));
    expect(useTradingStore.getState().tabs).toHaveLength(2);
    view.rerender(ui());
    fireEvent.click(screen.getByRole('button', { name: 'Create chart session tab' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Swing' }));
    expect(onSelectWorkspace).toHaveBeenCalledWith('swing');
    fireEvent.click(screen.getByRole('button', { name: 'Create chart session tab' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Screener' }));
    expect(onOpenTool).toHaveBeenCalledWith('scanner');
    fireEvent.click(screen.getByRole('button', { name: 'Create chart session tab' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Open this tab in a new window' }));
    expect(open).toHaveBeenCalledWith(expect.stringContaining(`workspace=main&tab=${useTradingStore.getState().activeTabId}`), '_blank', 'noopener');
    // Right-click a tab: duplicate it.
    const firstTab = screen.getAllByRole('button', { name: /^Open .* chart session$/ })[0].parentElement!;
    fireEvent.contextMenu(firstTab);
    fireEvent.click(screen.getByRole('menuitem', { name: 'Duplicate' }));
    expect(useTradingStore.getState().tabs).toHaveLength(3);
    // Escape closes a menu.
    view.rerender(ui());
    fireEvent.click(screen.getByRole('button', { name: 'Create chart session tab' }));
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('menu')).toBeNull();
  });
});

describe('time sync (TVP-4.2)', () => {
  it('scrolls the other charts to a clicked bar while the Time link is on', () => {
    const clicks: Array<(timeMs: number) => void> = [];
    const adapter = { onBarClick: (listener: (timeMs: number) => void) => { clicks.push(listener); return () => undefined; } };
    const goA = vi.fn();
    const goB = vi.fn();
    renderHook(() => useChartTimeSync('chart-a', adapter, goA));
    renderHook(() => useChartTimeSync('chart-b', null, goB));
    expect(clicks).toHaveLength(0);
    act(() => useTradingStore.getState().setLink('time', true));
    expect(clicks).toHaveLength(1);
    act(() => clicks[0](1_700_000_000_000));
    expect(goB).toHaveBeenCalledWith(1_700_000_000_000);
    expect(goA).not.toHaveBeenCalled();
    act(() => useTradingStore.getState().setLink('time', false));
    act(() => emitOmnixEvent('omnix:trading-time-sync', { sourceChartId: 'chart-a', timeMs: 1 }));
    expect(goB).toHaveBeenCalledTimes(1);
  });

  it('keeps the Time link in saved workspaces, and reads older ones without it', () => {
    const state = useTradingStore.getState();
    const payload = serializeTradingWorkspace({
      name: 'Main', layout: state.layout, activeChartId: state.activeChartId, charts: state.charts, links: { ...state.links, time: true },
      panels: state.panels, favoriteInstrumentIds: [], favoriteIntervals: [], activeTabId: state.activeTabId, tabs: state.tabs,
    });
    expect(parseTradingWorkspace(payload)?.links.time).toBe(true);
    const older = { ...payload, links: { instrument: false, interval: false, crosshair: true, visibleRange: false } };
    expect(parseTradingWorkspace(older)?.links.time).toBeUndefined();
    expect(parseTradingWorkspace({ ...payload, links: { ...payload.links, time: 'yes' } })).toBeNull();
  });
});

describe('workspace persistence across windows', () => {
  let records: TradingDocument[];
  const documentOf = (recordId: string, revision: number, tabName: string): TradingDocument => {
    const state = useTradingStore.getState();
    const tabs = state.tabs.map((tab) => ({ ...tab, name: tabName }));
    return {
      record_id: recordId,
      record_type: 'workspace',
      revision,
      status: 'active',
      updated_at: null,
      payload: serializeTradingWorkspace({
        name: recordId, layout: state.layout, activeChartId: state.activeChartId, charts: state.charts, links: state.links,
        panels: state.panels, favoriteInstrumentIds: [], favoriteIntervals: [], activeTabId: state.activeTabId, tabs,
      }) as unknown as Record<string, unknown>,
    };
  };

  beforeEach(() => {
    vi.spyOn(tradingDraftRecovery, 'load').mockResolvedValue(null);
    vi.spyOn(tradingDraftRecovery, 'save').mockResolvedValue(undefined);
    vi.spyOn(tradingDraftRecovery, 'clear').mockResolvedValue(undefined);
    records = [documentOf('main', 1, 'Main tab'), documentOf('swing', 4, 'Swing tab')];
    vi.spyOn(tradingApi, 'documents').mockImplementation(async () => records);
  });

  it('opens the workspace the window was opened on', async () => {
    window.history.replaceState(null, '', '/trading?workspace=swing');
    const { result } = renderHook(() => useTradingWorkspacePersistence());
    await waitFor(() => expect(result.current.status).toBe('saved'));
    expect(result.current.activeWorkspaceId).toBe('swing');
    expect(useTradingStore.getState().tabs[0].name).toBe('Swing tab');
  });

  it('reloads the workspace another window saved, unless it has edits of its own', async () => {
    const { result } = renderHook(() => useTradingWorkspacePersistence());
    await waitFor(() => expect(result.current.status).toBe('saved'));
    records = [documentOf('main', 2, 'Renamed elsewhere'), records[1]];
    act(() => tradingWindowPresence().receive({ type: 'saved', windowId: 'other', kind: 'workspace', id: 'main', revision: 2 }));
    await waitFor(() => expect(useTradingStore.getState().tabs[0].name).toBe('Renamed elsewhere'));
  });

  it('asks before leaving with unsaved edits', async () => {
    vi.spyOn(tradingApi, 'updateDocument').mockImplementation(() => new Promise(() => undefined));
    const { result } = renderHook(() => useTradingWorkspacePersistence());
    await waitFor(() => expect(result.current.status).toBe('saved'));
    const clean = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(clean);
    expect(clean.defaultPrevented).toBe(false);
    act(() => useTradingStore.getState().renameTab(useTradingStore.getState().activeTabId, 'Edited'));
    await waitFor(() => expect(result.current.status).toBe('draft'));
    const dirty = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(dirty);
    expect(dirty.defaultPrevented).toBe(true);
  });
});
