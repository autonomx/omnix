import { LIVE_COORDINATION_TERMINAL_EVENT } from './live-session-coordinator';

type CoordinationTerminalDetail = {
  outcome?: unknown;
};

let initialized = false;
let disposeListener: (() => void) | null = null;

export function removeTransientFinalUserRows(root: ParentNode = document): number {
  const rows = root.querySelectorAll<HTMLElement>(
    '.assistant-voice-transcript p.user[data-live-voice-id]:not([data-live-voice-id="live-voice-draft"])',
  );
  rows.forEach((row) => row.remove());
  return rows.length;
}

export function initializeLiveVoiceTranscriptReconciliation(): () => void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return () => undefined;
  if (initialized) return disposeListener ?? (() => undefined);
  initialized = true;

  const handleTerminal = (event: Event): void => {
    const detail = (event as CustomEvent<CoordinationTerminalDetail>).detail ?? {};
    if (detail.outcome !== 'conversation_submitted') return;
    // The dedicated voice controller owns only the in-progress draft. Once the
    // accepted final has been durably submitted, React's session message is the
    // canonical transcript row. Remove the controller-created final row so the
    // same user utterance cannot be displayed twice with different timestamps.
    removeTransientFinalUserRows(document);
  };

  window.addEventListener(LIVE_COORDINATION_TERMINAL_EVENT, handleTerminal);
  disposeListener = () => {
    window.removeEventListener(LIVE_COORDINATION_TERMINAL_EVENT, handleTerminal);
    initialized = false;
    disposeListener = null;
  };
  return disposeListener;
}

export function resetLiveVoiceTranscriptReconciliationForTests(): void {
  disposeListener?.();
  initialized = false;
  disposeListener = null;
}
