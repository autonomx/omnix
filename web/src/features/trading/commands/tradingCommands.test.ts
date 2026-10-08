import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import {
  TRADING_COMMANDS,
  findKeyConflicts,
  matchesHotkey,
  matchesKeyPattern,
  normalizeHotkey,
  resolveCommand,
  tradingCommandDefinition,
  type RegisteredCommand,
  type TradingCommandDefinition,
} from './tradingCommands';
import {
  canRunTradingCommand,
  runTradingCommand,
  setTradingCommandAvailability,
  setTradingCommandKeyOverrides,
  useTradingCommand,
  useTradingCommandDispatcher,
} from './useTradingCommands';
import { noteTradingPointerDown, resetTradingPointerContext } from './chartKeyContext';
import { formatCommandKeys, formatHotkey } from './hotkeyLabels';
import { watchlistKeyCommand } from '../useTradingWatchlistSelection';

function key(init: KeyboardEventInit, target?: EventTarget): KeyboardEvent {
  const event = new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...init });
  if (target) Object.defineProperty(event, 'target', { value: target });
  return event;
}

function command(definition: TradingCommandDefinition, active = true): RegisteredCommand & { run: ReturnType<typeof vi.fn> } {
  const run = vi.fn();
  return { definition, handler: { run, isActive: () => active }, run };
}

const chartUndo = tradingCommandDefinition('drawing.undo')!;

describe('trading command matching', () => {
  it('treats mod as Ctrl or Command and requires the exact modifiers', () => {
    expect(matchesHotkey('mod+z', key({ key: 'z', ctrlKey: true }))).toBe(true);
    expect(matchesHotkey('mod+z', key({ key: 'z', metaKey: true }))).toBe(true);
    expect(matchesHotkey('mod+z', key({ key: 'z', ctrlKey: true, shiftKey: true }))).toBe(false);
    expect(matchesHotkey('mod+z', key({ key: 'z', ctrlKey: true, altKey: true }))).toBe(false);
    expect(matchesHotkey('mod+shift+z', key({ key: 'Z', ctrlKey: true, shiftKey: true }))).toBe(true);
  });

  it('matches Alt shortcuts by physical key so macOS Option characters still work', () => {
    expect(matchesHotkey('alt+t', key({ key: '†', code: 'KeyT', altKey: true }))).toBe(true);
    expect(matchesHotkey('alt+t', key({ key: 't', code: 'KeyY', altKey: true }))).toBe(false);
  });

  it('normalizes modifier order for conflict detection', () => {
    expect(normalizeHotkey('Shift+Alt+B')).toBe('alt+shift+b');
    expect(normalizeHotkey('alt+shift+b')).toBe('alt+shift+b');
  });
});

describe('trading command resolution', () => {
  it('ignores key presses in text fields unless the command allows it', () => {
    const input = document.createElement('input');
    const undo = command(chartUndo);
    expect(resolveCommand([undo], key({ key: 'z', ctrlKey: true }, input))).toBeNull();
    const escape = command({ id: 'test.escape', label: 'Close', group: 'Test', scope: 'workspace', defaultKeys: ['escape'], allowInInputs: true });
    expect(resolveCommand([escape], key({ key: 'Escape' }, input))).toBe(escape);
  });

  it('skips inactive handlers and prefers the most specific scope', () => {
    const inactive = command(chartUndo, false);
    expect(resolveCommand([inactive], key({ key: 'z', ctrlKey: true }))).toBeNull();
    const workspace = command({ id: 'test.a', label: 'A', group: 'Test', scope: 'workspace', defaultKeys: ['delete'] });
    const drawing = command(tradingCommandDefinition('drawing.delete')!);
    expect(resolveCommand([drawing, workspace], key({ key: 'Delete' }))).toBe(drawing);
  });

  it('uses key overrides instead of the defaults', () => {
    const undo = command(chartUndo);
    const overrides = { 'drawing.undo': ['alt+u'] };
    expect(resolveCommand([undo], key({ key: 'z', ctrlKey: true }), overrides)).toBeNull();
    expect(resolveCommand([undo], key({ key: 'u', code: 'KeyU', altKey: true }), overrides)).toBe(undo);
  });

  it('has no conflicting default keys', () => {
    expect(findKeyConflicts(TRADING_COMMANDS)).toEqual([]);
    const conflicting = findKeyConflicts(TRADING_COMMANDS, { 'drawing.redo': ['mod+z'] });
    expect(conflicting).toEqual([{ hotkey: 'mod+z', scope: 'chart', ids: ['drawing.undo', 'drawing.redo'] }]);
  });
});

describe('trading command dispatcher', () => {
  it('runs a registered command once and stops after unmount', () => {
    const run = vi.fn();
    const dispatcher = renderHook(() => useTradingCommandDispatcher());
    const second = renderHook(() => useTradingCommandDispatcher());
    const binding = renderHook(() => useTradingCommand('drawing.undo', run));

    const event = key({ key: 'z', ctrlKey: true });
    window.dispatchEvent(event);
    expect(run).toHaveBeenCalledTimes(1);
    expect(event.defaultPrevented).toBe(true);

    binding.unmount();
    window.dispatchEvent(key({ key: 'z', ctrlKey: true }));
    expect(run).toHaveBeenCalledTimes(1);
    second.unmount();
    dispatcher.unmount();
  });

  it('does not handle events another handler already consumed, and honours overrides', () => {
    const run = vi.fn();
    const dispatcher = renderHook(() => useTradingCommandDispatcher());
    const binding = renderHook(() => useTradingCommand('drawing.undo', run));

    const consumed = key({ key: 'z', ctrlKey: true });
    consumed.preventDefault();
    window.dispatchEvent(consumed);
    expect(run).not.toHaveBeenCalled();

    setTradingCommandKeyOverrides({ 'drawing.undo': ['mod+u'] });
    window.dispatchEvent(key({ key: 'z', ctrlKey: true }));
    window.dispatchEvent(key({ key: 'u', ctrlKey: true }));
    expect(run).toHaveBeenCalledTimes(1);
    setTradingCommandKeyOverrides({});

    binding.unmount();
    dispatcher.unmount();
  });
});

afterEach(() => {
  resetTradingPointerContext();
  document.body.replaceChildren();
});

const symbolSearch = tradingCommandDefinition('chart.symbolSearch')!;
const intervalInput = tradingCommandDefinition('chart.intervalInput')!;
const moveLeft = tradingCommandDefinition('chart.moveLeft')!;

describe('typed-character commands (TVP-2.1)', () => {
  it('matches letters and interval characters without Ctrl, Command or Alt', () => {
    expect(matchesKeyPattern('letter', key({ key: 'a' }))).toBe(true);
    expect(matchesKeyPattern('letter', key({ key: 'A', shiftKey: true }))).toBe(true);
    expect(matchesKeyPattern('letter', key({ key: 'a', ctrlKey: true }))).toBe(false);
    expect(matchesKeyPattern('letter', key({ key: '5' }))).toBe(false);
    expect(matchesKeyPattern('interval', key({ key: '5' }))).toBe(true);
    expect(matchesKeyPattern('interval', key({ key: ',' }))).toBe(true);
    expect(matchesKeyPattern('interval', key({ key: '1', altKey: true }))).toBe(false);
  });

  it('lets a hotkey win over a typed-character pattern', () => {
    const letter = command(symbolSearch);
    const exact = command({ id: 'test.b', label: 'B', group: 'Test', scope: 'workspace', defaultKeys: ['b'] });
    expect(resolveCommand([exact, letter], key({ key: 'b' }))).toBe(exact);
    expect(resolveCommand([exact, letter], key({ key: 'c' }))).toBe(letter);
  });

  it('keeps pattern commands fixed even when an override names them', () => {
    const letter = command(symbolSearch);
    expect(resolveCommand([letter], key({ key: 'q' }), { 'chart.symbolSearch': ['mod+q'] })).toBe(letter);
  });
});

describe('where plain keys fire', () => {
  it('skips plain keys in widgets that navigate with them, but not modified keys', () => {
    const list = document.createElement('div');
    list.setAttribute('role', 'listbox');
    const option = document.createElement('div');
    list.append(option);
    document.body.append(list);
    expect(resolveCommand([command(intervalInput)], key({ key: '5' }, option))).toBeNull();
    const undo = command(chartUndo);
    expect(resolveCommand([undo], key({ key: 'z', ctrlKey: true }, option))).toBe(undo);
  });

  it('skips every command while a modal dialog is open, unless it allows inputs', () => {
    const dialog = document.createElement('section');
    dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('aria-modal', 'true');
    document.body.append(dialog);
    expect(resolveCommand([command(chartUndo)], key({ key: 'z', ctrlKey: true }, document.body))).toBeNull();
    const escape = command({ id: 'test.escape', label: 'Close', group: 'Test', scope: 'workspace', defaultKeys: ['escape'], allowInInputs: true });
    expect(resolveCommand([escape], key({ key: 'Escape' }, document.body))).toBe(escape);
  });

  it('fires chart keys only while the chart area has the keyboard', () => {
    const shell = document.createElement('section');
    shell.className = 'trading-chart-shell';
    const outside = document.createElement('aside');
    document.body.append(shell, outside);
    const left = command(moveLeft);
    expect(resolveCommand([left], key({ key: 'ArrowLeft' }, document.body))).toBe(left);
    noteTradingPointerDown(outside);
    expect(resolveCommand([left], key({ key: 'ArrowLeft' }, document.body))).toBeNull();
    noteTradingPointerDown(shell);
    expect(resolveCommand([left], key({ key: 'ArrowLeft' }, document.body))).toBe(left);
    const button = document.createElement('button');
    outside.append(button);
    button.focus();
    expect(resolveCommand([left], key({ key: 'ArrowLeft' }, button))).toBeNull();
  });
});

describe('running commands without keys', () => {
  it('runs the latest active registration and reports when none can run', () => {
    const first = vi.fn();
    const second = vi.fn();
    const one = renderHook(() => useTradingCommand('chart.reset', first));
    const two = renderHook(() => useTradingCommand('chart.reset', second, () => false));
    expect(runTradingCommand('chart.reset')).toBe(true);
    expect(first).toHaveBeenCalledWith(undefined);
    expect(second).not.toHaveBeenCalled();
    one.unmount();
    expect(canRunTradingCommand('chart.reset')).toBe(false);
    expect(runTradingCommand('chart.reset')).toBe(false);
    two.unmount();
  });
});

describe('hotkey labels', () => {
  it('formats keys for Windows and macOS', () => {
    expect(formatHotkey('mod+shift+z', false)).toBe('Ctrl+Shift+Z');
    expect(formatHotkey('mod+arrowleft', false)).toBe('Ctrl+←');
    expect(formatHotkey('alt+pagedown', true)).toBe('⌥+Page Down');
    expect(formatCommandKeys(symbolSearch, [], false)).toEqual(['A–Z']);
  });
});

describe('browser and installed-app keys (TVP-2.3)', () => {
  const newTab = tradingCommandDefinition('tab.new')!;

  it('uses TradingView keys the browser keeps only in the installed app', () => {
    const tab = command(newTab);
    expect(resolveCommand([tab], key({ key: 't', ctrlKey: true }))).toBeNull();
    expect(resolveCommand([tab], key({ key: 'T', code: 'KeyT', altKey: true, shiftKey: true }))).toBe(tab);
    expect(resolveCommand([tab], key({ key: 't', ctrlKey: true }), {}, 'installed')).toBe(tab);
    expect(resolveCommand([tab], key({ key: 'T', code: 'KeyT', altKey: true, shiftKey: true }), {}, 'installed')).toBe(tab);
  });

  it('has no conflicting default keys in either mode', () => {
    expect(findKeyConflicts(TRADING_COMMANDS, {}, 'browser')).toEqual([]);
    expect(findKeyConflicts(TRADING_COMMANDS, {}, 'installed')).toEqual([]);
  });

  it('switches the dispatcher to installed-app keys', () => {
    const run = vi.fn();
    const dispatcher = renderHook(() => useTradingCommandDispatcher());
    const binding = renderHook(() => useTradingCommand('tab.new', run));
    window.dispatchEvent(key({ key: 't', ctrlKey: true }));
    expect(run).not.toHaveBeenCalled();
    setTradingCommandAvailability('installed');
    window.dispatchEvent(key({ key: 't', ctrlKey: true }));
    expect(run).toHaveBeenCalledTimes(1);
    setTradingCommandAvailability('browser');
    binding.unmount();
    dispatcher.unmount();
  });

  it('matches Alt+digit by physical key', () => {
    expect(matchesHotkey('alt+1', key({ key: '¡', code: 'Digit1', altKey: true }))).toBe(true);
    expect(matchesHotkey('alt+1', key({ key: '2', code: 'Digit2', altKey: true }))).toBe(false);
  });
});

describe('watchlist grid keys (TVP-2.3)', () => {
  const ids = ['watchlist.next', 'watchlist.previous', 'watchlist.extendNext', 'watchlist.extendPrevious', 'watchlist.selectAll'];
  const expected: Record<string, string> = {
    'watchlist.next': 'next',
    'watchlist.previous': 'previous',
    'watchlist.extendNext': 'extendNext',
    'watchlist.extendPrevious': 'extendPrevious',
    'watchlist.selectAll': 'selectAll',
  };
  const eventFor = (hotkey: string) => {
    const parts = hotkey.split('+');
    const name = parts.at(-1)!;
    const keyName = ({ arrowdown: 'ArrowDown', arrowup: 'ArrowUp', space: ' ' } as Record<string, string>)[name] ?? name;
    return { key: keyName, shiftKey: parts.includes('shift'), ctrlKey: parts.includes('mod'), metaKey: false, altKey: false };
  };

  it('lists exactly the keys the watchlist grid reads, and never dispatches them', () => {
    for (const id of ids) {
      const definition = tradingCommandDefinition(id)!;
      expect(definition.handledLocally).toBe(true);
      for (const hotkey of definition.defaultKeys) expect(watchlistKeyCommand(eventFor(hotkey))).toBe(expected[id]);
      expect(resolveCommand([command(definition)], key(eventFor(definition.defaultKeys[0])))).toBeNull();
    }
  });
});
