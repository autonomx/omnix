import { getHotkeyHandler } from '@mantine/hooks';
import { chartKeyContextActive, type ChartKeyContext } from './chartKeyContext';

/** Where a command applies. When one key matches in several scopes, the most specific scope wins. */
export type CommandScope = 'workspace' | 'chart' | 'watchlist' | 'drawing';

const SCOPE_PRIORITY: Record<CommandScope, number> = { workspace: 0, chart: 1, watchlist: 2, drawing: 3 };

/** Keys matched by a pattern rather than a hotkey string. Pattern keys can't be rebound. */
export type CommandKeyPattern = 'letter' | 'interval';

export type TradingCommandDefinition = {
  id: string;
  label: string;
  group: string;
  scope: CommandScope;
  /** Mantine hotkey strings, e.g. `mod+z`, `alt+t`, `shift+alt+b`. `mod` is Ctrl on Windows/Linux and ⌘ on macOS. */
  defaultKeys: readonly string[];
  /** Runs even while a text field has focus (for keys such as Escape). */
  allowInInputs?: boolean;
  /** Matches typed characters instead of hotkeys: `letter` is A–Z, `interval` is 0–9 and comma. */
  keyPattern?: CommandKeyPattern;
  /** The keys only fire while the chart area has the keyboard (see `chartKeyContext`). */
  keyContext?: ChartKeyContext;
};

export type TradingCommandHandler = {
  /** The key event, or nothing when the command palette runs the command. */
  run: (event?: KeyboardEvent) => void;
  isActive: () => boolean;
};

export type KeyOverrides = Readonly<Record<string, readonly string[]>>;

export const TRADING_COMMANDS = [
  // Chart (TVP-2.1)
  { id: 'chart.symbolSearch', label: 'Change symbol (type a letter)', group: 'Chart', scope: 'chart', defaultKeys: [], keyPattern: 'letter', keyContext: 'chart' },
  { id: 'chart.intervalInput', label: 'Change interval (type a number or comma)', group: 'Chart', scope: 'chart', defaultKeys: [], keyPattern: 'interval', keyContext: 'chart' },
  { id: 'chart.indicators', label: 'Open indicators', group: 'Chart', scope: 'chart', defaultKeys: ['/'] },
  { id: 'chart.moveLeft', label: 'Move chart one bar left', group: 'Chart', scope: 'chart', defaultKeys: ['arrowleft'], keyContext: 'chart' },
  { id: 'chart.moveRight', label: 'Move chart one bar right', group: 'Chart', scope: 'chart', defaultKeys: ['arrowright'], keyContext: 'chart' },
  { id: 'chart.moveFurtherLeft', label: 'Move chart further left', group: 'Chart', scope: 'chart', defaultKeys: ['mod+arrowleft'], keyContext: 'chart' },
  { id: 'chart.moveFurtherRight', label: 'Move chart further right', group: 'Chart', scope: 'chart', defaultKeys: ['mod+arrowright'], keyContext: 'chart' },
  { id: 'chart.zoomIn', label: 'Zoom in', group: 'Chart', scope: 'chart', defaultKeys: ['mod+arrowup'], keyContext: 'chart' },
  { id: 'chart.zoomOut', label: 'Zoom out', group: 'Chart', scope: 'chart', defaultKeys: ['mod+arrowdown'], keyContext: 'chart' },
  { id: 'chart.reset', label: 'Reset chart view', group: 'Chart', scope: 'chart', defaultKeys: ['alt+r'] },
  { id: 'chart.invertScale', label: 'Invert price scale', group: 'Chart', scope: 'chart', defaultKeys: ['alt+i'] },
  { id: 'chart.logScale', label: 'Logarithmic price scale', group: 'Chart', scope: 'chart', defaultKeys: ['alt+l'] },
  { id: 'chart.percentScale', label: 'Percent price scale', group: 'Chart', scope: 'chart', defaultKeys: ['alt+p'] },
  { id: 'chart.snapshot', label: 'Chart snapshot (download PNG)', group: 'Chart', scope: 'chart', defaultKeys: ['alt+s'] },
  { id: 'chart.goToDate', label: 'Go to date', group: 'Chart', scope: 'chart', defaultKeys: ['alt+g'] },
  // Drawings
  { id: 'drawing.undo', label: 'Undo drawing change', group: 'Drawings', scope: 'chart', defaultKeys: ['mod+z'] },
  { id: 'drawing.redo', label: 'Redo drawing change', group: 'Drawings', scope: 'chart', defaultKeys: ['mod+shift+z', 'mod+y'] },
  { id: 'drawing.delete', label: 'Delete selected drawing', group: 'Drawings', scope: 'drawing', defaultKeys: ['delete', 'backspace'] },
  // General and layouts. Omnix calls a saved TradingView layout a workspace.
  { id: 'workspace.commandPalette', label: 'Open command palette', group: 'General', scope: 'workspace', defaultKeys: ['mod+k'] },
  { id: 'layout.save', label: 'Save layout (workspace)', group: 'Layout', scope: 'workspace', defaultKeys: ['mod+s'] },
  { id: 'layout.load', label: 'Load layout (workspace)', group: 'Layout', scope: 'workspace', defaultKeys: ['.'] },
] as const satisfies readonly TradingCommandDefinition[];

export type TradingCommandId = typeof TRADING_COMMANDS[number]['id'];

const definitionsById = new Map<string, TradingCommandDefinition>(TRADING_COMMANDS.map((command) => [command.id, command]));

export function tradingCommandDefinition(id: string): TradingCommandDefinition | undefined {
  return definitionsById.get(id);
}

/** Pattern keys are fixed; every other command can be rebound. */
export function isRebindable(definition: TradingCommandDefinition): boolean {
  return !definition.keyPattern;
}

export function commandKeys(definition: TradingCommandDefinition, overrides: KeyOverrides = {}): readonly string[] {
  return (isRebindable(definition) ? overrides[definition.id] : undefined) ?? definition.defaultKeys;
}

function hotkeyParts(hotkey: string): string[] {
  return hotkey.toLowerCase().split('+').map((part) => part.trim());
}

/** `event.code` names for keys Mantine's physical matching doesn't map (it compares `Digit1` with `1`). */
const PHYSICAL_KEY_NAMES: Record<string, string> = {
  '0': 'digit0', '1': 'digit1', '2': 'digit2', '3': 'digit3', '4': 'digit4',
  '5': 'digit5', '6': 'digit6', '7': 'digit7', '8': 'digit8', '9': 'digit9',
  '.': 'period', ',': 'comma', ';': 'semicolon', "'": 'quote', '[': 'bracketleft', ']': 'bracketright',
};

/** True when the event is exactly this hotkey. Alt combinations match the physical key, because macOS Option changes `event.key` (Option+T types "†"). */
export function matchesHotkey(hotkey: string, event: KeyboardEvent): boolean {
  const parts = hotkeyParts(hotkey);
  const physical = parts.includes('alt');
  const target = physical ? parts.map((part) => PHYSICAL_KEY_NAMES[part] ?? part).join('+') : hotkey;
  let matched = false;
  getHotkeyHandler([[target, () => { matched = true; }, { preventDefault: false, usePhysicalKeys: physical }]])(event);
  return matched;
}

/** Typed-character matching for pattern commands: no Ctrl, ⌘ or Alt; Shift is allowed for capital letters. */
export function matchesKeyPattern(pattern: CommandKeyPattern, event: KeyboardEvent): boolean {
  if (event.ctrlKey || event.metaKey || event.altKey) return false;
  if (pattern === 'letter') return /^[a-z]$/i.test(event.key);
  return !event.shiftKey && /^[0-9,]$/.test(event.key);
}

export function isEditableTarget(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && target.closest('input, textarea, select, [contenteditable="true"]') !== null;
}

const COMPOSITE_WIDGETS = [
  'listbox', 'menu', 'menubar', 'grid', 'treegrid', 'tree', 'tablist', 'radiogroup', 'slider', 'spinbutton', 'combobox',
].map((role) => `[role="${role}"]`).join(', ');

/** Widgets that use plain keys (arrows, letters, Tab) for their own navigation. */
export function isCompositeWidgetTarget(target: EventTarget | null): boolean {
  return target instanceof Element && target.closest(COMPOSITE_WIDGETS) !== null;
}

function modalDialogOpen(event: KeyboardEvent): boolean {
  const target = event.target instanceof Node ? event.target : null;
  const owner = target?.ownerDocument ?? (typeof document === 'undefined' ? null : document);
  return owner?.querySelector('[role="dialog"][aria-modal="true"]') != null;
}

export type RegisteredCommand = { definition: TradingCommandDefinition; handler: TradingCommandHandler };

/**
 * The command a key event triggers, or null. Text fields and open modal
 * dialogs are skipped unless a command allows inputs, and plain keys are
 * skipped in widgets that navigate with them. Inactive handlers are skipped.
 * A hotkey beats a typed-character pattern; then the most specific scope wins,
 * then the latest registration.
 */
export function resolveCommand(
  registered: readonly RegisteredCommand[],
  event: KeyboardEvent,
  overrides: KeyOverrides = {},
): RegisteredCommand | null {
  const blocked = isEditableTarget(event.target) || modalDialogOpen(event)
    || (!event.ctrlKey && !event.metaKey && !event.altKey && isCompositeWidgetTarget(event.target));
  let best: RegisteredCommand | null = null;
  let bestIsPattern = true;
  for (const candidate of registered) {
    const { definition, handler } = candidate;
    if (blocked && !definition.allowInInputs) continue;
    const pattern = definition.keyPattern ? matchesKeyPattern(definition.keyPattern, event) : false;
    if (!pattern && !commandKeys(definition, overrides).some((hotkey) => matchesHotkey(hotkey, event))) continue;
    if (definition.keyContext && !chartKeyContextActive(definition.keyContext, event)) continue;
    if (!handler.isActive()) continue;
    const better = !best
      || (bestIsPattern && !pattern)
      || (bestIsPattern === pattern && SCOPE_PRIORITY[definition.scope] >= SCOPE_PRIORITY[best.definition.scope]);
    if (better) {
      best = candidate;
      bestIsPattern = pattern;
    }
  }
  return best;
}

export function normalizeHotkey(hotkey: string): string {
  const parts = hotkeyParts(hotkey);
  const modifiers = ['mod', 'ctrl', 'meta', 'alt', 'shift'].filter((modifier) => parts.includes(modifier));
  const key = parts.find((part) => !['mod', 'ctrl', 'meta', 'alt', 'shift'].includes(part)) ?? '';
  return [...modifiers, key].join('+');
}

export type KeyConflict = { hotkey: string; scope: CommandScope; ids: string[] };

/** Commands that share a key in the same scope; the shortcut dialog shows these and a test keeps the defaults free of them. */
export function findKeyConflicts(definitions: readonly TradingCommandDefinition[], overrides: KeyOverrides = {}): KeyConflict[] {
  const byKey = new Map<string, KeyConflict>();
  for (const definition of definitions) {
    for (const hotkey of commandKeys(definition, overrides)) {
      const normalized = normalizeHotkey(hotkey);
      const slot = `${definition.scope}|${normalized}`;
      const entry = byKey.get(slot) ?? { hotkey: normalized, scope: definition.scope, ids: [] };
      if (!entry.ids.includes(definition.id)) entry.ids.push(definition.id);
      byKey.set(slot, entry);
    }
  }
  return [...byKey.values()].filter((entry) => entry.ids.length > 1);
}
