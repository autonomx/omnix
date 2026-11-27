import { useState } from 'react';
import type { StoryBlock, StoryCharacter } from './api/storyClient';

/** A block as the editor holds it: the stored block, with a key that stays put as blocks move. */
type DraftBlock = StoryBlock & { key: number };

const blankParagraph = (): StoryBlock => ({ kind: 'narration', text: '', speaker_id: null, attribution: null });

/**
 * The writer's editor over one page's blocks (ST-6.1). A paragraph is narration or a spoken line; a spoken
 * line keeps the speaker the server recorded until the writer picks another, so editing the words never
 * loses the tag. A speaker the writer chose is theirs, so it is no longer marked unverified.
 */
export function StoryPageEditor({ pageNumber, blocks, characters, onSave, onCancel }: {
  pageNumber: number;
  blocks: StoryBlock[];
  characters: StoryCharacter[];
  /** The edited blocks, and the blocks the editor was opened with, which the server checks are still the page's. */
  onSave: (blocks: StoryBlock[], baseBlocks: StoryBlock[]) => Promise<unknown>;
  onCancel: () => void;
}) {
  const [base] = useState(blocks);
  const [draft, setDraft] = useState<DraftBlock[]>(() => blocks.map((block, key) => ({ ...block, key })));
  const [nextKey, setNextKey] = useState(blocks.length);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cast = characters.filter((character) => !character.suggested);

  const change = (key: number, patch: Partial<StoryBlock>) =>
    setDraft((current) => current.map((block) => (block.key === key ? { ...block, ...patch } : block)));
  const addAfter = (key: number) => {
    setDraft((current) => {
      const index = current.findIndex((block) => block.key === key);
      return [...current.slice(0, index + 1), { ...blankParagraph(), key: nextKey }, ...current.slice(index + 1)];
    });
    setNextKey((value) => value + 1);
  };
  const remove = (key: number) => setDraft((current) => current.filter((block) => block.key !== key));

  const save = async () => {
    const kept = draft.filter((block) => block.text.trim()).map(({ key, ...block }) => (void key, { ...block, text: block.text.trim() }));
    if (!kept.length) {
      setError('A page needs at least one paragraph.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave(kept, base);
    } catch (caught) {
      setError(caught instanceof Error && caught.message ? caught.message : 'The page could not be saved.');
      setSaving(false);
    }
  };

  return (
    <form
      aria-label={`Edit page ${pageNumber}`}
      className="storyteller-page-editor"
      onSubmit={(event) => { event.preventDefault(); void save(); }}
    >
      <ol>
        {draft.map((block, index) => {
          const label = `Paragraph ${index + 1}`;
          const speakerKnown = !block.speaker_id || cast.some((character) => character.id === block.speaker_id);
          return (
            <li className={block.kind === 'dialogue' ? 'dialogue' : undefined} key={block.key}>
              <div className="storyteller-page-editor-row">
                <select
                  aria-label={`${label} kind`}
                  value={block.kind ?? 'narration'}
                  onChange={(event) => change(block.key, event.target.value === 'dialogue'
                    ? { kind: 'dialogue' }
                    : { kind: 'narration', speaker_id: null, attribution: null })}
                >
                  <option value="narration">Narration</option>
                  <option value="dialogue">Spoken line</option>
                </select>
                {block.kind === 'dialogue' ? (
                  <select
                    aria-label={`${label} speaker`}
                    value={block.speaker_id ?? ''}
                    onChange={(event) => change(block.key, { speaker_id: event.target.value || null, attribution: null })}
                  >
                    <option value="">Unknown speaker</option>
                    {cast.map((character) => <option key={character.id} value={character.id}>{character.name}</option>)}
                    {speakerKnown ? null : <option value={block.speaker_id ?? ''}>{block.speaker_id} (not in cast)</option>}
                  </select>
                ) : null}
                <button aria-label={`Add a paragraph after paragraph ${index + 1}`} type="button" onClick={() => addAfter(block.key)}>+ Paragraph</button>
                <button aria-label={`Remove paragraph ${index + 1}`} disabled={draft.length === 1} type="button" onClick={() => remove(block.key)}>Remove</button>
              </div>
              <textarea
                aria-label={label}
                rows={Math.min(8, Math.max(2, Math.ceil(block.text.length / 80)))}
                value={block.text}
                onChange={(event) => change(block.key, { text: event.target.value })}
              />
            </li>
          );
        })}
      </ol>
      {error ? <p className="storyteller-persist-feedback error" role="alert">{error}</p> : null}
      <div className="storyteller-page-editor-actions">
        <button className="storyteller-primary-action" disabled={saving} type="submit">{saving ? 'Saving…' : 'Save page'}</button>
        <button disabled={saving} type="button" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}
