import { useQuery } from '@tanstack/react-query';
import { useMemo, useRef, useState } from 'react';
import { tradingApi } from '../tradingApi';
import { isIntervalAvailable, TRADING_VIEW_INTERVAL_GROUPS } from '../tradingIntervals';
import { useTradingStore, type TradingTabState } from '../tradingStore';
import type { TradingWorkspacePersistence } from '../persistence/useTradingWorkspacePersistence';
import { formatCommandKeys } from './hotkeyLabels';
import { TRADING_COMMANDS, commandKeys } from './tradingCommands';
import { TradingCommandPalette, type TradingPaletteItem } from './TradingCommandPalette';
import { TradingIntervalInputBox } from './TradingIntervalInputBox';
import { useTradingTabCommands } from './useTradingTabCommands';
import {
  canRunTradingCommand,
  runTradingCommand,
  tradingCommandKeyOverrides,
  useTradingCommand,
} from './useTradingCommands';

type PaletteMode = 'all' | 'layouts';

function restoreFocus(element: Element | null): void {
  if (element instanceof HTMLElement && element.isConnected) element.focus();
}

/**
 * Workspace keyboard commands and the surfaces they open: the command
 * palette (Ctrl+K), the layout list (.) and the interval box (digits), plus
 * the tab and chart-switching commands.
 */
export function TradingKeyboardLayer({
  persistence,
  supportedIntervals,
  onOpenSymbolSearch,
  onCloseTab,
}: {
  persistence: Pick<TradingWorkspacePersistence, 'status' | 'workspaces' | 'activeWorkspaceId' | 'selectWorkspace' | 'saveNow'>;
  supportedIntervals: readonly string[];
  onOpenSymbolSearch: (typed?: string) => void;
  /** The workspace's close-tab action, which asks before closing. */
  onCloseTab: (tab: TradingTabState) => void;
}) {
  const [paletteMode, setPaletteMode] = useState<PaletteMode | null>(null);
  const [intervalText, setIntervalText] = useState<string | null>(null);
  const focusBeforeRef = useRef<Element | null>(null);
  const instruments = useQuery({ queryKey: ['trading', 'instruments'], queryFn: () => tradingApi.instruments() });
  const updateChart = useTradingStore((state) => state.updateChart);
  const activeChartId = useTradingStore((state) => state.activeChartId);
  const workspaceReady = persistence.status !== 'loading';

  const openPalette = (mode: PaletteMode) => {
    focusBeforeRef.current = document.activeElement;
    setPaletteMode(mode);
  };
  const closePalette = () => {
    setPaletteMode(null);
    restoreFocus(focusBeforeRef.current);
  };

  useTradingCommand('chart.symbolSearch', (event) => onOpenSymbolSearch(event?.key));
  useTradingCommand('chart.intervalInput', (event) => {
    focusBeforeRef.current = document.activeElement;
    setIntervalText(event && event.key !== ',' ? event.key : '');
  });
  useTradingCommand('workspace.commandPalette', () => openPalette('all'));
  useTradingCommand('layout.load', () => openPalette('layouts'), () => workspaceReady);
  useTradingCommand('layout.save', () => void persistence.saveNow(), () => workspaceReady);
  useTradingTabCommands(onCloseTab);

  const layoutItems = useMemo<TradingPaletteItem[]>(() => persistence.workspaces.map((workspace) => ({
    id: `layout:${workspace.workspaceId}`,
    label: workspace.workspaceId === persistence.activeWorkspaceId ? `${workspace.name} (open)` : workspace.name,
    group: 'Layout',
    run: () => void persistence.selectWorkspace(workspace.workspaceId),
  })), [persistence]);

  const paletteItems = useMemo<TradingPaletteItem[]>(() => {
    if (paletteMode !== 'all') return [];
    const overrides = tradingCommandKeyOverrides();
    const commands = TRADING_COMMANDS
      .filter((definition) => definition.id !== 'workspace.commandPalette')
      .map((definition) => ({
        id: `command:${definition.id}`,
        label: definition.label,
        group: definition.group,
        keys: formatCommandKeys(definition, commandKeys(definition, overrides)),
        disabled: !canRunTradingCommand(definition.id),
        run: () => { runTradingCommand(definition.id); },
      }));
    const intervals = TRADING_VIEW_INTERVAL_GROUPS.flatMap((group) => group.options)
      .filter((option) => isIntervalAvailable(option.value, supportedIntervals))
      .map((option) => ({
        id: `interval:${option.value}`,
        label: `Interval ${option.label}`,
        group: 'Interval',
        run: () => updateChart(activeChartId, { interval: option.value }),
      }));
    const symbols = (instruments.data ?? [])
      .filter((instrument) => instrument.asset_class !== 'crypto' || instrument.venue === 'BINANCE')
      .map((instrument) => ({
        id: `symbol:${instrument.instrument_id}`,
        label: `${instrument.display_symbol} · ${instrument.venue}`,
        group: 'Symbol',
        run: () => updateChart(activeChartId, { instrumentId: instrument.instrument_id, bindingId: null }),
      }));
    return [...commands, ...layoutItems.map((item) => ({ ...item, label: `Load layout ${item.label}` })), ...intervals, ...symbols];
  }, [activeChartId, instruments.data, layoutItems, paletteMode, supportedIntervals, updateChart]);

  return (
    <>
      <TradingCommandPalette
        open={paletteMode !== null}
        title={paletteMode === 'layouts' ? 'Load layout' : 'Command palette'}
        placeholder={paletteMode === 'layouts' ? 'Search layouts' : 'Search commands, symbols, intervals and layouts'}
        items={paletteMode === 'layouts' ? layoutItems : paletteItems}
        onClose={closePalette}
      />
      <TradingIntervalInputBox
        initialText={intervalText}
        supportedIntervals={supportedIntervals}
        onApply={(interval) => updateChart(activeChartId, { interval })}
        onClose={() => { setIntervalText(null); restoreFocus(focusBeforeRef.current); }}
      />
    </>
  );
}
