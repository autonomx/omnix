/** The library sidebar: writing projects, interactive ones, and the server's trash (ST-1.2). */
import { StoryLibrarySection, librarySectionLabel, librarySections } from './storyModel';
import type { StoryLibraryEntry } from './storyProjectModel';

export function StoryLibrary({
  entries,
  activeId,
  activeSection,
  trashEntries,
  onNewDraft,
  onSectionChange,
  onSelect,
  onShowTrash,
  onRestore,
  onPurge,
}: {
  entries: StoryLibraryEntry[];
  activeId: string | null;
  activeSection: StoryLibrarySection;
  trashEntries: StoryLibraryEntry[];
  onNewDraft: () => void;
  onSectionChange: (section: StoryLibrarySection) => void;
  onSelect: (projectId: string) => void;
  onShowTrash: () => void;
  onRestore: (entry: StoryLibraryEntry) => void;
  onPurge: (entry: StoryLibraryEntry) => void;
}) {
  const sectionEntries = activeSection === 'interactive'
    ? entries.filter((entry) => entry.mode === 'interactive')
    : entries.filter((entry) => entry.mode !== 'interactive');
  return (
    <aside className="storyteller-library" aria-label="Story library">
      <div className="storyteller-panel-heading compact">
        <p className="eyebrow">Library</p>
        <button aria-label="New story draft" type="button" onClick={onNewDraft}>+</button>
      </div>
      <nav aria-label="Story library sections">
        {librarySections.map((section) => (
          <button
            aria-pressed={activeSection === section.id}
            className={activeSection === section.id ? 'active' : ''}
            key={section.id}
            type="button"
            onClick={() => onSectionChange(section.id)}
          >
            {section.label}
          </button>
        ))}
      </nav>
      <section className="storyteller-library-section" aria-label={`${librarySectionLabel(activeSection)} library pane`}>
        <p className="eyebrow">{librarySectionLabel(activeSection)}</p>
        {activeSection === 'trash' ? (
          trashEntries.length ? (
            <div className="storyteller-recent-list">
              {trashEntries.map((entry) => (
                <article className="storyteller-trash-entry" key={entry.id}>
                  <span className="storyteller-thumb muted" />
                  <div><strong>{entry.title}</strong><small>{entry.subtitle}</small></div>
                  <div className="storyteller-trash-actions">
                    <button aria-label={`Restore ${entry.title}`} type="button" onClick={() => onRestore(entry)}>Restore</button>
                    <button aria-label={`Delete ${entry.title} forever`} type="button" onClick={() => onPurge(entry)}>Delete forever</button>
                  </div>
                </article>
              ))}
            </div>
          ) : <LibrarySectionEmpty section="trash" onNewDraft={onNewDraft} />
        ) : sectionEntries.length ? (
          <div className="storyteller-recent-list">
            {sectionEntries.map((entry) => (
              <LibraryEntryButton activeId={activeId} entry={entry} key={entry.id} onSelect={onSelect} />
            ))}
          </div>
        ) : (
          <LibrarySectionEmpty section={activeSection} onNewDraft={onNewDraft} />
        )}
      </section>
      <section>
        <p className="eyebrow">Recent stories</p>
        <div className="storyteller-recent-list">
          {entries.length ? (
            entries.slice(0, 6).map((entry) => (
              <LibraryEntryButton activeId={activeId} entry={entry} key={entry.id} onSelect={onSelect} />
            ))
          ) : (
            <article>
              <span className="storyteller-thumb muted" />
              <div><strong>No stories yet</strong><small>Generate a story to begin</small></div>
            </article>
          )}
        </div>
      </section>
      <button
        aria-pressed={activeSection === 'trash'}
        className={`storyteller-trash ${activeSection === 'trash' ? 'active' : ''}`}
        type="button"
        title="Stories in Trash"
        onClick={onShowTrash}
      >
        Trash
      </button>
    </aside>
  );
}

export function LibraryEntryButton({ entry, activeId, onSelect }: {
  entry: StoryLibraryEntry;
  activeId: string | null;
  onSelect: (projectId: string) => void;
}) {
  return (
    <button
      aria-pressed={entry.id === activeId}
      className={entry.id === activeId ? 'active' : ''}
      type="button"
      onClick={() => onSelect(entry.id)}
    >
      <span className="storyteller-thumb" />
      <div><strong>{entry.title}</strong><small>{entry.subtitle}</small></div>
    </button>
  );
}

export function LibrarySectionEmpty({ section, onNewDraft }: { section: StoryLibrarySection; onNewDraft: () => void }) {
  const copy: Record<StoryLibrarySection, { title: string; body: string }> = {
    stories: { title: 'No stories yet', body: 'Stories you write appear here.' },
    interactive: { title: 'No interactive stories yet', body: 'Stories you play in Interactive mode appear here.' },
    trash: { title: 'Trash is empty', body: 'Stories moved to Trash can be restored from here.' },
  };
  return (
    <article className="storyteller-library-empty" role="status">
      <strong>{copy[section].title}</strong>
      <small>{copy[section].body}</small>
      {section === 'stories' ? <button type="button" onClick={onNewDraft}>Start blank draft</button> : null}
    </article>
  );
}
