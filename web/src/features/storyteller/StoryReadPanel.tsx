import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { loadSettingsProfile, storytellerDefaults } from '../settings';
import type { StoryProject } from './api/storyClient';
import { pronunciationFromText, pronunciationText, storyReadSettings, type StoryReadSettings } from './storyReadSettings';

const presets = ['Dramatic audiobook', 'Calm bedtime', 'Documentary', 'Fast draft', 'Character-forward'];

/**
 * How this story is read aloud (ST-1.7). The account's default lives in Settings; a change here is the
 * project's own override, saved on the project.
 */
export function StoryReadPanel({ project, onChange }: {
  project: StoryProject | null;
  onChange: (readSettings: Record<string, unknown>) => void;
}) {
  const settingsQuery = useQuery({ queryKey: ['settings', 'profile'], queryFn: () => loadSettingsProfile() });
  const defaults = storytellerDefaults(settingsQuery.data?.profile);
  const settings = storyReadSettings(defaults, project?.read_settings);
  const notesSource = pronunciationText(settings.pronunciation);
  const [notes, setNotes] = useState(notesSource);
  useEffect(() => setNotes(notesSource), [project?.id, notesSource]);
  const disabled = !project;

  function update(patch: Partial<StoryReadSettings>): void {
    if (!project) return;
    onChange({ ...(project.read_settings ?? {}), ...patch });
  }
  /** A pause typed in: a cleared or unreadable field is not saved as no pause at all. */
  function updatePause(key: 'pauseParagraphMs' | 'pauseChapterMs', raw: string): void {
    const value = Number(raw);
    if (raw.trim() === '' || !Number.isFinite(value) || value < 0) return;
    update({ [key]: value });
  }

  return (
    <section className="storyteller-cast-panel" aria-label="Story read controls">
      <div className="storyteller-cast-heading">
        <div><p className="eyebrow">Read controls</p><h3>Pacing and style</h3></div>
        <strong>{settings.readStylePreset}</strong>
      </div>
      <p>
        {project
          ? 'Pacing, chapter titles, speed, style and word notes for this story. Settings holds the defaults.'
          : 'Select a story to change how it is read. Settings holds the defaults.'}
      </p>
      <div className="storyteller-voice-cast-table">
        <article className="storyteller-voice-row">
          <div><strong>Style preset</strong><span>Global tone</span></div>
          <select aria-label="Story read style" disabled={disabled} value={settings.readStylePreset} onChange={(event) => update({ readStylePreset: event.currentTarget.value })}>
            {[...new Set([settings.readStylePreset, ...presets])].map((preset) => <option key={preset} value={preset}>{preset}</option>)}
          </select>
          <label><input type="checkbox" disabled={disabled} checked={settings.readChapterTitles} onChange={(event) => update({ readChapterTitles: event.currentTarget.checked })} /> Read chapter titles</label>
        </article>
        <article className="storyteller-voice-row">
          <div><strong>Speed</strong><span>{settings.readSpeed.toFixed(2)}x</span></div>
          <input aria-label="Story read speed" disabled={disabled} type="range" min="0.6" max="1.4" step="0.05" value={settings.readSpeed} onChange={(event) => update({ readSpeed: Number(event.currentTarget.value) })} />
          <span />
        </article>
        <article className="storyteller-voice-row">
          <div><strong>Pauses</strong><span>Paragraph / chapter</span></div>
          <input aria-label="Pause after paragraph" disabled={disabled} type="number" min="0" value={settings.pauseParagraphMs} onChange={(event) => updatePause('pauseParagraphMs', event.currentTarget.value)} />
          <input aria-label="Pause after chapter" disabled={disabled} type="number" min="0" value={settings.pauseChapterMs} onChange={(event) => updatePause('pauseChapterMs', event.currentTarget.value)} />
        </article>
        <article className="storyteller-cast-card">
          <div><strong>Word notes</strong><span>One per line: word: how to say it</span></div>
          <textarea
            aria-label="Word notes"
            disabled={disabled}
            rows={4}
            value={notes}
            onBlur={() => update({ pronunciation: pronunciationFromText(notes) })}
            onChange={(event) => setNotes(event.currentTarget.value)}
          />
        </article>
      </div>
    </section>
  );
}
