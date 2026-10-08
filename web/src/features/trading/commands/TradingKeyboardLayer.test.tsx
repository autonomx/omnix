import { act, fireEvent, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '../../../test/renderWithProviders';
import { tradingApi } from '../tradingApi';
import { useTradingStore } from '../tradingStore';
import type { CanonicalInstrument } from '../tradingTypes';
import { TradingKeyboardLayer } from './TradingKeyboardLayer';
import { useTradingCommandDispatcher } from './useTradingCommands';

const initialStore = useTradingStore.getState();

const bitcoin = {
  instrument_id: 'crypto:BINANCE:spot:BTC-USDT',
  asset_class: 'crypto',
  instrument_type: 'spot',
  venue: 'BINANCE',
  venue_symbol: 'BTCUSDT',
  display_symbol: 'BTC/USDT',
} as CanonicalInstrument;

function Harness(props: Parameters<typeof TradingKeyboardLayer>[0]) {
  useTradingCommandDispatcher();
  return <TradingKeyboardLayer {...props} />;
}

function setup() {
  const persistence = {
    status: 'saved' as const,
    workspaces: [
      { workspaceId: 'main', name: 'Main Workspace', revision: 1 },
      { workspaceId: 'swing', name: 'Swing setups', revision: 1 },
    ],
    activeWorkspaceId: 'main',
    selectWorkspace: vi.fn(async () => undefined),
    saveNow: vi.fn(async () => undefined),
  };
  const onOpenSymbolSearch = vi.fn();
  renderWithProviders(
    <Harness persistence={persistence} supportedIntervals={['1m', '1h', '4h', '1d']} onOpenSymbolSearch={onOpenSymbolSearch} />,
  );
  return { persistence, onOpenSymbolSearch };
}

const press = (init: KeyboardEventInit, target: Element = document.body) => act(() => { fireEvent.keyDown(target, init); });

beforeEach(() => {
  vi.spyOn(tradingApi, 'instruments').mockResolvedValue([bitcoin]);
});

afterEach(() => {
  vi.restoreAllMocks();
  act(() => useTradingStore.setState(initialStore, true));
});

describe('chart typing shortcuts (TVP-2.1)', () => {
  it('opens symbol search with the typed letter', () => {
    const { onOpenSymbolSearch } = setup();
    press({ key: 'b' });
    expect(onOpenSymbolSearch).toHaveBeenCalledWith('b');
  });

  it('ignores typing in text fields', () => {
    const { onOpenSymbolSearch } = setup();
    const input = document.createElement('input');
    document.body.append(input);
    press({ key: 'b' }, input);
    press({ key: '5' }, input);
    expect(onOpenSymbolSearch).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog', { name: 'Change interval' })).not.toBeInTheDocument();
    input.remove();
  });

  it('opens the interval box with the typed digit and applies a valid interval', () => {
    setup();
    press({ key: '1' });
    const box = screen.getByRole('textbox', { name: 'Interval' });
    expect(box).toHaveValue('1');
    expect(box).toHaveFocus();
    fireEvent.change(box, { target: { value: '5s' } });
    fireEvent.keyDown(box, { key: 'Enter' });
    expect(screen.getByRole('alert')).toHaveTextContent("doesn't support 5s");
    fireEvent.change(box, { target: { value: '4h' } });
    fireEvent.keyDown(box, { key: 'Enter' });
    expect(screen.queryByRole('textbox', { name: 'Interval' })).not.toBeInTheDocument();
    expect(useTradingStore.getState().charts[0].interval).toBe('4h');
  });

  it('opens an empty interval box with a comma and rejects unknown text', () => {
    setup();
    press({ key: ',' });
    const box = screen.getByRole('textbox', { name: 'Interval' });
    expect(box).toHaveValue('');
    fireEvent.change(box, { target: { value: '7q' } });
    fireEvent.keyDown(box, { key: 'Enter' });
    expect(screen.getByRole('alert')).toHaveTextContent('not an interval');
    fireEvent.keyDown(box, { key: 'Escape' });
    expect(screen.queryByRole('textbox', { name: 'Interval' })).not.toBeInTheDocument();
  });
});

describe('command palette and layouts (TVP-2.1)', () => {
  it('lists catalogued commands with their keys and runs quick actions', async () => {
    setup();
    press({ key: 'k', ctrlKey: true });
    const input = screen.getByRole('combobox', { name: 'Command palette' });
    expect(screen.getByRole('option', { name: /Reset chart view.*not available now.*Alt\+R/ })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /Load layout Swing setups/ })).toBeInTheDocument();
    fireEvent.change(input, { target: { value: 'interval 4 hours' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(useTradingStore.getState().charts[0].interval).toBe('4h');

    press({ key: 'k', ctrlKey: true });
    fireEvent.change(screen.getByRole('combobox', { name: 'Command palette' }), { target: { value: 'btc' } });
    expect(await screen.findByRole('option', { name: /BTC\/USDT · BINANCE/ })).toBeInTheDocument();
  });

  it('opens the layout list with a full stop and saves with Ctrl+S', () => {
    const { persistence } = setup();
    press({ key: '.' });
    const input = screen.getByRole('combobox', { name: 'Load layout' });
    fireEvent.change(input, { target: { value: 'swing' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(persistence.selectWorkspace).toHaveBeenCalledWith('swing');
    press({ key: 's', ctrlKey: true });
    expect(persistence.saveNow).toHaveBeenCalledTimes(1);
  });
});
