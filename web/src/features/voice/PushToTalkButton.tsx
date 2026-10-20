import { useCallback, useEffect, useRef, useState } from 'react';
import { voiceApiClient } from './api/voiceClient';

const WARM_EVERY_MS = 4 * 60 * 1000;
const MAX_SECONDS = 60;

type Phase = 'idle' | 'recording' | 'transcribing';

function recorderType(): string {
  if (typeof MediaRecorder === 'undefined') return '';
  return ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4'].find((type) => MediaRecorder.isTypeSupported?.(type)) ?? '';
}

/** Whether this browser can record a dictation at all. */
export function dictationSupported(): boolean {
  return typeof navigator !== 'undefined' && Boolean(navigator.mediaDevices?.getUserMedia) && typeof MediaRecorder !== 'undefined';
}

/**
 * Hold to talk: records while the button (or Space, while it has focus) is held, then transcribes the
 * utterance with the batch speech-to-text engine, so any language it knows works. While it is on screen
 * the engine is kept warm, so a short utterance does not wait for a cold load.
 */
export function PushToTalkButton({ onText, language = '', label = 'Hold to dictate', className = '' }: {
  onText: (text: string) => void;
  language?: string;
  label?: string;
  className?: string;
}) {
  const [phase, setPhase] = useState<Phase>('idle');
  const [message, setMessage] = useState('');
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const limit = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const warmedAt = useRef(0);
  // Held from press to release; a microphone grant that arrives after release records nothing.
  const held = useRef(false);
  const starting = useRef(false);
  const supported = dictationSupported();

  // Warm when the composer opens, and again when the button is reached after the engine may have
  // unloaded; an idle page does not keep the model loaded.
  const warm = useCallback(() => {
    if (!supported || Date.now() - warmedAt.current < WARM_EVERY_MS) return;
    warmedAt.current = Date.now();
    void voiceApiClient.warmDictation().catch(() => undefined);
  }, [supported]);
  useEffect(() => { warm(); }, [warm]);

  const stop = useCallback(() => {
    held.current = false;
    clearTimeout(limit.current);
    if (recorder.current?.state === 'recording') recorder.current.stop();
  }, []);

  const start = useCallback(async () => {
    if (phase !== 'idle' || !supported || starting.current) return;
    held.current = true;
    starting.current = true;
    setMessage('');
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch {
      setMessage('Allow the microphone to dictate.');
      return;
    } finally {
      starting.current = false;
    }
    if (!held.current) {
      // Released while the browser asked for the microphone (the first use): never record unheld.
      stream.getTracks().forEach((track) => track.stop());
      setMessage('Microphone ready: hold the button while you speak.');
      return;
    }
    const type = recorderType();
    const next = type ? new MediaRecorder(stream, { mimeType: type }) : new MediaRecorder(stream);
    chunks.current = [];
    next.ondataavailable = (event) => { if (event.data.size) chunks.current.push(event.data); };
    next.onstop = () => {
      stream.getTracks().forEach((track) => track.stop());
      const audio = new Blob(chunks.current, { type: next.mimeType || type || 'audio/webm' });
      recorder.current = null;
      if (audio.size < 2000) {
        setPhase('idle');
        setMessage('Hold the button while you speak.');
        return;
      }
      setPhase('transcribing');
      voiceApiClient.dictate(audio, language)
        .then((result) => {
          if (result.text.trim()) onText(result.text.trim());
          else setMessage('No speech was heard.');
        })
        .catch((error: unknown) => setMessage(error instanceof Error ? error.message : 'Dictation failed.'))
        .finally(() => setPhase('idle'));
    };
    recorder.current = next;
    next.start();
    setPhase('recording');
    limit.current = setTimeout(stop, MAX_SECONDS * 1000);
  }, [language, onText, phase, stop, supported]);

  useEffect(() => () => stop(), [stop]);

  if (!supported) return null;
  const busy = phase === 'transcribing';
  return (
    <span className={`voice-ptt ${className}`.trim()}>
      <button
        type="button"
        className={phase === 'recording' ? 'voice-ptt-button recording' : 'voice-ptt-button'}
        aria-label={phase === 'recording' ? 'Recording: release to transcribe' : label}
        aria-pressed={phase === 'recording'}
        disabled={busy}
        onPointerEnter={warm}
        onFocus={warm}
        onPointerDown={(event) => { event.preventDefault(); void start(); }}
        onPointerUp={stop}
        onPointerLeave={stop}
        onKeyDown={(event) => { if ((event.key === ' ' || event.key === 'Enter') && !event.repeat) { event.preventDefault(); void start(); } }}
        onKeyUp={(event) => { if (event.key === ' ' || event.key === 'Enter') { event.preventDefault(); stop(); } }}
      >
        {phase === 'recording' ? 'Release to transcribe' : busy ? 'Transcribing…' : 'Hold to talk'}
      </button>
      {message ? <small role="status">{message}</small> : null}
    </span>
  );
}
