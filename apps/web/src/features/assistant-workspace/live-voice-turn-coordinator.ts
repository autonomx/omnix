const PERF_EVENT = 'omnix:assistant-voice-perf';
export const LIVE_VOICE_TURN_TIMELINE_EVENT = 'omnix:live-voice-turn-timeline';

export type LiveVoiceTurnState =
  | 'listening'
  | 'speaking'
  | 'endpoint_candidate'
  | 'speculating'
  | 'finalizing'
  | 'committed'
  | 'playing'
  | 'cancelled';

export type EndpointFusionAction = 'continue' | 'speculate' | 'commit';

export type EndpointFusionInput = {
  endpointProbability: number;
  endpointThreshold: number;
  silenceMs: number;
  transcriptStableMs: number;
  semanticProbabilityDone: number;
  transcriptWords: number;
  correctionPending: boolean;
};

export type LiveVoiceTurnTimelineDetail = {
  turnId: string;
  event: 'speech_ended' | 'final_received' | 'playback_started' | 'cancelled';
  atMs: number;
  state: LiveVoiceTurnState;
};

type PerfDetail = {
  stage?: unknown;
  turnId?: unknown;
};

type TurnRecord = {
  turnId: string;
  state: LiveVoiceTurnState;
  speechEndedAt: number | null;
  finalReceivedAt: number | null;
  playbackStartedAt: number | null;
};

export function endpointFusionAction(input: EndpointFusionInput): EndpointFusionAction {
  if (input.correctionPending || input.transcriptWords < 1) return 'continue';
  const probability = Number.isFinite(input.endpointProbability)
    ? input.endpointProbability
    : 0;
  const stable = Math.max(0, input.transcriptStableMs);
  const silence = Math.max(0, input.silenceMs);
  const complete = input.semanticProbabilityDone >= 0.9;
  if (
    complete
    && probability >= input.endpointThreshold
    && silence >= 160
    && stable >= 80
  ) return 'commit';
  if (
    probability >= Math.max(0.35, input.endpointThreshold - 0.35)
    && stable >= 60
    && (input.transcriptWords >= 2 || probability >= 0.9)
  ) return 'speculate';
  return 'continue';
}

export class LiveVoiceTurnCoordinator {
  private readonly turns = new Map<string, TurnRecord>();

  speechEnded(turnId: string, atMs = performance.now()): void {
    const turn = this.record(turnId);
    if (
      turn.finalReceivedAt !== null
      || turn.playbackStartedAt !== null
      || turn.state === 'cancelled'
    ) return;
    // A user may pause and then resume within one utterance. Keep the latest
    // speech-to-silence transition so release latency is measured from the
    // pause that actually led to finalization, not an earlier internal pause.
    turn.speechEndedAt = atMs;
    turn.state = 'endpoint_candidate';
    this.emit(turn, 'speech_ended', atMs);
  }

  finalReceived(turnId: string, atMs = performance.now()): void {
    const turn = this.record(turnId);
    turn.finalReceivedAt = atMs;
    turn.state = 'committed';
    this.emit(turn, 'final_received', atMs);
  }

  playbackStarted(turnId: string, atMs = performance.now()): void {
    const turn = this.record(turnId);
    if (turn.playbackStartedAt !== null) return;
    turn.playbackStartedAt = atMs;
    turn.state = 'playing';
    this.emit(turn, 'playback_started', atMs);
  }

  cancel(turnId: string, atMs = performance.now()): void {
    const turn = this.record(turnId);
    turn.state = 'cancelled';
    this.emit(turn, 'cancelled', atMs);
  }

  snapshot(turnId: string): Readonly<TurnRecord> | null {
    const turn = this.turns.get(turnId);
    return turn ? { ...turn } : null;
  }

  clear(turnId?: string): void {
    if (turnId) this.turns.delete(turnId);
    else this.turns.clear();
  }

  private record(turnId: string): TurnRecord {
    const normalized = turnId.trim();
    const existing = this.turns.get(normalized);
    if (existing) return existing;
    const created: TurnRecord = {
      turnId: normalized,
      state: 'listening',
      speechEndedAt: null,
      finalReceivedAt: null,
      playbackStartedAt: null,
    };
    this.turns.set(normalized, created);
    while (this.turns.size > 32) {
      const oldest = this.turns.keys().next().value;
      if (typeof oldest !== 'string') break;
      this.turns.delete(oldest);
    }
    return created;
  }

  private emit(
    turn: TurnRecord,
    event: LiveVoiceTurnTimelineDetail['event'],
    atMs: number,
  ): void {
    if (typeof window === 'undefined') return;
    window.dispatchEvent(new CustomEvent<LiveVoiceTurnTimelineDetail>(
      LIVE_VOICE_TURN_TIMELINE_EVENT,
      {
        detail: {
          turnId: turn.turnId,
          event,
          atMs,
          state: turn.state,
        },
      },
    ));
  }
}

export const liveVoiceTurnCoordinator = new LiveVoiceTurnCoordinator();

let initialized = false;

export function initializeLiveVoiceTurnCoordinator(): () => void {
  if (initialized || typeof window === 'undefined') return () => undefined;
  initialized = true;
  const handlePerformance = (event: Event): void => {
    const detail = (event as CustomEvent<PerfDetail>).detail ?? {};
    const stage = typeof detail.stage === 'string' ? detail.stage : '';
    const turnId = typeof detail.turnId === 'string' ? detail.turnId.trim() : '';
    if (!turnId) return;
    if (stage === 'semantic_turn_assessed') {
      liveVoiceTurnCoordinator.speechEnded(turnId);
    } else if (stage === 'stt_final_received') {
      liveVoiceTurnCoordinator.finalReceived(turnId);
    }
  };
  window.addEventListener(PERF_EVENT, handlePerformance);
  return () => {
    window.removeEventListener(PERF_EVENT, handlePerformance);
    liveVoiceTurnCoordinator.clear();
    initialized = false;
  };
}
