import './StoryBible.css';
import { useState } from 'react';
import type { StoryCharacter, StoryCharacterInput, StoryNote, StoryNoteInput, StoryProject } from './api/storyClient';
import {
  type CharacterDraft, acceptCharacter, draftOf, emptyCharacterDraft, withCharacter, withWorldNote, withoutCharacter, withoutNote,
} from './storyBibleModel';
import type { SaveFeedback } from './storyModel';
import { StoryPresetsCard } from './StoryPresetsCard';

type BibleProps = {
  project: StoryProject | null;
  onFeedback: (feedback: SaveFeedback) => void;
};

/** Saves the story bible. Resolves to whether the save took, so a form keeps the writer's text when it did not. */
export type BibleSave = (task: () => Promise<unknown>) => Promise<boolean>;

/** Runs one save of the story bible, holding its buttons while it runs and reporting a failure. */
function useBibleSave(onFeedback: (feedback: SaveFeedback) => void) {
  const [busy, setBusy] = useState(false);
  const save: BibleSave = (task) => {
    setBusy(true);
    return task()
      .then(() => true)
      .catch((caught: unknown) => {
        onFeedback({
          kind: 'error',
          message: caught instanceof Error && caught.message ? caught.message : 'The story bible could not be saved.',
        });
        return false;
      })
      .finally(() => setBusy(false));
  };
  return { busy, save };
}

/**
 * The story bible's cast (ST-2.3), sent with every page so the story keeps its characters. Characters a page
 * proposed wait here as suggestions until the writer accepts or dismisses them. The Characters tab (ST-6.4).
 */
export function StoryCharactersPanel({ project, onFeedback, replaceCharacters }: BibleProps & {
  replaceCharacters: (projectId: string, characters: StoryCharacterInput[]) => Promise<unknown>;
}) {
  const { busy, save } = useBibleSave(onFeedback);
  if (!project) return <p className="storyteller-side-empty">Open or start a story to give it a cast.</p>;
  return <CharactersCard busy={busy} cast={project.characters} onChange={(next) => save(() => replaceCharacters(project.id, next))} />;
}

/** The world notes the story keeps to and the presets it can be told with (ST-2.3, ST-5.2). The World tab (ST-6.4). */
export function StoryWorldPanel({ project, onFeedback, replaceNotes, choosePreset }: BibleProps & {
  replaceNotes: (projectId: string, notes: StoryNoteInput[]) => Promise<unknown>;
  /** Tells the story with a preset, or with none (``''``). */
  choosePreset: (projectId: string, presetId: string) => Promise<unknown>;
}) {
  const { busy, save } = useBibleSave(onFeedback);
  if (!project) return <p className="storyteller-side-empty">Open or start a story to note its world.</p>;
  return (
    <div className="storyteller-bible-cards">
      <WorldNotesCard busy={busy} notes={project.notes} onChange={(next) => save(() => replaceNotes(project.id, next))} />
      <StoryPresetsCard
        activeId={project.preset_id}
        busy={busy}
        notes={project.notes}
        onChange={(next) => save(() => replaceNotes(project.id, next))}
        onUse={(presetId) => save(() => choosePreset(project.id, presetId))}
      />
    </div>
  );
}

function CharactersCard({ busy, cast, onChange }: {
  busy: boolean;
  cast: StoryCharacter[];
  onChange: (characters: StoryCharacterInput[]) => Promise<boolean>;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const accepted = cast.filter((character) => !character.suggested);
  const suggested = cast.filter((character) => character.suggested);
  return (
    <section className="storyteller-bible-card" aria-label="Characters">
      <header><h3>Characters</h3><strong>{accepted.length}</strong></header>
      {suggested.length ? (
        <ul className="storyteller-bible-suggestions" aria-label="Suggested characters">
          {suggested.map((character) => (
            <li key={character.id}>
              <div><strong>{character.name}</strong>{character.description ? <span>{character.description}</span> : null}</div>
              <button type="button" disabled={busy} onClick={() => void onChange(acceptCharacter(cast, character.id))}>Accept {character.name}</button>
              <button type="button" disabled={busy} onClick={() => void onChange(withoutCharacter(cast, character.id))}>Dismiss {character.name}</button>
            </li>
          ))}
        </ul>
      ) : null}
      {accepted.length ? (
        <ul className="storyteller-bible-list">
          {accepted.map((character) => (editing === character.id ? (
            <li key={character.id}>
              <CharacterForm
                busy={busy}
                initial={draftOf(character)}
                label={`Save ${character.name}`}
                onCancel={() => setEditing(null)}
                onSubmit={async (draft) => { const saved = await onChange(withCharacter(cast, draft, character.id)); if (saved) setEditing(null); return saved; }}
              />
            </li>
          ) : (
            <li key={character.id}>
              <div>
                <strong>{character.name}</strong>
                {character.role ? <em>{character.role}</em> : null}
                {character.aliases.length ? <small>Also called {character.aliases.join(', ')}</small> : null}
                {character.description ? <span>{character.description}</span> : null}
              </div>
              <button type="button" disabled={busy} onClick={() => setEditing(character.id)}>Edit {character.name}</button>
              <button type="button" disabled={busy} onClick={() => void onChange(withoutCharacter(cast, character.id))}>Remove {character.name}</button>
            </li>
          )))}
        </ul>
      ) : <p>No characters yet. Add one, or accept those the story suggests.</p>}
      <CharacterForm busy={busy} initial={emptyCharacterDraft} label="Add character" onSubmit={(draft) => onChange(withCharacter(cast, draft))} />
    </section>
  );
}

function CharacterForm({ busy, initial, label, onSubmit, onCancel }: {
  busy: boolean;
  initial: CharacterDraft;
  label: string;
  /** Resolves to whether the save took; the form clears only then. */
  onSubmit: (draft: CharacterDraft) => Promise<boolean>;
  onCancel?: () => void;
}) {
  const [draft, setDraft] = useState(initial);
  const field = (key: keyof CharacterDraft) => ({
    value: draft[key],
    onChange: (event: { currentTarget: { value: string } }) => setDraft({ ...draft, [key]: event.currentTarget.value }),
  });
  return (
    <form
      className="storyteller-bible-form"
      aria-label={label}
      onSubmit={(event) => {
        event.preventDefault();
        void onSubmit(draft).then((saved) => { if (saved && !onCancel) setDraft(emptyCharacterDraft); });
      }}
    >
      <input aria-label="Character name" maxLength={120} placeholder="Name" {...field('name')} />
      <input aria-label="Character role" maxLength={120} placeholder="Role (lead, rival…)" {...field('role')} />
      <input aria-label="Also called" placeholder="Also called (comma separated)" {...field('aliases')} />
      <textarea aria-label="Character description" maxLength={2000} placeholder="Who they are" rows={2} {...field('description')} />
      <div>
        <button type="submit" disabled={busy || !draft.name.trim()}>{label}</button>
        {onCancel ? <button type="button" onClick={onCancel}>Cancel</button> : null}
      </div>
    </form>
  );
}

function WorldNotesCard({ busy, notes, onChange }: {
  busy: boolean;
  notes: StoryNote[];
  onChange: (notes: StoryNoteInput[]) => Promise<boolean>;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const world = notes.filter((note) => note.kind === 'world');
  return (
    <section className="storyteller-bible-card" aria-label="World notes">
      <header><h3>World notes</h3><strong>{world.length}</strong></header>
      {world.length ? (
        <ul className="storyteller-bible-list">
          {world.map((note) => (editing === note.id ? (
            <li key={note.id}>
              <NoteForm
                busy={busy}
                initial={note}
                label={`Save ${note.title || 'note'}`}
                onCancel={() => setEditing(null)}
                onSubmit={async (title, body) => { const saved = await onChange(withWorldNote(notes, title, body, note.id)); if (saved) setEditing(null); return saved; }}
              />
            </li>
          ) : (
            <li key={note.id}>
              <div><strong>{note.title || 'Untitled note'}</strong>{note.body ? <span>{note.body}</span> : null}</div>
              <button type="button" disabled={busy} onClick={() => setEditing(note.id)}>Edit {note.title || 'note'}</button>
              <button type="button" disabled={busy} onClick={() => void onChange(withoutNote(notes, note.id))}>Remove {note.title || 'note'}</button>
            </li>
          )))}
        </ul>
      ) : <p>Places, rules and history the story must keep to.</p>}
      <NoteForm busy={busy} label="Add note" onSubmit={(title, body) => onChange(withWorldNote(notes, title, body))} />
    </section>
  );
}

function NoteForm({ busy, initial, label, onSubmit, onCancel }: {
  busy: boolean;
  initial?: { title: string; body: string };
  label: string;
  /** Resolves to whether the save took; the form clears only then. */
  onSubmit: (title: string, body: string) => Promise<boolean>;
  onCancel?: () => void;
}) {
  const [title, setTitle] = useState(initial?.title ?? '');
  const [body, setBody] = useState(initial?.body ?? '');
  return (
    <form
      className="storyteller-bible-form"
      aria-label={label}
      onSubmit={(event) => {
        event.preventDefault();
        void onSubmit(title, body).then((saved) => { if (saved && !onCancel) { setTitle(''); setBody(''); } });
      }}
    >
      <input aria-label="Note title" maxLength={200} placeholder="Title" value={title} onChange={(event) => setTitle(event.currentTarget.value)} />
      <textarea aria-label="Note text" maxLength={20000} placeholder="What the story must keep to" rows={3} value={body} onChange={(event) => setBody(event.currentTarget.value)} />
      <div>
        <button type="submit" disabled={busy || !(title.trim() || body.trim())}>{label}</button>
        {onCancel ? <button type="button" onClick={onCancel}>Cancel</button> : null}
      </div>
    </form>
  );
}
