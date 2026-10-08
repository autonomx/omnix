import type { TradingCommandDefinition } from './tradingCommands';

export function isMacPlatform(): boolean {
  if (typeof navigator === 'undefined') return false;
  return /mac|iphone|ipad/i.test(navigator.platform || navigator.userAgent);
}

const KEY_LABELS: Record<string, string> = {
  arrowleft: '←',
  arrowright: '→',
  arrowup: '↑',
  arrowdown: '↓',
  pageup: 'Page Up',
  pagedown: 'Page Down',
  enter: 'Enter',
  tab: 'Tab',
  space: 'Space',
  delete: 'Delete',
  backspace: 'Backspace',
  escape: 'Esc',
  '[plus]': '+',
  slash: '/',
};

/** A hotkey string as people read it: `mod+shift+z` is "Ctrl+Shift+Z" (or "⌘+⇧+Z" on macOS). */
export function formatHotkey(hotkey: string, mac = isMacPlatform()): string {
  const modifierLabels: Record<string, string> = mac
    ? { mod: '⌘', ctrl: '⌃', meta: '⌘', alt: '⌥', shift: '⇧' }
    : { mod: 'Ctrl', ctrl: 'Ctrl', meta: 'Win', alt: 'Alt', shift: 'Shift' };
  return hotkey.toLowerCase().split('+').map((part) => part.trim()).map((part) => (
    modifierLabels[part] ?? KEY_LABELS[part] ?? part.toUpperCase()
  )).join('+');
}

/** The keys a command lists, including typed-character patterns. */
export function formatCommandKeys(definition: TradingCommandDefinition, keys: readonly string[], mac = isMacPlatform()): string[] {
  if (definition.keyPattern === 'letter') return ['A–Z'];
  if (definition.keyPattern === 'interval') return ['0–9', ','];
  return keys.map((hotkey) => formatHotkey(hotkey, mac));
}

const MODIFIER_KEYS = new Set(['Shift', 'Control', 'Alt', 'Meta', 'AltGraph', 'OS']);

const EVENT_KEY_NAMES: Record<string, string> = {
  ' ': 'space',
  '+': '[plus]',
  Esc: 'escape',
};

/**
 * The hotkey string for a key press, for rebinding. Ctrl and ⌘ both become
 * `mod`. Letters and digits come from the physical key, so Shift+1 is
 * `shift+1` and macOS Option+T is `alt+t`. Returns null for a lone modifier.
 */
export function hotkeyFromEvent(event: Pick<KeyboardEvent, 'key' | 'code' | 'ctrlKey' | 'metaKey' | 'altKey' | 'shiftKey'>): string | null {
  if (MODIFIER_KEYS.has(event.key)) return null;
  const physical = /^Key([A-Z])$/.exec(event.code ?? '')?.[1] ?? /^Digit(\d)$/.exec(event.code ?? '')?.[1];
  const key = physical?.toLowerCase() ?? EVENT_KEY_NAMES[event.key] ?? event.key.toLowerCase();
  if (!key || key === 'unidentified' || key === 'dead') return null;
  const modifiers = [
    event.ctrlKey || event.metaKey ? 'mod' : null,
    event.altKey ? 'alt' : null,
    event.shiftKey ? 'shift' : null,
  ].filter((modifier): modifier is string => modifier !== null);
  return [...modifiers, key].join('+');
}

/** Keys browsers keep for themselves: a page never receives them, so they only work in the installed app. */
const BROWSER_RESERVED = new Set([
  'mod+t', 'mod+w', 'mod+n', 'mod+shift+t', 'mod+shift+w', 'mod+shift+n', 'mod+tab', 'mod+shift+tab', 'mod+pageup', 'mod+pagedown',
  'mod+1', 'mod+2', 'mod+3', 'mod+4', 'mod+5', 'mod+6', 'mod+7', 'mod+8', 'mod+9',
]);

export function isBrowserReservedHotkey(normalizedHotkey: string): boolean {
  return BROWSER_RESERVED.has(normalizedHotkey);
}
