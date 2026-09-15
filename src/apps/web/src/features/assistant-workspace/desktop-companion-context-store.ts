export type DesktopCompanionContextUpdate = {
  sessionId: string;
  characterId: string | null;
  observationId: string;
  sceneSummary: string;
  reaction: string | null;
  importance: number;
  observedAtMs: number;
};

export type DesktopCompanionContextSnapshot = {
  sessionId: string;
  characterId: string | null;
  observationId: string;
  sceneSummary: string;
  activityThread: string;
  reaction: string | null;
  importance: number;
  observedAtMs: number;
  observationCount: number;
  revision: number;
};

type SessionState = DesktopCompanionContextSnapshot & {
  summaries: string[];
};

type Listener = (snapshot: DesktopCompanionContextSnapshot | null) => void;

export class DesktopCompanionContextStore {
  private readonly states = new Map<string, SessionState>();
  private readonly listeners = new Set<Listener>();
  private revision = 0;

  record(update: DesktopCompanionContextUpdate): DesktopCompanionContextSnapshot | null {
    const sessionId = update.sessionId.trim();
    const observationId = update.observationId.trim();
    const sceneSummary = compact(update.sceneSummary, 1500);
    if (!sessionId || !observationId || !sceneSummary) return null;

    const previous = this.states.get(sessionId);
    const summaries = [...(previous?.summaries ?? [])];
    if (!summaries.length || summaries[summaries.length - 1] !== sceneSummary) summaries.push(sceneSummary);
    while (summaries.length > 6) summaries.shift();
    this.revision += 1;
    const state: SessionState = {
      sessionId,
      characterId: update.characterId?.trim() || null,
      observationId,
      sceneSummary,
      activityThread: compact(summaries.join(' | '), 2200),
      reaction: update.reaction?.trim() || null,
      importance: bounded(update.importance, 0, 1),
      observedAtMs: finite(update.observedAtMs),
      observationCount: (previous?.observationCount ?? 0) + 1,
      revision: this.revision,
      summaries,
    };
    this.states.set(sessionId, state);
    this.publish(this.publicSnapshot(state));
    return this.publicSnapshot(state);
  }

  snapshot(sessionId: string): DesktopCompanionContextSnapshot | null {
    const state = this.states.get(sessionId);
    return state ? this.publicSnapshot(state) : null;
  }

  fresh(sessionId: string, nowMs: number, maxAgeMs = 120_000): DesktopCompanionContextSnapshot | null {
    const state = this.states.get(sessionId);
    if (!state) return null;
    if (finite(nowMs) - state.observedAtMs > Math.max(0, maxAgeMs)) return null;
    return this.publicSnapshot(state);
  }

  clear(sessionId?: string): void {
    if (sessionId) this.states.delete(sessionId);
    else this.states.clear();
    this.revision += 1;
    this.publish(null);
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private publicSnapshot(state: SessionState): DesktopCompanionContextSnapshot {
    const { summaries: _summaries, ...snapshot } = state;
    return { ...snapshot };
  }

  private publish(snapshot: DesktopCompanionContextSnapshot | null): void {
    for (const listener of this.listeners) listener(snapshot);
  }
}

function compact(value: string, maximum: number): string {
  return String(value || '').replace(/\s+/g, ' ').trim().slice(0, maximum);
}

function bounded(value: number, minimum: number, maximum: number): number {
  if (!Number.isFinite(value)) return minimum;
  return Math.max(minimum, Math.min(maximum, value));
}

function finite(value: number): number {
  return Number.isFinite(value) ? value : 0;
}

export const desktopCompanionContextStore = new DesktopCompanionContextStore();
