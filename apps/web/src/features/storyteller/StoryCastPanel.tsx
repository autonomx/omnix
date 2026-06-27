import { useEffect, useMemo, useState } from 'react';
import { readStorySnapshot } from './StoryAudioPanel';
import { addStoryCharacter, deriveStoryCast, loadStoryCast, saveStoryCast, type StoryCharacter } from './storyCast';

export function StoryCastPanel() {
  const [snapshot, setSnapshot] = useState(() => readStorySnapshot());
  const [cast, setCast] = useState<StoryCharacter[]>(() => deriveStoryCast(snapshot.text, loadStoryCast(snapshot.fingerprint)));
  const [newCharacterName, setNewCharacterName] = useState('');
  const nonNarratorCount = useMemo(() => cast.filter((character) => character.id !== 'narrator').length, [cast]);

  useEffect(() => {
    const refreshCast = () => {
      const nextSnapshot = readStorySnapshot();
      setSnapshot((current) => current.fingerprint === nextSnapshot.fingerprint ? current : nextSnapshot);
      setCast((current) => {
        const stored = loadStoryCast(nextSnapshot.fingerprint);
        const next = deriveStoryCast(nextSnapshot.text, stored.length > 1 ? stored : current);
        saveStoryCast(nextSnapshot.fingerprint, next);
        return next;
      });
    };
    refreshCast();
    const intervalId = window.setInterval(refreshCast, 1_500);
    window.addEventListener('focus', refreshCast);
    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener('focus', refreshCast);
    };
  }, []);

  function addManualCharacter(): void {
    const next = addStoryCharacter(cast, newCharacterName);
    setCast(next);
    saveStoryCast(snapshot.fingerprint, next);
    setNewCharacterName('');
  }

  return (
    <section className="storyteller-cast-panel" aria-label="Story cast registry">
      <div className="storyteller-cast-heading">
        <div><p className="eyebrow">Story cast</p><h3>Character registry</h3></div>
        <strong>{nonNarratorCount} characters</strong>
      </div>
      <p>Characters are saved with stable ids so future voice assignments target the character instead of display text.</p>
      <div className="storyteller-cast-list">
        {cast.map((character) => (
          <article key={character.id} className="storyteller-cast-card">
            <div><strong>{character.displayName}</strong><span>{character.role} · {character.detectedFrom}</span></div>
            <small>{character.aliases.join(', ')}</small>
          </article>
        ))}
      </div>
      <div className="storyteller-cast-add">
        <input aria-label="New character name" placeholder="Add character name" value={newCharacterName} onChange={(event) => setNewCharacterName(event.currentTarget.value)} />
        <button type="button" onClick={addManualCharacter} disabled={!newCharacterName.trim()}>Add</button>
      </div>
    </section>
  );
}
