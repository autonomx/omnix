import { useState } from 'react';
import type { StoryNote, StoryNoteInput } from './api/storyClient';
import { type PresetDraft, emptyPresetDraft, presetDraftOf, withPreset, withoutNote } from './storyBibleModel';

/**
 * Presets (ST-5.2): a named tone and writing style with instructions on how the story is told. The preset
 * in use gives the story its tone and style, and its instructions go with every page as style notes.
 */
export function StoryPresetsCard({ busy, notes, activeId, onChange, onUse }: {
  busy: boolean;
  notes: StoryNote[];
  activeId: string;
  /** Resolves to whether the save took, so an edit closes and a form clears only then. */
  onChange: (notes: StoryNoteInput[]) => Promise<boolean>;
  onUse: (presetId: string) => Promise<boolean>;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const presets = notes.filter((note) => note.kind === 'preset');
  return (
    <section className="storyteller-bible-card" aria-label="Presets">
      <header><h3>Presets</h3><strong>{presets.length}</strong></header>
      {presets.length ? (
        <ul className="storyteller-bible-list">
          {presets.map((preset) => (editing === preset.id ? (
            <li key={preset.id}>
              <PresetForm
                busy={busy}
                initial={presetDraftOf(preset)}
                label={`Save ${preset.title}`}
                onCancel={() => setEditing(null)}
                onSubmit={async (draft) => { const saved = await onChange(withPreset(notes, draft, preset.id)); if (saved) setEditing(null); return saved; }}
              />
            </li>
          ) : (
            <li key={preset.id}>
              <div>
                <strong>{preset.title}</strong>
                {preset.id === activeId ? <em>In use</em> : null}
                {preset.tone || preset.writing_style ? <small>{[preset.tone, preset.writing_style].filter(Boolean).join(' · ')}</small> : null}
                {preset.body ? <span>{preset.body}</span> : null}
              </div>
              {preset.id === activeId ? (
                <button type="button" disabled={busy} onClick={() => void onUse('')}>Stop using {preset.title}</button>
              ) : (
                <button type="button" disabled={busy} onClick={() => void onUse(preset.id)}>Use {preset.title}</button>
              )}
              <button type="button" disabled={busy} onClick={() => setEditing(preset.id)}>Edit {preset.title}</button>
              <button type="button" disabled={busy} onClick={() => void onChange(withoutNote(notes, preset.id))}>Remove {preset.title}</button>
            </li>
          )))}
        </ul>
      ) : <p>A tone, a style and how to tell the story, kept to use again.</p>}
      <PresetForm busy={busy} initial={emptyPresetDraft} label="Add preset" onSubmit={(draft) => onChange(withPreset(notes, draft))} />
    </section>
  );
}

function PresetForm({ busy, initial, label, onSubmit, onCancel }: {
  busy: boolean;
  initial: PresetDraft;
  label: string;
  onSubmit: (draft: PresetDraft) => Promise<boolean>;
  onCancel?: () => void;
}) {
  const [draft, setDraft] = useState(initial);
  const field = (key: keyof PresetDraft) => ({
    value: draft[key],
    onChange: (event: { currentTarget: { value: string } }) => setDraft({ ...draft, [key]: event.currentTarget.value }),
  });
  return (
    <form
      className="storyteller-bible-form"
      aria-label={label}
      onSubmit={(event) => {
        event.preventDefault();
        void onSubmit(draft).then((saved) => { if (saved && !onCancel) setDraft(emptyPresetDraft); });
      }}
    >
      <input aria-label="Preset name" maxLength={200} placeholder="Name" {...field('title')} />
      <input aria-label="Preset tone" maxLength={80} placeholder="Tone (cozy, bleak…)" {...field('tone')} />
      <input aria-label="Preset writing style" maxLength={80} placeholder="Writing style (terse, lyrical…)" {...field('writingStyle')} />
      <textarea aria-label="Preset instructions" maxLength={20000} placeholder="How the story is told" rows={3} {...field('body')} />
      <div>
        <button type="submit" disabled={busy || !draft.title.trim()}>{label}</button>
        {onCancel ? <button type="button" onClick={onCancel}>Cancel</button> : null}
      </div>
    </form>
  );
}
