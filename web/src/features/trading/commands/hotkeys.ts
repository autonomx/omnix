/**
 * Hotkey strings: parsing, matching key events, and recording key presses.
 *
 * One rule decides which key a hotkey names, for both recording and matching:
 * - with Alt held, the physical key (`event.code`), because macOS Option and
 *   AltGr change the typed character (Option+T types "†");
 * - otherwise the typed character (`event.key`), so Ctrl+Z is the key that
 *   types "z" on QWERTY, QWERTZ and AZERTY alike.
 * For typed characters other than letters (digits and punctuation such as
 * `/`, `.` or `!`), Shift is part of producing the character, so it is
 * neither recorded nor checked: `/` is Shift+7 on QWERTZ, and the digit row
 * needs Shift on AZERTY.
 *
 * Hotkey strings look like Mantine's (`mod+shift+z`, `alt+1`, `/`). `mod` is
 * Ctrl on Windows/Linux and ⌘ on macOS; `plus` names the + key.
 */

export type ParsedHotkey = { mod: boolean; ctrl: boolean; meta: boolean; alt: boolean; shift: boolean; key: string };

const MODIFIERS = ['mod', 'ctrl', 'meta', 'alt', 'shift'];

const KEY_ALIASES: Record<string, string> = {
  '[plus]': 'plus',
  esc: 'escape',
  spacebar: 'space',
  slash: '/',
  period: '.',
  comma: ',',
  left: 'arrowleft',
  right: 'arrowright',
  up: 'arrowup',
  down: 'arrowdown',
  del: 'delete',
};

/** Digits and punctuation: keys whose character already says whether Shift was needed. */
export function isCharacterKey(key: string): boolean {
  return key === 'plus' || (key.length === 1 && !/[a-z]/.test(key));
}

export function parseHotkey(hotkey: string): ParsedHotkey {
  const parts = hotkey.toLowerCase().split('+').map((part) => part.trim());
  const rawKey = parts.find((part) => part !== '' && !MODIFIERS.includes(part)) ?? (parts.at(-1) === '' ? 'plus' : '');
  const key = KEY_ALIASES[rawKey] ?? rawKey;
  const alt = parts.includes('alt');
  return {
    mod: parts.includes('mod'),
    ctrl: parts.includes('ctrl'),
    meta: parts.includes('meta'),
    alt,
    shift: parts.includes('shift') && (alt || !isCharacterKey(key)),
    key,
  };
}

export function normalizeHotkey(hotkey: string): string {
  const parsed = parseHotkey(hotkey);
  const modifiers = MODIFIERS.filter((modifier) => parsed[modifier as keyof Omit<ParsedHotkey, 'key'>]);
  return [...modifiers, parsed.key].join('+');
}

/** No Ctrl, ⌘ or Alt (Shift alone still types). */
export function isPlainHotkey(hotkey: string): boolean {
  const parsed = parseHotkey(hotkey);
  return !parsed.mod && !parsed.ctrl && !parsed.meta && !parsed.alt;
}

const TYPED_KEY_NAMES: Record<string, string> = { ' ': 'space', '+': 'plus' };

function typedKeyName(key: string): string {
  const name = TYPED_KEY_NAMES[key] ?? key.toLowerCase();
  return KEY_ALIASES[name] ?? name;
}

const CODE_NAMES: Record<string, string> = {
  Period: '.', Comma: ',', Slash: '/', Semicolon: ';', Quote: "'", BracketLeft: '[', BracketRight: ']',
  Backslash: '\\', Backquote: '`', Minus: '-', Equal: '=', Space: 'space', NumpadEnter: 'enter',
};

function physicalKeyName(code: string): string {
  const letter = /^Key([A-Z])$/.exec(code)?.[1];
  if (letter) return letter.toLowerCase();
  const digit = /^(?:Digit|Numpad)(\d)$/.exec(code)?.[1];
  if (digit) return digit;
  return CODE_NAMES[code] ?? code.toLowerCase();
}

type KeyLike = Pick<KeyboardEvent, 'key' | 'code' | 'ctrlKey' | 'metaKey' | 'altKey' | 'shiftKey'>;

function eventKeyName(event: KeyLike, physical: boolean): string {
  return physical && event.code ? physicalKeyName(event.code) : typedKeyName(event.key ?? '');
}

/** True when the event is exactly this hotkey (see the rule at the top of this file). */
export function matchesHotkey(hotkey: string, event: KeyLike): boolean {
  const parsed = parseHotkey(hotkey);
  if (parsed.alt !== event.altKey) return false;
  if (parsed.mod) {
    if (!event.ctrlKey && !event.metaKey) return false;
  } else if (parsed.ctrl !== event.ctrlKey || parsed.meta !== event.metaKey) {
    return false;
  }
  if (eventKeyName(event, parsed.alt) !== parsed.key) return false;
  return (!parsed.alt && isCharacterKey(parsed.key)) || parsed.shift === event.shiftKey;
}

const MODIFIER_KEYS = new Set(['Shift', 'Control', 'Alt', 'Meta', 'AltGraph', 'OS', 'Hyper', 'Super', 'CapsLock', 'Fn']);

/** The hotkey a key press records, by the same rule `matchesHotkey` uses. Null for a lone modifier or a dead key. */
export function hotkeyFromEvent(event: KeyLike): string | null {
  if (MODIFIER_KEYS.has(event.key)) return null;
  const key = eventKeyName(event, event.altKey);
  if (!key || ['unidentified', 'dead', 'process'].includes(key)) return null;
  const modifiers = [
    event.ctrlKey || event.metaKey ? 'mod' : null,
    event.altKey ? 'alt' : null,
    event.shiftKey ? 'shift' : null,
  ].filter((modifier): modifier is string => modifier !== null);
  return normalizeHotkey([...modifiers, key === 'plus' ? '[plus]' : key].join('+'));
}

/** Keys browsers keep for themselves: a page never receives them, so they only work in the installed app. */
const BROWSER_RESERVED = new Set([
  'mod+t', 'mod+w', 'mod+n', 'mod+shift+t', 'mod+shift+w', 'mod+shift+n', 'mod+tab', 'mod+shift+tab', 'mod+pageup', 'mod+pagedown',
  'mod+1', 'mod+2', 'mod+3', 'mod+4', 'mod+5', 'mod+6', 'mod+7', 'mod+8', 'mod+9',
]);

export function isBrowserReservedHotkey(hotkey: string): boolean {
  return BROWSER_RESERVED.has(normalizeHotkey(hotkey));
}
