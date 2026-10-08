import { getHotkeyHandler } from '@mantine/hooks';
import { chartKeyContextActive, type ChartKeyContext } from './chartKeyContext';

/** Where a command applies. When one key matches in several scopes, the most specific scope wins. */
export type CommandScope = 'workspace' | 'chart' | 'watchlist' | 'drawing';

const SCOPE_PRIORITY: Record<CommandScope, number> = { workspace: 0, chart: 1, watchlist: 2, drawing: 3 };

/**
 * Where Omnix runs. Browsers keep some keys for themselves (Ctrl+T, Ctrl+W,
 * Ctrl+N, Ctrl+Tab, Ctrl+PgUp/PgDn, Ctrl+1-9) and a page can't override them,
 * so those TradingView keys only work in the installed app (TVP-4.5). The
 * browser is the default.
 */
export type TradingCommandAvailability = 'browser' | 'installed';

/** Keys matched by a pattern rather than a hotkey string. Pattern keys can't be rebound. */
export type CommandKeyPattern = 'letter' | 'interval';

export type TradingCommandDefinition = {
  id: string;
  label: string;
  group: string;
  scope: CommandScope;
  /** Mantine hotkey strings, e.g. `mod+z`, `alt+t`, `shift+alt+b`. `mod` is Ctrl on Windows/Linux and ⌘ on macOS. */
  defaultKeys: readonly string[];
  /** TradingView's keys that browsers keep for themselves; they only work in the installed app, alongside `defaultKeys`. */
  installedKeys?: readonly string[];
  /** Runs even while a text field has focus (for keys such as Escape). */
  allowInInputs?: boolean;
  /** Matches typed characters instead of hotkeys: `letter` is A–Z, `interval` is 0–9 and comma. */
  keyPattern?: CommandKeyPattern;
  /** The keys only fire while the chart area has the keyboard (see `chartKeyContext`). */
  keyContext?: ChartKeyContext;
  /** Keys a component's own keyboard pattern reads (the watchlist tree grid). Listed in the shortcut dialog; never dispatched or rebound. */
  handledLocally?: boolean;
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
  { id: 'workspace.shortcuts', label: 'Keyboard shortcuts', group: 'General', scope: 'workspace', defaultKeys: ['mod+/'] },
  { id: 'layout.save', label: 'Save layout (workspace)', group: 'Layout', scope: 'workspace', defaultKeys: ['mod+s'] },
  { id: 'layout.load', label: 'Load layout (workspace)', group: 'Layout', scope: 'workspace', defaultKeys: ['.'] },
  // Layout and watchlist (TVP-2.3)
  { id: 'layout.nextChart', label: 'Next chart in the layout', group: 'Layout', scope: 'chart', defaultKeys: ['tab'], keyContext: 'chartClicked' },
  { id: 'layout.previousChart', label: 'Previous chart in the layout', group: 'Layout', scope: 'chart', defaultKeys: ['shift+tab'], keyContext: 'chartClicked' },
  { id: 'layout.maximizeChart', label: 'Maximise or restore the active chart', group: 'Layout', scope: 'workspace', defaultKeys: ['alt+enter'] },
  { id: 'watchlist.addActiveSymbol', label: 'Add the chart symbol to the open watchlist', group: 'Watchlist', scope: 'workspace', defaultKeys: ['alt+w'] },
  // Tabs (TVP-2.3). In the browser they use Alt, because the browser keeps Ctrl+T, W, N, Tab, PgUp/PgDn and 1-9.
  { id: 'tab.new', label: 'New tab, copying this one (browser Alt+Shift+T, app Ctrl+T)', group: 'Tabs', scope: 'workspace', defaultKeys: ['alt+shift+t'], installedKeys: ['mod+t', 'mod+u'] },
  { id: 'tab.close', label: 'Close tab (browser Alt+Shift+W, app Ctrl+W)', group: 'Tabs', scope: 'workspace', defaultKeys: ['alt+shift+w'], installedKeys: ['mod+w'] },
  { id: 'tab.next', label: 'Next tab (browser Alt+Page Down, app Ctrl+Tab)', group: 'Tabs', scope: 'workspace', defaultKeys: ['alt+pagedown'], installedKeys: ['mod+tab', 'mod+pagedown'] },
  { id: 'tab.previous', label: 'Previous tab (browser Alt+Page Up, app Ctrl+Shift+Tab)', group: 'Tabs', scope: 'workspace', defaultKeys: ['alt+pageup'], installedKeys: ['mod+shift+tab', 'mod+pageup'] },
  { id: 'tab.goTo1', label: 'Go to tab 1 (browser Alt+1, app Ctrl+1)', group: 'Tabs', scope: 'workspace', defaultKeys: ['alt+1'], installedKeys: ['mod+1'] },
  { id: 'tab.goTo2', label: 'Go to tab 2 (browser Alt+2, app Ctrl+2)', group: 'Tabs', scope: 'workspace', defaultKeys: ['alt+2'], installedKeys: ['mod+2'] },
  { id: 'tab.goTo3', label: 'Go to tab 3 (browser Alt+3, app Ctrl+3)', group: 'Tabs', scope: 'workspace', defaultKeys: ['alt+3'], installedKeys: ['mod+3'] },
  { id: 'tab.goTo4', label: 'Go to tab 4 (browser Alt+4, app Ctrl+4)', group: 'Tabs', scope: 'workspace', defaultKeys: ['alt+4'], installedKeys: ['mod+4'] },
  { id: 'tab.goTo5', label: 'Go to tab 5 (browser Alt+5, app Ctrl+5)', group: 'Tabs', scope: 'workspace', defaultKeys: ['alt+5'], installedKeys: ['mod+5'] },
  { id: 'tab.goTo6', label: 'Go to tab 6 (browser Alt+6, app Ctrl+6)', group: 'Tabs', scope: 'workspace', defaultKeys: ['alt+6'], installedKeys: ['mod+6'] },
  { id: 'tab.goTo7', label: 'Go to tab 7 (browser Alt+7, app Ctrl+7)', group: 'Tabs', scope: 'workspace', defaultKeys: ['alt+7'], installedKeys: ['mod+7'] },
  { id: 'tab.goTo8', label: 'Go to tab 8 (browser Alt+8, app Ctrl+8)', group: 'Tabs', scope: 'workspace', defaultKeys: ['alt+8'], installedKeys: ['mod+8'] },
  { id: 'tab.goToLast', label: 'Go to the last tab (browser Alt+9, app Ctrl+9)', group: 'Tabs', scope: 'workspace', defaultKeys: ['alt+9'], installedKeys: ['mod+9'] },
  { id: 'tab.reopenClosed', label: 'Reopen closed tab (browser Alt+Shift+Z, app Ctrl+Shift+T)', group: 'Tabs', scope: 'workspace', defaultKeys: ['alt+shift+z'], installedKeys: ['mod+shift+t'] },
  // The watchlist tree grid reads these keys itself (TVP-5.3); they stay fixed so the grid keeps its ARIA keyboard pattern.
  { id: 'watchlist.next', label: 'Next symbol', group: 'Watchlist', scope: 'watchlist', defaultKeys: ['arrowdown', 'space'], handledLocally: true },
  { id: 'watchlist.previous', label: 'Previous symbol', group: 'Watchlist', scope: 'watchlist', defaultKeys: ['arrowup', 'shift+space'], handledLocally: true },
  { id: 'watchlist.extendNext', label: 'Extend the selection down', group: 'Watchlist', scope: 'watchlist', defaultKeys: ['shift+arrowdown'], handledLocally: true },
  { id: 'watchlist.extendPrevious', label: 'Extend the selection up', group: 'Watchlist', scope: 'watchlist', defaultKeys: ['shift+arrowup'], handledLocally: true },
  { id: 'watchlist.selectAll', label: 'Select all symbols', group: 'Watchlist', scope: 'watchlist', defaultKeys: ['mod+a'], handledLocally: true },
] as const satisfies readonly TradingCommandDefinition[];

export type TradingCommandId = typeof TRADING_COMMANDS[number]['id'];

const definitionsById = new Map<string, TradingCommandDefinition>(TRADING_COMMANDS.map((command) => [command.id, command]));

export function tradingCommandDefinition(id: string): TradingCommandDefinition | undefined {
  return definitionsById.get(id);
}

/** Pattern keys and the watchlist grid keys are fixed; every other command can be rebound. */
export function isRebindable(definition: TradingCommandDefinition): boolean {
  return !definition.keyPattern && !definition.handledLocally;
}

/** A command's keys: the user's override, else its defaults plus, in the installed app, TradingView's browser-reserved keys. */
export function commandKeys(
  definition: TradingCommandDefinition,
  overrides: KeyOverrides = {},
  availability: TradingCommandAvailability = 'browser',
): readonly string[] {
  const override = isRebindable(definition) ? overrides[definition.id] : undefined;
  if (override) return override;
  return availability === 'installed' && definition.installedKeys
    ? [...definition.defaultKeys, ...definition.installedKeys]
    : definition.defaultKeys;
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

/**
 * True when the event is exactly this hotkey. Alt combinations match the
 * physical key, because macOS Option changes `event.key` (Option+T types
 * "†"); so do Shift+digit combinations, because Shift+1 types "!".
 */
export function matchesHotkey(hotkey: string, event: KeyboardEvent): boolean {
  const parts = hotkeyParts(hotkey);
  const physical = parts.includes('alt') || (parts.includes('shift') && parts.some((part) => /^\d$/.test(part)));
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
  availability: TradingCommandAvailability = 'browser',
): RegisteredCommand | null {
  const blocked = isEditableTarget(event.target) || modalDialogOpen(event)
    || (!event.ctrlKey && !event.metaKey && !event.altKey && isCompositeWidgetTarget(event.target));
  let best: RegisteredCommand | null = null;
  let bestIsPattern = true;
  for (const candidate of registered) {
    const { definition, handler } = candidate;
    if (definition.handledLocally || (blocked && !definition.allowInInputs)) continue;
    const pattern = definition.keyPattern ? matchesKeyPattern(definition.keyPattern, event) : false;
    if (!pattern && !commandKeys(definition, overrides, availability).some((hotkey) => matchesHotkey(hotkey, event))) continue;
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
export function findKeyConflicts(
  definitions: readonly TradingCommandDefinition[],
  overrides: KeyOverrides = {},
  availability: TradingCommandAvailability = 'browser',
): KeyConflict[] {
  const byKey = new Map<string, KeyConflict>();
  for (const definition of definitions) {
    for (const hotkey of commandKeys(definition, overrides, availability)) {
      const normalized = normalizeHotkey(hotkey);
      const slot = `${definition.scope}|${normalized}`;
      const entry = byKey.get(slot) ?? { hotkey: normalized, scope: definition.scope, ids: [] };
      if (!entry.ids.includes(definition.id)) entry.ids.push(definition.id);
      byKey.set(slot, entry);
    }
  }
  return [...byKey.values()].filter((entry) => entry.ids.length > 1);
}
