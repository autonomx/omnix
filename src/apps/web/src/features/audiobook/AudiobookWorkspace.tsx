import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState, type FormEvent } from 'react';
import { omnixApiClient } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';

interface ProjectSummary {
  id: string;
  title: string;
  author: string;
  language: string;
  state: string;
  current_source_revision_id: string | null;
}

interface Span {
  id: string;
  source_text: string;
  structural_kind: string;
  annotation: { id: string; role: string; speaker_id: string | null; speaker_candidate: string | null;
    delivery: string; review_status: string; evidence: Record<string, unknown> } | null;
  speech_plan: { tts_input_text: string; hash: string;
    transformations: { rule: string; source: string; spoken: string }[] };
}

interface ChapterSummary {
  id: string;
  ordinal: number;
  title: string;
  character_count: number;
}

interface Chapter extends ChapterSummary {
  canonical_text: string;
  spans: Span[];
}

interface ReviewIssue {
  id: string;
  span_id: string;
  reason: string;
  evidence: Record<string, unknown>;
  source_text: string;
  chapter_id: string;
  chapter_title: string;
  speaker_id: string | null;
  speaker_candidate: string | null;
  structural_kind: string;
}

interface Speaker {
  id: string;
  canonical_name: string;
  kind: string;
  casting: { voice_profile_id: string; voice_revision_hash: string; revision: number } | null;
  aliases: string[];
}

interface JobStatus {
  id: string;
  status: string;
  chapter_id?: string;
  progress?: { current?: number; total?: number; message?: string; cache_hits?: number; generated?: number };
  error?: { message?: string; code?: string; retryable?: boolean } | null;
  attempts?: number;
  max_attempts?: number;
  can_retry?: boolean;
  format?: string;
  span_id?: string;
  type?: string;
}

interface ProjectDetail extends ProjectSummary {
  cover_asset_id: string | null;
  chapters: ChapterSummary[];
  review_issues: ReviewIssue[];
  speakers: Speaker[];
  render_jobs: JobStatus[];
  pipeline_jobs?: JobStatus[];
  preview_jobs: JobStatus[];
  export_jobs: JobStatus[];
  render_progress: { completed: number; total: number };
  pronunciations: { source_term: string; spoken_term: string; revision: number }[];
  word_count?: number;
  estimated_runtime_seconds?: number;
  actual_runtime_seconds?: number;
}

interface ExportRecord {
  id: string;
  format: string;
  manifest_hash: string;
  created_at: string;
  byte_size: number;
}

interface VoiceRecord { id: string; name: string; language: string }

const base = '/api/audiobook';

async function responseError(response: Response): Promise<Error> {
  const body = await response.json().catch(() => ({})) as { detail?: string };
  return new Error(body.detail || `Request failed (${response.status})`);
}

async function uploadSource(projectId: string, file: File): Promise<void> {
  const extension = file.name.split('.').pop()?.toLowerCase();
  if (extension !== 'epub' && extension !== 'txt' && extension !== 'md') {
    throw new Error('Choose an EPUB, TXT, or Markdown file.');
  }
  const url = `${base}/projects/${encodeURIComponent(projectId)}/source?source_format=${extension}&filename=${encodeURIComponent(file.name)}`;
  const response = await fetch(url, { method: 'POST', body: file });
  if (!response.ok) throw await responseError(response);
}

async function uploadCover(projectId: string, file: File): Promise<void> {
  const response = await fetch(`${base}/projects/${encodeURIComponent(projectId)}/cover?filename=${encodeURIComponent(file.name)}`,
    { method: 'POST', body: file });
  if (!response.ok) throw await responseError(response);
}

async function updateProjectMetadata(projectId: string, title: string, author: string): Promise<void> {
  const response = await fetch(`${base}/projects/${encodeURIComponent(projectId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, author }),
  });
  if (!response.ok) throw await responseError(response);
}

function formatDuration(seconds?: number): string {
  if (!seconds || seconds <= 0) return '—';
  const totalMinutes = Math.round(seconds / 60);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return hours ? `${hours}h ${minutes}m` : `${minutes}m`;
}

export function AudiobookWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const queryClient = useQueryClient();
  const [projectId, setProjectId] = useState<string | null>(null);
  const [chapterId, setChapterId] = useState<string | null>(null);
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const [workspaceMode, setWorkspaceMode] = useState<'review' | 'production'>('review');
  const [mobileRail, setMobileRail] = useState<'library' | 'outline' | null>(null);
  const [title, setTitle] = useState('');
  const [author, setAuthor] = useState('');
  const [language, setLanguage] = useState('en');
  const [projectTitle, setProjectTitle] = useState('');
  const [projectAuthor, setProjectAuthor] = useState('');
  const [speakerName, setSpeakerName] = useState('');
  const [sourceTerm, setSourceTerm] = useState('');
  const [spokenTerm, setSpokenTerm] = useState('');
  const [exportFormat, setExportFormat] = useState('m4b');
  const [reviewSpeakers, setReviewSpeakers] = useState<Record<string, string>>({});
  const [spanEdits, setSpanEdits] = useState<Record<string, { speaker_id: string; role: string; delivery: string }>>({});
  const [aliasNames, setAliasNames] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const projectsQuery = useQuery({
    queryKey: ['audiobook', 'projects'],
    queryFn: () => omnixApiClient.get<{ projects: ProjectSummary[] }>(`${base}/projects`),
    refetchInterval: 5000,
  });
  const projectQuery = useQuery({
    queryKey: ['audiobook', 'project', projectId],
    queryFn: () => omnixApiClient.get<ProjectDetail>(`${base}/projects/${encodeURIComponent(projectId!)}`),
    enabled: Boolean(projectId), refetchInterval: 3000,
  });
  const voicesQuery = useQuery({
    queryKey: ['audiobook', 'voices'],
    queryFn: () => omnixApiClient.get<{ voices: VoiceRecord[] }>(`${base}/voices`),
  });
  const modelQuery = useQuery({
    queryKey: ['audiobook', 'model'],
    queryFn: () => omnixApiClient.get<{ provider_id: string; model_id: string; model_revision: string }>(`${base}/models/current`),
    staleTime: 30_000,
  });
  const exportsQuery = useQuery({
    queryKey: ['audiobook', 'exports', projectId],
    queryFn: () => omnixApiClient.get<{ exports: ExportRecord[] }>(`${base}/projects/${encodeURIComponent(projectId!)}/exports`),
    enabled: Boolean(projectId), refetchInterval: 5000,
  });
  const project = projectQuery.data;
  const modelRevision = modelQuery.data?.model_revision ?? '';
  useEffect(() => {
    if (!project) return;
    setProjectTitle(project.title);
    setProjectAuthor(project.author);
  }, [project?.id, project?.title, project?.author]);
  const activeChapterId = project?.chapters.find((chapter) => chapter.id === chapterId)?.id ?? project?.chapters[0]?.id ?? null;
  const chapterQuery = useQuery({
    queryKey: ['audiobook', 'chapter', projectId, activeChapterId],
    queryFn: () => omnixApiClient.get<Chapter>(`${base}/projects/${encodeURIComponent(projectId!)}/chapters/${encodeURIComponent(activeChapterId!)}`),
    enabled: Boolean(projectId && activeChapterId),
  });
  const selectedChapter = chapterQuery.data;
  const selectedSpan = selectedChapter?.spans.find((span) => span.id === selectedSpanId) ?? selectedChapter?.spans[0];
  const selectedPreview = project?.preview_jobs?.find((job) => job.span_id === selectedSpan?.id);
  const selectedSpeaker = project?.speakers.find((speaker) => speaker.id === selectedSpan?.annotation?.speaker_id);
  const selectedIssue = project?.review_issues.find((issue) => issue.span_id === selectedSpan?.id);
  const canRender = project?.state === 'ready_to_render' ||
    (project?.state === 'rendering' && project.render_jobs.length > 0 &&
      project.render_jobs.every((job) => ['completed', 'failed', 'canceled'].includes(job.status)));
  const latestPipelineJob = project?.pipeline_jobs?.[0];
  const failedPipelineJob = latestPipelineJob && ['failed', 'canceled', 'stale', 'dead_letter'].includes(latestPipelineJob.status) ? latestPipelineJob : null;
  const selectedEdit = selectedSpan && (spanEdits[selectedSpan.id] ?? {
    speaker_id: selectedSpan.annotation?.speaker_id ?? '',
    role: selectedSpan.annotation?.role ?? selectedSpan.structural_kind,
    delivery: selectedSpan.annotation?.delivery ?? '',
  });

  function changeSpanEdit(changes: Partial<{ speaker_id: string; role: string; delivery: string }>): void {
    if (!selectedSpan || !selectedEdit) return;
    setSpanEdits((previous) => ({ ...previous, [selectedSpan.id]: { ...selectedEdit, ...changes } }));
  }

  async function findSpeakerSpan(speakerId: string): Promise<{ chapterId: string; spanId: string }> {
    if (!project) throw new Error('Open an audiobook project first.');
    for (const chapter of project.chapters) {
      const detail = chapter.id === selectedChapter?.id ? selectedChapter : await queryClient.fetchQuery({
        queryKey: ['audiobook', 'chapter', project.id, chapter.id],
        queryFn: () => omnixApiClient.get<Chapter>(`${base}/projects/${encodeURIComponent(project.id)}/chapters/${encodeURIComponent(chapter.id)}`),
      });
      const span = detail.spans.find((candidate) => candidate.annotation?.speaker_id === speakerId);
      if (span) return { chapterId: chapter.id, spanId: span.id };
    }
    throw new Error('No annotated span uses this speaker yet.');
  }

  async function action(task: () => Promise<unknown>, success: string): Promise<void> {
    setBusy(true); setError(null); setNotice(null);
    try {
      await task();
      await queryClient.invalidateQueries({ queryKey: ['audiobook'] });
      setNotice(success);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  function submitProject(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    void action(async () => {
      const created = await omnixApiClient.post<object, ProjectSummary>(`${base}/projects`, { title, author, language });
      setProjectId(created.id); setChapterId(null); setProjectTitle(created.title); setProjectAuthor(created.author); setTitle(''); setAuthor(''); setMobileRail(null);
    }, 'Project created. Upload a source book to begin.');
  }

  function submitSpeaker(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (!projectId || !speakerName.trim()) return;
    void action(async () => {
      await omnixApiClient.post(`${base}/projects/${encodeURIComponent(projectId)}/speakers`, { canonical_name: speakerName.trim() });
      setSpeakerName('');
    }, 'Speaker added.');
  }

  function submitPronunciation(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (!projectId || !sourceTerm.trim() || !spokenTerm.trim()) return;
    void action(async () => {
      await omnixApiClient.post(`${base}/projects/${encodeURIComponent(projectId)}/pronunciations`,
        { source_term: sourceTerm.trim(), spoken_term: spokenTerm.trim() });
      setSourceTerm(''); setSpokenTerm('');
    }, 'Pronunciation saved. Affected speech plans will use the new form.');
  }

  return (
    <main className="audiobook-workspace" aria-label={`${module.label} workspace`}>
      <aside id="audiobook-library-rail" className={`audiobook-rail audiobook-library${mobileRail === 'library' ? ' mobile-open' : ''}`} aria-label="Audiobook projects">
        <button className="audiobook-mobile-close" type="button" onClick={() => setMobileRail(null)}>Close library</button>
        <div className="audiobook-panel-heading"><p className="eyebrow">Library</p><h2>Audiobooks</h2></div>
        <nav className="audiobook-library-nav" aria-label="Audiobook sections">
          <a href="#audiobook-projects">Projects</a>
          <a href="#audiobook-book">Books</a>
          <a href="#audiobook-cast">Characters</a>
          <a href="#audiobook-cast">Voices</a>
          <a href="#audiobook-pronunciations">Pronunciations</a>
          <a href="#audiobook-exports" onClick={() => setWorkspaceMode('production')}>Exports</a>
        </nav>
        <form className="audiobook-form" onSubmit={submitProject}>
          <label>Book title<input value={title} onChange={(event) => setTitle(event.target.value)} required /></label>
          <label>Author<input value={author} onChange={(event) => setAuthor(event.target.value)} /></label>
          <label>Language<input value={language} onChange={(event) => setLanguage(event.target.value)} required /></label>
          <button type="submit" disabled={busy}>New project</button>
        </form>
        <div className="audiobook-project-list" id="audiobook-projects">
          {projectsQuery.isLoading && <p>Loading projects…</p>}
          {projectsQuery.isError && <p role="alert">Could not load projects.</p>}
          {projectsQuery.data?.projects.map((item) => (
            <button type="button" key={item.id} className={item.id === projectId ? 'selected' : ''}
              onClick={() => { setProjectId(item.id); setChapterId(null); setProjectTitle(item.title); setProjectAuthor(item.author); setError(null); setMobileRail(null); }}>
              <strong>{item.title}</strong><small>{item.author || 'Unknown author'} · {item.state.replaceAll('_', ' ')}</small>
            </button>
          ))}
          {projectsQuery.data?.projects.length === 0 && <p>Start with a source book.</p>}
        </div>
      </aside>

      <div className="audiobook-stage">
        <nav className="audiobook-mobile-navigation" aria-label="Mobile audiobook panels">
          <button type="button" aria-controls="audiobook-library-rail" aria-expanded={mobileRail === 'library'} onClick={() => setMobileRail('library')}>Library and projects</button>
          <button type="button" aria-controls="audiobook-outline-rail" aria-expanded={mobileRail === 'outline'} onClick={() => setMobileRail('outline')}>Outline and cast</button>
        </nav>
        {error && <p className="audiobook-message error" role="alert">{error}</p>}
        {notice && <p className="audiobook-message" role="status">{notice}</p>}
        {!projectId && <section className="audiobook-card audiobook-empty"><p className="eyebrow">Production workspace</p><h1>Make a book audible</h1><p>Create a project, upload a DRM-free EPUB, TXT, or Markdown book, then review its speakers before rendering. The source and production jobs stay in local Omnix storage.</p><p>Use existing <a href="/voice-cloning">voice profiles</a> when casting.</p></section>}
        {projectId && projectQuery.isLoading && <section className="audiobook-card"><p>Loading book…</p></section>}
        {projectId && projectQuery.isError && <section className="audiobook-card" role="alert"><p>Could not load this project.</p></section>}
        {project && <>
          <header className="audiobook-card audiobook-project-header" id="audiobook-book">
            {project.cover_asset_id && <img className="audiobook-cover" src={`${base}/projects/${encodeURIComponent(project.id)}/cover`} alt={`Cover of ${project.title}`} />}
            <div className="audiobook-header-copy"><p className="eyebrow">Audiobook project · {project.state.replaceAll('_', ' ')}</p><h1>{project.title}</h1><p>{project.author || 'Unknown author'} · {project.language}</p>
              <p className="audiobook-project-stats">{(project.word_count ?? 0).toLocaleString()} words · {project.chapters.length} chapters · {project.speakers.length} speakers · {project.review_issues.length} review issues · est. {formatDuration(project.estimated_runtime_seconds)}{project.actual_runtime_seconds ? ` · actual ${formatDuration(project.actual_runtime_seconds)}` : ''}</p>
            </div>
            <div className="audiobook-project-actions">
              <label>Title<input value={projectTitle} onChange={(event) => setProjectTitle(event.target.value)} /></label>
              <label>Author<input value={projectAuthor} onChange={(event) => setProjectAuthor(event.target.value)} /></label>
              <button type="button" disabled={busy || !projectTitle.trim() || (projectTitle === project.title && projectAuthor === project.author)}
                onClick={() => void action(() => updateProjectMetadata(project.id, projectTitle.trim(), projectAuthor.trim()), 'Project metadata saved. Export metadata will use the new values.')}>Save project</button>
              <label className="audiobook-upload">Upload source
                <input type="file" accept=".epub,.txt,.md" disabled={busy}
                  onChange={(event) => { const file = event.currentTarget.files?.[0]; if (file) void action(() => uploadSource(project.id, file), 'Source queued for extraction.'); event.currentTarget.value = ''; }} />
              </label>
              <label className="audiobook-upload">{project.cover_asset_id ? 'Replace cover' : 'Add cover'}
                <input type="file" accept="image/jpeg,image/png" disabled={busy}
                  onChange={(event) => { const file = event.currentTarget.files?.[0]; if (file) void action(() => uploadCover(project.id, file), 'Cover saved for future exports.'); event.currentTarget.value = ''; }} />
              </label>
            </div>
          </header>
          <div className="audiobook-tool-bars">
            <details><summary>Cast &amp; voice tools <small>Narrator, voices, aliases, pronunciations, auditions</small></summary>
              <p>Assign voices in the cast panel, confirm aliases, then audition an annotated span. <a href="#audiobook-cast">Manage cast</a> · <a href="#audiobook-pronunciations">Pronunciations</a></p>
            </details>
            <details><summary>Render &amp; delivery tools <small>Chapter rendering, mastering, export manifests</small></summary>
              <p>Provider: Faster Qwen3 TTS · one span per checkpoint · chapter-level mastering. The Production view shows durable jobs, cache hits, and export history.</p>
              <button type="button" onClick={() => setWorkspaceMode('production')}>Open Production</button>
            </details>
          </div>
          {latestPipelineJob && ['queued', 'leased', 'running', 'retrying'].includes(latestPipelineJob.status) &&
            <p className="audiobook-message" role="status">{latestPipelineJob.type?.replace('audiobook.', '')} {latestPipelineJob.status}: {latestPipelineJob.progress?.message || 'Processing the book'}</p>}
          {failedPipelineJob && <div className="audiobook-message error" role="alert">
            <strong>{failedPipelineJob.type?.replace('audiobook.', '')} {failedPipelineJob.status}</strong>
            {failedPipelineJob.chapter_id && <> · {project.chapters.find((chapter) => chapter.id === failedPipelineJob.chapter_id)?.title || failedPipelineJob.chapter_id}</>}
            {failedPipelineJob.error?.code && <> · {failedPipelineJob.error.code}</>}
            <> · {failedPipelineJob.error?.message || 'Open the job queue for details.'}</>
            {failedPipelineJob.attempts !== undefined && <> · attempt {failedPipelineJob.attempts}/{failedPipelineJob.max_attempts}</>}
            {failedPipelineJob.error?.retryable !== undefined && <> · {failedPipelineJob.error.retryable ? 'retryable' : 'manual retry required'}</>}
            {failedPipelineJob.can_retry && <button type="button" disabled={busy}
              onClick={() => void action(() => omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/jobs/${encodeURIComponent(failedPipelineJob.id)}/retry`, {}), 'Pipeline retry queued.')}>Retry stage</button>}
            <a href="/jobs">Diagnostics</a>
          </div>}
          <nav className="audiobook-mode-switch" aria-label="Audiobook workspace mode">
            <button type="button" aria-current={workspaceMode === 'review' ? 'page' : undefined}
              onClick={() => setWorkspaceMode('review')}><strong>Book &amp; Review</strong><small>Read, cast, resolve, audition</small></button>
            <button type="button" aria-current={workspaceMode === 'production' ? 'page' : undefined}
              onClick={() => setWorkspaceMode('production')}><strong>Production</strong><small>Render, master, export</small></button>
          </nav>
          {workspaceMode === 'review' &&
          <section className="audiobook-card audiobook-manuscript" id="audiobook-manuscript">
            <div className="audiobook-section-title"><div><p className="eyebrow">Canonical source</p><h2>{selectedChapter?.title ?? project.chapters.find((chapter) => chapter.id === activeChapterId)?.title ?? 'Awaiting extraction'}</h2></div><span>{project.chapters.length} chapters</span></div>
            {selectedChapter ? <>
              <div className="audiobook-text" aria-label="Canonical chapter text">
                {selectedChapter.spans.map((span) => <span key={span.id} role="button" tabIndex={0}
                  className={`audiobook-source-span${span.id === selectedSpan?.id ? ' selected' : ''}${span.annotation?.review_status === 'review_required' ? ' needs-review' : ''}`}
                  aria-label={`Inspect ${span.annotation?.role ?? span.structural_kind} span: ${span.source_text.slice(0, 64)}`}
                  onClick={() => setSelectedSpanId(span.id)}
                  onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelectedSpanId(span.id); } }}>
                  {span.source_text}
                </span>)}
              </div>
              {selectedSpan && <section className="audiobook-span-inspector" aria-label="Selected span">
                <div className="audiobook-section-title"><div><p className="eyebrow">Interpretation overlay</p><h3>{selectedSpeaker?.canonical_name ?? selectedSpan.annotation?.speaker_candidate ?? 'Narrator'} · {selectedSpan.annotation?.role ?? selectedSpan.structural_kind}</h3></div><small>{selectedSpan.annotation?.review_status ?? 'Awaiting analysis'}</small></div>
                <p><strong>Author's text</strong><span className="audiobook-source-quote">{selectedSpan.source_text}</span></p>
                <p><strong>Spoken text</strong><span className="audiobook-source-quote">{selectedSpan.speech_plan.tts_input_text}</span></p>
                {selectedSpan.speech_plan.transformations.length > 0 && <p><strong>Speech changes</strong> {selectedSpan.speech_plan.transformations.map((item) => `${item.source} → ${item.spoken}`).join(', ')}</p>}
                {selectedSpan.annotation?.delivery && <p><strong>Delivery</strong> {selectedSpan.annotation.delivery}</p>}
                {selectedIssue && <p className="audiobook-review-reason"><strong>Review: {selectedIssue.reason}</strong> {JSON.stringify(selectedIssue.evidence ?? {})}</p>}
                {selectedEdit && <div className="audiobook-annotation-controls" aria-label="Span interpretation controls">
                  <label>Speaker<select aria-label="Selected span speaker" value={selectedEdit.speaker_id} onChange={(event) => changeSpanEdit({ speaker_id: event.target.value })}>
                    <option value="">Choose speaker</option>{project.speakers.map((speaker) => <option key={speaker.id} value={speaker.id}>{speaker.canonical_name}</option>)}
                  </select></label>
                  <label>Role<select aria-label="Selected span role" value={selectedEdit.role} onChange={(event) => changeSpanEdit({ role: event.target.value })}>
                    {['narration', 'dialogue', 'heading', 'other'].map((role) => <option key={role} value={role}>{role}</option>)}
                  </select></label>
                  <label>Delivery<input aria-label="Selected span delivery" value={selectedEdit.delivery} maxLength={512} onChange={(event) => changeSpanEdit({ delivery: event.target.value })} /></label>
                  <button type="button" disabled={busy || !selectedEdit.speaker_id} onClick={() => void action(async () => {
                    const url: `/api/${string}` = selectedIssue
                      ? `${base}/projects/${encodeURIComponent(project.id)}/review/${encodeURIComponent(selectedIssue.id)}`
                      : `${base}/projects/${encodeURIComponent(project.id)}/spans/${encodeURIComponent(selectedSpan.id)}/annotation`;
                    await omnixApiClient.post(url, selectedEdit);
                    setSpanEdits((previous) => { const next = { ...previous }; delete next[selectedSpan.id]; return next; });
                  }, selectedIssue ? 'Review decision saved.' : 'Span interpretation saved. Render again to update affected audio.')}>Save interpretation</button>
                  <button type="button" disabled={busy || !modelRevision.trim()} onClick={() => void action(() => omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/preview`,
                    { chapter_id: selectedChapter.id, span_id: selectedSpan.id, model_revision: modelRevision.trim() }), 'Span preview queued.')}>Preview or regenerate span</button>
                </div>}
                {selectedPreview?.status === 'completed' && <audio controls preload="none" src={`${base}/projects/${encodeURIComponent(project.id)}/previews/${encodeURIComponent(selectedPreview.id)}/audio`} aria-label={`Selected span preview ${selectedSpan.source_text.slice(0, 48)}`} />}
              </section>}
              <div className="audiobook-preview-list" aria-label="Span previews">
                <h3>Audition a span</h3>
                {selectedChapter.spans.map((span) => {
                  const preview = project.preview_jobs?.find((job) => job.span_id === span.id);
                  return <div className="audiobook-preview-row" key={span.id}>
                    <p><small>{span.structural_kind}</small> {span.source_text}</p>
                    <button type="button" disabled={busy || !modelRevision.trim()}
                      onClick={() => void action(() => omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/preview`,
                        { chapter_id: selectedChapter.id, span_id: span.id, model_revision: modelRevision.trim() }), 'Span preview queued.')}>
                      Preview
                    </button>
                    {preview && <span>{preview.status}{preview.error?.message ? ` · ${preview.error.message}` : ''}</span>}
                    {preview?.status === 'completed' && <audio controls preload="none" src={`${base}/projects/${encodeURIComponent(project.id)}/previews/${encodeURIComponent(preview.id)}/audio`} aria-label={`Preview ${span.source_text.slice(0, 48)}`} />}
                  </div>;
                })}
              </div>
            </> : project.chapters.length ? <p>{chapterQuery.isError ? 'Could not load this chapter.' : 'Loading chapter…'}</p> : <p>Upload a source file to extract chapters. The original text remains available throughout production.</p>}
          </section>}
          {workspaceMode === 'production' && <>
          <section className="audiobook-card audiobook-production">
            <div className="audiobook-section-title"><div><p className="eyebrow">Production</p><h2>Render and export</h2></div></div>
            <div className="audiobook-progress"><progress max={Math.max(1, project.render_progress.total)} value={project.render_progress.completed} /><span>{project.render_progress.completed} / {project.render_progress.total} spans rendered</span></div>
            <div className="audiobook-action-row">
              <label>Installed model revision<input value={modelRevision} readOnly placeholder="Checking installed model" /></label>
              <button type="button" disabled={busy || !canRender || !modelRevision.trim()}
                onClick={() => void action(() => omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/render`, { model_revision: modelRevision.trim() }), 'Chapter render jobs queued.')}>
                {project.state === 'rendering' ? 'Retry render' : 'Render book'}
              </button>
              <label>Format<select value={exportFormat} onChange={(event) => setExportFormat(event.target.value)}><option value="m4b">M4B</option><option value="flac">FLAC</option><option value="wav">WAV</option><option value="mp3">MP3</option></select></label>
              <button type="button" disabled={busy || !['ready_to_export', 'exported'].includes(project.state)}
                onClick={() => void action(() => omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/exports`, { format: exportFormat }), `${exportFormat.toUpperCase()} export queued.`)}>
                Export {exportFormat.toUpperCase()}
              </button>
            </div>
            {modelQuery.isError && <p className="audiobook-hint" role="alert">The installed TTS model could not be verified. Check its local model directory.</p>}
            <p className="audiobook-hint">{project.cover_asset_id ? 'Cover ready' : 'No cover uploaded'} · {project.chapters.length} chapters · {project.state === 'ready_to_export' || project.state === 'exported' ? 'Chapter audio ready' : 'Chapter audio pending'} · Exports freeze a manifest when queued.</p>
            {project.state === 'ready_to_render' && modelQuery.isLoading && <p className="audiobook-hint">Verifying installed model artifacts…</p>}
            {project.state !== 'ready_to_render' && !['ready_to_export', 'exported'].includes(project.state) && <p className="audiobook-hint">Resolve review issues and cast every speaker before rendering. Export unlocks after chapter assembly.</p>}
            <div className="audiobook-job-list" aria-label="Production jobs">
              {[...project.render_jobs, ...project.export_jobs].map((job) => <p key={job.id}><strong>{job.format?.toUpperCase() || project.chapters.find((chapter) => chapter.id === job.chapter_id)?.title || 'Chapter render'}</strong> · {job.status} {job.progress?.message || ''}{job.progress?.generated !== undefined && ` · ${job.progress.generated} generated · ${job.progress.cache_hits ?? 0} cache hits`}{job.error?.message && <em> · {job.error.message}</em>}{['queued', 'waiting', 'retrying', 'leased', 'running'].includes(job.status) && <button type="button" disabled={busy} onClick={() => void action(() => omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/jobs/${encodeURIComponent(job.id)}/cancel`, {}), 'Job cancellation requested.')}>Cancel job</button>}</p>)}
            </div>
          </section>
          <section className="audiobook-card audiobook-exports" id="audiobook-exports"><div className="audiobook-section-title"><div><p className="eyebrow">Delivery</p><h2>Exports</h2></div></div>
            {exportsQuery.data?.exports.map((item) => <div className="audiobook-export-row" key={item.id}>
              <a href={`${base}/projects/${encodeURIComponent(project.id)}/exports/${encodeURIComponent(item.id)}/download`} download>
                <strong>{item.format.toUpperCase()}</strong><span>{new Date(item.created_at).toLocaleString()} · {(item.byte_size / 1048576).toFixed(1)} MB</span><small>Manifest {item.manifest_hash.slice(0, 12)}</small>
              </a>
              <a href={`${base}/projects/${encodeURIComponent(project.id)}/exports/${encodeURIComponent(item.id)}/report`} target="_blank" rel="noreferrer">Integrity and provenance report</a>
            </div>)}
            {exportsQuery.data?.exports.length === 0 && <p>Completed exports will appear here.</p>}
          </section>
          </>}
        </>}
      </div>

      <aside id="audiobook-outline-rail" className={`audiobook-rail audiobook-inspector${mobileRail === 'outline' ? ' mobile-open' : ''}`} aria-label="Chapter and cast inspector">
        <button className="audiobook-mobile-close" type="button" onClick={() => setMobileRail(null)}>Close outline</button>
        <section><div className="audiobook-panel-heading"><p className="eyebrow">Outline</p><h2>Chapters</h2></div>
          <div className="audiobook-outline">{project?.chapters.map((chapter) => {
            const issues = project.review_issues.filter((issue) => issue.chapter_id === chapter.id).length;
            const render = project.render_jobs.find((job) => job.chapter_id === chapter.id);
            return <button type="button" key={chapter.id} className={chapter.id === activeChapterId ? 'selected' : ''} onClick={() => setChapterId(chapter.id)}><small>{String(chapter.ordinal + 1).padStart(2, '0')} · {issues ? `${issues} to review` : render?.status || 'ready'}</small>{chapter.title}</button>;
          })}
            {project?.chapters.length === 0 && <p>No chapters yet.</p>}</div></section>
        {project && <><section className="audiobook-project-status" aria-label="Project status"><div className="audiobook-panel-heading"><p className="eyebrow">Status</p><h2>Project status</h2></div>
          <p>Canonical source: {project.current_source_revision_id ? 'extracted' : 'awaiting import'}</p>
          <p>Review issues: {project.review_issues.length}</p>
          <p>Rendered coverage: {project.render_progress.completed} / {project.render_progress.total}</p>
          <p>Words: {(project.word_count ?? 0).toLocaleString()}</p>
          <p>Estimated runtime: {formatDuration(project.estimated_runtime_seconds)}</p>
          <p>Actual runtime: {formatDuration(project.actual_runtime_seconds)}</p>
          <p>Production: {project.state.replaceAll('_', ' ')}</p>
        </section><section id="audiobook-cast"><div className="audiobook-panel-heading"><p className="eyebrow">Characters</p><h2>Voice cast</h2></div>
          <form className="audiobook-form audiobook-inline" onSubmit={submitSpeaker}><label>Speaker name<input value={speakerName} onChange={(event) => setSpeakerName(event.target.value)} /></label><button disabled={busy || !speakerName.trim()}>Add</button></form>
          {project.speakers.map((speaker) => <div className="audiobook-cast-row" key={speaker.id}><span>{speaker.canonical_name}<small>{speaker.kind} · {speaker.casting ? `revision ${speaker.casting.revision} · ${speaker.casting.voice_revision_hash?.slice(0, 10) || 'voice hash unavailable'}` : 'uncast'}</small></span>
            <select value={speaker.casting?.voice_profile_id ?? ''} disabled={busy} aria-label={`Voice for ${speaker.canonical_name}`}
              onChange={(event) => { const voice_profile_id = event.currentTarget.value; if (voice_profile_id) void action(() => omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/speakers/${encodeURIComponent(speaker.id)}/casting`, { voice_profile_id }), `Voice assigned to ${speaker.canonical_name}.`); }}>
              <option value="">Choose voice</option>{voicesQuery.data?.voices.map((voice) => <option key={voice.id} value={voice.id}>{voice.name}{voice.language ? ` · ${voice.language}` : ''}</option>)}
            </select>
            <div className="audiobook-cast-actions"><button type="button" aria-label={`Find span for ${speaker.canonical_name}`} disabled={busy} onClick={() => void action(async () => {
              const location = await findSpeakerSpan(speaker.id);
              setChapterId(location.chapterId); setSelectedSpanId(location.spanId); setWorkspaceMode('review');
            }, `Located ${speaker.canonical_name}.`)}>Find span</button>
              <button type="button" aria-label={`Audition voice for ${speaker.canonical_name}`} disabled={busy || !modelRevision.trim()} onClick={() => void action(async () => {
                const location = await findSpeakerSpan(speaker.id);
                await omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/preview`,
                  { chapter_id: location.chapterId, span_id: location.spanId, model_revision: modelRevision.trim() });
              }, `Audition queued for ${speaker.canonical_name}.`)}>Audition voice</button></div>
            {speaker.aliases?.length > 0 && <small>Aliases: {speaker.aliases.join(', ')}</small>}
            <span className="audiobook-alias-controls"><input aria-label={`Alias for ${speaker.canonical_name}`} placeholder="Known alias" value={aliasNames[speaker.id] ?? ''} onChange={(event) => setAliasNames((previous) => ({ ...previous, [speaker.id]: event.target.value }))} />
              <button type="button" disabled={busy || !aliasNames[speaker.id]?.trim()} onClick={() => void action(async () => {
                await omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/speakers/${encodeURIComponent(speaker.id)}/aliases`, { alias: aliasNames[speaker.id].trim() });
                setAliasNames((previous) => ({ ...previous, [speaker.id]: '' }));
              }, 'Speaker alias confirmed.')}>Add alias</button></span>
          </div>)}
          {voicesQuery.data?.voices.length === 0 && <p className="audiobook-hint">Add a voice profile in Voice Cloning to cast speakers.</p>}
        </section>
        <section><div className="audiobook-panel-heading"><p className="eyebrow">Human review</p><h2>Review queue <span>{project.review_issues.length}</span></h2></div>
          {project.review_issues.map((issue) => <article className="audiobook-review" key={issue.id}><small>{issue.chapter_title} · {issue.reason}{issue.speaker_candidate ? ` · proposed: ${issue.speaker_candidate}` : ''}</small><p>{issue.source_text}</p>
            {issue.speaker_candidate && <button type="button" disabled={busy} onClick={() => setSpeakerName(issue.speaker_candidate || '')}>Use proposed speaker name</button>}
            <select aria-label={`Speaker for review ${issue.id}`} value={reviewSpeakers[issue.id] ?? issue.speaker_id ?? ''} onChange={(event) => setReviewSpeakers((previous) => ({ ...previous, [issue.id]: event.target.value }))}><option value="">Choose speaker</option>{project.speakers.map((speaker) => <option key={speaker.id} value={speaker.id}>{speaker.canonical_name}</option>)}</select>
            <button type="button" disabled={busy || !(reviewSpeakers[issue.id] ?? issue.speaker_id)} onClick={() => void action(() => omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/review/${encodeURIComponent(issue.id)}`, { speaker_id: reviewSpeakers[issue.id] ?? issue.speaker_id, role: issue.structural_kind || 'narration' }), 'Review decision saved.')}>
              Confirm speaker
            </button></article>)}
          {project.review_issues.length === 0 && <p>No open review issues.</p>}
        </section>
        <section id="audiobook-pronunciations"><div className="audiobook-panel-heading"><p className="eyebrow">Speech plan</p><h2>Pronunciations</h2></div>
          <form className="audiobook-form" onSubmit={submitPronunciation}>
            <label>Source term<input value={sourceTerm} onChange={(event) => setSourceTerm(event.target.value)} maxLength={128} /></label>
            <label>Spoken form<input value={spokenTerm} onChange={(event) => setSpokenTerm(event.target.value)} maxLength={256} /></label>
            <button disabled={busy || !sourceTerm.trim() || !spokenTerm.trim()}>Save pronunciation</button>
          </form>
          {project.pronunciations?.map((entry) => <p className="audiobook-pronunciation" key={entry.source_term}><strong>{entry.source_term}</strong> → {entry.spoken_term}</p>)}
        </section></>}
      </aside>
    </main>
  );
}
