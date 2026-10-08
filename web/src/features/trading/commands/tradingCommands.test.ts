import { describe, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import {
  TRADING_COMMANDS,
  findKeyConflicts,
  matchesHotkey,
  normalizeHotkey,
  resolveCommand,
  tradingCommandDefinition,
  type RegisteredCommand,
  type TradingCommandDefinition,
} from './tradingCommands';
import { setTradingCommandKeyOverrides, useTradingCommand, useTradingCommandDispatcher } from './useTradingCommands';

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
