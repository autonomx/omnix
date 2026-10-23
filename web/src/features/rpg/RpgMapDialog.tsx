import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { RpgMapSurface } from './RpgMapSurface';
import { RpgTacticalGrid } from './RpgTacticalGrid';
import './RpgMapDialog.css';

interface RpgMapDialogProps {
  locationLabel: string;
  /** The region's illustrated map, when the session has one. */
  mapId: string;
  /** The local map's tactical grid (a session launched from a published world), when there is one. */
  mapInstanceId?: string;
  playerActorId?: string;
  heroName?: string;
  onClose: () => void;
  open: boolean;
  sessionId: string;
}

type MapView = 'local' | 'region';

export function RpgMapDialog({ locationLabel, mapId, mapInstanceId = '', playerActorId = '', heroName = '', onClose, open, sessionId }: RpgMapDialogProps) {
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const hasLocal = Boolean(mapInstanceId && playerActorId);
  const hasRegion = Boolean(mapId);
  const [view, setView] = useState<MapView>(hasLocal ? 'local' : 'region');
  // The latest onClose, so a parent's new callback on each render does not re-run the open/close effect below.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (open) setView(hasLocal ? 'local' : 'region');
  }, [hasLocal, open]);

  useEffect(() => {
    if (!open) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeButtonRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCloseRef.current();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      previousFocus?.focus();
    };
  }, [open]);

  if (!open) return null;

  // On the page itself: a rail with a backdrop filter or transform would otherwise contain the fixed backdrop.
  return createPortal(
    <div className="rpg-map-dialog-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section
        aria-labelledby="rpg-map-dialog-title"
        aria-modal="true"
        className="rpg-map-dialog"
        role="dialog"
      >
        <header className="rpg-map-dialog-header">
          <div>
            <p className="eyebrow">Interactive map</p>
            <h2 id="rpg-map-dialog-title">{locationLabel}</h2>
          </div>
          {hasLocal && hasRegion ? (
            <div className="rpg-map-dialog-tabs" role="tablist" aria-label="Map">
              <button aria-selected={view === 'local'} className={view === 'local' ? 'is-active' : undefined} onClick={() => setView('local')} role="tab" type="button">Local map</button>
              <button aria-selected={view === 'region'} className={view === 'region' ? 'is-active' : undefined} onClick={() => setView('region')} role="tab" type="button">Region map</button>
            </div>
          ) : null}
          <button aria-label="Close map" className="rpg-map-dialog-close" onClick={onClose} ref={closeButtonRef} type="button">
            ×
          </button>
        </header>
        {view === 'local' && hasLocal
          ? <RpgTacticalGrid heroName={heroName} mapInstanceId={mapInstanceId} playerActorId={playerActorId} />
          : <RpgMapSurface mapId={mapId} sessionId={sessionId} />}
      </section>
    </div>,
    document.body,
  );
}
