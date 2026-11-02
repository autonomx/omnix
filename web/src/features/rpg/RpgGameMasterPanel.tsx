import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { api } from './api/gateway';
import type { components } from './api/generated';
import './RpgGameMasterPanel.css';

type GameMasterEntry = components['schemas']['RpgGameMasterEntry'];
type GameMasterResponse = components['schemas']['RpgGameMasterResponse'];

function selectedSessionId(): string {
  if (typeof window === 'undefined') return '';
  try {
    return window.localStorage.getItem('omnix:rpg:selected-session-id')?.trim() ?? '';
  } catch {
    return '';
  }
}

const WISH_SAID: Record<string, (value: string) => string> = {
  pace: (value) => `a ${value} pace`,
  danger: (value) => `${value} danger`,
  tone: (value) => `a ${value} tone`,
  focus: () => 'more of them',
};

/**
 * Talking to the game master (evolution roadmap EV-0): the player asks about the campaign, as at a table. A question
 * changes nothing; an answer that would tell a secret is withheld. A wish the game master offers is a card to confirm.
 */
export function RpgGameMasterPanel() {
  const sessionId = selectedSessionId();
  const [entries, setEntries] = useState<GameMasterEntry[]>([]);
  const [question, setQuestion] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [noted, setNoted] = useState('');

  useEffect(() => {
    let active = true;
    if (!sessionId) return () => { active = false; };
    void api.GET('/api/rpg/sessions/{session_id}/game-master', { params: { path: { session_id: sessionId } } })
      .then(({ data }) => {
        if (active) setEntries(((data as GameMasterResponse | undefined)?.entries ?? []) as GameMasterEntry[]);
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, [sessionId]);

  const ask = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const asked = question.trim();
    if (!asked || !sessionId) return;
    setPending(true);
    setError('');
    try {
      const { data, error: failed } = await api.POST('/api/rpg/sessions/{session_id}/game-master', {
        params: { path: { session_id: sessionId } },
        body: { question: asked },
      });
      const entry = (data as GameMasterResponse | undefined)?.entry;
      if (failed || !entry) {
        setError('The game master could not answer just now.');
        return;
      }
      setEntries((rows) => [entry as GameMasterEntry, ...rows]);
      setQuestion('');
    } finally {
      setPending(false);
    }
  };

  const confirmWish = async (wish: { kind: string; value: string }) => {
    if (!sessionId) return;
    const said = (WISH_SAID[wish.kind] ?? (() => wish.value))(wish.value);
    const { error: failed } = await api.POST('/api/rpg/sessions/{session_id}/turn', {
      params: { path: { session_id: sessionId } },
      body: { command: `Note: ${said}.`, preference: wish },
    });
    setNoted(failed ? 'The wish could not be noted.' : `Noted: ${said}.`);
  };

  if (!sessionId) {
    return <p className="rpg-gm-empty">Start a campaign to talk to its game master.</p>;
  }
  return (
    <div className="rpg-gm-panel">
      <form className="rpg-gm-ask" onSubmit={(event) => void ask(event)}>
        <label htmlFor="rpg-gm-question">Ask the game master</label>
        <div className="rpg-gm-ask-row">
          <input
            id="rpg-gm-question"
            maxLength={1000}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="What is going on here? What could I do next?"
            value={question}
          />
          <button disabled={pending || !question.trim()} type="submit">{pending ? 'Asking…' : 'Ask'}</button>
        </div>
      </form>
      {error ? <p className="rpg-gm-error" role="alert">{error}</p> : null}
      {noted ? <p className="rpg-gm-noted" role="status">{noted}</p> : null}
      <ol className="rpg-gm-log" aria-label="Your questions to the game master">
        {entries.map((entry) => (
          <li key={entry.id}>
            <p className="rpg-gm-question"><strong>You:</strong> {entry.question}</p>
            <p className={entry.withheld ? 'rpg-gm-answer rpg-gm-withheld' : 'rpg-gm-answer'}>
              <strong>Game master:</strong> {entry.answer}
            </p>
            {entry.wish ? (
              <button className="rpg-gm-wish" onClick={() => void confirmWish(entry.wish as { kind: string; value: string })} type="button">
                Note: {(WISH_SAID[entry.wish.kind] ?? (() => entry.wish?.value ?? ''))(entry.wish.value)}?
              </button>
            ) : null}
          </li>
        ))}
      </ol>
    </div>
  );
}
