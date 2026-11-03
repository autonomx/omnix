import { useEffect, useRef, useState, type ReactNode } from 'react';

interface RpgHeaderMoreMenuProps {
  /** The menu's buttons; `close` is for one that opens something over the screen. */
  children: (close: () => void) => ReactNode;
}

/** What is not played with: world lore, voices and how the screen is laid out, one button away. */
export function RpgHeaderMoreMenu({ children }: RpgHeaderMoreMenuProps) {
  const [isOpen, setIsOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!isOpen) return undefined;
    const closeFromOutside = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setIsOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsOpen(false);
    };
    window.addEventListener('pointerdown', closeFromOutside);
    window.addEventListener('keydown', closeOnEscape);
    return () => {
      window.removeEventListener('pointerdown', closeFromOutside);
      window.removeEventListener('keydown', closeOnEscape);
    };
  }, [isOpen]);

  return (
    <div className="rpg-header-more" ref={rootRef}>
      <button
        aria-controls="rpg-header-more-menu"
        aria-expanded={isOpen}
        className="rpg-secondary-button rpg-header-more-toggle"
        onClick={() => setIsOpen((value) => !value)}
        type="button"
      >
        More
      </button>
      <div hidden={!isOpen} role="group" id="rpg-header-more-menu" className="rpg-unified-header-controls" aria-label="Workspace layout controls">
        {children(() => setIsOpen(false))}
      </div>
    </div>
  );
}
