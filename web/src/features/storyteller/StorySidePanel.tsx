import './StorySidePanel.css';
import { type KeyboardEvent, type ReactNode, useId, useRef, useState } from 'react';

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
 * stays mounted, so a half-typed form survives a look at another tab, or the panel being folded away.
 *
 * The writer may fold the panel into a rail of its tabs to give the manuscript the room; a tab chosen there opens
 * it again. The choice lasts between visits.
 */
export function StorySidePanel({ active, onChange, panels, badges = {} }: {
  active: StorySideTab;
  onChange: (tab: StorySideTab) => void;
  panels: Record<StorySideTab, ReactNode>;
  /** A count beside a tab's name, such as the characters a page suggested. */
  badges?: Partial<Record<StorySideTab, number>>;
}) {
  const base = useId();
  const [collapsed, setCollapsed] = useState(storedCollapsed);
  const fold = (next: boolean) => {
    setCollapsed(next);
    storeCollapsed(next);
  };
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
    <section className={`storyteller-side-panel${collapsed ? ' collapsed' : ''}`} aria-label="Story panel">
      <div className="storyteller-side-top">
        <button
          aria-expanded={!collapsed}
          aria-label={collapsed ? 'Show the story panel' : 'Hide the story panel'}
          className="storyteller-side-fold"
          title={collapsed ? 'Show the story panel' : 'Hide the story panel'}
          type="button"
          onClick={() => fold(!collapsed)}
        >
          <span aria-hidden="true">{collapsed ? '«' : '»'}</span>
        </button>
        <div className="storyteller-side-tabs" role="tablist" aria-label="Story panel" aria-orientation={collapsed ? 'vertical' : 'horizontal'}>
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
                onClick={() => {
                  onChange(tab.id);
                  if (collapsed) fold(false);
                }}
                onKeyDown={(event) => move(event, index)}
              >
                {tab.label}
                {badge ? <span className="storyteller-side-badge" aria-label={`${badge} new`}>{badge}</span> : null}
              </button>
            );
          })}
        </div>
      </div>
      {tabs.map((tab) => (
        <div
          aria-labelledby={`${base}-${tab.id}-tab`}
          className="storyteller-side-tabpanel"
          hidden={collapsed || tab.id !== active}
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

const COLLAPSED_KEY = 'omnix.storyteller.sidePanelCollapsed';

function storedCollapsed(): boolean {
  try {
    return window.localStorage.getItem(COLLAPSED_KEY) === 'yes';
  } catch {
    return false;
  }
}

function storeCollapsed(collapsed: boolean): void {
  try {
    window.localStorage.setItem(COLLAPSED_KEY, collapsed ? 'yes' : 'no');
  } catch {
    // a private window: the panel stays as it is for the page
  }
}
