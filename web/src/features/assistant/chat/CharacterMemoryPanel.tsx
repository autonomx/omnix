/** What a character or the System Assistant remembers: to read, correct, add to or forget, with no chat open. */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import {
  ownerMemoryClient,
  type ManagedMemoryRecord,
  type MemoryCategory,
} from './memoryClient';
import { CharacterUnderstandingPanel } from './CharacterUnderstandingPanel';
import './CharacterMemoryPanel.css';

export const SYSTEM_ASSISTANT_MEMORY_OWNER = 'system-assistant';

const CATEGORIES: [MemoryCategory, string][] = [
  ['fact', 'Fact'],
  ['preference', 'Preference'],
  ['relationship', 'Relationship'],
  ['project', 'Project'],
  ['instruction', 'Instruction'],
];
const CATEGORY_LABEL = Object.fromEntries(CATEGORIES) as Record<string, string>;

function savedOn(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString(undefined, { dateStyle: 'medium' });
}

export function CharacterMemoryPanel({ ownerId, ownerName }: { ownerId: string; ownerName: string }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [newContent, setNewContent] = useState('');
  const [newCategory, setNewCategory] = useState<MemoryCategory>('fact');
  const queryKey = ['feature', 'chatbot', 'owner-memory', ownerId];
  const memoryQuery = useQuery({ queryKey, queryFn: () => ownerMemoryClient.read(ownerId) });

  const refreshed = {
    onSuccess: async () => {
      setError(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey }),
        queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'character-data'] }),
      ]);
    },
    onError: (failure: unknown) => setError(failure instanceof Error ? failure.message : 'That memory change failed.'),
  };
  const addMutation = useMutation({
    mutationFn: () => ownerMemoryClient.add(ownerId, newCategory, newContent.trim()),
    ...refreshed,
    onSuccess: async () => {
      setNewContent('');
      await refreshed.onSuccess();
    },
  });
  const approveMutation = useMutation({
    mutationFn: (candidateId: string) => ownerMemoryClient.approve(ownerId, candidateId),
    ...refreshed,
  });
  const dismissMutation = useMutation({
    mutationFn: (candidateId: string) => ownerMemoryClient.dismiss(ownerId, candidateId),
    ...refreshed,
  });

  const records = memoryQuery.data?.records ?? [];
  const suggestions = memoryQuery.data?.suggestions ?? [];

  return <section className="character-dashboard-section character-memory-section" aria-label={`${ownerName} memory`}>
    <header className="character-section-heading">
      <div><h4>What {ownerName} remembers</h4></div>
      {memoryQuery.data ? <small>{records.length.toLocaleString()} {records.length === 1 ? 'memory' : 'memories'}</small> : null}
    </header>
    <p className="character-memory-intro">
      {ownerName} picks these up from what you say in any chat, and uses them in every chat. Correct or forget anything here.
    </p>
    {error ? <p className="character-memory-error" role="alert">{error}</p> : null}
    {memoryQuery.isPending ? <p>Loading memories…</p> : null}
    {/* A failure while the gateway restarts would otherwise stay until the panel is opened again. */}
    {memoryQuery.isError ? <p className="character-memory-error" role="alert">
      Memories could not be loaded.{' '}
      <button type="button" onClick={() => void memoryQuery.refetch()} disabled={memoryQuery.isFetching}>Try again</button>
    </p> : null}

    {suggestions.length ? <div className="character-memory-group">
      <h5>Waiting for your OK</h5>
      <p className="character-memory-intro">Things {ownerName} worked out rather than heard you say. They are not used until you keep them.</p>
      <ul className="character-memory-list">
        {suggestions.map((suggestion) => <li key={suggestion.id}>
          <div>
            <small>{CATEGORY_LABEL[suggestion.proposed_category] ?? suggestion.proposed_category}</small>
            <p>{suggestion.proposed_content}</p>
          </div>
          <div className="character-memory-actions">
            <button type="button" disabled={approveMutation.isPending} onClick={() => approveMutation.mutate(suggestion.id)}>Keep</button>
            <button type="button" disabled={dismissMutation.isPending} onClick={() => dismissMutation.mutate(suggestion.id)}>Dismiss</button>
          </div>
        </li>)}
      </ul>
    </div> : null}

    {memoryQuery.data && !records.length ? <p className="character-memory-empty">Nothing yet. {ownerName} will remember what comes up in your chats.</p> : null}
    {records.length ? <ul className="character-memory-list">
      {records.map((record) => <MemoryRow key={record.id} ownerId={ownerId} record={record} refreshed={refreshed} />)}
    </ul> : null}

    <form
      className="character-memory-add"
      onSubmit={(event) => {
        event.preventDefault();
        if (newContent.trim()) addMutation.mutate();
      }}
    >
      <label>
        <span>Add a memory</span>
        <textarea value={newContent} rows={2} maxLength={4096} onChange={(event) => setNewContent(event.target.value)} placeholder={`Something ${ownerName} should remember`} />
      </label>
      <div>
        <label>
          <span>Type</span>
          <select value={newCategory} onChange={(event) => setNewCategory(event.target.value as MemoryCategory)}>
            {CATEGORIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <button type="submit" disabled={!newContent.trim() || addMutation.isPending}>Add</button>
      </div>
    </form>

    {memoryQuery.data?.understanding ? <CharacterUnderstandingPanel
      ownerId={ownerId}
      ownerName={ownerName}
      understanding={memoryQuery.data.understanding}
      refreshed={refreshed}
    /> : null}
  </section>;
}

function MemoryRow({ ownerId, record, refreshed }: {
  ownerId: string;
  record: ManagedMemoryRecord;
  refreshed: { onSuccess: () => Promise<void>; onError: (failure: unknown) => void };
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const [forgetting, setForgetting] = useState(false);
  const editMutation = useMutation({
    mutationFn: (content: string) => ownerMemoryClient.edit(ownerId, record, content),
    ...refreshed,
    onSuccess: async () => {
      setDraft(null);
      await refreshed.onSuccess();
    },
  });
  const forgetMutation = useMutation({ mutationFn: () => ownerMemoryClient.forget(ownerId, record), ...refreshed });

  if (draft !== null) {
    return <li>
      <div>
        <small>{CATEGORY_LABEL[record.category] ?? record.category}</small>
        <textarea aria-label="Edit memory" value={draft} rows={3} maxLength={4096} onChange={(event) => setDraft(event.target.value)} />
      </div>
      <div className="character-memory-actions">
        <button type="button" disabled={!draft.trim() || editMutation.isPending} onClick={() => editMutation.mutate(draft.trim())}>Save</button>
        <button type="button" onClick={() => setDraft(null)}>Cancel</button>
      </div>
    </li>;
  }
  return <li>
    <div>
      <small>{CATEGORY_LABEL[record.category] ?? record.category} · {savedOn(record.updated_at)}</small>
      <p>{record.content}</p>
    </div>
    <div className="character-memory-actions">
      {forgetting ? <>
        <span>Forget this?</span>
        <button type="button" disabled={forgetMutation.isPending} onClick={() => forgetMutation.mutate()}>Forget</button>
        <button type="button" onClick={() => setForgetting(false)}>Keep</button>
      </> : <>
        <button type="button" onClick={() => setDraft(record.content)}>Edit</button>
        <button type="button" onClick={() => setForgetting(true)}>Forget</button>
      </>}
    </div>
  </li>;
}
