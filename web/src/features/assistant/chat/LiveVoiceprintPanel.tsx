import { useEffect, useRef, useState } from 'react';

import { startTicker } from '../../../shared/timers';
import { voiceApiClient, type VoiceprintStatus } from '../../voice';
import {
  VOICEPRINT_PASSAGES,
  VOICEPRINT_PASSAGE_SECONDS,
  recordVoiceprintPassage,
} from '../workspace/voiceprint-recording';
import { readLiveConversationSettings, updateLiveConversationSettings } from '../workspace/live-voice-conversation-settings';

type Phase = { kind: 'idle' } | { kind: 'recording'; passage: number; secondsLeft: number } | { kind: 'saving' };

export type LiveVoiceprintPanelProps = {
  /** Records one passage (tests replace the microphone). */
  record?: (seconds: number) => Promise<Blob>;
};

/** "Learn my voice": a voiceprint the call compares what it hears with (companion 2.1). */
export function LiveVoiceprintPanel({ record = recordVoiceprintPassage }: LiveVoiceprintPanelProps) {
  const [status, setStatus] = useState<VoiceprintStatus | null>(null);
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' });
  const [message, setMessage] = useState<string | null>(null);
  const [onlyMe, setOnlyMe] = useState(() => readLiveConversationSettings().onlyRespondToMe);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    void voiceApiClient.voiceprintStatus()
      .then((next) => { if (mounted.current) setStatus(next); })
      .catch(() => { if (mounted.current) setMessage('Whether Omnix knows your voice could not be checked.'); });
    return () => { mounted.current = false; };
  }, []);

  async function learn(): Promise<void> {
    if (phase.kind !== 'idle') return;
    setMessage(null);
    const passages: Blob[] = [];
    try {
      for (let index = 0; index < VOICEPRINT_PASSAGES.length; index += 1) {
        let secondsLeft = VOICEPRINT_PASSAGE_SECONDS;
        setPhase({ kind: 'recording', passage: index, secondsLeft });
        const stopTicker = startTicker(() => {
          secondsLeft = Math.max(0, secondsLeft - 1);
          if (mounted.current) setPhase({ kind: 'recording', passage: index, secondsLeft });
        }, 1_000);
        try {
          passages.push(await record(VOICEPRINT_PASSAGE_SECONDS));
        } finally {
          stopTicker();
        }
        if (!mounted.current) return;
      }
      setPhase({ kind: 'saving' });
      const next = await voiceApiClient.enrolVoiceprint(passages);
      if (!mounted.current) return;
      setStatus(next);
      setMessage('Omnix knows your voice now.');
    } catch (error) {
      if (mounted.current) setMessage(error instanceof Error ? error.message : 'Your voice could not be learned.');
    } finally {
      if (mounted.current) setPhase({ kind: 'idle' });
    }
  }

  async function forget(): Promise<void> {
    setMessage(null);
    try {
      setStatus(await voiceApiClient.deleteVoiceprint());
      setMessage('Your voiceprint is deleted.');
    } catch {
      setMessage('Your voiceprint could not be deleted.');
    }
  }

  function changeOnlyMe(next: boolean): void {
    updateLiveConversationSettings({ onlyRespondToMe: next });
    setOnlyMe(next);
  }

  const busy = phase.kind !== 'idle';
  return (
    <section className="live-chat-card" aria-labelledby="live-chat-voiceprint-heading">
      <header>
        <div>
          <p className="eyebrow">Your voice</p>
          <h3 id="live-chat-voiceprint-heading">Learn my voice</h3>
          <p>Read three short passages (about twenty seconds) so calls can tell your voice from the TV or someone else in the room.</p>
        </div>
        {status?.can_enrol ? (
          <button type="button" disabled={busy} onClick={() => void learn()}>
            {busy ? 'Listening…' : status.enrolled ? 'Learn my voice again' : 'Learn my voice'}
          </button>
        ) : null}
      </header>
      {status && !status.can_enrol ? <p className="live-chat-note">Sign up to teach Omnix your voice.</p> : null}
      {phase.kind === 'recording' ? (
        <div role="status" aria-live="polite">
          <p className="live-chat-note">Passage {phase.passage + 1} of {VOICEPRINT_PASSAGES.length}, read it aloud in your normal voice ({phase.secondsLeft} s):</p>
          <blockquote className="live-chat-voiceprint-passage">{VOICEPRINT_PASSAGES[phase.passage]}</blockquote>
        </div>
      ) : null}
      {phase.kind === 'saving' ? <p className="live-chat-note" role="status">Learning your voice…</p> : null}
      {status?.enrolled ? (
        <div className="live-chat-profile-actions">
          <small>Learned {status.created_at ? new Date(status.created_at).toLocaleString() : ''} from {status.samples} passages</small>
          <button type="button" disabled={busy} onClick={() => void forget()}>Delete my voiceprint</button>
        </div>
      ) : null}
      {status?.enrolled ? (
        <div>
          <label className="assistant-voice-toggle">
            <input type="checkbox" checked={onlyMe} onChange={(event) => changeOnlyMe(event.currentTarget.checked)} /> Only respond to me
          </label>
          <p className="live-chat-note">
            Off by default. When on, Omnix holds what another voice says (shown greyed, with “Send anyway”) and lets it
            talk over a reply without stopping it. Each turn waits up to a third of a second to know whose voice it is,
            and how sure that has to be is still provisional.
          </p>
        </div>
      ) : null}
      <p className="live-chat-note">Only the voiceprint is kept, never the recordings.</p>
      {message ? <p className="live-chat-note" role="status">{message}</p> : null}
    </section>
  );
}
