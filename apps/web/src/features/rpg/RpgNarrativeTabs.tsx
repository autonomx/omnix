import { useMemo, useState } from 'react';
import type { RpgJournalDetailPreview, RpgJournalEntryPreview } from './rpgUiState';

type RpgNarrativeTab = 'journal' | 'dialogue' | 'turns';

interface RpgNarrativeTabsProps {
  journalEntries: RpgJournalEntryPreview[];
  journalDetail: RpgJournalDetailPreview;
  recentEvents: string[];
}

const tabs: Array<{ id: RpgNarrativeTab; label: string }> = [
  { id: 'journal', label: 'Journal' },
  { id: 'dialogue', label: 'Dialogue log' },
  { id: 'turns', label: 'Turn history' },
];

export function RpgNarrativeTabs({ journalEntries, journalDetail, recentEvents }: RpgNarrativeTabsProps) {
  const [activeTab, setActiveTab] = useState<RpgNarrativeTab>('journal');
  const dialogueRows = useMemo(() => buildDialogueRows(journalEntries, recentEvents), [journalEntries, recentEvents]);
  const turnRows = useMemo(() => buildTurnRows(journalEntries), [journalEntries]);

  return (
    <section className="rpg-card rpg-journal-card">
      <div className="rpg-tabs" role="tablist" aria-label="RPG logs">
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
      {activeTab === 'journal' ? <JournalPanel journalDetail={journalDetail} journalEntries={journalEntries} /> : null}
      {activeTab === 'dialogue' ? <DialoguePanel dialogueRows={dialogueRows} /> : null}
      {activeTab === 'turns' ? <TurnHistoryPanel turnRows={turnRows} /> : null}
    </section>
  );
}

function JournalPanel({ journalEntries, journalDetail }: Pick<RpgNarrativeTabsProps, 'journalEntries' | 'journalDetail'>) {
  return (
    <div aria-labelledby="rpg-journal-tab" className="rpg-journal-grid" id="rpg-journal-panel" role="tabpanel">
      <div className="rpg-journal-list">
        {journalEntries.map((entry, index) => (
          <article className={index === 0 ? 'active' : undefined} key={`${entry.time}:${entry.title}`}>
            <span aria-hidden="true" />
            <div>
              <strong>{entry.time}</strong>
              <p>{entry.title}</p>
            </div>
          </article>
        ))}
      </div>
      <article className="rpg-journal-detail">
        <h3>{journalDetail.title}</h3>
        <p>{journalDetail.detail}</p>
        <ul>
          {journalDetail.bullets.map((bullet) => (
            <li key={bullet}>{bullet}</li>
          ))}
        </ul>
        <div className="rpg-chip-row">
          {journalDetail.tags.map((tag) => (
            <span key={tag}>{tag}</span>
          ))}
        </div>
      </article>
    </div>
  );
}

function DialoguePanel({ dialogueRows }: { dialogueRows: RpgJournalEntryPreview[] }) {
  return (
    <div aria-labelledby="rpg-dialogue-tab" className="rpg-journal-grid" id="rpg-dialogue-panel" role="tabpanel">
      <div className="rpg-journal-list">
        {dialogueRows.map((row, index) => (
          <article className={index === 0 ? 'active' : undefined} key={`${row.time}:${row.title}`}>
            <span aria-hidden="true" />
            <div>
              <strong>{row.time}</strong>
              <p>{row.title}</p>
            </div>
          </article>
        ))}
      </div>
      <article className="rpg-journal-detail">
        <h3>Dialogue log</h3>
        <p>Conversation-facing timeline entries extracted from the selected RPG session.</p>
        <ul>
          {dialogueRows.map((row) => (
            <li key={`${row.time}:${row.detail}`}>{row.detail}</li>
          ))}
        </ul>
        <div className="rpg-chip-row">
          <span>Conversation</span>
          <span>Session timeline</span>
          <span>Replay-safe</span>
        </div>
      </article>
    </div>
  );
}

function TurnHistoryPanel({ turnRows }: { turnRows: RpgJournalEntryPreview[] }) {
  return (
    <div aria-labelledby="rpg-turns-tab" className="rpg-journal-grid" id="rpg-turns-panel" role="tabpanel">
      <div className="rpg-journal-list">
        {turnRows.map((row, index) => (
          <article className={index === 0 ? 'active' : undefined} key={`${row.time}:${row.title}`}>
            <span aria-hidden="true" />
            <div>
              <strong>{row.time}</strong>
              <p>{row.title}</p>
            </div>
          </article>
        ))}
      </div>
      <article className="rpg-journal-detail">
        <h3>Turn history</h3>
        <p>Replay-safe command and event timeline for the selected RPG session.</p>
        <ul>
          {turnRows.map((row) => (
            <li key={`${row.time}:${row.detail}`}>{row.detail}</li>
          ))}
        </ul>
        <div className="rpg-chip-row">
          <span>Deterministic</span>
          <span>Turn log</span>
          <span>Checkpoint aware</span>
        </div>
      </article>
    </div>
  );
}

function buildDialogueRows(journalEntries: RpgJournalEntryPreview[], recentEvents: string[]): RpgJournalEntryPreview[] {
  const dialogueLikeEntries = journalEntries.filter((entry) => isDialogueLike(entry.title) || isDialogueLike(entry.detail));
  if (dialogueLikeEntries.length) {
    return dialogueLikeEntries;
  }

  return recentEvents.slice(0, 6).map((event, index) => ({
    time: `Event ${index + 1}`,
    title: speakerFromEvent(event) ?? 'Narration',
    detail: event,
  }));
}

function buildTurnRows(journalEntries: RpgJournalEntryPreview[]): RpgJournalEntryPreview[] {
  return journalEntries.slice(0, 6).map((entry, index) => ({
    time: entry.time || `Turn ${index + 1}`,
    title: entry.title || `Turn ${index + 1}`,
    detail: entry.detail,
  }));
}

function isDialogueLike(value: string): boolean {
  const normalized = value.toLowerCase();
  return normalized.includes('dialogue') || normalized.includes('speaks') || normalized.includes('says') || value.includes(':');
}

function speakerFromEvent(event: string): string | undefined {
  const [speaker] = event.split(':');
  return speaker && speaker !== event ? speaker.trim() : undefined;
}
