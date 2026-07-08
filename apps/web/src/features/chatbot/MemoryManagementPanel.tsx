import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import {
  memoryClient,
  type ManagedMemoryRecord,
  type MemoryCategory,
  type MemoryScope,
} from './memoryClient';

const scopes: MemoryScope[] = ['global', 'workspace', 'project', 'session'];
const categories: MemoryCategory[] = ['preference', 'fact', 'project', 'relationship', 'instruction'];

export function MemoryManagementPanel({ sessionId }: { sessionId: string | null }) {
  const queryClient = useQueryClient();
  const [query, setQuery] = useState('');
  const [scope, setScope] = useState('');
  const [category, setCategory] = useState('');
  const [newContent, setNewContent] = useState('');
  const [newScope, setNewScope] = useState<MemoryScope>('session');
  const [newCategory, setNewCategory] = useState<MemoryCategory>('preference');
  const [status, setStatus] = useState<string | null>(null);

  const memoryQuery = useQuery({
    queryKey: ['feature', 'chatbot', 'memory', sessionId, query, scope, category],
    queryFn: () => memoryClient.list(sessionId ?? '', query, scope, category),
    enabled: Boolean(sessionId),
  });
  const candidatesQuery = useQuery({
    queryKey: ['feature', 'chatbot', 'memory-candidates', sessionId],
    queryFn: () => memoryClient.candidates(sessionId ?? ''),
    enabled: Boolean(sessionId),
  });
  const snapshotQuery = useQuery({
    queryKey: ['feature', 'chatbot', 'memory-state', sessionId],
    queryFn: () => memoryClient.sessionState(sessionId ?? ''),
    enabled: Boolean(sessionId),
  });

  async function refreshAll(): Promise<void> {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'memory'] }),
      queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'memory-candidates'] }),
      queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'memory-state'] }),
      queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'sessions'] }),
    ]);
  }

  const createMutation = useMutation({
    mutationFn: () => memoryClient.create(sessionId ?? '', {
      scope: newScope,
      category: newCategory,
      content: newContent.trim(),
      pinned: false,
    }),
    onSuccess: async () => {
      setNewContent('');
      setStatus('Memory saved. Refresh the active snapshot to use it in this chat.');
      await refreshAll();
    },
    onError: (error) => setStatus(error instanceof Error ? error.message : 'Memory save failed.'),
  });
  const recordMutation = useMutation({
    mutationFn: async (input: { action: 'pin' | 'forget' | 'move' | 'edit'; record: ManagedMemoryRecord; value?: string }) => {
      if (!sessionId) throw new Error('Select a chat session first.');
      if (input.action === 'pin') return memoryClient.pin(sessionId, input.record, !input.record.pinned);
      if (input.action === 'move') return memoryClient.move(sessionId, input.record, input.value as MemoryScope);
      if (input.action === 'edit') return memoryClient.edit(sessionId, input.record, input.value ?? input.record.content);
      return memoryClient.forget(sessionId, input.record);
    },
    onSuccess: async () => {
      setStatus('Memory updated.');
      await refreshAll();
    },
    onError: (error) => setStatus(error instanceof Error ? error.message : 'Memory update failed.'),
  });
  const candidateMutation = useMutation({
    mutationFn: (input: { id: string; action: 'approve' | 'reject' }) => input.action === 'approve'
      ? memoryClient.approve(sessionId ?? '', input.id)
      : memoryClient.reject(sessionId ?? '', input.id),
    onSuccess: async () => {
      setStatus('Memory suggestion reviewed.');
      await refreshAll();
    },
    onError: (error) => setStatus(error instanceof Error ? error.message : 'Suggestion review failed.'),
  });
  const refreshMutation = useMutation({
    mutationFn: () => memoryClient.refresh(sessionId ?? '', snapshotQuery.data?.snapshot_revision),
    onSuccess: async () => {
      setStatus('Active chat memory refreshed.');
      await refreshAll();
    },
    onError: (error) => setStatus(error instanceof Error ? error.message : 'Memory refresh failed.'),
  });

  if (!sessionId) {
    return <section className="assistant-view-panel" aria-label="Memory view"><p className="eyebrow">Omnix Assistant</p><h2>Memory</h2><p>Create or select a Chat session before managing memory.</p></section>;
  }

  const records = memoryQuery.data?.records ?? [];
  const candidates = candidatesQuery.data?.candidates ?? [];
  const snapshot = snapshotQuery.data;

  return (
    <section className="assistant-view-panel" aria-label="Memory view">
      <p className="eyebrow">Omnix Assistant</p>
      <h2>Memory</h2>
      <p>Review exactly what Omnix has saved, approve inferred suggestions, and refresh what this Chat can use.</p>
      {status ? <p role="status">{status}</p> : null}

      <div className="platform-grid">
        <article>
          <h3>Active for this Chat</h3>
          {snapshotQuery.isPending ? <p>Loading snapshot…</p> : snapshot ? (
            <>
              <p>{snapshot.memory_enabled ? `${snapshot.memory_record_count} active records` : 'Memory is not active for this session.'}</p>
              <p>Snapshot revision: {snapshot.snapshot_revision ?? 'none'} · Token estimate: {snapshot.snapshot?.token_estimate ?? 0}</p>
              <button type="button" disabled={refreshMutation.isPending} onClick={() => refreshMutation.mutate()}>{refreshMutation.isPending ? 'Refreshing…' : 'Refresh active memory'}</button>
            </>
          ) : <p>Snapshot state is unavailable.</p>}
        </article>
        <article>
          <h3>Add explicit memory</h3>
          <label>Scope<select aria-label="New memory scope" value={newScope} onChange={(event) => setNewScope(event.currentTarget.value as MemoryScope)}>{scopes.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
          <label>Category<select aria-label="New memory category" value={newCategory} onChange={(event) => setNewCategory(event.currentTarget.value as MemoryCategory)}>{categories.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
          <label>Memory<textarea aria-label="New memory content" rows={3} value={newContent} onChange={(event) => setNewContent(event.currentTarget.value)} /></label>
          <button type="button" disabled={!newContent.trim() || createMutation.isPending} onClick={() => createMutation.mutate()}>Save memory</button>
        </article>
      </div>

      <section aria-labelledby="saved-memory-heading">
        <h3 id="saved-memory-heading">Saved memory</h3>
        <div className="assistant-composer-controls">
          <label>Search<input aria-label="Search saved memory" value={query} onChange={(event) => setQuery(event.currentTarget.value)} /></label>
          <label>Scope<select aria-label="Filter memory scope" value={scope} onChange={(event) => setScope(event.currentTarget.value)}><option value="">All scopes</option>{scopes.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
          <label>Category<select aria-label="Filter memory category" value={category} onChange={(event) => setCategory(event.currentTarget.value)}><option value="">All categories</option>{categories.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
        </div>
        {memoryQuery.isPending ? <p>Loading saved memory…</p> : records.length ? (
          <div className="platform-grid">
            {records.map((record) => (
              <article key={record.id}>
                <header><h4>{record.category}</h4><strong>{record.scope}{record.pinned ? ' · pinned' : ''}</strong></header>
                <p>{record.content}</p>
                <small>Source: {record.source} · Trust: {record.trust_level} · Revision {record.revision}</small>
                <div>
                  <button type="button" onClick={() => recordMutation.mutate({ action: 'pin', record })}>{record.pinned ? 'Unpin' : 'Pin'}</button>
                  <button type="button" onClick={() => { const value = window.prompt('Edit memory', record.content); if (value?.trim()) recordMutation.mutate({ action: 'edit', record, value }); }}>Edit</button>
                  <select aria-label={`Move ${record.content}`} value={record.scope} onChange={(event) => recordMutation.mutate({ action: 'move', record, value: event.currentTarget.value })}>{scopes.map((item) => <option key={item} value={item}>{item}</option>)}</select>
                  <button type="button" onClick={() => { if (window.confirm('Forget this memory? It will be removed from active snapshots.')) recordMutation.mutate({ action: 'forget', record }); }}>Forget</button>
                </div>
              </article>
            ))}
          </div>
        ) : <p>No saved memory matches the current filters.</p>}
      </section>

      <section aria-labelledby="pending-memory-heading">
        <h3 id="pending-memory-heading">Pending suggestions</h3>
        {candidatesQuery.isPending ? <p>Loading suggestions…</p> : candidates.length ? (
          <div className="platform-grid">
            {candidates.map((candidate) => (
              <article key={candidate.id}>
                <header><h4>{candidate.proposed_category}</h4><strong>{candidate.proposed_scope}</strong></header>
                <p>{candidate.proposed_content}</p>
                <small>Source: {candidate.source} · Confidence: {Math.round(candidate.confidence * 100)}%</small>
                <div><button type="button" onClick={() => candidateMutation.mutate({ id: candidate.id, action: 'approve' })}>Approve</button><button type="button" onClick={() => candidateMutation.mutate({ id: candidate.id, action: 'reject' })}>Reject</button></div>
              </article>
            ))}
          </div>
        ) : <p>No pending memory suggestions.</p>}
      </section>
    </section>
  );
}
