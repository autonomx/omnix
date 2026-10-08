import { createPortal } from 'react-dom';
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { formatCommandKeys, formatHotkey, hotkeyFromEvent, isBrowserReservedHotkey } from './hotkeyLabels';
import { saveKeyOverrides } from './keyOverridesStorage';
import {
  TRADING_COMMANDS,
  commandKeys,
  findKeyConflicts,
  isRebindable,
  normalizeHotkey,
  type TradingCommandDefinition,
} from './tradingCommands';
import { useTradingCommandAvailability, useTradingCommandKeyOverrides } from './useTradingCommands';
import './TradingKeyboard.css';

const COMMANDS: readonly TradingCommandDefinition[] = TRADING_COMMANDS;
const GROUPS = [...new Set(COMMANDS.map((command) => command.group))];
const labelById = new Map(COMMANDS.map((command) => [command.id, command.label]));

function ShortcutRow({
  definition,
  keys,
  appOnlyKeys,
  overridden,
  capturing,
  sharedWith,
  onToggleCapture,
  onCaptureKeyDown,
  onCancelCapture,
  onReset,
}: {
  definition: TradingCommandDefinition;
  keys: readonly string[];
  appOnlyKeys: readonly string[];
  overridden: boolean;
  capturing: boolean;
  sharedWith?: readonly string[];
  onToggleCapture: () => void;
  onCaptureKeyDown: (event: KeyboardEvent<HTMLButtonElement>) => void;
  onCancelCapture: () => void;
  onReset: () => void;
}) {
  return (
    <tr data-command-id={definition.id}>
      <th scope="row">
        {definition.label}
        {sharedWith ? <small className="trading-shortcut-conflict">Same key as {sharedWith.join(', ')}</small> : null}
      </th>
      <td>
        <span className="trading-shortcut-keys">
          {keys.map((key) => <kbd key={key}>{key}</kbd>)}
          {keys.length === 0 ? <em>Not set</em> : null}
          {appOnlyKeys.map((key) => <kbd key={key} className="is-app-only" title="Installed app only">{key} · app</kbd>)}
        </span>
      </td>
      <td className="trading-shortcut-actions">
        {isRebindable(definition) ? (
          <>
            <button
              type="button"
              aria-label={capturing ? `Press new keys for ${definition.label}` : `Change keys for ${definition.label}`}
              aria-pressed={capturing}
              onClick={onToggleCapture}
              onKeyDown={onCaptureKeyDown}
              onBlur={() => { if (capturing) onCancelCapture(); }}
            >
              {capturing ? 'Press keys…' : 'Change'}
            </button>
            {overridden ? <button type="button" aria-label={`Reset ${definition.label}`} onClick={onReset}>Reset</button> : null}
          </>
        ) : <span className="trading-shortcut-fixed">{definition.handledLocally ? 'Watchlist grid' : 'Fixed'}</span>}
      </td>
    </tr>
  );
}

/**
 * Ctrl+/: every shortcut by context, searchable, with rebinding. Change waits
 * for the next key press (Escape cancels, Tab leaves); conflicts with other
 * commands in the same context are listed. Overrides persist in this browser.
 */
export function TradingShortcutDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const overrides = useTradingCommandKeyOverrides();
  const availability = useTradingCommandAvailability();
  const [query, setQuery] = useState('');
  const [capturingId, setCapturingId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setQuery('');
    setCapturingId(null);
    setNotice(null);
    searchRef.current?.focus();
  }, [open]);

  const conflicts = useMemo(() => findKeyConflicts(COMMANDS, overrides, availability), [availability, overrides]);
  const conflictsById = useMemo(() => {
    const byId = new Map<string, string[]>();
    for (const conflict of conflicts) {
      for (const id of conflict.ids) {
        const others = conflict.ids.filter((other) => other !== id).map((other) => labelById.get(other) ?? other);
        byId.set(id, [...(byId.get(id) ?? []), ...others]);
      }
    }
    return byId;
  }, [conflicts]);

  if (!open || typeof document === 'undefined') return null;

  const keysFor = (definition: TradingCommandDefinition) => formatCommandKeys(definition, commandKeys(definition, overrides, availability));
  const appOnlyKeys = (definition: TradingCommandDefinition) => (
    availability === 'browser' && !overrides[definition.id] ? (definition.installedKeys ?? []).map((key) => formatHotkey(key)) : []
  );
  const normalizedQuery = query.trim().toLowerCase();
  const matches = (definition: TradingCommandDefinition) => !normalizedQuery
    || [definition.label, definition.group, ...keysFor(definition), ...appOnlyKeys(definition)].join(' ').toLowerCase().includes(normalizedQuery);

  const rebind = (definition: TradingCommandDefinition, hotkey: string) => {
    const normalized = normalizeHotkey(hotkey);
    saveKeyOverrides({ ...overrides, [definition.id]: [normalized] });
    setCapturingId(null);
    setNotice(availability === 'browser' && isBrowserReservedHotkey(normalized)
      ? `The browser keeps ${formatHotkey(normalized)} for itself, so it only works in the installed app.`
      : `${definition.label}: ${formatHotkey(normalized)}`);
  };

  const reset = (id: string) => {
    const next = { ...overrides };
    delete next[id];
    saveKeyOverrides(next);
    setNotice(`${labelById.get(id) ?? id}: default keys restored`);
  };

  const resetAll = () => {
    saveKeyOverrides({});
    setNotice('All shortcuts restored to their defaults');
  };

  const onCaptureKeyDown = (definition: TradingCommandDefinition) => (event: KeyboardEvent<HTMLButtonElement>) => {
    if (capturingId !== definition.id) return;
    if (event.key === 'Tab' && !event.ctrlKey && !event.metaKey && !event.altKey) {
      setCapturingId(null);
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    if (event.key === 'Escape') {
      setCapturingId(null);
      return;
    }
    const hotkey = hotkeyFromEvent(event);
    if (hotkey) rebind(definition, hotkey);
  };

  return createPortal(
    <div className="trading-shortcut-dialog-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section
        className="trading-shortcut-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="trading-shortcut-dialog-title"
        onKeyDown={(event) => { if (event.key === 'Escape') onClose(); }}
      >
        <header>
          <h2 id="trading-shortcut-dialog-title">Keyboard shortcuts</h2>
          <button type="button" onClick={resetAll} disabled={Object.keys(overrides).length === 0}>Reset all</button>
          <button type="button" aria-label="Close keyboard shortcuts" onClick={onClose}>×</button>
        </header>
        <input
          ref={searchRef}
          type="search"
          aria-label="Search shortcuts"
          placeholder="Search by name, context or key"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        {conflicts.length > 0 ? (
          <p className="trading-shortcut-conflicts" role="alert">
            {conflicts.length === 1 ? '1 key is' : `${conflicts.length} keys are`} used by more than one command in the same context.
          </p>
        ) : null}
        <p className="trading-shortcut-notice" role="status">{notice ?? ''}</p>
        <div className="trading-shortcut-groups">
          {GROUPS.map((group) => {
            const rows = COMMANDS.filter((definition) => definition.group === group && matches(definition));
            if (rows.length === 0) return null;
            const headingId = `trading-shortcut-group-${group.toLowerCase()}`;
            return (
              <section key={group} aria-labelledby={headingId}>
                <h3 id={headingId}>{group}</h3>
                <table>
                  <tbody>
                    {rows.map((definition) => (
                      <ShortcutRow
                        key={definition.id}
                        definition={definition}
                        keys={keysFor(definition)}
                        appOnlyKeys={appOnlyKeys(definition)}
                        overridden={Boolean(overrides[definition.id])}
                        capturing={capturingId === definition.id}
                        sharedWith={conflictsById.get(definition.id)}
                        onToggleCapture={() => setCapturingId(capturingId === definition.id ? null : definition.id)}
                        onCaptureKeyDown={onCaptureKeyDown(definition)}
                        onCancelCapture={() => setCapturingId(null)}
                        onReset={() => reset(definition.id)}
                      />
                    ))}
                  </tbody>
                </table>
              </section>
            );
          })}
        </div>
      </section>
    </div>,
    document.body,
  );
}
