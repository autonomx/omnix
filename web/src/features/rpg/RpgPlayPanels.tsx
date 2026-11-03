import { useEffect, useRef, type ReactNode } from 'react';
import './RpgPlayPanels.css';

export type RpgPlayPanelId = 'pack' | 'character' | 'journal' | 'world' | 'game-master' | 'voices';

const BAR_PANELS: Array<{ id: RpgPlayPanelId; label: string; shortcut: string }> = [
  { id: 'pack', label: 'Inventory', shortcut: 'I' },
  { id: 'character', label: 'Character', shortcut: 'C' },
  { id: 'journal', label: 'Journal', shortcut: 'J' },
  { id: 'world', label: 'World', shortcut: 'L' },
];

const PANEL_TITLES: Record<RpgPlayPanelId, string> = {
  pack: 'Inventory',
  character: 'Character',
  journal: 'Journal',
  world: 'World',
  'game-master': 'Game master',
  voices: 'Voices',
};

interface RpgPlayPanelsProps {
  /** What the open panel shows. */
  children: ReactNode;
  onChange: (panel: RpgPlayPanelId | null) => void;
  open: RpgPlayPanelId | null;
}

function isTypingOrInDialog(target: EventTarget | null): boolean {
  const element = target instanceof HTMLElement ? target : null;
  if (element?.closest('input, textarea, select, [contenteditable="true"]')) return true;
  return Boolean(document.querySelector('[aria-modal="true"], dialog[open]'));
}

/**
 * The bar under the play screen and the one panel it opens: everything that is not the story waits here. The panel
 * sits over the screen's edge and leaves the story in view; it is not modal, so play goes on beside it.
 */
export function RpgPlayPanels({ children, onChange, open }: RpgPlayPanelsProps) {
  const headingRef = useRef<HTMLHeadingElement | null>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const wasOpen = useRef(false);

  useEffect(() => {
    if (open) {
      if (!wasOpen.current) returnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      headingRef.current?.focus();
    } else if (wasOpen.current && returnFocusRef.current?.isConnected) {
      returnFocusRef.current.focus();
    }
    wasOpen.current = Boolean(open);
  }, [open]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        if (open && !isTypingOrInDialog(null)) onChange(null);
        return;
      }
      if (event.ctrlKey || event.metaKey || event.altKey || isTypingOrInDialog(event.target)) return;
      const panel = BAR_PANELS.find((row) => row.shortcut === event.key.toUpperCase());
      if (panel) {
        event.preventDefault();
        onChange(open === panel.id ? null : panel.id);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onChange, open]);

  return (
    <>
      {open ? (
        <section aria-labelledby="rpg-play-panel-title" className="rpg-play-panel" id="rpg-play-panel">
          <header className="rpg-play-panel-header">
            <h2 id="rpg-play-panel-title" ref={headingRef} tabIndex={-1}>{PANEL_TITLES[open]}</h2>
            <button aria-label="Close panel" className="rpg-play-panel-close" onClick={() => onChange(null)} type="button">
              <span aria-hidden="true">×</span>
            </button>
          </header>
          <div className="rpg-play-panel-body">{children}</div>
        </section>
      ) : null}
      <nav aria-label="Play panels" className="rpg-play-bar">
        {BAR_PANELS.map((panel) => (
          <button
            aria-controls={open === panel.id ? 'rpg-play-panel' : undefined}
            aria-expanded={open === panel.id}
            className={open === panel.id ? 'is-open' : undefined}
            key={panel.id}
            onClick={() => onChange(open === panel.id ? null : panel.id)}
            title={`${panel.label} (${panel.shortcut})`}
            type="button"
          >
            {panel.label}
          </button>
        ))}
      </nav>
    </>
  );
}
