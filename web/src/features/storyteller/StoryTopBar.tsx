import { useRef } from 'react';
import type { StoryExportFormat } from './api/storyClient';
import type { SaveFeedback } from './storyModel';

/** What the Export menu offers: the manuscript as Markdown, or as a book file the server builds (ST-6.5). */
export const exportChoices: Array<{ format: 'markdown' | StoryExportFormat; label: string }> = [
  { format: 'markdown', label: 'Export Markdown' },
  { format: 'epub', label: 'Export EPUB' },
  { format: 'docx', label: 'Export Word (DOCX)' },
  { format: 'pdf', label: 'Export PDF' },
];

/**
 * The story's bar above the manuscript (ST-6.4): its title, premise and size, what last happened, and the
 * whole-project actions: save a version, export, narrate in Audiobook, move to Trash.
 */
export function StoryTopBar({ title, premise, providerLabel, wordCount, chapterCount, canPersistStory, canTrash, saveFeedback, onSave, onExport, onNarrate, onTrash }: {
  title: string;
  premise: string;
  providerLabel: string;
  wordCount: number;
  chapterCount: number;
  canPersistStory: boolean;
  canTrash: boolean;
  saveFeedback: SaveFeedback | null;
  onSave: () => void;
  onExport: (format: 'markdown' | StoryExportFormat) => void;
  /** Hands the story to Audiobook (ST-4.4). */
  onNarrate: () => void;
  onTrash: () => void;
}) {
  const menu = useRef<HTMLDetailsElement>(null);
  return (
    <header className="storyteller-project-header">
      <div className="storyteller-cover" aria-hidden="true" />
      <div className="storyteller-project-copy">
        <h1>{title}</h1>
        <p>{premise || 'A new story draft.'}</p>
        <p className="storyteller-project-stats">
          <span>{wordCount.toLocaleString()} words</span>
          <span>{chapterCount === 1 ? '1 chapter' : `${chapterCount} chapters`}</span>
          <span>{providerLabel}</span>
        </p>
        {saveFeedback ? <p className={`storyteller-persist-feedback ${saveFeedback.kind}`} role="status">{saveFeedback.message}</p> : null}
      </div>
      <div className="storyteller-project-actions">
        <button disabled={!canPersistStory} type="button" onClick={onSave}>Save version</button>
        <details className="storyteller-export-menu" ref={menu}>
          <summary className="storyteller-primary-action">Export</summary>
          <div className="storyteller-export-choices">
            {exportChoices.map((choice) => (
              <button
                disabled={!canPersistStory}
                key={choice.format}
                type="button"
                onClick={() => { if (menu.current) menu.current.open = false; onExport(choice.format); }}
              >
                {choice.label}
              </button>
            ))}
          </div>
        </details>
        <button disabled={!canPersistStory} type="button" onClick={onNarrate}>Narrate in Audiobook</button>
        <button disabled={!canTrash} type="button" onClick={onTrash}>Move to Trash</button>
      </div>
    </header>
  );
}
