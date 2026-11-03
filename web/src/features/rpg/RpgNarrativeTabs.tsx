import { useEffect, useMemo, useRef, useState } from 'react';
import { VirtualList } from '../../design/VirtualList';
import { RpgLinkedText } from './rpgLoreLinks';
import type { RpgJournalDetailPreview, RpgJournalEntryPreview, RpgQuestPreview } from './rpgUiTypes';
import { emptyWorldChanges, type RpgWorldChangesPreview } from './rpgWorldChanges';

export type RpgNarrativeTab = 'journal' | 'quests' | 'changes' | 'history';
type RpgHistoryFilter = 'all' | 'said' | 'did';

interface RpgNarrativeTabsProps {
  initialTab?: RpgNarrativeTab;
  journalEntries: RpgJournalEntryPreview[];
  logEntries: RpgJournalEntryPreview[];
  journalDetail: RpgJournalDetailPreview;
  quests?: RpgQuestPreview[];
  recentEvents: string[];
  worldChanges?: RpgWorldChangesPreview;
}

const tabs: Array<{ id: RpgNarrativeTab; label: string }> = [
  { id: 'journal', label: 'Journal' },
  { id: 'quests', label: 'Quests' },
  { id: 'changes', label: 'What has changed' },
  { id: 'history', label: 'History' },
];

const historyFilters: Array<{ id: RpgHistoryFilter; label: string }> = [
  { id: 'all', label: 'Everything' },
  { id: 'said', label: 'What was said' },
  { id: 'did', label: 'What you did' },
];

const emptyHistoryRow: RpgJournalEntryPreview = {
  time: 'History',
  title: 'Nothing yet',
  detail: 'What happens is kept here.',
};

const emptyDialogueRow: RpgJournalEntryPreview = {
  time: 'Dialogue',
  title: 'No conversations yet',
  detail: 'What people say to you is kept here.',
};

const emptyTurnRow: RpgJournalEntryPreview = {
  time: 'Turn history',
  title: 'Nothing done yet',
  detail: 'What you do is kept here, turn by turn.',
};

export function RpgNarrativeTabs({
  initialTab = 'journal', journalEntries, logEntries, journalDetail, quests = [], recentEvents, worldChanges = emptyWorldChanges,
}: RpgNarrativeTabsProps) {
  const [activeTab, setActiveTab] = useState<RpgNarrativeTab>(initialTab);
  const [selectedJournalIndex, setSelectedJournalIndex] = useState(0);

  useEffect(() => {
    setSelectedJournalIndex(0);
  }, [journalEntries]);

  return (
    <section className="rpg-card rpg-journal-card">
      <div className="rpg-tabs" role="tablist" aria-label="Journal">
        {tabs.map((tab) => (
          <button
            aria-controls={`rpg-${tab.id}-panel`}
            aria-selected={activeTab === tab.id}
            className={activeTab === tab.id ? 'active' : undefined}
            id={`rpg-${tab.id}-tab`}
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            role="tab"
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>
      {activeTab === 'journal' ? (
        <JournalPanel
          journalDetail={journalDetail}
          journalEntries={journalEntries}
          onSelectedIndexChange={setSelectedJournalIndex}
          selectedIndex={selectedJournalIndex}
        />
      ) : null}
      {activeTab === 'quests' ? <QuestsPanel quests={quests} /> : null}
      {activeTab === 'changes' ? <WorldChangesPanel worldChanges={worldChanges} /> : null}
      {activeTab === 'history' ? <HistoryPanel logEntries={logEntries} recentEvents={recentEvents} /> : null}
    </section>
  );
}

function JournalPanel({
  journalEntries,
  journalDetail,
  onSelectedIndexChange,
  selectedIndex,
}: Pick<RpgNarrativeTabsProps, 'journalEntries' | 'journalDetail'> & {
  onSelectedIndexChange: (index: number) => void;
  selectedIndex: number;
}) {
  const safeSelectedIndex = journalEntries[selectedIndex] ? selectedIndex : 0;
  const selectedEntry = journalEntries[safeSelectedIndex];
  const detailTitle = selectedEntry?.title ?? journalDetail.title;
  const detailText = selectedEntry?.detail ?? journalDetail.detail;
  // One entry per in-game day: a long campaign's journal renders only the rows in view (WP-9.9).
  const listRef = useRef<HTMLDivElement>(null);
  const indexedEntries = useMemo(() => journalEntries.map((entry, index) => ({ entry, index })), [journalEntries]);

  return (
    <div aria-labelledby="rpg-journal-tab" className="rpg-journal-grid" id="rpg-journal-panel" role="tabpanel">
      <div className="rpg-journal-list" ref={listRef}>
        <VirtualList
          items={indexedEntries}
          getKey={({ entry, index }) => `${index}:${entry.time}:${entry.title}`}
          scrollRef={listRef}
          estimateSize={56}
          renderItem={({ entry, index }) => (
            <article
              aria-pressed={index === safeSelectedIndex}
              className={index === safeSelectedIndex ? 'active' : undefined}
              onClick={() => onSelectedIndexChange(index)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onSelectedIndexChange(index);
                }
              }}
              role="button"
              tabIndex={0}
            >
              <span aria-hidden="true" />
              <div>
                <strong>{entry.time}</strong>
                <p>{entry.title}</p>
              </div>
            </article>
          )}
        />
      </div>
      <article className="rpg-journal-detail">
        <h3>{detailTitle}</h3>
        <p>{detailText}</p>
        <ul>
          {journalDetail.bullets.map((bullet) => <li key={bullet}>{bullet}</li>)}
        </ul>
        {journalDetail.tags.length ? (
          <div className="rpg-chip-row">
            {journalDetail.tags.map((tag) => <span key={tag}>{tag}</span>)}
          </div>
        ) : null}
      </article>
    </div>
  );
}

/** What the hero's decisions changed, as the world's author tells it, where the hero stands with each group, and the
 * word they have heard of what people are about. */
function WorldChangesPanel({ worldChanges }: { worldChanges: RpgWorldChangesPreview }) {
  return (
    <div aria-labelledby="rpg-changes-tab" className="rpg-journal-grid" id="rpg-changes-panel" role="tabpanel">
      <article className="rpg-journal-detail">
        <h3>What has changed</h3>
        {worldChanges.lines.length
          ? <ul>{worldChanges.lines.map((line) => <li key={line}><RpgLinkedText text={line} /></li>)}</ul>
          : <p>Nothing you have done has changed the world yet.</p>}
      </article>
      <article className="rpg-journal-detail">
        <h3>Standing</h3>
        {worldChanges.standing.length
          ? <ul>{worldChanges.standing.map((row) => <li key={row.groupId}><strong>{row.name}</strong>: {row.band}</li>)}</ul>
          : <p>No group has taken notice of you yet.</p>}
      </article>
      {worldChanges.word.length ? (
        <article className="rpg-journal-detail">
          <h3>Word going about</h3>
          <ul>{worldChanges.word.map((line) => <li key={line}><RpgLinkedText text={line} /></li>)}</ul>
        </article>
      ) : null}
    </div>
  );
}

function QuestsPanel({ quests }: { quests: RpgQuestPreview[] }) {
  return (
    <div aria-labelledby="rpg-quests-tab" className="rpg-list-stack" id="rpg-quests-panel" role="tabpanel">
      {quests.length ? quests.map((quest) => (
        <article className="rpg-journal-detail rpg-quest-entry" key={quest.title}>
          <div className="rpg-section-heading">
            <h3>{quest.title}</h3>
            {quest.status ? <span className="rpg-pill">{quest.status}</span> : null}
          </div>
          {quest.detail ? <p>{quest.detail}</p> : null}
        </article>
      )) : <p>No quests yet.</p>}
    </div>
  );
}

/** One history in place of three logs: all of it, what people said, or what the hero did. */
function HistoryPanel({ logEntries, recentEvents }: { logEntries: RpgJournalEntryPreview[]; recentEvents: string[] }) {
  const [filter, setFilter] = useState<RpgHistoryFilter>('all');
  const rows = useMemo(() => {
    if (filter === 'said') return buildDialogueRows(logEntries, recentEvents);
    if (filter === 'did') return buildTurnRows(logEntries);
    return buildAllRows(logEntries, recentEvents);
  }, [filter, logEntries, recentEvents]);
  return (
    <div aria-labelledby="rpg-history-tab" className="rpg-history" id="rpg-history-panel" role="tabpanel">
      <div role="group" aria-label="Show" className="rpg-history-filters">
        {historyFilters.map((row) => (
          <button aria-pressed={filter === row.id} key={row.id} onClick={() => setFilter(row.id)} type="button">{row.label}</button>
        ))}
      </div>
      <ul className="rpg-history-list">
        {rows.map((row, index) => (
          <li key={`${index}:${row.time}:${row.detail}`}>
            <small>{row.time}</small>
            <strong>{row.title}</strong>
            {row.detail !== row.title ? <span>{row.detail}</span> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

function buildAllRows(logEntries: RpgJournalEntryPreview[], recentEvents: string[]): RpgJournalEntryPreview[] {
  const told = new Set(logEntries.map((entry) => entry.detail));
  const events = recentEvents.filter((event) => !told.has(event))
    .map((event, index) => ({ time: `Event ${index + 1}`, title: speakerFromEvent(event) ?? 'Narration', detail: event }));
  const rows = [...logEntries, ...events];
  return rows.length ? rows : [emptyHistoryRow];
}

function buildDialogueRows(journalEntries: RpgJournalEntryPreview[], recentEvents: string[]): RpgJournalEntryPreview[] {
  const dialogueLikeEntries = journalEntries.filter((entry) => isDialogueEntry(entry));
  if (dialogueLikeEntries.length) return dialogueLikeEntries;
  const dialogueLikeEvents = recentEvents
    .map((event, index) => ({ time: `Event ${index + 1}`, title: speakerFromEvent(event) ?? 'Narration', detail: event }))
    .filter((entry) => isDialogueEntry(entry));
  return dialogueLikeEvents.length ? dialogueLikeEvents.slice(0, 6) : [emptyDialogueRow];
}

function buildTurnRows(journalEntries: RpgJournalEntryPreview[]): RpgJournalEntryPreview[] {
  const turnLikeEntries = journalEntries.filter((entry) => isTurnHistoryEntry(entry));
  if (!turnLikeEntries.length) return [emptyTurnRow];
  return turnLikeEntries.slice(0, 6).map((entry, index) => ({
    time: entry.time || `Turn ${index + 1}`,
    title: normalizeTurnTitle(entry.title, index),
    detail: entry.detail,
  }));
}

function isDialogueEntry(entry: RpgJournalEntryPreview): boolean {
  return isDialogueLike(entry.title) || isDialogueLike(entry.detail);
}

function isDialogueLike(value: string): boolean {
  const normalized = value.toLowerCase();
  return normalized.includes('dialogue') || normalized.includes('message') || normalized.includes('replied') || normalized.includes('speaks') || normalized.includes('says') || value.includes(':');
}

function isTurnHistoryEntry(entry: RpgJournalEntryPreview): boolean {
  const normalized = `${entry.title} ${entry.detail}`.toLowerCase();
  return /\b(?:player message|player command|command|queued turn|completed turn|turn job|rpg\.turn|submitted command)\b/.test(normalized);
}

function normalizeTurnTitle(title: string, index: number): string {
  return title.trim() ? title : `Turn ${index + 1}`;
}

function speakerFromEvent(event: string): string | undefined {
  const [speaker] = event.split(':');
  return speaker && speaker !== event ? speaker.trim() : undefined;
}
