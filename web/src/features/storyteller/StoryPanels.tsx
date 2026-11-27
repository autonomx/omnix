/** Presentational parts of the story stage: mode switch, versions, actions, outline and text. */
import { useState } from 'react';
import type { OmnixModuleDefinition } from '../../app/modules';
import type { StoryVersionSummary } from './api/storyClient';
import { ManuscriptOutlineChapter, StoryQuickActionMode, StoryWorkspaceMode, quickActions } from './storyModel';
import { type ManuscriptItem, shortDate, versionLabel } from './storyProjectModel';

export function StoryModeSwitch({ mode, onChange }: { mode: StoryWorkspaceMode; onChange: (mode: StoryWorkspaceMode) => void }) {
  return (
    <section className="storyteller-mode-switch" aria-label="Storyteller mode">
      <button className={mode === 'writing' ? 'active' : ''} type="button" onClick={() => onChange('writing')}>
        <strong>Writing Mode</strong>
        <span>Draft, revise, save, and export manuscripts.</span>
      </button>
      <button className={mode === 'story' ? 'active' : ''} type="button" onClick={() => onChange('story')}>
        <strong>Interactive Story Mode</strong>
        <span>Read a page, make a move, and let AI continue.</span>
      </button>
    </section>
  );
}

export function StoryEmptyState({ isLoading, module }: { isLoading: boolean; module: OmnixModuleDefinition }) {
  if (isLoading) {
    return (
      <div className="storyteller-empty-manuscript" role="status">
        <p className="eyebrow">Story</p>
        <p>Loading the story…</p>
      </div>
    );
  }
  return (
    <div className="storyteller-empty-manuscript" role="status">
      <p className="eyebrow">Feature module</p>
      <h3>{module.label}</h3>
      <p>{module.summary}</p>
      <p>Start with a premise, choose a tone, then generate the first scene.</p>
    </div>
  );
}

/** The project's versions, newest first, each one restorable (ST-1.6). */
export function StoryVersions({ versions, disabled, onRestore, onCompare }: {
  versions: StoryVersionSummary[];
  disabled: boolean;
  onRestore: (version: StoryVersionSummary) => void;
  /** Reads the version against the manuscript before restoring it (ST-6.3). */
  onCompare?: (version: StoryVersionSummary) => void;
}) {
  if (!versions.length) return null;
  const newestFirst = versions.slice().sort((left, right) => right.version_number - left.version_number);
  return (
    <section className="storyteller-versions" aria-label="Story versions">
      <p className="eyebrow">Versions</p>
      <ol>
        {newestFirst.map((version) => (
          <li key={version.id}>
            <span><strong>v{version.version_number}</strong> {versionLabel(version)}</span>
            <small>{shortDate(version.created_at)}</small>
            {onCompare ? (
              <button aria-label={`Compare version ${version.version_number}`} type="button" onClick={() => onCompare(version)}>
                Compare
              </button>
            ) : null}
            <button
              aria-label={`Restore version ${version.version_number}`}
              disabled={disabled}
              type="button"
              onClick={() => onRestore(version)}
            >
              Restore
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}

export function StoryActionBar({ disabled, onAction }: { disabled: boolean; onAction: (action: StoryQuickActionMode) => void }) {
  return (
    <section className="storyteller-action-bar" aria-label="Story actions">
      {quickActions.map((action) => (
        <button disabled={disabled} key={action.mode} type="button" onClick={() => onAction(action.mode)}>
          <strong>{action.label}</strong>
          <span>{action.description}</span>
        </button>
      ))}
    </section>
  );
}

export function StoryOutline({ chapters, selectedChapter, disabled, onAddChapter, onSelect }: {
  chapters: ManuscriptOutlineChapter[];
  /** Holds Add chapter while a job is being queued. */
  disabled: boolean;
  selectedChapter: number;
  onAddChapter: () => void;
  onSelect: (chapterNumber: number, targetId: string) => void;
}) {
  const [showScenes, setShowScenes] = useState(true);
  return (
    <aside className="storyteller-outline" aria-label="Story outline">
      <div className="storyteller-panel-heading compact">
        <p className="eyebrow">Outline</p>
        <button
          aria-expanded={showScenes}
          aria-label={showScenes ? 'Collapse outline scenes' : 'Expand outline scenes'}
          type="button"
          onClick={() => setShowScenes((current) => !current)}
        >
          ☰
        </button>
      </div>
      {chapters.map((chapter) => (
        <article className={selectedChapter === chapter.number ? 'active' : ''} key={chapter.id}>
          <button type="button" onClick={() => onSelect(chapter.number, chapter.id)}>
            <strong>{chapter.label}</strong>
            <span>{chapter.title}</span>
          </button>
          {showScenes ? <ol>
            {chapter.scenes.map((scene, sceneIndex) => (
              <li className={selectedChapter === chapter.number && sceneIndex === 0 ? 'active' : ''} key={scene.id}>
                <button type="button" onClick={() => onSelect(chapter.number, scene.id)}>
                  <span>{scene.label}</span>
                  <strong>{scene.title}</strong>
                </button>
              </li>
            ))}
          </ol> : null}
        </article>
      ))}
      <button className="storyteller-add-chapter" disabled={disabled} type="button" onClick={onAddChapter}>Add chapter</button>
    </aside>
  );
}

/** The manuscript's chapter line, reading time and title (ST-6.4). */
export function ManuscriptHeading({ chapter, minutes, title }: { chapter: string; minutes: number; title: string }) {
  return (
    <>
      <div className="storyteller-manuscript-meta">
        <span>{chapter}</span>
        <span>{minutes} min read</span>
      </div>
      <h2>{title}</h2>
      <div className="storyteller-flourish" aria-hidden="true"><span /><strong>◇</strong><span /></div>
    </>
  );
}

/**
 * Headings, narration, and spoken lines with the speaker in the margin; a speaker not in the cast is flagged.
 * `speaking` marks the line being read aloud, counted among the narration and spoken lines.
 */
export function ManuscriptLines({ items, speaking = null }: { items: ManuscriptItem[]; speaking?: number | null }) {
  let line = -1;
  return items.map((item, index) => {
    const key = `${item.kind}-${index}`;
    if (item.kind === 'chapter') return <h3 id={item.id} key={key} tabIndex={-1}>{item.text}</h3>;
    if (item.kind === 'scene') return <h4 id={item.id} key={key} tabIndex={-1}>{item.text}</h4>;
    line += 1;
    const heard = line === speaking;
    const current = heard ? { 'aria-current': true as const } : {};
    const source = { 'data-page-id': item.pageId, 'data-block-index': item.block };
    if (item.kind === 'narration') {
      return <p className={heard ? 'storyteller-line-speaking' : undefined} key={key} {...current} {...source}>{item.text}</p>;
    }
    const classes = ['storyteller-line', item.unverified ? 'storyteller-line-unverified' : '', heard ? 'storyteller-line-speaking' : '']
      .filter(Boolean).join(' ');
    return (
      <p className={classes} key={key} {...current} {...source}>
        <span className="storyteller-line-speaker">
          {item.speakerName}
          {item.unverified ? <small title="This speaker is not in the story's cast">not in cast</small> : null}
        </span>
        <span className="storyteller-line-text">{item.text}</span>
      </p>
    );
  });
}
