import { useEffect, useState } from 'react';
import { api } from './api/gateway';
import type { components } from './api/generated';
import { setVoiceAutoplay, speakResponse, voiceAutoplay } from './rpgVoices';

type Cast = components['schemas']['RpgVoiceCastResponse'];

function selectedSessionId(): string {
  try {
    return window.localStorage.getItem('omnix:rpg:selected-session-id')?.trim() ?? '';
  } catch {
    return '';
  }
}

/**
 * The Voices panel (evolution roadmap EV-13): the narrator and everyone who has spoken, each with their voice, a
 * preview and a choice among the castable voices; and whether responses play by themselves.
 */
export function RpgVoicesPanel() {
  const sessionId = selectedSessionId();
  const [cast, setCast] = useState<Cast | null>(null);
  const [autoplay, setAutoplay] = useState(voiceAutoplay());
  const [status, setStatus] = useState('');

  useEffect(() => {
    if (!sessionId) return;
    void api.GET('/api/rpg/sessions/{session_id}/voices', { params: { path: { session_id: sessionId } } })
      .then(({ data }) => setCast((data as Cast | undefined) ?? null))
      .catch(() => setStatus('The voices could not be loaded.'));
  }, [sessionId]);

  const choose = async (speakerId: string, voiceId: string) => {
    const { data, error } = await api.PUT('/api/rpg/sessions/{session_id}/voices/{speaker_id}', {
      params: { path: { session_id: sessionId, speaker_id: speakerId } }, body: { voice_id: voiceId },
    });
    if (error || !data) {
      setStatus('That voice cannot be chosen.');
      return;
    }
    setCast(data as Cast);
    setStatus('Voice chosen.');
  };

  if (!sessionId) return <p>Start a campaign to hear its voices.</p>;
  return (
    <section className="rpg-voices" aria-label="Voices">
      <label>
        <input checked={autoplay} type="checkbox" onChange={(event) => {
          setAutoplay(event.currentTarget.checked);
          setVoiceAutoplay(event.currentTarget.checked);
        }} /> Play each response when it is ready
      </label>
      {status ? <p role="status">{status}</p> : null}
      <ul className="rpg-voices-cast">
        {(cast?.cast ?? []).map((row) => (
          <li key={row.speaker_id}>
            <label htmlFor={`rpg-voice-${row.speaker_id}`}>{row.name}</label>
            <select id={`rpg-voice-${row.speaker_id}`} value={row.voice_id ?? ''}
              onChange={(event) => void choose(row.speaker_id, event.currentTarget.value)}>
              {(cast?.voices ?? []).map((voice) => (
                <option key={voice.voice_id} value={voice.voice_id}>{voice.name}{voice.description ? ` — ${voice.description}` : ''}</option>
              ))}
            </select>
            <button type="button" onClick={() => void speakResponse(sessionId, [{ speakerId: row.speaker_id, text: `This is the voice of ${row.name}.` }])}>
              Preview
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
