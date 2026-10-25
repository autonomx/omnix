import { useEffect, useState } from 'react';
import type { components } from './api/generated';

/** What the play screen offers after a turn (RQ-7.3): suggestions from the scene, and the game's question's answers. */
export type RpgTurnSuggestion = components['schemas']['Suggestion'];

export interface RpgTurnOffers {
  suggestions: RpgTurnSuggestion[];
  choices: RpgTurnSuggestion[];
}

const offersBySession = new Map<string, RpgTurnOffers>();
const listeners = new Set<() => void>();

export function recordRpgTurnOffers(
  sessionId: string,
  presentation: { suggestions?: RpgTurnSuggestion[]; choices?: RpgTurnSuggestion[] } | null | undefined,
): void {
  if (!presentation) return;
  offersBySession.set(sessionId, {
    suggestions: [...(presentation.suggestions ?? [])],
    choices: [...(presentation.choices ?? [])],
  });
  for (const listener of listeners) listener();
}

export function latestRpgTurnOffers(sessionId: string): RpgTurnOffers | undefined {
  return offersBySession.get(sessionId);
}

export function useLatestRpgTurnOffers(sessionId: string): RpgTurnOffers | undefined {
  const [, setVersion] = useState(0);
  useEffect(() => {
    const listener = () => setVersion((value) => value + 1);
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, []);
  return latestRpgTurnOffers(sessionId);
}

export function resetRpgTurnOffersForTests(): void {
  offersBySession.clear();
  listeners.clear();
}
