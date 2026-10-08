import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { hotkeyFromEvent } from './hotkeyLabels';
import { KEY_OVERRIDES_STORAGE_KEY, loadStoredKeyOverrides, sanitizeKeyOverrides } from './keyOverridesStorage';
import { TradingShortcutDialog } from './TradingShortcutDialog';
import { setTradingCommandAvailability, setTradingCommandKeyOverrides, tradingCommandKeyOverrides } from './useTradingCommands';

afterEach(() => {
  act(() => {
    setTradingCommandKeyOverrides({});
    setTradingCommandAvailability('browser');
  });
  window.localStorage.clear();
});

const row = (label: string) => screen.getByRole('rowheader', { name: new RegExp(`^${label}`) }).closest('tr') as HTMLElement;

function capture(label: string, init: KeyboardEventInit) {
  fireEvent.click(screen.getByRole('button', { name: `Change keys for ${label}` }));
  const button = screen.getByRole('button', { name: `Press new keys for ${label}` });
  expect(button).toHaveTextContent('Press keys…');
  fireEvent.keyDown(button, init);
}

describe('TradingShortcutDialog (TVP-2.4)', () => {
  it('lists every command by context and filters by name, context or key', () => {
    render(<TradingShortcutDialog open onClose={() => undefined} />);
    for (const group of ['General', 'Chart', 'Drawings', 'Layout', 'Watchlist', 'Tabs']) {
      expect(screen.getByRole('heading', { name: group })).toBeInTheDocument();
    }
    expect(within(row('Reset chart view')).getByText('Alt+R')).toBeInTheDocument();
    expect(within(row('New tab')).getByText('Alt+Shift+T')).toBeInTheDocument();
    expect(within(row('New tab')).getByText('Ctrl+T · app')).toBeInTheDocument();
    expect(within(row('Next symbol')).getByText('Watchlist grid')).toBeInTheDocument();
    expect(within(row('Change symbol')).getByText('Fixed')).toBeInTheDocument();

    fireEvent.change(screen.getByRole('searchbox', { name: 'Search shortcuts' }), { target: { value: 'zoom' } });
    expect(screen.getAllByRole('rowheader').map((header) => header.textContent)).toEqual(['Zoom in', 'Zoom out']);
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search shortcuts' }), { target: { value: 'alt+9' } });
    expect(screen.getAllByRole('rowheader')).toHaveLength(1);
  });

  it('rebinds a command, saves it and resets it', () => {
    render(<TradingShortcutDialog open onClose={() => undefined} />);
    capture('Reset chart view', { key: '≈', code: 'KeyX', altKey: true });
    expect(within(row('Reset chart view')).getByText('Alt+X')).toBeInTheDocument();
    expect(tradingCommandKeyOverrides()).toEqual({ 'chart.reset': ['alt+x'] });
    expect(JSON.parse(window.localStorage.getItem(KEY_OVERRIDES_STORAGE_KEY)!)).toEqual({ 'chart.reset': ['alt+x'] });
    expect(loadStoredKeyOverrides()).toEqual({ 'chart.reset': ['alt+x'] });

    fireEvent.click(screen.getByRole('button', { name: 'Reset Reset chart view' }));
    expect(within(row('Reset chart view')).getByText('Alt+R')).toBeInTheDocument();
    expect(window.localStorage.getItem(KEY_OVERRIDES_STORAGE_KEY)).toBeNull();
  });

  it('shows conflicts and clears every change with Reset all', () => {
    render(<TradingShortcutDialog open onClose={() => undefined} />);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    capture('Zoom in', { key: 'ArrowDown', code: 'ArrowDown', ctrlKey: true });
    expect(screen.getByRole('alert')).toHaveTextContent('1 key is used by more than one command');
    expect(within(row('Zoom in')).getByText('Same key as Zoom out')).toBeInTheDocument();
    expect(within(row('Zoom out')).getByText('Same key as Zoom in')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Reset all' }));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(tradingCommandKeyOverrides()).toEqual({});
    expect(screen.getByRole('button', { name: 'Reset all' })).toBeDisabled();
  });

  it('cancels with Escape, ignores lone modifiers and warns about browser keys', () => {
    render(<TradingShortcutDialog open onClose={() => undefined} />);
    capture('Save layout (workspace)', { key: 'Control', code: 'ControlLeft', ctrlKey: true });
    const waiting = screen.getByRole('button', { name: 'Press new keys for Save layout (workspace)' });
    fireEvent.keyDown(waiting, { key: 'Escape' });
    expect(screen.getByRole('button', { name: 'Change keys for Save layout (workspace)' })).toBeInTheDocument();
    expect(tradingCommandKeyOverrides()).toEqual({});

    capture('Save layout (workspace)', { key: 't', code: 'KeyT', ctrlKey: true });
    expect(screen.getByRole('status')).toHaveTextContent('only works in the installed app');
  });

  it('closes with Escape outside a key capture', () => {
    let closed = false;
    render(<TradingShortcutDialog open onClose={() => { closed = true; }} />);
    fireEvent.keyDown(screen.getByRole('searchbox', { name: 'Search shortcuts' }), { key: 'Escape' });
    expect(closed).toBe(true);
  });
});

describe('stored key overrides', () => {
  it('keeps only known, rebindable commands and survives bad storage', () => {
    expect(sanitizeKeyOverrides({
      'chart.reset': ['Alt+X', 'alt+x', 7],
      'chart.symbolSearch': ['mod+q'],
      'watchlist.next': ['j'],
      'nope.command': ['mod+j'],
      'layout.save': 'mod+e',
    })).toEqual({ 'chart.reset': ['alt+x'] });
    window.localStorage.setItem(KEY_OVERRIDES_STORAGE_KEY, '{not json');
    expect(loadStoredKeyOverrides()).toEqual({});
  });

  it('turns key presses into hotkey strings', () => {
    expect(hotkeyFromEvent({ key: 'K', code: 'KeyK', ctrlKey: true, metaKey: false, altKey: false, shiftKey: true })).toBe('mod+shift+k');
    expect(hotkeyFromEvent({ key: '†', code: 'KeyT', ctrlKey: false, metaKey: false, altKey: true, shiftKey: false })).toBe('alt+t');
    expect(hotkeyFromEvent({ key: '!', code: 'Digit1', ctrlKey: false, metaKey: false, altKey: false, shiftKey: true })).toBe('shift+1');
    expect(hotkeyFromEvent({ key: 'ArrowLeft', code: 'ArrowLeft', ctrlKey: false, metaKey: true, altKey: false, shiftKey: false })).toBe('mod+arrowleft');
    expect(hotkeyFromEvent({ key: 'Shift', code: 'ShiftLeft', ctrlKey: false, metaKey: false, altKey: false, shiftKey: true })).toBeNull();
  });
});
