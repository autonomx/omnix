import { useEffect, useState } from 'react';

import {
  liveConversationStore,
  selectLiveChatSnapshot,
  useLiveConversationState,
} from '../assistant-workspace/live-conversation-store';
import { CharacterModePanel } from './CharacterModePanel';
import { LiveConversationControls } from './LiveConversationControls';
import { LiveConversationEvaluationPanel } from './LiveConversationEvaluationPanel';
import { LivePronunciationPanel } from './LivePronunciationPanel';
import { LiveVoiceCalibrationPanel } from './LiveVoiceCalibrationPanel';
import './LiveChatPanel.css';

export type LiveChatPanelProps = {
  sessionId: string | null;
};

type LegacyLiveCallSnapshot = {
  connected: boolean;
  state: string;
  identity: string;
  duplexMode: string;
};

const DEFAULT_LEGACY_SNAPSHOT: LegacyLiveCallSnapshot = {
  connected: false,
  state: 'Idle',
  identity: 'System Assistant',
  duplexMode: 'Safe half-duplex',
};

/** Compatibility-only DOM read for the legacy call button tests. Runtime policy uses the store. */
export function readLiveCallSnapshot(root: ParentNode = document): LegacyLiveCallSnapshot {
  const card = root.querySelector<HTMLElement>('.assistant-live-card');
  if (!card) return DEFAULT_LEGACY_SNAPSHOT;
  const action = Array.from(card.querySelectorAll<HTMLButtonElement>('button'))
    .find((button) => /^(?:Start Call|End Call)$/i.test(button.textContent?.trim() ?? ''));
  const state = card.querySelector<HTMLElement>('.assistant-live-state span')?.textContent?.trim()
    || card.querySelector<HTMLElement>('.assistant-voice-status strong')?.textContent?.trim()
    || 'Idle';
  const identity = card.querySelector<HTMLElement>('.assistant-live-identity')?.textContent?.trim()
    || 'System Assistant';
  const duplexMode = card.dataset.duplexMode === 'echo_aware'
    ? 'Echo-aware barge-in'
    : card.dataset.duplexGate === 'assistant-speaking'
      ? 'Safe half-duplex · microphone paused during playback'
      : 'Safe half-duplex';
  return {
    connected: action?.textContent?.trim().toLocaleLowerCase() === 'end call',
    state,
    identity,
    duplexMode,
  };
}

export function invokeExistingLiveCallControl(root: ParentNode = document): boolean {
  const button = Array.from(root.querySelectorAll<HTMLButtonElement>('.assistant-live-card button'))
    .find((candidate) => /^(?:Start Call|End Call)$/i.test(candidate.textContent?.trim() ?? ''));
  if (!button) return false;
  button.click();
  return true;
}

export function liveCallCharacterName(identity: string): string {
  return identity.replace(/^Talking to\s+/i, '').trim() || 'Assistant';
}

export function LiveChatPanel({ sessionId }: LiveChatPanelProps) {
  const runtimeState = useLiveConversationState();
  const snapshot = selectLiveChatSnapshot(runtimeState);
  const [callStatus, setCallStatus] = useState<string | null>(null);

  useEffect(() => {
    liveConversationStore.dispatch({ type: 'session', sessionId });
  }, [sessionId]);

  function toggleCall(): void {
    if (!invokeExistingLiveCallControl()) {
      setCallStatus('Live Voice controls are not mounted yet. Open a Chat session and try again.');
      return;
    }
    setCallStatus(snapshot.connected ? 'Ending live call…' : 'Starting live call…');
  }

  const duplexLabel = snapshot.duplexMode === 'echo_aware'
    ? 'Echo-aware barge-in'
    : snapshot.duplexReason === 'calibration_missing'
      ? 'Safe half-duplex · calibration required'
      : 'Safe half-duplex';

  return (
    <section className="assistant-view-panel live-chat-panel" aria-label="Live Chat view">
      <header className="live-chat-page-header">
        <div>
          <p className="eyebrow">Omnix Assistant</p>
          <h2>Live Chat</h2>
          <p>Configure the character and conversation presence used by the existing live voice pipeline.</p>
        </div>
        <span className={snapshot.connected ? 'live-chat-status active' : 'live-chat-status'}>
          {snapshot.connected ? 'Call connected' : snapshot.connection === 'connecting' ? 'Call connecting' : 'Call idle'}
        </span>
      </header>

      {!sessionId ? (
        <article className="live-chat-card live-chat-empty" role="status">
          <h3>Select a Chat session</h3>
          <p>Choose or create a Chat session to configure its character. Presence changes below update your user defaults.</p>
        </article>
      ) : (
        <CharacterModePanel sessionId={sessionId} />
      )}

      <LiveConversationControls sessionId={sessionId} />
      <LiveVoiceCalibrationPanel />
      <LivePronunciationPanel sessionId={sessionId} />

      <section className="live-chat-card" aria-labelledby="live-chat-call-heading">
        <header>
          <div>
            <p className="eyebrow">Call preview</p>
            <h3 id="live-chat-call-heading">Live conversation</h3>
            <p>This page controls the same microphone, STT, LLM, and PCM session used by Chats.</p>
          </div>
          <button type="button" onClick={toggleCall}>{snapshot.connected ? 'End Call' : 'Start Call'}</button>
        </header>
        <dl className="live-chat-metrics">
          <div><dt>Identity</dt><dd>{snapshot.identity}</dd></div>
          <div><dt>State</dt><dd>{snapshot.state}</dd></div>
          <div><dt>Floor</dt><dd>{snapshot.floorOwner}</dd></div>
          <div><dt>Duplex</dt><dd>{duplexLabel}</dd></div>
        </dl>
        {callStatus ? <p className="live-chat-note" role="status">{callStatus}</p> : null}
      </section>

      <LiveConversationEvaluationPanel />
    </section>
  );
}
