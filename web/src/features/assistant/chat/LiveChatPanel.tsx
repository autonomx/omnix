 
import { useEffect, useState } from 'react';

import {
  liveConversationStore,
  selectLiveChatSnapshot,
  useLiveConversationState,
} from '../workspace/live-conversation-store';
import { CharacterModePanel } from './CharacterModePanel';
import {
  enterLiveChatFullscreen,
  exitLiveChatFullscreen,
  initializeLiveChatFullscreenController,
  useLiveChatFullscreenState,
} from './live-chat-fullscreen-controller';
import { LiveConversationControls } from './LiveConversationControls';
import { LiveConversationEvaluationPanel } from './LiveConversationEvaluationPanel';
import { LiveCallScene } from './LiveCallScene';
import { LiveCallTaskChips } from './LiveCallTaskChips';
import { LiveMuteButton } from './LiveMuteButton';
import { LivePronunciationPanel } from './LivePronunciationPanel';
import { LiveVoiceCalibrationPanel } from './LiveVoiceCalibrationPanel';
import { LiveVoiceprintPanel } from './LiveVoiceprintPanel';
import { LivePortraitEngineCard } from './portrait/LivePortraitEngineCard';
import './LiveChatPanel.css';
import './LiveChatFullscreenEntry.css';

export type LiveChatPanelProps = {
  sessionId: string | null;
  onSessionResolved?: (sessionId: string) => void;
  /** Starts or ends the live call (Chat's call controls). */
  onToggleCall: () => void;
};

/** The page's sections, one tab each (owner request, 2026-11-21). */
const LIVE_CHAT_TABS = [
  ['character', 'Character'],
  ['presence', 'Presence'],
  ['voice', 'Voice'],
  ['video', 'Video'],
  ['call', 'Call'],
] as const;
type LiveChatTab = (typeof LIVE_CHAT_TABS)[number][0];

// The open tab outlives the page, so going back to Live Chat returns to it.
let lastTab: LiveChatTab = 'character';

export function LiveChatPanel({ sessionId, onSessionResolved, onToggleCall }: LiveChatPanelProps) {
  const runtimeState = useLiveConversationState();
  const snapshot = selectLiveChatSnapshot(runtimeState);
  const fullscreen = useLiveChatFullscreenState();
  const [callStatus, setCallStatus] = useState<string | null>(null);
  const [tab, setTab] = useState<LiveChatTab>(lastTab);
  function openTab(next: LiveChatTab): void {
    lastTab = next;
    setTab(next);
  }

  useEffect(() => {
    liveConversationStore.dispatch({ type: 'session', sessionId });
  }, [sessionId]);

  useEffect(() => {
    const dispose = initializeLiveChatFullscreenController();
    return () => {
      dispose();
      void exitLiveChatFullscreen();
    };
  }, []);

  function toggleCall(): void {
    onToggleCall();
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
        <div className="live-chat-page-actions">
          <span className={snapshot.connected ? 'live-chat-status active' : 'live-chat-status'}>
            {snapshot.connected ? 'Call connected' : snapshot.connection === 'connecting' ? 'Call connecting' : 'Call idle'}
          </span>
          <button
            type="button"
            className="live-chat-fullscreen-action"
            aria-pressed={fullscreen.immersive}
            onClick={() => enterLiveChatFullscreen('header')}
          >
            Enter fullscreen
          </button>
        </div>
      </header>

      <div className="live-chat-tabs" role="tablist" aria-label="Live Chat sections">
        {LIVE_CHAT_TABS.map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`live-chat-tab-${id}`}
            aria-controls={`live-chat-section-${id}`}
            aria-selected={tab === id}
            className={tab === id ? 'is-active' : undefined}
            onClick={() => openTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="live-chat-section" role="tabpanel" id={`live-chat-section-${tab}`} aria-labelledby={`live-chat-tab-${tab}`}>
        {tab === 'character' ? (!sessionId ? (
          <article className="live-chat-card live-chat-empty" role="status">
            <h3>Select a Chat session</h3>
            <p>Choose or create a Chat session to configure its character. Presence changes update your user defaults.</p>
          </article>
        ) : (
          <CharacterModePanel sessionId={sessionId} onSessionResolved={onSessionResolved} />
        )) : null}
        {tab === 'presence' ? <LiveConversationControls sessionId={sessionId} /> : null}
        {tab === 'voice' ? (
          <>
            <LiveVoiceCalibrationPanel />
            <LiveVoiceprintPanel />
            <LivePronunciationPanel sessionId={sessionId} />
          </>
        ) : null}
        {tab === 'video' ? <LivePortraitEngineCard /> : null}
        {tab === 'call' ? (
          <>
            <LiveCallPreview
              sessionId={sessionId}
              connected={snapshot.connected}
              metrics={[['Identity', snapshot.identity], ['State', snapshot.state], ['Floor', snapshot.floorOwner], ['Duplex', duplexLabel]]}
              immersive={fullscreen.immersive}
              callStatus={callStatus}
              onToggleCall={toggleCall}
            />
            <LiveConversationEvaluationPanel />
          </>
        ) : null}
      </div>
    </section>
  );
}

function LiveCallPreview({ sessionId, connected, metrics, immersive, callStatus, onToggleCall }: {
  sessionId: string | null;
  connected: boolean;
  metrics: ReadonlyArray<readonly [string, string]>;
  immersive: boolean;
  callStatus: string | null;
  onToggleCall: () => void;
}) {
  return (
    <section className="live-chat-card" aria-labelledby="live-chat-call-heading">
      <header>
        <div>
          <p className="eyebrow">Call preview</p>
          <h3 id="live-chat-call-heading">Live conversation</h3>
          <p>This page controls the same microphone, STT, LLM, and PCM session used by Chats.</p>
        </div>
        <div className="live-chat-call-actions">
          <button
            type="button"
            className="live-chat-secondary-action"
            aria-pressed={immersive}
            onClick={() => enterLiveChatFullscreen('call-card')}
          >
            Fullscreen
          </button>
          <LiveMuteButton className="live-chat-secondary-action" />
          <button type="button" onClick={onToggleCall}>{connected ? 'End Call' : 'Start Call'}</button>
        </div>
      </header>
      <dl className="live-chat-metrics">
        {metrics.map(([term, value]) => <div key={term}><dt>{term}</dt><dd>{value}</dd></div>)}
      </dl>
      <LiveCallScene sessionId={sessionId} />
      <LiveCallTaskChips />
      {callStatus ? <p className="live-chat-note" role="status">{callStatus}</p> : null}
    </section>
  );
}

/** Tests: start each on the first tab. */
export function resetLiveChatTabForTests(): void {
  lastTab = 'character';
}
