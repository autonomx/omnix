import { createPortal } from 'react-dom';
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { CoreIndicatorId, CoreIndicatorInstance } from './indicators/coreIndicators';

type MenuPosition = { top: number; left: number };

export function TradingIndicatorManager({
  indicators,
  onToggle,
}: {
  indicators: CoreIndicatorInstance[];
  onToggle: (id: CoreIndicatorId) => void;
}) {
  const enabledCount = indicators.filter((indicator) => indicator.enabled).length;
  const managerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [menuPosition, setMenuPosition] = useState<MenuPosition | null>(null);

  const updateMenuPosition = useCallback(() => {
    const trigger = triggerRef.current;
    const menu = menuRef.current;
    if (!trigger) return;
    const triggerRect = trigger.getBoundingClientRect();
    const menuWidth = menu?.offsetWidth ?? 186;
    const left = Math.min(
      Math.max(8, triggerRect.right - menuWidth),
      Math.max(8, window.innerWidth - menuWidth - 8),
    );
    setMenuPosition({ top: triggerRect.bottom + 4, left });
  }, []);

  useLayoutEffect(() => {
    if (open) updateMenuPosition();
  }, [open, indicators.length, updateMenuPosition]);

  useEffect(() => {
    if (!open) return undefined;
    const reposition = () => updateMenuPosition();
    const closeOnOutsideClick = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!managerRef.current?.contains(target) && !menuRef.current?.contains(target)) {
        setOpen(false);
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    window.addEventListener('resize', reposition);
    window.addEventListener('scroll', reposition, true);
    document.addEventListener('pointerdown', closeOnOutsideClick);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      window.removeEventListener('resize', reposition);
      window.removeEventListener('scroll', reposition, true);
      document.removeEventListener('pointerdown', closeOnOutsideClick);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [open, updateMenuPosition]);

  const menu = open && typeof document !== 'undefined' ? createPortal(
    <div
      ref={menuRef}
      className="trading-indicator-menu"
      role="group"
      aria-label="Technical indicators"
      style={{
        top: menuPosition?.top ?? 0,
        left: menuPosition?.left ?? 0,
        visibility: menuPosition ? 'visible' : 'hidden',
      }}
    >
      {indicators.map((indicator) => (
        <button
          key={indicator.id}
          type="button"
          className={indicator.enabled ? 'active' : undefined}
          aria-pressed={indicator.enabled}
          onClick={() => onToggle(indicator.id)}
        >
          {indicator.id.toUpperCase()} {indicator.period}
        </button>
      ))}
    </div>,
    document.body,
  ) : null;

  return (
    <div ref={managerRef} className={`trading-indicator-manager${enabledCount > 0 ? ' has-active' : ''}`}>
      <button
        ref={triggerRef}
        type="button"
        aria-label="Indicators"
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen((current) => !current)}
      >
        <span className="trading-indicator-glyph" aria-hidden="true"><i /><i /><i /></span>
        <span>Indicators</span>
        <span className="trading-menu-caret" aria-hidden="true">⌄</span>
      </button>
      {menu}
    </div>
  );
}
