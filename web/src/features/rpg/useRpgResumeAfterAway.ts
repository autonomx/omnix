import { useEffect, useRef } from 'react';
import { rpgSessionClient } from './api/rpgSessionClient';

/** How long away counts as time away: shorter breaks leave the world as it was. */
export const RPG_AWAY_MS = 10 * 60 * 1000;

/**
 * Coming back to a campaign after time away (RQ-2.7): opening one last played at least ten minutes ago, or returning
 * to the tab after ten minutes hidden, runs the resume turn, so the world moves on and the story log says how. Each
 * absence is resumed once.
 */
export function useRpgResumeAfterAway(sessionId: string, lastPlayedMs: number | undefined, onTurnApplied: () => void): void {
  const resumed = useRef(new Set<string>());
  const hiddenSince = useRef<number | null>(null);
  const turnApplied = useRef(onTurnApplied);
  turnApplied.current = onTurnApplied;

  useEffect(() => {
    if (!sessionId || !lastPlayedMs) return;
    const key = `${sessionId}:${lastPlayedMs}`;
    const away = Date.now() - lastPlayedMs;
    if (away < RPG_AWAY_MS || resumed.current.has(key)) return;
    resumed.current.add(key);
    void resume(sessionId, away, turnApplied.current);
  }, [sessionId, lastPlayedMs]);

  useEffect(() => {
    if (!sessionId || typeof document === 'undefined') return undefined;
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') {
        hiddenSince.current = Date.now();
        return;
      }
      const since = hiddenSince.current;
      hiddenSince.current = null;
      if (since !== null && Date.now() - since >= RPG_AWAY_MS) {
        void resume(sessionId, Date.now() - since, turnApplied.current);
      }
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, [sessionId]);
}

async function resume(sessionId: string, awayMs: number, onTurnApplied: () => void): Promise<void> {
  try {
    await rpgSessionClient.resumeRpgSession(sessionId, awayMs / 1000);
    onTurnApplied();
  } catch {
    // A refused resume (the campaign is busy with another turn) leaves the world as it was; the story log says why.
  }
}
