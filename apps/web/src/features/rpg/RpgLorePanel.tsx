import { useEffect, useMemo, useState } from 'react';

interface LoreDocumentSummary {
  document_id: string;
  title: string;
  topic_id: string;
  category: string;
  summary_120: string;
  summary_500: string;
  keywords: string[];
  visibility: string;
  status: string;
  canon_revision: number;
}

interface LoreDocumentDetail extends LoreDocumentSummary {
  full_text: string;
}

interface GenerationJob {
  topic_id?: string;
  status?: string;
  generator_role?: string;
  output_counts?: Record<string, number>;
  error?: string;
}

interface LoreResponse {
  ok: boolean;
  session_id: string;
  canon_revision: number;
  content_hash: string;
  categories: Array<{ label: string; documents: LoreDocumentSummary[] }>;
  visible_count: number;
  hidden_count: number;
  generation?: {
    status?: string;
    stage?: string;
    launch_ready?: boolean;
    percent?: number;
    completed_jobs?: number;
    total_jobs?: number;
    jobs?: GenerationJob[];
  };
}

function selectedSessionId(): string {
  if (typeof window === 'undefined') return '';
  try {
    return window.localStorage.getItem('omnix:rpg:selected-session-id')?.trim() ?? '';
  } catch {
    return '';
  }
}

function statusLabel(value: string): string {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

async function readJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { headers: { Accept: 'application/json' } });
  if (!response.ok) {
    throw new Error(`Lore request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export function RpgLorePanel() {
  const sessionId = selectedSessionId();
  const [lore, setLore] = useState<LoreResponse | null>(null);
  const [selectedId, setSelectedId] = useState('');
  const [detail, setDetail] = useState<LoreDocumentDetail | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    setLore(null);
    setDetail(null);
    setSelectedId('');
    setError('');
    if (!sessionId) return () => { active = false; };
    readJson<LoreResponse>(`/api/rpg/sessions/${encodeURIComponent(sessionId)}/lore`)
      .then((payload) => {
        if (!active) return;
        setLore(payload);
        const first = payload.categories.flatMap((category) => category.documents)[0];
        setSelectedId(first?.document_id ?? '');
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : 'Lore could not be loaded.');
      });
    return () => { active = false; };
  }, [sessionId]);

  useEffect(() => {
    let active = true;
    setDetail(null);
    if (!sessionId || !selectedId) return () => { active = false; };
    readJson<{ document: LoreDocumentDetail }>(
      `/api/rpg/sessions/${encodeURIComponent(sessionId)}/lore/document?document_id=${encodeURIComponent(selectedId)}`,
    )
      .then((payload) => {
        if (active) setDetail(payload.document);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : 'Lore page could not be loaded.');
      });
    return () => { active = false; };
  }, [selectedId, sessionId]);

  const generation = lore?.generation;
  const jobs = generation?.jobs ?? [];
  const topicSummary = useMemo(() => {
    const completed = jobs.filter((job) => job.status === 'completed').length;
    return jobs.length ? `${completed}/${jobs.length} topics compiled` : 'No generation jobs recorded';
  }, [jobs]);

  if (!sessionId) {
    return <div className="rpg-journal-detail"><h3>Lore</h3><p>Select or create a campaign to browse its Campaign Bible.</p></div>;
  }
  if (error && !lore) {
    return <div className="rpg-journal-detail"><h3>Lore unavailable</h3><p>{error}</p></div>;
  }
  if (!lore) {
    return <div className="rpg-journal-detail"><h3>Loading Campaign Bible…</h3><p>Reading generated lore and discovery state.</p></div>;
  }

  return (
    <div aria-labelledby="rpg-lore-tab" className="rpg-journal-grid" id="rpg-lore-panel" role="tabpanel">
      <div className="rpg-journal-list" aria-label="Lore categories">
        <article className="active">
          <span aria-hidden="true" />
          <div>
            <strong>{generation?.launch_ready ? 'World ready' : statusLabel(generation?.status ?? 'unknown')}</strong>
            <p>{generation?.percent ?? 0}% · {topicSummary}</p>
          </div>
        </article>
        {lore.categories.map((category) => (
          <div key={category.label} style={{ display: 'contents' }}>
            <div style={{ padding: '10px 12px 4px', opacity: 0.68, fontSize: 12, fontWeight: 700 }}>
              {category.label}
            </div>
            {category.documents.map((document) => (
              <article
                aria-pressed={selectedId === document.document_id}
                className={selectedId === document.document_id ? 'active' : undefined}
                key={document.document_id}
                onClick={() => setSelectedId(document.document_id)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    setSelectedId(document.document_id);
                  }
                }}
                role="button"
                tabIndex={0}
              >
                <span aria-hidden="true" />
                <div>
                  <strong>{statusLabel(document.status)}</strong>
                  <p>{document.title}</p>
                </div>
              </article>
            ))}
          </div>
        ))}
      </div>
      <article className="rpg-journal-detail">
        <h3>{detail?.title ?? 'Campaign Bible'}</h3>
        <p>{detail?.full_text || detail?.summary_500 || 'Select a lore page to read it.'}</p>
        <div className="rpg-chip-row">
          <span>Canon r{lore.canon_revision}</span>
          <span>{lore.visible_count} known pages</span>
          <span>{lore.hidden_count} undiscovered</span>
          {detail ? <span>{statusLabel(detail.status)}</span> : null}
        </div>
        <details style={{ marginTop: 14 }}>
          <summary>World Forge generation evidence</summary>
          <ul>
            {jobs.slice(0, 20).map((job) => (
              <li key={job.topic_id ?? `${job.generator_role}:${job.status}`}>
                {statusLabel(job.topic_id ?? job.generator_role ?? 'topic')} — {statusLabel(job.status ?? 'unknown')}
                {job.error ? `: ${job.error}` : ''}
              </li>
            ))}
          </ul>
        </details>
        {error ? <p role="alert">{error}</p> : null}
      </article>
    </div>
  );
}
