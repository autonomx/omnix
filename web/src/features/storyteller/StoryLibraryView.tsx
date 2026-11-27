/** The library view: every story at a glance, to open, rename and re-premise, or move to Trash. */
import './StoryLibraryView.css';
import { useMemo, useState } from 'react';
import type { StoryProjectSummary } from './api/storyClient';
import { premiseMaxChars, type SaveFeedback, truncate } from './storyModel';

type LibraryFilter = 'all' | 'writing' | 'interactive';
type LibrarySort = 'updated' | 'title' | 'longest';

const filters: Array<{ id: LibraryFilter; label: string }> = [
  { id: 'all', label: 'All' },
  { id: 'writing', label: 'Stories' },
  { id: 'interactive', label: 'Interactive' },
];
/** A story's title as the server caps it (contracts.TITLE_MAX_CHARS). */
const titleMaxChars = 200;

export interface StoryDetails { title: string; premise: string }

const storyName = (story: StoryProjectSummary) => story.title.trim() || 'Untitled story';
const updatedOn = (value: string) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
};

/** The stories shown: those matching the search and filter, in the order chosen. */
export function libraryStories(stories: StoryProjectSummary[], query: string, filter: LibraryFilter, sort: LibrarySort) {
  const words = query.trim().toLocaleLowerCase();
  const shown = stories.filter((story) => (filter === 'all' || (filter === 'interactive') === (story.mode === 'interactive'))
    && (!words || `${story.title}\n${story.premise}`.toLocaleLowerCase().includes(words)));
  const order: Record<LibrarySort, (a: StoryProjectSummary, b: StoryProjectSummary) => number> = {
    updated: (a, b) => b.updated_at.localeCompare(a.updated_at),
    title: (a, b) => storyName(a).localeCompare(storyName(b)),
    longest: (a, b) => b.word_count - a.word_count,
  };
  return [...shown].sort(order[sort]);
}

function StoryDetailsForm({ story, onSave, onCancel }: {
  story: StoryProjectSummary;
  onSave: (details: StoryDetails) => Promise<boolean>;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState(story.title);
  const [premise, setPremise] = useState(story.premise);
  const [saving, setSaving] = useState(false);
  return (
    <form
      className="storyteller-library-details"
      onSubmit={(event) => {
        event.preventDefault();
        setSaving(true);
        void onSave({ title: title.trim(), premise: premise.trim() }).then((saved) => (saved ? onCancel() : setSaving(false)));
      }}
    >
      <label>Title<input autoFocus maxLength={titleMaxChars} placeholder="Untitled story" value={title} onChange={(event) => setTitle(event.target.value)} /></label>
      <label>
        Premise
        <textarea maxLength={premiseMaxChars} rows={3} value={premise} onChange={(event) => setPremise(event.target.value)} />
      </label>
      <div className="storyteller-library-card-actions">
        <button disabled={saving} type="submit">{saving ? 'Saving…' : 'Save'}</button>
        <button disabled={saving} type="button" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

function StoryCard({ story, active, editing, onOpen, onEdit, onSave, onCancel, onTrash }: {
  story: StoryProjectSummary;
  active: boolean;
  editing: boolean;
  onOpen: () => void;
  onEdit: () => void;
  onSave: (details: StoryDetails) => Promise<boolean>;
  onCancel: () => void;
  onTrash: () => void;
}) {
  const name = storyName(story);
  return (
    <article aria-label={name} className={`storyteller-library-card${active ? ' active' : ''}`}>
      <header>
        <span className="storyteller-library-kind">{story.mode === 'interactive' ? 'Interactive' : 'Story'}</span>
        {active ? <span className="storyteller-library-open-now">Open now</span> : null}
      </header>
      {editing ? <StoryDetailsForm story={story} onCancel={onCancel} onSave={onSave} /> : (
        <>
          <h4>{name}</h4>
          <p>{story.premise.trim() ? truncate(story.premise.trim(), 180) : 'No premise yet.'}</p>
          <small>
            {story.page_count} {story.page_count === 1 ? 'page' : 'pages'} • {story.word_count.toLocaleString()} words
            {updatedOn(story.updated_at) ? ` • Updated ${updatedOn(story.updated_at)}` : ''}
          </small>
          <div className="storyteller-library-card-actions">
            <button aria-label={`Open ${name}`} type="button" onClick={onOpen}>Open</button>
            <button aria-label={`Edit details of ${name}`} type="button" onClick={onEdit}>Edit details</button>
            <button aria-label={`Delete ${name}`} className="danger" type="button" onClick={onTrash}>Delete</button>
          </div>
        </>
      )}
    </article>
  );
}

export function StoryLibraryView({ stories, trashCount, activeId, feedback, onOpen, onSaveDetails, onTrash, onNewDraft, onShowTrash, onClose }: {
  stories: StoryProjectSummary[];
  trashCount: number;
  activeId: string | null;
  feedback: SaveFeedback | null;
  onOpen: (projectId: string) => void;
  onSaveDetails: (story: StoryProjectSummary, details: StoryDetails) => Promise<boolean>;
  onTrash: (story: StoryProjectSummary) => void;
  onNewDraft: () => void;
  onShowTrash: () => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<LibraryFilter>('all');
  const [sort, setSort] = useState<LibrarySort>('updated');
  const [editingId, setEditingId] = useState<string | null>(null);
  const shown = useMemo(() => libraryStories(stories, query, filter, sort), [stories, query, filter, sort]);
  return (
    <section aria-label="Story library view" className="storyteller-library-view">
      <div className="storyteller-library-view-heading">
        <div>
          <p className="eyebrow">Library</p>
          <h3>All stories <span>{stories.length}</span></h3>
        </div>
        <div className="storyteller-library-card-actions">
          <button type="button" onClick={onNewDraft}>New story</button>
          <button type="button" onClick={onShowTrash}>Trash ({trashCount})</button>
          <button type="button" onClick={onClose}>Back to story</button>
        </div>
      </div>
      {feedback ? <p className={`storyteller-persist-feedback ${feedback.kind}`} role="status">{feedback.message}</p> : null}
      <div className="storyteller-library-view-tools">
        <input aria-label="Search stories" placeholder="Search titles and premises" type="search" value={query} onChange={(event) => setQuery(event.target.value)} />
        <div className="storyteller-chip-row" role="group" aria-label="Show">
          {filters.map((item) => (
            <button aria-pressed={filter === item.id} className={filter === item.id ? 'active' : ''} key={item.id} type="button" onClick={() => setFilter(item.id)}>
              {item.label}
            </button>
          ))}
        </div>
        <label>
          Sort
          <select value={sort} onChange={(event) => setSort(event.target.value as LibrarySort)}>
            <option value="updated">Recently updated</option>
            <option value="title">Title A–Z</option>
            <option value="longest">Longest first</option>
          </select>
        </label>
      </div>
      {shown.length ? (
        <div className="storyteller-library-grid">
          {shown.map((story) => (
            <StoryCard
              active={story.id === activeId}
              editing={story.id === editingId}
              key={story.id}
              story={story}
              onCancel={() => setEditingId(null)}
              onEdit={() => setEditingId(story.id)}
              onOpen={() => onOpen(story.id)}
              onSave={(details) => onSaveDetails(story, details)}
              onTrash={() => onTrash(story)}
            />
          ))}
        </div>
      ) : (
        <article className="storyteller-library-empty" role="status">
          <strong>{stories.length ? 'No stories match' : 'No stories yet'}</strong>
          <small>{stories.length ? 'Try other words or show all stories.' : 'Stories you write or play appear here.'}</small>
        </article>
      )}
    </section>
  );
}
