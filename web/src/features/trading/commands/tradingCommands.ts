import { getHotkeyHandler } from '@mantine/hooks';

/** Where a command applies. When one key matches in several scopes, the most specific scope wins. */
export type CommandScope = 'workspace' | 'chart' | 'watchlist' | 'drawing';

const SCOPE_PRIORITY: Record<CommandScope, number> = { workspace: 0, chart: 1, watchlist: 2, drawing: 3 };

export type TradingCommandDefinition = {
  id: string;
  label: string;
  group: string;
  scope: CommandScope;
  /** Mantine hotkey strings, e.g. `mod+z`, `alt+t`, `shift+alt+b`. `mod` is Ctrl on Windows/Linux and ⌘ on macOS. */
  defaultKeys: readonly string[];
  /** Runs even while a text field has focus (for keys such as Escape). */
  allowInInputs?: boolean;
};

export type TradingCommandHandler = {
  run: (event: KeyboardEvent) => void;
  isActive: () => boolean;
};

export type KeyOverrides = Readonly<Record<string, readonly string[]>>;

export const TRADING_COMMANDS = [
  { id: 'drawing.undo', label: 'Undo drawing change', group: 'Drawings', scope: 'chart', defaultKeys: ['mod+z'] },
  { id: 'drawing.redo', label: 'Redo drawing change', group: 'Drawings', scope: 'chart', defaultKeys: ['mod+shift+z'] },
  { id: 'drawing.delete', label: 'Delete selected drawing', group: 'Drawings', scope: 'drawing', defaultKeys: ['delete', 'backspace'] },
] as const satisfies readonly TradingCommandDefinition[];

export type TradingCommandId = typeof TRADING_COMMANDS[number]['id'];

const definitionsById = new Map<string, TradingCommandDefinition>(TRADING_COMMANDS.map((command) => [command.id, command]));

export function tradingCommandDefinition(id: string): TradingCommandDefinition | undefined {
  return definitionsById.get(id);
}

export function commandKeys(definition: TradingCommandDefinition, overrides: KeyOverrides = {}): readonly string[] {
  return overrides[definition.id] ?? definition.defaultKeys;
}

function usesAlt(hotkey: string): boolean {
  return hotkey.toLowerCase().split('+').map((part) => part.trim()).includes('alt');
}

/** True when the event is exactly this hotkey. Alt combinations match the physical key, because macOS Option changes `event.key` (Option+T types "†"). */
export function matchesHotkey(hotkey: string, event: KeyboardEvent): boolean {
  let matched = false;
  getHotkeyHandler([[hotkey, () => { matched = true; }, { preventDefault: false, usePhysicalKeys: usesAlt(hotkey) }]])(event);
  return matched;
}

export function isEditableTarget(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && target.closest('input, textarea, select, [contenteditable="true"]') !== null;
}

export type RegisteredCommand = { definition: TradingCommandDefinition; handler: TradingCommandHandler };

/** The command a key event triggers, or null. Inactive handlers are skipped; the most specific scope wins, then the latest registration. */
export function resolveCommand(
  registered: readonly RegisteredCommand[],
  event: KeyboardEvent,
  overrides: KeyOverrides = {},
): RegisteredCommand | null {
  const editable = isEditableTarget(event.target);
  let best: RegisteredCommand | null = null;
  for (const candidate of registered) {
    const { definition, handler } = candidate;
    if (editable && !definition.allowInInputs) continue;
    if (!commandKeys(definition, overrides).some((hotkey) => matchesHotkey(hotkey, event))) continue;
    if (!handler.isActive()) continue;
    if (!best || SCOPE_PRIORITY[definition.scope] >= SCOPE_PRIORITY[best.definition.scope]) best = candidate;
  }
  return best;
}

export function normalizeHotkey(hotkey: string): string {
  const parts = hotkey.toLowerCase().split('+').map((part) => part.trim());
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
