import './StorySidePanel.css';
import { type KeyboardEvent, type ReactNode, useId, useRef } from 'react';

export type StorySideTab = 'write' | 'characters' | 'world' | 'audio';

const tabs: Array<{ id: StorySideTab; label: string }> = [
  { id: 'write', label: 'Write' },
  { id: 'characters', label: 'Characters' },
  { id: 'world', label: 'World' },
  { id: 'audio', label: 'Audio' },
];

/**
 * The one panel beside the manuscript (ST-6.4): Write (the request, the whole-story actions, the plan, the
 * contents and the versions), Characters, World (notes and presets) and Audio (voices and reading). Every tab
 * stays mounted, so a half-typed form survives a look at another tab.
 */
export function StorySidePanel({ active, onChange, panels, badges = {} }: {
  active: StorySideTab;
  onChange: (tab: StorySideTab) => void;
  panels: Record<StorySideTab, ReactNode>;
  /** A count beside a tab's name, such as the characters a page suggested. */
  badges?: Partial<Record<StorySideTab, number>>;
}) {
  const base = useId();
  const buttons = useRef(new Map<StorySideTab, HTMLButtonElement>());
  const move = (event: KeyboardEvent, index: number) => {
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key];
    const target = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1
      : step === undefined ? null : (index + step + tabs.length) % tabs.length;
    if (target === null) return;
    event.preventDefault();
    onChange(tabs[target].id);
    buttons.current.get(tabs[target].id)?.focus();
  };
  return (
    <section className="storyteller-side-panel" aria-label="Story panel">
      <div className="storyteller-side-tabs" role="tablist" aria-label="Story panel">
        {tabs.map((tab, index) => {
          const selected = tab.id === active;
          const badge = badges[tab.id];
          return (
            <button
              aria-controls={`${base}-${tab.id}-panel`}
              aria-selected={selected}
              id={`${base}-${tab.id}-tab`}
              key={tab.id}
              ref={(element) => { if (element) buttons.current.set(tab.id, element); else buttons.current.delete(tab.id); }}
              role="tab"
              tabIndex={selected ? 0 : -1}
              type="button"
              onClick={() => onChange(tab.id)}
              onKeyDown={(event) => move(event, index)}
            >
              {tab.label}
              {badge ? <span className="storyteller-side-badge" aria-label={`${badge} new`}>{badge}</span> : null}
            </button>
          );
        })}
      </div>
      {tabs.map((tab) => (
        <div
          aria-labelledby={`${base}-${tab.id}-tab`}
          className="storyteller-side-tabpanel"
          hidden={tab.id !== active}
          id={`${base}-${tab.id}-panel`}
          key={tab.id}
          role="tabpanel"
        >
          {panels[tab.id]}
        </div>
      ))}
    </section>
  );
}
