import { useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
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
  cover_asset_id?: string | null;
  source_format?: string | null;
  source_filename?: string | null;
  source_size_bytes?: number;
  chapters?: ChapterSummary[];
  word_count?: number;
  estimated_runtime_seconds?: number;
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
  span_count?: number;
  word_count?: number;
  estimated_runtime_seconds?: number;
}

interface DocumentBlockView {
  id: string;
  original_text: string;
  effective_role: string;
  confidence: number;
  render_action: 'READ' | 'SKIP' | 'READ_ONCE';
  speaker_analysis_visibility: 'INCLUDE' | 'CONTEXT_ONLY' | 'EXCLUDE';
  provenance: { source?: string; signal?: string; value?: unknown }[];
}

interface Chapter extends ChapterSummary {
  canonical_text: string;
  spans: Span[];
  document_blocks?: DocumentBlockView[];
  audiobook_mode?: 'standard' | 'story_only' | 'verbatim';
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
  status?: 'active' | 'proposed' | string;
  occurrence_count?: number;
  analysis_metadata?: {
    role?: string;
    traits?: string[];
    estimated_age?: string;
    gender_presentation?: string;
  };
  casting: { voice_profile_id: string; voice_revision_hash: string; revision: number } | null;
  aliases: string[];
  proposed_aliases?: string[];
}

interface JobStatus {
  id: string;
  status: string;
  chapter_id?: string;
  progress?: {
    current?: number;
    total?: number;
    unit_current?: number;
    unit_total?: number;
    message?: string;
    cache_hits?: number;
    generated?: number;
  };
  error?: { message?: string; code?: string; retryable?: boolean } | null;
  attempts?: number;
  max_attempts?: number;
  can_retry?: boolean;
  pause_requested?: boolean;
  paused?: boolean;
  format?: string;
  span_id?: string;
  type?: string;
  reason?: string;
  migration?: Record<string, unknown> | null;
}

const ACTIVE_RENDER_STATUSES = new Set(['queued', 'waiting', 'leased', 'running', 'retrying', 'cancel_requested', 'paused']);
const CONTROLLABLE_RENDER_STATUSES = new Set(['queued', 'waiting', 'leased', 'running', 'retrying', 'paused']);
const QUEUED_RENDER_STATUSES = new Set(['queued', 'waiting', 'retrying']);
const RUNNING_RENDER_STATUSES = new Set(['leased', 'running']);

function renderJobLabel(job: JobStatus | undefined, projectState: string): string {
  if (!job) {
    if (projectState === 'rendering') return 'Waiting';
    if (projectState === 'mastering') return 'Mastering';
    if (projectState === 'ready_to_export' || projectState === 'exported') return 'Completed';
    return 'Not started';
  }
  if (job.status === 'completed') return 'Completed';
  if (QUEUED_RENDER_STATUSES.has(job.status)) return 'Queued';
  if (RUNNING_RENDER_STATUSES.has(job.status)) return 'Rendering';
  if (job.status === 'cancel_requested') return 'Cancelling';
  if (job.status === 'paused') return 'Paused';
  if (job.status === 'failed' || job.status === 'dead_letter') return 'Failed';
  if (job.status === 'canceled' || job.status === 'cancelled') return 'Canceled';
  if (job.status === 'stale') return 'Stale';
  return job.status.replaceAll('_', ' ');
}

function renderJobProgress(job: JobStatus | undefined, projectState: string): number {
  const status = renderJobLabel(job, projectState);
  if (status === 'Completed') return 100;
  const current = Number(job?.progress?.current);
  const total = Number(job?.progress?.total);
  if (!Number.isFinite(current) || !Number.isFinite(total) || total <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((current / total) * 100)));
}

function pipelineJobProgress(job: JobStatus | undefined): number {
  return pipelineJobProgressPercent(job) ?? 0;
}

function pipelineJobProgressPercent(job: JobStatus | undefined): number | null {
  const current = Number(job?.progress?.current);
  const total = Number(job?.progress?.total);
  if (!Number.isFinite(current) || !Number.isFinite(total) || total <= 0) return null;
  return Math.max(0, Math.min(100, Math.round((current / total) * 100)));
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
  audiobook_mode?: 'standard' | 'story_only' | 'verbatim';
  document_structure_version?: string;
  render_policy_version?: string;
  analysis_policy_version?: string;
}

interface ExportRecord {
  id: string;
  format: string;
  manifest_hash: string;
  asset_id: string;
  created_at: string;
  byte_size: number;
}

interface VoiceRecord { id: string; name: string; language: string }
interface SourceLibraryFile { name: string; source_format: string; size_bytes: number }
interface SourceLibrary { directory: string; files: SourceLibraryFile[] }

type LibrarySection = 'library' | 'projects' | 'books' | 'chapters' | 'assets' | 'documents' | 'characters' | 'voices' | 'pronunciations' | 'exports';

type WorkspaceAsset = {
  id: string;
  name: string;
  type: 'Cover Art' | 'Chapter Thumbnail' | 'Audio' | 'Document' | 'Export' | 'Reference';
  detail: string;
  status: 'Used' | 'Unused' | 'Reference' | 'Ready';
  chapters?: string;
  href?: string;
  image?: boolean;
  format?: string;
  assetId?: string;
  deletable?: boolean;
};

type WorkspaceDocument = {
  id: string;
  title: string;
  type: string;
  lastEdited: string;
  author: string;
  linked: string;
  status: 'Final';
  preview: string;
  href?: string;
};

const base = '/api/audiobook';
const sourceExtensions = new Set([
  'docx', 'epub', 'html', 'htm', 'markdown', 'md', 'pdf', 'text', 'txt',
]);
const sourceAccept = '.pdf,.epub,.docx,.html,.htm,.txt,.text,.md,.markdown';
const sourceFormatsLabel = 'PDF, EPUB, DOCX, HTML, TXT, or Markdown';

async function responseError(response: Response): Promise<Error> {
  const body = await response.json().catch(() => ({})) as { detail?: string };
  return new Error(body.detail || `Request failed (${response.status})`);
}

function pageExclusionQuery(excludePageRanges: string): string {
  const value = excludePageRanges.trim();
  return value ? `&exclude_pages=${encodeURIComponent(value)}` : '';
}

async function uploadSource(projectId: string, file: File, excludePageRanges: string): Promise<void> {
  const extension = file.name.split('.').pop()?.toLowerCase();
  if (!extension || !sourceExtensions.has(extension)) {
    throw new Error(`Choose a ${sourceFormatsLabel} file.`);
  }
  const url = `${base}/projects/${encodeURIComponent(projectId)}/source?source_format=${extension}&filename=${encodeURIComponent(file.name)}${pageExclusionQuery(excludePageRanges)}`;
  const response = await fetch(url, { method: 'POST', body: file });
  if (!response.ok) throw await responseError(response);
}

async function importLibrarySource(projectId: string, filename: string, excludePageRanges: string): Promise<void> {
  const url = `${base}/projects/${encodeURIComponent(projectId)}/source/library?filename=${encodeURIComponent(filename)}${pageExclusionQuery(excludePageRanges)}`;
  const response = await fetch(url, { method: 'POST' });
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

async function deleteAudiobookProject(projectId: string): Promise<void> {
  const response = await fetch(`${base}/projects/${encodeURIComponent(projectId)}`, { method: 'DELETE' });
  if (!response.ok) throw await responseError(response);
}

async function deleteAudiobookAsset(projectId: string, assetId: string): Promise<void> {
  const response = await fetch(`${base}/projects/${encodeURIComponent(projectId)}/assets/${encodeURIComponent(assetId)}`, { method: 'DELETE' });
  if (!response.ok) throw await responseError(response);
}

async function reclassifyAudiobook(projectId: string): Promise<void> {
  await omnixApiClient.post<Record<string, never>, { job_id: string }>(
    `${base}/projects/${encodeURIComponent(projectId)}/reclassify`, {},
  );
}

async function setAudiobookReadingMode(
  projectId: string, mode: 'standard' | 'story_only' | 'verbatim',
): Promise<void> {
  const response = await fetch(
    `${base}/projects/${encodeURIComponent(projectId)}/reading-policy`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode }),
    },
  );
  if (!response.ok) throw await responseError(response);
}

async function setDocumentBlockAction(
  projectId: string, blockId: string, action: 'DEFAULT' | 'READ' | 'SKIP',
): Promise<void> {
  const response = await fetch(
    `${base}/projects/${encodeURIComponent(projectId)}/document-overrides`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scope: 'BLOCK',
        scope_key: blockId,
        action,
        role_override: null,
      }),
    },
  );
  if (!response.ok) throw await responseError(response);
}

function formatDuration(seconds?: number): string {
  if (!seconds || seconds <= 0) return '—';
  const totalMinutes = Math.round(seconds / 60);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return hours ? `${hours}h ${minutes}m` : `${minutes}m`;
}

function formatStorage(bytes: number): string {
  if (bytes <= 0) return '—';
  if (bytes >= 1024 ** 3) return `${(bytes / (1024 ** 3)).toFixed(1)} GB`;
  return `${Math.max(1, Math.round(bytes / (1024 ** 2)))} MB`;
}

function formatCount(value?: number | null): string {
  return value == null ? '—' : value.toLocaleString();
}

export function AudiobookWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const queryClient = useQueryClient();
  const [projectId, setProjectId] = useState<string | null>(null);
  const [ebookLibraryOpen, setEbookLibraryOpen] = useState(false);
  const [chapterId, setChapterId] = useState<string | null>(null);
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const [expandedSpanId, setExpandedSpanId] = useState<string | null | undefined>(undefined);
  const [speakerFilter, setSpeakerFilter] = useState('all');
  const [selectedPronunciation, setSelectedPronunciation] = useState<{ spanId: string } | null>(null);
  const [workspaceMode, setWorkspaceMode] = useState<'review' | 'production'>('review');
  const [librarySection, setLibrarySection] = useState<LibrarySection>('projects');
  const [projectSettingsOpen, setProjectSettingsOpen] = useState(false);
  const [sourceUploadProjectId, setSourceUploadProjectId] = useState<string | null>(null);
  const [deleteConfirmationOpen, setDeleteConfirmationOpen] = useState(false);
  const [assetDeleteConfirmation, setAssetDeleteConfirmation] = useState<WorkspaceAsset | null>(null);
  const [mobileRail, setMobileRail] = useState<'library' | 'outline' | null>(null);
  const [title, setTitle] = useState('');
  const [author, setAuthor] = useState('');
  const [language, setLanguage] = useState('en');
  const [projectTitle, setProjectTitle] = useState('');
  const [projectAuthor, setProjectAuthor] = useState('');
  const [speakerName, setSpeakerName] = useState('');
  const [sourceTerm, setSourceTerm] = useState('');
  const [spokenTerm, setSpokenTerm] = useState('');
  const [excludePageRanges, setExcludePageRanges] = useState('');
  const [createExcludePageRanges, setCreateExcludePageRanges] = useState('');
  const [pendingSource, setPendingSource] = useState<File | null>(null);
  const [sourceText, setSourceText] = useState('');
  const [sourceIntent, setSourceIntent] = useState<'file' | 'paste' | 'blank'>('file');
  const [sourceLibraryFilename, setSourceLibraryFilename] = useState('');
  const [sourceLibraryOpen, setSourceLibraryOpen] = useState(false);
  const [exportFormat, setExportFormat] = useState('m4b');
  const [reviewSpeakers, setReviewSpeakers] = useState<Record<string, string>>({});
  const [spanEdits, setSpanEdits] = useState<Record<string, { speaker_id: string; role: string; delivery: string }>>({});
  const [aliasNames, setAliasNames] = useState<Record<string, string>>({});
  const [voiceTargetSpeakerId, setVoiceTargetSpeakerId] = useState('');
  const [selectedVoiceId, setSelectedVoiceId] = useState('');
  const [bookSearch, setBookSearch] = useState('');
  const [ebookLibrarySearch, setEbookLibrarySearch] = useState('');
  const [ebookLibraryFormat, setEbookLibraryFormat] = useState('all');
  const [ebookLibraryFilter, setEbookLibraryFilter] = useState('all');
  const [ebookLibrarySort, setEbookLibrarySort] = useState<'recent' | 'title' | 'author'>('recent');
  const [ebookLibraryView, setEbookLibraryView] = useState<'grid' | 'list'>('grid');
  const [chapterStatusFilter, setChapterStatusFilter] = useState('all');
  const [chapterView, setChapterView] = useState<'list' | 'grid'>('list');
  const [assetSearch, setAssetSearch] = useState('');
  const [assetFilter, setAssetFilter] = useState('all');
  const [selectedAssetId, setSelectedAssetId] = useState('');
  const [documentSearch, setDocumentSearch] = useState('');
  const [documentTypeFilter, setDocumentTypeFilter] = useState('all');
  const [documentView, setDocumentView] = useState<'list' | 'grid'>('list');
  const [selectedDocumentId, setSelectedDocumentId] = useState('manuscript');
  const [documentDetailTab, setDocumentDetailTab] = useState<'preview' | 'details' | 'versions'>('preview');
  const [pronunciationSearch, setPronunciationSearch] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const projectsQuery = useQuery({
    queryKey: ['audiobook', 'projects'],
    queryFn: async () => {
      const projects: ProjectSummary[] = [];
      let page: ProjectSummary[];
      do {
        const path: `/api/${string}` = projects.length === 0
          ? `${base}/projects` : `${base}/projects?offset=${projects.length}`;
        ({ projects: page } = await omnixApiClient.get<{ projects: ProjectSummary[] }>(path));
        projects.push(...page);
      } while (page.length === 100);
      return { projects };
    },
    refetchInterval: 5000,
  });
  const libraryProjectQueries = useQueries({
    queries: (ebookLibraryOpen ? (projectsQuery.data?.projects ?? []) : []).map((item) => ({
      queryKey: ['audiobook', 'project', item.id],
      queryFn: () => omnixApiClient.get<ProjectDetail>(`${base}/projects/${encodeURIComponent(item.id)}`),
      staleTime: 5_000,
    })),
  });
  const projectQuery = useQuery({
    queryKey: ['audiobook', 'project', projectId],
    queryFn: () => omnixApiClient.get<ProjectDetail>(`${base}/projects/${encodeURIComponent(projectId!)}`),
    enabled: Boolean(projectId), refetchInterval: 3000,
  });
  const voicesQuery = useQuery({
    queryKey: ['audiobook', 'voices'],
    queryFn: () => omnixApiClient.get<{ voices: VoiceRecord[] }>(`${base}/voices`),
    enabled: Boolean(projectId),
  });
  const modelQuery = useQuery({
    queryKey: ['audiobook', 'model'],
    queryFn: () => omnixApiClient.get<{ provider_id: string; model_id: string; model_revision: string }>(`${base}/models/current`),
    staleTime: 30_000,
    enabled: false,
  });
  const exportsQuery = useQuery({
    queryKey: ['audiobook', 'exports', projectId],
    queryFn: () => omnixApiClient.get<{ exports: ExportRecord[] }>(`${base}/projects/${encodeURIComponent(projectId!)}/exports`),
    enabled: Boolean(projectId), refetchInterval: 5000,
  });
  useEffect(() => {
    if (!selectedVoiceId && voicesQuery.data?.voices[0]) setSelectedVoiceId(voicesQuery.data.voices[0].id);
  }, [selectedVoiceId, voicesQuery.data?.voices]);
  const sourceLibraryQuery = useQuery({
    queryKey: ['audiobook', 'source-library'],
    queryFn: () => omnixApiClient.get<SourceLibrary>(`${base}/source-library`),
    enabled: false,
  });
  function openSourceLibrary(): void {
    setSourceLibraryOpen(true);
    void sourceLibraryQuery.refetch();
  }
  const project = projectId ? projectQuery.data : undefined;
  useEffect(() => {
    if (busy || !projectSettingsOpen || project?.id !== sourceUploadProjectId) return;
    const sourceHeading = document.getElementById('audiobook-source-settings-title');
    sourceHeading?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
    sourceHeading?.focus();
    setSourceUploadProjectId(null);
  }, [busy, project?.id, projectSettingsOpen, sourceUploadProjectId]);
  function openSourceUpload(targetProjectId: string): void {
    setProjectSettingsOpen(true);
    setSourceUploadProjectId(targetProjectId);
  }
  const renderJobs = project?.render_jobs ?? [];
  const renderChapterIds = new Set(
    renderJobs.map((job) => job.chapter_id).filter((chapterId): chapterId is string => Boolean(chapterId)),
  );
  const renderChapterCount = renderJobs.length > 0 ? renderChapterIds.size : (project?.chapters.length ?? 0);
  const skippedRenderChapterCount = project && renderJobs.length > 0
    ? Math.max(0, project.chapters.length - renderChapterCount)
    : 0;
  const completedRenderChapters = project
    ? renderJobs.length === 0 && ['ready_to_export', 'exported'].includes(project.state)
      ? project.chapters.length
      : renderJobs.filter((job) => job.status === 'completed').length
    : 0;
  const renderProgressPercent = renderJobs.length > 0
    ? Math.round(renderJobs.reduce(
      (total, job) => total + renderJobProgress(job, project?.state ?? ''),
      0,
    ) / renderJobs.length)
    : project && ['ready_to_export', 'exported'].includes(project.state) && project.chapters.length > 0
      ? 100
      : 0;
  const isPolicySkippedChapter = (chapterId: string): boolean =>
    renderJobs.length > 0 && !renderChapterIds.has(chapterId);
  const queuedRenderJobs = renderJobs.filter((job) => QUEUED_RENDER_STATUSES.has(job.status)).length;
  const runningRenderJobs = renderJobs.filter((job) => RUNNING_RENDER_STATUSES.has(job.status)).length;
  const pausedRenderJobs = renderJobs.filter((job) => job.status === 'paused').length;
  const failedRenderJobs = renderJobs.filter((job) => ['failed', 'dead_letter'].includes(job.status)).length;
  const retryableRenderJobs = renderJobs.filter((job) => job.can_retry).length;
  const cacheHits = renderJobs.reduce((total, job) => total + (job.progress?.cache_hits ?? 0), 0);
  const proposedSpeakers = project?.speakers.filter((speaker) => speaker.status === 'proposed') ?? [];
  const castableSpeakers = project?.speakers ?? [];
  const assignedVoiceCount = castableSpeakers.filter((speaker) => speaker.casting !== null).length;
  const castLabel = castableSpeakers.length ? `${castableSpeakers.length} cast members` : 'No cast detected';
  const renderStateLabel = failedRenderJobs > 0
    ? 'Needs attention'
    : project && renderChapterCount > 0 && completedRenderChapters === renderChapterCount
      ? 'Complete'
      : project?.state === 'ready_to_render' && renderJobs.length === 0
        ? 'Not started'
        : project?.state === 'rendering'
          ? (pausedRenderJobs > 0 && runningRenderJobs === 0 ? 'Paused' : 'Rendering')
          : project?.state === 'mastering'
            ? 'Mastering'
            : 'Waiting';
  const selectedVoice = voicesQuery.data?.voices.find((voice) => voice.id === selectedVoiceId) ?? voicesQuery.data?.voices[0];
  const modelRevision = modelQuery.data?.model_revision ?? '';

  async function getInstalledModelRevision(): Promise<string> {
    const identity = await queryClient.fetchQuery({
      queryKey: ['audiobook', 'model'],
      queryFn: () => omnixApiClient.get<{
        provider_id: string;
        model_id: string;
        model_revision: string;
      }>(`${base}/models/current`),
      staleTime: 30_000,
    });
    return identity.model_revision;
  }

  const libraryProjects = (projectsQuery.data?.projects ?? []).map((item, index) => libraryProjectQueries[index]?.data ?? item);
  const filteredEbookProjects = [...libraryProjects]
    .filter((item) => {
      const search = ebookLibrarySearch.trim().toLowerCase();
      const matchesSearch = !search || `${item.title} ${item.author} ${item.language} ${item.source_format ?? ''}`.toLowerCase().includes(search);
      const status = libraryCardStatus(item);
      const matchesFormat = ebookLibraryFormat === 'all' || item.source_format === ebookLibraryFormat;
      const matchesFilter = ebookLibraryFilter === 'all'
        || (ebookLibraryFilter === 'ready' && status === 'Ready to Export')
        || (ebookLibraryFilter === 'ready-to-render' && status === 'Ready to Render')
        || (ebookLibraryFilter === 'completed' && status === 'Completed')
        || (ebookLibraryFilter === 'in-progress' && status === 'In Production')
        || (ebookLibraryFilter === 'review' && status === 'In Review')
        || (ebookLibraryFilter === 'attention' && status === 'Needs Attention')
        || (ebookLibraryFilter === 'draft' && status === 'Draft');
      return matchesSearch && matchesFormat && matchesFilter;
    })
    .sort((left, right) => ebookLibrarySort === 'title'
      ? left.title.localeCompare(right.title)
      : ebookLibrarySort === 'author'
        ? left.author.localeCompare(right.author)
        : 0);
  const libraryInProductionCount = libraryProjects.filter((item) => libraryCardStatus(item) === 'In Production').length;
  const libraryReadyCount = libraryProjects.filter((item) => libraryCardStatus(item) === 'Ready to Export').length;
  const libraryRuntimeSeconds = libraryProjects.reduce((total, item) => total + (item.estimated_runtime_seconds ?? 0), 0);
  const libraryStorageBytes = libraryProjects.reduce((total, item) => total + (item.source_size_bytes ?? 0), 0);
  useEffect(() => {
    if (!project) return;
    setProjectTitle(project.title);
    setProjectAuthor(project.author);
  }, [project?.id, project?.title, project?.author]);
  useEffect(() => {
    const rail = document.getElementById('audiobook-library-rail');
    if (rail) rail.scrollTop = 0;
  }, [projectId]);
  const activeChapterId = project?.chapters.find((chapter) => chapter.id === chapterId)?.id ?? project?.chapters[0]?.id ?? null;
  useEffect(() => {
    setExpandedSpanId(undefined);
    setSpeakerFilter('all');
    setSelectedPronunciation(null);
  }, [projectId, activeChapterId]);
  const chapterQuery = useQuery({
    queryKey: ['audiobook', 'chapter', projectId, activeChapterId],
    queryFn: () => omnixApiClient.get<Chapter>(`${base}/projects/${encodeURIComponent(projectId!)}/chapters/${encodeURIComponent(activeChapterId!)}`),
    enabled: Boolean(projectId && activeChapterId),
  });
  const selectedChapter = chapterQuery.data;
  const selectedSpan = selectedChapter?.spans.find((span) => span.id === selectedSpanId) ?? selectedChapter?.spans[0];
  const canRender = project?.state === 'ready_to_render' ||
    (project?.state === 'rendering' && project.render_jobs.length > 0 &&
      project.render_jobs.every((job) => ['completed', 'failed', 'canceled'].includes(job.status)));
  const latestPipelineJob = project?.pipeline_jobs?.[0];
  const reclassificationJob = project?.pipeline_jobs?.find((job) =>
    job.type === 'audiobook.analyze' ||
    (job.type === 'audiobook.ingest' && job.reason === 'user_requested_reclassification'));
  const reclassificationRunning = Boolean(
    reclassificationJob && ACTIVE_RENDER_STATUSES.has(reclassificationJob.status),
  );
  const reclassificationMigrating = reclassificationJob?.type === 'audiobook.ingest';
  const reclassificationProgress = pipelineJobProgress(reclassificationJob);
  const latestPipelineProgress = pipelineJobProgressPercent(latestPipelineJob);
  const failedPipelineJob = latestPipelineJob &&
    ['failed', 'canceled', 'stale', 'dead_letter'].includes(latestPipelineJob.status) &&
    latestPipelineJob.can_retry !== false ? latestPipelineJob : null;
  const selectedEdit = selectedSpan && (spanEdits[selectedSpan.id] ?? {
    speaker_id: selectedSpan.annotation?.speaker_id ?? '',
    role: selectedSpan.annotation?.role ?? selectedSpan.structural_kind,
    delivery: selectedSpan.annotation?.delivery ?? '',
  });
  const visibleSpans = selectedChapter?.spans.filter((span) =>
    speakerFilter === 'all' || (speakerFilter === 'unassigned'
      ? !span.annotation?.speaker_id
      : span.annotation?.speaker_id === speakerFilter)) ?? [];

  function capturePronunciation(spanId: string, container: HTMLElement): void {
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || !selection.anchorNode || !selection.focusNode
      || !container.contains(selection.anchorNode) || !container.contains(selection.focusNode)) return;
    const term = selection.toString().trim();
    if (!/^\p{L}[\p{L}\p{M}'’\-]*$/u.test(term) || term.length > 128) return;
    const existing = project?.pronunciations?.find((entry) => entry.source_term.toLocaleLowerCase() === term.toLocaleLowerCase());
    setSelectedPronunciation({ spanId });
    setSourceTerm(existing?.source_term ?? term);
    setSpokenTerm(existing?.spoken_term ?? term);
  }

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

  function confirmProjectDeletion(): void {
    if (!project) return;
    void action(async () => {
      await deleteAudiobookProject(project.id);
      setDeleteConfirmationOpen(false);
      setProjectSettingsOpen(false);
      setProjectId(null);
      setChapterId(null);
      setEbookLibraryOpen(true);
      setLibrarySection('library');
    }, 'Audiobook deleted from the library.');
  }

  function confirmAssetDeletion(): void {
    const assetId = assetDeleteConfirmation?.assetId;
    if (!project || !assetDeleteConfirmation || !assetId) return;
    const asset = assetDeleteConfirmation;
    void action(async () => {
      await deleteAudiobookAsset(project.id, assetId);
      setAssetDeleteConfirmation(null);
      setSelectedAssetId('');
    }, `${asset.name} deleted.`);
  }

  function submitProject(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    void action(async () => {
      const created = await omnixApiClient.post<object, ProjectSummary>(`${base}/projects`, { title, author, language });
      setProjectId(created.id);
      setChapterId(null);
      openSourceUpload(created.id);
      const source = pendingSource ?? (sourceText.trim() ? new File([sourceText], 'pasted-story.txt', { type: 'text/plain' }) : null);
      if (source) await uploadSource(created.id, source, createExcludePageRanges);
      setProjectTitle(created.title); setProjectAuthor(created.author); setExcludePageRanges(''); setCreateExcludePageRanges(''); setTitle(''); setAuthor(''); setPendingSource(null); setSourceText(''); setSourceIntent('file'); setLibrarySection('projects'); setMobileRail(null);
    }, pendingSource || sourceText.trim() ? 'Project created and source queued for extraction.' : 'Project created. Upload a source book to begin.');
  }

  function queueSamplePreview(): void {
    if (!project) return;
    void action(async () => {
      if (!project.chapters.length) throw new Error('Add a source book before playing a sample.');
      const modelRevision = await getInstalledModelRevision();
      const orderedChapters = selectedChapter
        ? [
            project.chapters.find((chapter) => chapter.id === selectedChapter.id),
            ...project.chapters.filter((chapter) => chapter.id !== selectedChapter.id),
          ].filter((chapter): chapter is ChapterSummary => Boolean(chapter))
        : project.chapters;
      for (const chapter of orderedChapters) {
        const detail = chapter.id === selectedChapter?.id ? selectedChapter : await queryClient.fetchQuery({
          queryKey: ['audiobook', 'chapter', project.id, chapter.id],
          queryFn: () => omnixApiClient.get<Chapter>(`${base}/projects/${encodeURIComponent(project.id)}/chapters/${encodeURIComponent(chapter.id)}`),
        });
        const span = detail.spans.find(
          (candidate) => Boolean(candidate.speech_plan?.tts_input_text?.trim()),
        );
        if (!span) continue;
        setChapterId(detail.id);
        setSelectedSpanId(span.id);
        await omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/preview`, {
          chapter_id: detail.id, span_id: span.id, model_revision: modelRevision.trim(),
        });
        return;
      }
      throw new Error('No renderable story speech is available under the current reading policy.');
    }, 'Sample preview queued.');
  }

  function navigateLibrary(section: LibrarySection): void {
    setEbookLibraryOpen(false);
    setLibrarySection(section);
    setProjectSettingsOpen(false);
    setSourceUploadProjectId(null);
    if (section === 'exports') setWorkspaceMode('production');
    else if (section !== 'projects') setWorkspaceMode('review');
    setMobileRail(null);
  }

  function openManuscriptReview(): void {
    navigateLibrary('projects');
    setWorkspaceMode('review');
  }

  function openEbookLibrary(): void {
    setEbookLibraryOpen(true);
    setProjectId(null);
    setChapterId(null);
    setLibrarySection('library');
    setProjectSettingsOpen(false);
    setSourceUploadProjectId(null);
    setMobileRail(null);
  }

  function startNewProject(): void {
    setEbookLibraryOpen(false);
    setProjectId(null);
    setChapterId(null);
    setSelectedSpanId(null);
    setTitle('');
    setAuthor('');
    setLanguage('en');
    setPendingSource(null);
    setSourceText('');
    setSourceIntent('file');
    setCreateExcludePageRanges('');
    setProjectSettingsOpen(false);
    setSourceUploadProjectId(null);
    setWorkspaceMode('review');
    setLibrarySection('projects');
    setError(null);
    setNotice(null);
    window.setTimeout(() => {
      const titleInput = document.getElementById('audiobook-create-title') as HTMLInputElement | null;
      titleInput?.focus();
      document.querySelector('.audiobook-create-page')?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
    }, 0);
  }

  function openProject(item: ProjectSummary): void {
    setEbookLibraryOpen(false);
    setProjectId(item.id);
    setChapterId(null);
    setProjectTitle(item.title);
    setProjectAuthor(item.author);
    setExcludePageRanges('');
    setError(null);
    setProjectSettingsOpen(false);
    setSourceUploadProjectId(null);
    setLibrarySection('projects');
    setWorkspaceMode('review');
    setMobileRail(null);
  }

  function libraryProjectStatus(item: ProjectSummary): string {
    if (item.state === 'exported') return 'Exported';
    if (item.state === 'ready_to_export') return 'Ready';
    if (item.state === 'review_required') return 'Review required';
    if (['rendering', 'mastering'].includes(item.state)) return 'In progress';
    if (item.state === 'ready_to_render') return 'Ready to render';
    if (item.state === 'failed') return 'Needs attention';
    return item.state.replaceAll('_', ' ');
  }

  function libraryCardStatus(item: ProjectSummary): string {
    if (item.state === 'exported') return 'Completed';
    if (item.state === 'ready_to_export') return 'Ready to Export';
    if (['rendering', 'mastering'].includes(item.state)) return 'In Production';
    if (item.state === 'ready_to_render') return 'Ready to Render';
    if (item.state === 'review_required') return 'In Review';
    if (item.state === 'failed') return 'Needs Attention';
    return 'Draft';
  }

  function chapterStatus(chapter: ChapterSummary): string {
    const render = project?.render_jobs.find((job) => job.chapter_id === chapter.id);
    if (project && isPolicySkippedChapter(chapter.id)) return 'Skipped';
    const renderLabel = renderJobLabel(render, project?.state ?? '');
    if (renderLabel === 'Completed') return 'Rendered';
    if (['Queued', 'Rendering', 'Retrying', 'Waiting', 'Cancelling', 'Paused'].includes(renderLabel)) return renderLabel === 'Queued' ? 'Queued' : 'In Progress';
    if (['Failed', 'Canceled', 'Stale'].includes(renderLabel)) return 'Needs attention';
    if (project?.review_issues.some((issue) => issue.chapter_id === chapter.id)) return 'In Review';
    return 'Draft';
  }

  function workspaceAssetList(): WorkspaceAsset[] {
    if (!project) return [];
    const cover = project.cover_asset_id ? [{
      id: `cover-${project.cover_asset_id}`, name: 'Project cover', type: 'Cover Art' as const,
      detail: 'Cover image', status: 'Used' as const, chapters: 'Current project cover',
      href: `${base}/projects/${encodeURIComponent(project.id)}/cover`, image: true, format: 'Image',
      assetId: project.cover_asset_id, deletable: true,
    }] : [];
    const source = project.current_source_revision_id ? [{
      id: `source-${project.current_source_revision_id}`, name: project.source_filename || `${project.title} (Manuscript)`, type: 'Document' as const,
      detail: `Manuscript · ${(project.source_format || 'source').toUpperCase()}`, status: 'Used' as const, chapters: `All ${project.chapters.length} chapters`,
      href: `${base}/projects/${encodeURIComponent(project.id)}/source/download`, format: (project.source_format || 'Source').toUpperCase(), deletable: false,
    }] : [];
    const exports = (exportsQuery.data?.exports ?? []).map((item) => ({
      id: `export-${item.id}`, name: `audiobook.${item.format}`, type: 'Audio' as const,
      detail: `${item.format.toUpperCase()} · Export`, status: 'Ready' as const, chapters: 'Entire book',
      href: `${base}/projects/${encodeURIComponent(project.id)}/exports/${encodeURIComponent(item.id)}/download`, format: item.format.toUpperCase(),
      assetId: item.asset_id, deletable: true,
    }));
    return [...cover, ...source, ...exports];
  }

  function workspaceDocumentList(): WorkspaceDocument[] {
    if (!project) return [];
    const preview = selectedChapter?.canonical_text || 'Open this document to preview the canonical manuscript.';
    return [
      ...(project.current_source_revision_id ? [{ id: 'manuscript', title: project.source_filename || `${project.title} (Manuscript)`, type: 'Manuscript', lastEdited: 'Current source', author: project.author || 'Unknown author', linked: `All (${project.chapters.length})`, status: 'Final' as const, preview, href: `${base}/projects/${encodeURIComponent(project.id)}/source/download` }] : []),
      ...(exportsQuery.data?.exports ?? []).map((item) => ({ id: `export-${item.id}`, title: `${item.format.toUpperCase()} Export Report`, type: 'Export Notes', lastEdited: new Date(item.created_at).toLocaleString(), author: project.author || 'Project export', linked: 'Entire book', status: 'Final' as const, preview: `Manifest ${item.manifest_hash}`, href: `${base}/projects/${encodeURIComponent(project.id)}/exports/${encodeURIComponent(item.id)}/report` })),
    ];
  }

  async function queueChapterPreview(chapter: ChapterSummary): Promise<void> {
    if (!project) return;
    const modelRevision = await getInstalledModelRevision();
    const detail = chapter.id === selectedChapter?.id ? selectedChapter : await queryClient.fetchQuery({
      queryKey: ['audiobook', 'chapter', project.id, chapter.id],
      queryFn: () => omnixApiClient.get<Chapter>(`${base}/projects/${encodeURIComponent(project.id)}/chapters/${encodeURIComponent(chapter.id)}`),
    });
    const span = detail.spans.find(
      (candidate) => Boolean(candidate.speech_plan?.tts_input_text?.trim()),
    );
    if (!span) {
      throw new Error('This chapter has no renderable speech under the current reading policy.');
    }
    await omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/preview`, {
      chapter_id: chapter.id, span_id: span.id, model_revision: modelRevision.trim(),
    });
    setChapterId(chapter.id); setSelectedSpanId(span.id);
  }

  function renderJobEndpoint(jobId: string, actionName: 'pause' | 'resume' | 'cancel'): `/api/${string}` {
    return `${base}/projects/${encodeURIComponent(project!.id)}/jobs/${encodeURIComponent(jobId)}/${actionName}`;
  }

  function pauseReclassification(): void {
    if (!project || !reclassificationJob || reclassificationMigrating) return;
    void action(
      () => omnixApiClient.post(renderJobEndpoint(reclassificationJob.id, 'pause'), {}),
      'Text reclassification pause requested.',
    );
  }

  function resumeReclassification(): void {
    if (!project || !reclassificationJob || reclassificationMigrating) return;
    void action(
      () => omnixApiClient.post(renderJobEndpoint(reclassificationJob.id, 'resume'), {}),
      'Text reclassification resumed.',
    );
  }

  function cancelReclassification(): void {
    if (!project || !reclassificationJob) return;
    void action(
      () => omnixApiClient.post(renderJobEndpoint(reclassificationJob.id, 'cancel'), {}),
      'Text reclassification canceled.',
    );
  }

  function pauseAllRenderJobs(): void {
    if (!project) return;
    void action(() => omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/render/pause`, {}), 'Render queue paused.');
  }

  function resumeAllRenderJobs(): void {
    if (!project) return;
    void action(() => omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/render/resume`, {}), 'Render queue resumed.');
  }

  function stopAllRenderJobs(): void {
    if (!project) return;
    void action(() => omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/render/stop`, {}), 'Render queue stopped.');
  }

  function startChapter(chapter: ChapterSummary): void {
    setChapterId(chapter.id);
    navigateLibrary('projects');
  }

  function importProjectFile(file: File): void {
    if (!project) return;
    const image = /^image\/(jpeg|png)$/.test(file.type) || /\.(jpe?g|png)$/i.test(file.name);
    void action(async () => {
      if (image) await uploadCover(project.id, file);
      else await uploadSource(project.id, file, excludePageRanges);
      setExcludePageRanges('');
    }, image ? 'Cover saved.' : 'Document queued for extraction.');
  }

  function openDocument(document: WorkspaceDocument): void {
    if (document.id.startsWith('export-')) navigateLibrary('exports');
    else navigateLibrary('projects');
  }

  function submitSpeaker(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (!projectId || !speakerName.trim()) return;
    void action(async () => {
      await omnixApiClient.post(`${base}/projects/${encodeURIComponent(projectId)}/speakers`, { canonical_name: speakerName.trim() });
      setSpeakerName('');
    }, 'Speaker added.');
  }

  function confirmProposedSpeaker(speaker: Speaker): void {
    if (!projectId) return;
    void action(
      () => omnixApiClient.post(`${base}/projects/${encodeURIComponent(projectId)}/speakers`, {
        canonical_name: speaker.canonical_name,
      }),
      `${speaker.canonical_name} added to the cast. Review spans are now assigned to this speaker.`,
    );
  }

  function submitPronunciation(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (!projectId || !sourceTerm.trim() || !spokenTerm.trim()) return;
    void action(async () => {
      await omnixApiClient.post(`${base}/projects/${encodeURIComponent(projectId)}/pronunciations`,
        { source_term: sourceTerm.trim(), spoken_term: spokenTerm.trim() });
      setSourceTerm(''); setSpokenTerm(''); setSelectedPronunciation(null);
    }, 'Pronunciation saved. Affected speech plans will use the new form.');
  }

  return (
    <main className="audiobook-workspace" aria-label={`${module.label} workspace`}>
      <aside id="audiobook-library-rail" className={`audiobook-rail audiobook-library${mobileRail === 'library' ? ' mobile-open' : ''}`} aria-label="Audiobook projects">
        <button className="audiobook-mobile-close" type="button" onClick={() => setMobileRail(null)}>Close library</button>
        <div className="audiobook-panel-heading"><p className="eyebrow">Library</p><h2>Audiobooks</h2></div>
        <nav className="audiobook-library-nav" aria-label="Audiobook sections">
          {([['library', 'Library'], ['projects', 'Projects'], ['books', 'Books'], ['characters', 'Characters'], ['voices', 'Voices'], ['pronunciations', 'Pronunciations'], ['exports', 'Exports']] as [LibrarySection, string][]).map(([section, label]) => {
            const activeSideSection = ebookLibraryOpen ? 'library' : ['projects', 'chapters', 'assets', 'documents', 'exports'].includes(librarySection) ? 'projects' : librarySection;
            return <button key={section} type="button" className={activeSideSection === section ? 'selected' : ''}
              aria-current={activeSideSection === section ? 'page' : undefined} onClick={() => section === 'library' || (section === 'books' && !projectId) ? openEbookLibrary() : navigateLibrary(section)}>{label}</button>;
          })}
        </nav>
        <section className="audiobook-drafts">
          <p className="eyebrow">Create</p>
          <div className="audiobook-draft-card"><strong>New audiobook</strong><p>Create a project and upload a source book.</p><button type="button" onClick={startNewProject}>Start new project</button></div>
        </section>
        <div className="audiobook-project-list" id="audiobook-projects">
          <p className="eyebrow">Projects</p>
          {projectsQuery.isLoading && <p>Loading projects…</p>}
          {projectsQuery.isError && <p role="alert">Could not load projects.</p>}
          {projectsQuery.data?.projects.map((item) => (
            <button type="button" key={item.id} className={item.id === projectId ? 'selected' : ''}
              onClick={() => openProject(item)}>
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
        {!projectId && ebookLibraryOpen && <section className="audiobook-card audiobook-ebook-library-page">
          <div className="audiobook-library-hero">
            <div><p className="eyebrow">Audiobook library</p><h1>Audiobook Library</h1><p>All your audiobook projects in one place.</p></div>
            <div className="audiobook-library-hero-art" aria-hidden="true"><div className="audiobook-library-books"><i /><i /><i /><i /><i /></div><span>“Great stories<br />sound even better here.”</span></div>
            <button type="button" className="audiobook-primary-action" onClick={() => { setEbookLibraryOpen(false); setLibrarySection('projects'); }}>＋ New audiobook</button>
          </div>
          <div className="audiobook-library-stats" aria-label="Library summary">
            <article><span className="library-stat-icon">▣</span><div><strong>{libraryProjects.length}</strong><small>Total Audiobooks</small></div></article>
            <article><span className="library-stat-icon">▶</span><div><strong>{libraryInProductionCount}</strong><small>In Production</small></div></article>
            <article><span className="library-stat-icon">✓</span><div><strong>{libraryReadyCount}</strong><small>Ready to Export</small></div></article>
            <article><span className="library-stat-icon">◷</span><div><strong>{formatDuration(libraryRuntimeSeconds)}</strong><small>Est. Runtime</small></div></article>
            <article><span className="library-stat-icon">▤</span><div><strong>{formatStorage(libraryStorageBytes)}</strong><small>Source Storage</small></div></article>
          </div>
          <div className="audiobook-library-toolbar">
            <label className="audiobook-search-field">Search audiobooks<input aria-label="Search audiobooks" value={ebookLibrarySearch} onChange={(event) => setEbookLibrarySearch(event.target.value)} placeholder="Search by title, author, language, or format..." /></label>
            <label><span>Format</span><select aria-label="Filter by format" value={ebookLibraryFormat} onChange={(event) => setEbookLibraryFormat(event.target.value)}><option value="all">All formats</option><option value="pdf">PDF</option><option value="epub">EPUB</option><option value="docx">DOCX</option><option value="html">HTML</option><option value="htm">HTM</option><option value="txt">TXT</option><option value="text">Text</option><option value="md">MD</option><option value="markdown">Markdown</option></select></label>
            <label><span>Status</span><select aria-label="Filter by status" value={ebookLibraryFilter} onChange={(event) => setEbookLibraryFilter(event.target.value)}><option value="all">All statuses</option><option value="in-progress">In production</option><option value="ready">Ready to export</option><option value="ready-to-render">Ready to render</option><option value="completed">Completed</option><option value="review">In review</option><option value="attention">Needs attention</option><option value="draft">Draft</option></select></label>
            <label><span>Sort</span><select aria-label="Sort library" value={ebookLibrarySort} onChange={(event) => setEbookLibrarySort(event.target.value as typeof ebookLibrarySort)}><option value="recent">Last edited</option><option value="title">Title</option><option value="author">Author</option></select></label>
            <button type="button" className={ebookLibraryView === 'grid' ? 'selected' : ''} aria-label="Grid view" onClick={() => setEbookLibraryView('grid')}>▦</button>
            <button type="button" className={ebookLibraryView === 'list' ? 'selected' : ''} aria-label="List view" onClick={() => setEbookLibraryView('list')}>☷</button>
          </div>
          <p className="audiobook-library-count">Showing {filteredEbookProjects.length} of {libraryProjects.length} audiobooks</p>
          {(projectsQuery.isLoading || libraryProjectQueries.some((query) => query.isLoading)) && <p role="status">Loading audiobook library...</p>}
          {projectsQuery.isError && <p role="alert">Could not load the audiobook library.</p>}
          {ebookLibraryView === 'grid' ? <div className="audiobook-ebook-grid">
            {filteredEbookProjects.map((item) => {
              const status = libraryCardStatus(item);
              return <article className="audiobook-ebook-card" key={item.id}>
                <div className="audiobook-ebook-cover">{item.cover_asset_id ? <img src={`${base}/projects/${encodeURIComponent(item.id)}/cover`} alt={`Cover of ${item.title}`} /> : <span>✦</span>}</div>
                <div className="audiobook-ebook-card-copy">
                  <div className="audiobook-ebook-card-topline"><span className={`audiobook-status-pill library-status-${status.toLowerCase().replaceAll(' ', '-')}`}>{status}</span><button type="button" aria-label={`More actions for ${item.title}`} onClick={() => { openProject(item); setProjectSettingsOpen(true); }}>...</button></div>
                  <h2 title={item.title}>{item.title}</h2>
                  <p>{item.author || 'Unknown author'} · {item.language === 'en' ? 'English' : item.language}</p>
                  <p className="audiobook-ebook-description">{item.source_filename || 'No source uploaded yet'}</p>
                  {item.source_format && <div className="audiobook-library-card-tags"><span>{item.source_format.toUpperCase()} source</span></div>}
                  <div className="audiobook-ebook-card-stats"><span><strong>{formatCount(item.word_count)}</strong><small>words</small></span><span><strong>{formatCount(item.chapters?.length)}</strong><small>chapters</small></span><span><strong>{formatDuration(item.estimated_runtime_seconds)}</strong><small>runtime</small></span></div>
                  <div className="audiobook-card-actions"><button type="button" className="audiobook-primary-action" onClick={() => openProject(item)}>{status === 'In Production' ? 'Continue' : 'Open'}</button>{item.current_source_revision_id && <a className="audiobook-button-link" href={`${base}/projects/${encodeURIComponent(item.id)}/source/download`} download aria-label={`Download ${item.title} source`}>{item.source_format === 'pdf' ? 'Download PDF' : 'Download source'}</a>}<button type="button" onClick={() => { openProject(item); setProjectSettingsOpen(true); }}>Edit</button></div>
                </div>
              </article>;
            })}
          </div> : <div className="audiobook-ebook-list" role="table" aria-label="All audiobooks">
            {filteredEbookProjects.map((item) => <div className="audiobook-ebook-list-row" role="row" key={item.id}><div className="audiobook-ebook-list-cover">{item.cover_asset_id ? <img src={`${base}/projects/${encodeURIComponent(item.id)}/cover`} alt="" /> : <span>✦</span>}</div><div><strong>{item.title}</strong><small>{item.author || 'Unknown author'} · {libraryCardStatus(item)}</small></div><span>{formatCount(item.chapters?.length)} chapters</span><span>{formatCount(item.word_count)} words</span><button type="button" className="audiobook-primary-action" onClick={() => openProject(item)}>Open</button>{item.current_source_revision_id && <a className="audiobook-button-link" href={`${base}/projects/${encodeURIComponent(item.id)}/source/download`} download aria-label={`Download ${item.title} source`}>{item.source_format === 'pdf' ? 'Download PDF' : 'Download source'}</a>}</div>)}
          </div>}
          {!projectsQuery.isLoading && !filteredEbookProjects.length && <div className="audiobook-library-empty"><strong>No audiobooks match this view.</strong><p>Try another search or create your first audiobook project.</p><button type="button" onClick={() => { setEbookLibraryOpen(false); setLibrarySection('projects'); }}>Create audiobook</button></div>}
        </section>}
        {!projectId && !ebookLibraryOpen && <section className="audiobook-card audiobook-empty audiobook-create-page">
          <div className="audiobook-create-hero">
            <div><p className="eyebrow">Audiobook project</p><h1>Create a New Audiobook Project</h1><p>Turn your story, document, or ideas into a professional audiobook with AI.</p>
              <div className="audiobook-value-points"><span>◉ Natural voices</span><span>▣ Local &amp; private</span><span>✦ Full creative control</span><span>⇧ Export anywhere</span></div>
            </div>
            <div className="audiobook-hero-art" aria-hidden="true"><span>Stories<br />sound better<br />here.</span></div>
          </div>
          <h2>1. Choose your content source</h2><p className="audiobook-subtitle">Start with a file, paste your text, or begin with a blank project.</p>
          <div className="audiobook-source-options">
            <label className={`audiobook-source-option${pendingSource && /\.(epub|pdf)$/i.test(pendingSource.name) ? ' selected' : ''}`}>
              <input type="file" accept=".epub,.pdf" onChange={(event) => { const file = event.currentTarget.files?.[0]; if (file) { setPendingSource(file); setSourceIntent('file'); } }} />
              <strong>▥<br />Import EPUB or PDF</strong><small>Import a book file with chapters automatically detected.</small>
            </label>
            <label className={`audiobook-source-option${pendingSource && /\.(md|markdown)$/i.test(pendingSource.name) ? ' selected' : ''}`}>
              <input type="file" accept=".md,.markdown" onChange={(event) => { const file = event.currentTarget.files?.[0]; if (file) { setPendingSource(file); setSourceIntent('file'); } }} />
              <strong>▤<br />Import Markdown</strong><small>Import a .md file with clean formatting and chapter support.</small>
            </label>
            <button type="button" className={`audiobook-source-option${sourceIntent === 'paste' ? ' selected' : ''}`} onClick={() => setSourceIntent('paste')}>
              <strong>▣<br />Paste Text</strong><small>Paste your story or text content directly into the editor.</small>
            </button>
            <label className={`audiobook-source-option${pendingSource && /\.(txt|text)$/i.test(pendingSource.name) ? ' selected' : ''}`}>
              <input type="file" accept=".txt,.text" onChange={(event) => { const file = event.currentTarget.files?.[0]; if (file) { setPendingSource(file); setSourceIntent('file'); } }} />
              <strong>⇧<br />Upload TXT</strong><small>Upload a plain text file to get started quickly.</small>
            </label>
            <button type="button" className={`audiobook-source-option${sourceIntent === 'blank' ? ' selected' : ''}`} onClick={() => { setSourceIntent('blank'); setPendingSource(null); setSourceText(''); }}>
              <strong>＋<br />Start Blank Project</strong><small>Create a project now and upload a source later.</small>
            </button>
          </div>
          {sourceIntent === 'paste' && <label className="audiobook-paste-source">Paste source text<textarea value={sourceText} onChange={(event) => setSourceText(event.target.value)} placeholder="Paste a short story or manuscript here…" rows={5} /></label>}
          {(pendingSource || sourceText.trim()) && <p className="audiobook-selected-source" role="status">Source ready: {pendingSource?.name ?? 'pasted-story.txt'}. It will be queued immediately after the project is created.</p>}
          <form className="audiobook-create-details" onSubmit={submitProject}>
            <div><h2>2. Project details</h2><p className="audiobook-subtitle">Set up your audiobook project. You can change these later.</p></div>
            <label>Project title *<input id="audiobook-create-title" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="e.g. The Lantern at Hollow Bay" required /></label>
            <label>Author<input value={author} onChange={(event) => setAuthor(event.target.value)} placeholder="e.g. Mira Vale" /></label>
            <label>Language<input value={language} onChange={(event) => setLanguage(event.target.value)} placeholder="en" required /></label>
            <details className="audiobook-create-advanced"><summary>Advanced settings</summary><label>Exclude PDF pages<input inputMode="text" placeholder="e.g. 1-3, 42-45" value={createExcludePageRanges} onChange={(event) => setCreateExcludePageRanges(event.target.value)} /><small>Applied when the selected PDF is queued.</small></label></details>
            <div className="audiobook-create-details-actions"><span>Local-first processing · source files stay in Omnix storage.</span><button type="submit" disabled={busy || !title.trim()}>✦ Create project&nbsp; →</button></div>
          </form>
        </section>}
        {projectId && projectQuery.isLoading && <section className="audiobook-card"><p>Loading book…</p></section>}
        {projectId && projectQuery.isError && <section className="audiobook-card" role="alert"><p>Could not load this project.</p></section>}
        {project && <>
          <nav className="audiobook-breadcrumb" aria-label="Audiobook breadcrumb"><button type="button" onClick={() => navigateLibrary('projects')}>Audiobook</button><span>›</span><strong>{project.title}</strong>{librarySection !== 'projects' && <><span>›</span><strong>{({ library: 'Library', books: 'Books', chapters: 'Chapters', assets: 'Assets', documents: 'Documents', characters: 'Cast & Voice Tools', voices: 'Voices', pronunciations: 'Pronunciations', exports: 'Render & Export', projects: 'Projects' } as Record<LibrarySection, string>)[librarySection]}</strong></>}</nav>
          <header className="audiobook-card audiobook-project-header" id="audiobook-book">
            <div className="audiobook-project-overview">
              {project.cover_asset_id && <img className="audiobook-cover" src={`${base}/projects/${encodeURIComponent(project.id)}/cover`} alt={`Cover of ${project.title}`} />}
              <div className="audiobook-header-copy"><p className="eyebrow">Audiobook project · {project.state.replaceAll('_', ' ')}</p><h1>{project.title}</h1><p>A local-first audiobook production workspace.</p>
                <div className="audiobook-tag-row">{project.source_format && <span>{project.source_format.toUpperCase()} source</span>}<span>{project.chapters.length} chapters</span></div>
                <p className="audiobook-project-stats"><span className="audiobook-project-stats-sentence">{formatCount(project.word_count)} words</span><strong>{formatCount(project.word_count)}</strong><small>WORDS</small><strong>{project.chapters.length}</strong><small>CHAPTERS</small><strong>{project.speakers.length}</strong><small>SPEAKERS</small><strong>{formatDuration(project.estimated_runtime_seconds)}</strong><small>EST. RUNTIME</small></p>
              </div>
            </div>
            <div className="audiobook-project-header-side">
              <div className="audiobook-header-action-buttons"><button type="button" aria-expanded={projectSettingsOpen} onClick={() => setProjectSettingsOpen((open) => !open)}>{projectSettingsOpen ? 'Close editor' : 'Edit project'}</button><button type="button" className="audiobook-primary-action" disabled={busy} onClick={queueSamplePreview}>Play sample</button><button type="button" aria-label="More project actions" onClick={() => setProjectSettingsOpen(true)}>...</button></div>
              <div className="audiobook-status-meter"><div><p className="eyebrow">Project status</p><strong>{project.review_issues.length ? 'Review required' : project.state.replaceAll('_', ' ')}</strong><span>{project.review_issues.length ? `${project.review_issues.length} issues to resolve` : `${completedRenderChapters} / ${renderChapterCount} audiobook chapters rendered`}</span></div><b>{renderProgressPercent}%</b><progress max={100} value={renderProgressPercent} /></div>
            </div>
            <section className="audiobook-production-flow" aria-labelledby="audiobook-production-flow-title">
              <div className="audiobook-production-flow-heading"><div><p className="eyebrow">Production path</p><h2 id="audiobook-production-flow-title">From manuscript to audiobook</h2></div><p>Follow these steps in order. Open any step to continue your work.</p></div>
              <ol className="audiobook-production-flow-steps" aria-label="Audiobook production steps">
                {[
                  { title: 'Add source', detail: 'Upload the book; set title, author, and reading mode.', status: project.current_source_revision_id ? 'Source attached' : 'Source needed', complete: Boolean(project.current_source_revision_id), action: 'Open source', open: () => openSourceUpload(project.id) },
                  { title: 'Review text', detail: 'Check spans and set names or words TTS should pronounce differently.', status: `${project.pronunciations?.length ?? 0} pronunciation rules`, complete: false, action: 'Review spans', open: openManuscriptReview },
                  { title: 'Check speakers', detail: 'Run or review classification, then correct character assignments.', status: reclassificationRunning ? 'Classifying' : project.review_issues.length ? `${project.review_issues.length} issues to review` : `${project.speakers.length} speakers found`, complete: false, action: 'Review speakers', open: openManuscriptReview },
                  { title: 'Cast and direct', detail: 'Assign voices and adjust the delivery or emotion of dialogue.', status: `${assignedVoiceCount} / ${castableSpeakers.length} voices assigned`, complete: castableSpeakers.length > 0 && assignedVoiceCount === castableSpeakers.length, action: 'Manage cast', open: () => navigateLibrary('characters') },
                  { title: 'Preview and render', detail: 'Listen to a sample, then generate the chapter audio.', status: `${renderProgressPercent}% rendered`, complete: renderChapterCount > 0 && completedRenderChapters === renderChapterCount, action: 'Open render', open: () => navigateLibrary('exports') },
                  { title: 'Export', detail: 'Choose a format and download the finished audiobook.', status: project.state === 'exported' ? 'Exported' : ['ready_to_export', 'exported'].includes(project.state) ? 'Ready to export' : 'After rendering', complete: project.state === 'exported', action: 'Open exports', open: () => navigateLibrary('exports') },
                ].map((step, index) => <li key={step.title} className={step.complete ? 'complete' : ''}>
                  <span className="audiobook-production-flow-number" aria-hidden="true">{index + 1}</span>
                  <div className="audiobook-production-flow-copy"><strong>{step.title}</strong><small>{step.detail}</small></div>
                  <span className="audiobook-production-flow-status">{step.status}</span>
                  <button type="button" onClick={step.open}>{step.action}</button>
                </li>)}
              </ol>
            </section>
            {projectSettingsOpen && <div className="audiobook-project-actions">
              <section className="audiobook-settings-card audiobook-source-settings" aria-labelledby="audiobook-source-settings-title">
                <div className="audiobook-settings-heading"><div><p className="eyebrow">Manuscript</p><h2 id="audiobook-source-settings-title" tabIndex={-1}>Book source</h2></div><span className={`audiobook-source-state ${project.current_source_revision_id ? 'attached' : 'needed'}`}>{project.current_source_revision_id ? 'Source attached' : 'Source needed'}</span></div>
                <p className="audiobook-source-filename">{project.source_filename || 'No book uploaded yet'}</p>
                <p className="audiobook-settings-description">Upload a PDF, EPUB, DOCX, Markdown, HTML, or text file to extract chapters.</p>
                <div className="audiobook-source-actions">
                  <label className="audiobook-source-file-button"><span>Upload from computer</span>
                    <input type="file" accept={sourceAccept} disabled={busy}
                      onChange={(event) => { const file = event.currentTarget.files?.[0]; if (file) void action(async () => { await uploadSource(project.id, file, excludePageRanges); setExcludePageRanges(''); }, 'Source queued for extraction.'); event.currentTarget.value = ''; }} />
                  </label>
                  <button type="button" className="audiobook-source-library-trigger" disabled={busy} onClick={openSourceLibrary}>Choose from local library</button>
                </div>
                <details className="audiobook-source-library" open={sourceLibraryOpen} onToggle={(event) => {
                  setSourceLibraryOpen(event.currentTarget.open);
                  if (event.currentTarget.open && !sourceLibraryQuery.data) void sourceLibraryQuery.refetch();
                }}>
                  <summary>Browse resources\data\audiobooks</summary>
                  <p className="audiobook-hint">Choose a book already stored in the local audiobook folder.</p>
                  {sourceLibraryQuery.isFetching && <p role="status">Loading local books…</p>}
                  {sourceLibraryQuery.isError && <p role="alert">Could not read the local audiobook folder.</p>}
                  {sourceLibraryQuery.data && !sourceLibraryQuery.data.files.length && <p role="status">No supported books found in this folder.</p>}
                  {sourceLibraryQuery.data && sourceLibraryQuery.data.files.length > 0 && <>
                    <label>Source book<select aria-label="Local audiobook source" value={sourceLibraryFilename}
                      onChange={(event) => setSourceLibraryFilename(event.target.value)} disabled={busy}>
                      <option value="">Choose a source book</option>
                      {sourceLibraryQuery.data.files.map((file) => <option key={file.name} value={file.name}>{file.name}</option>)}
                    </select></label>
                    <button type="button" disabled={busy || !sourceLibraryFilename}
                      onClick={() => void action(async () => { await importLibrarySource(project.id, sourceLibraryFilename, excludePageRanges); setExcludePageRanges(''); }, 'Source queued for extraction.')}>Use selected book</button>
                  </>}
                </details>
                <details className="audiobook-source-advanced"><summary>PDF page options</summary>
                  <label className="audiobook-page-filter">Exclude pages
                    <input aria-label="Exclude PDF pages" inputMode="text" placeholder="e.g. 1-3, 42-45"
                      value={excludePageRanges} onChange={(event) => setExcludePageRanges(event.target.value)} disabled={busy} />
                    <small>Enter 1-based page numbers. Applied when the next PDF source is uploaded.</small>
                  </label>
                </details>
                <div className="audiobook-source-reclassify"><div><strong>Text classification</strong><p>Rerun dialogue and speaker detection for this source.</p></div>
                  <button type="button" disabled={busy || reclassificationRunning || !project.current_source_revision_id}
                    onClick={() => void action(() => reclassifyAudiobook(project.id), 'Text reclassification queued.')}>
                    {reclassificationRunning ? 'Reclassifying…' : 'Reclassify text'}
                  </button>
                </div>
              </section>
              <div className="audiobook-settings-side">
                <section className="audiobook-settings-card" aria-labelledby="audiobook-details-settings-title">
                  <div className="audiobook-settings-heading"><div><p className="eyebrow">Project</p><h2 id="audiobook-details-settings-title">Details &amp; reading</h2></div></div>
                  <div className="audiobook-settings-fields"><label>Title<input value={projectTitle} onChange={(event) => setProjectTitle(event.target.value)} /></label>
                    <label>Author<input value={projectAuthor} onChange={(event) => setProjectAuthor(event.target.value)} /></label></div>
                  <label className="audiobook-reading-mode">Audiobook reading mode
                    <select aria-label="Audiobook reading mode" value={project.audiobook_mode ?? 'standard'} disabled={busy}
                      onChange={(event) => { const mode = event.target.value as 'standard' | 'story_only' | 'verbatim'; void action(() => setAudiobookReadingMode(project.id, mode), `Reading mode changed to ${mode.replaceAll('_', ' ')}.`); }}>
                      <option value="standard">Standard audiobook</option><option value="story_only">Story only</option><option value="verbatim">Verbatim source</option>
                    </select>
                    <small>{(project.audiobook_mode ?? 'standard') === 'story_only'
                      ? 'Reads the story and scene headings while skipping front matter, page numbers, and publishing details.'
                      : (project.audiobook_mode ?? 'standard') === 'verbatim'
                        ? 'Reads every extracted block, including headings and publishing details.'
                        : 'Reads story and chapter structure while skipping contents pages and running headers.'}</small>
                  </label>
                  <button type="button" className="audiobook-settings-save" disabled={busy || !projectTitle.trim() || (projectTitle === project.title && projectAuthor === project.author)}
                    onClick={() => void action(() => updateProjectMetadata(project.id, projectTitle.trim(), projectAuthor.trim()), 'Project metadata saved. Export metadata will use the new values.')}>Save details</button>
                </section>
                <section className="audiobook-settings-card audiobook-cover-settings" aria-labelledby="audiobook-cover-settings-title">
                  <div className="audiobook-settings-heading"><div><p className="eyebrow">Artwork</p><h2 id="audiobook-cover-settings-title">Book cover</h2></div></div>
                  <p className="audiobook-settings-description">{project.cover_asset_id ? 'Cover added. Upload a new image to replace it.' : 'Add a cover image for your audiobook.'}</p>
                  <label className="audiobook-source-file-button audiobook-cover-file-button"><span>{project.cover_asset_id ? 'Replace cover' : 'Choose cover image'}</span>
                    <input type="file" accept="image/jpeg,image/png" disabled={busy}
                      onChange={(event) => { const file = event.currentTarget.files?.[0]; if (file) void action(() => uploadCover(project.id, file), 'Cover saved for future exports.'); event.currentTarget.value = ''; }} />
                  </label>
                </section>
                <section className="audiobook-settings-card audiobook-danger-settings" aria-labelledby="audiobook-danger-settings-title">
                  <div><p className="eyebrow">Danger zone</p><h2 id="audiobook-danger-settings-title">Delete project</h2></div>
                  <button type="button" className="audiobook-danger-action" disabled={busy} onClick={() => setDeleteConfirmationOpen(true)}>Delete audiobook</button>
                </section>
              </div>
            </div>}
          </header>
          {deleteConfirmationOpen && <div className="audiobook-modal-backdrop" role="presentation" onMouseDown={() => { if (!busy) setDeleteConfirmationOpen(false); }}>
            <section className="audiobook-confirmation-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-audiobook-title" onMouseDown={(event) => event.stopPropagation()}>
              <p className="eyebrow">Delete audiobook</p>
              <h2 id="delete-audiobook-title">Delete “{project.title}”?</h2>
              <p>This removes the audiobook from your library and cancels active production jobs. Immutable source and production history is retained for audit safety.</p>
              <div className="audiobook-confirmation-actions"><button type="button" disabled={busy} onClick={() => setDeleteConfirmationOpen(false)}>Cancel</button><button type="button" className="audiobook-danger-action" disabled={busy} onClick={confirmProjectDeletion}>{busy ? 'Deleting...' : 'Delete audiobook'}</button></div>
            </section>
          </div>}
           {assetDeleteConfirmation && <div className="audiobook-modal-backdrop" role="presentation" onMouseDown={() => { if (!busy) setAssetDeleteConfirmation(null); }}>
             <section className="audiobook-confirmation-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-asset-title" onMouseDown={(event) => event.stopPropagation()}>
               <p className="eyebrow">Delete asset</p>
               <h2 id="delete-asset-title">Delete “{assetDeleteConfirmation.name}”?</h2>
               <p>This removes the stored file from this audiobook. The manuscript source stays protected and can only be replaced by uploading a new source.</p>
               <div className="audiobook-confirmation-actions"><button type="button" disabled={busy} onClick={() => setAssetDeleteConfirmation(null)}>Cancel</button><button type="button" className="audiobook-danger-action" disabled={busy} onClick={confirmAssetDeletion}>{busy ? 'Deleting...' : 'Delete asset'}</button></div>
             </section>
           </div>}
           <nav className="audiobook-project-tabs" aria-label="Audiobook project sections">
            {([['books', 'Books'], ['chapters', 'Chapters'], ['assets', 'Assets'], ['documents', 'Documents'], ['characters', 'Cast & Voice Tools'], ['exports', 'Render & Export']] as [LibrarySection, string][]).map(([section, label]) => (
              <button key={section} type="button" className={librarySection === section ? 'selected' : ''} aria-current={librarySection === section ? 'page' : undefined}
                onClick={() => navigateLibrary(section)}>{label}</button>
            ))}
          </nav>
          <div className="audiobook-tool-bars audiobook-tool-bars-legacy">
            <details><summary>Cast &amp; voice tools <small>Narrator, voices, aliases, pronunciations, auditions</small></summary>
              <p>Assign voices in the cast panel, confirm aliases, then audition an annotated span.</p><button type="button" onClick={() => navigateLibrary('characters')}>Manage cast</button>
            </details>
            <details><summary>Render &amp; delivery tools <small>Chapter rendering, mastering, export manifests</small></summary>
              <p>Provider: Faster Qwen3 TTS · one span per checkpoint · chapter-level mastering. The Production view shows durable jobs, cache hits, and export history.</p>
              <button type="button" onClick={() => navigateLibrary('exports')}>Open Production</button>
            </details>
          </div>
          {latestPipelineJob && ['queued', 'leased', 'running', 'retrying'].includes(latestPipelineJob.status) &&
            !(reclassificationRunning && latestPipelineJob.id === reclassificationJob?.id) &&
            <div className="audiobook-message audiobook-pipeline-status" role="status" aria-live="polite">
              <p>{latestPipelineJob.type?.replace('audiobook.', '')} {latestPipelineJob.status}: {latestPipelineJob.progress?.message || 'Processing the book'}</p>
              <div className="audiobook-pipeline-progress">
                <progress aria-label={`${latestPipelineJob.type?.replace('audiobook.', '') || 'Book processing'} progress`} max={100}
                  {...(latestPipelineProgress === null ? {} : { value: latestPipelineProgress })} />
                {latestPipelineProgress !== null && <span>{latestPipelineProgress}%</span>}
              </div>
            </div>}
          {reclassificationJob && reclassificationRunning && <div className="audiobook-progress audiobook-reclassification-progress" role="status" aria-live="polite">
            <div className="audiobook-reclassification-header"><strong>{reclassificationMigrating ? 'Refreshing source spans' : 'Reclassifying text'}</strong><span>{reclassificationProgress}%</span><div className="audiobook-reclassification-actions" role="group" aria-label="Text reclassification controls">
              {!reclassificationMigrating && (reclassificationJob.status === 'paused'
                ? <button type="button" disabled={busy} onClick={resumeReclassification}>Resume</button>
                : reclassificationJob.status === 'cancel_requested'
                  ? <button type="button" disabled={busy} onClick={cancelReclassification}>Cancel now</button>
                  : reclassificationJob.pause_requested
                    ? <button type="button" disabled>Pausing…</button>
                  : <button type="button" disabled={busy} onClick={pauseReclassification}>Pause</button>) }
              {reclassificationJob.status !== 'cancel_requested' && <button type="button" className="audiobook-danger-action" disabled={busy} onClick={cancelReclassification}>Cancel</button>}
            </div></div>
            <progress aria-label="Text reclassification progress" max={100} value={reclassificationProgress} />
            <small>{reclassificationMigrating
              ? (reclassificationJob.progress?.message || 'Regenerating canonical dialogue spans before AI analysis')
              : `${reclassificationJob.progress?.current ?? 0} / ${reclassificationJob.progress?.total ?? '—'} spans · ${reclassificationJob.progress?.message || reclassificationJob.status}`}</small>
          </div>}
          {failedPipelineJob && <div className="audiobook-message error" role="alert">
            <strong>{failedPipelineJob.type?.replace('audiobook.', '')} {failedPipelineJob.status}</strong>
            {failedPipelineJob.chapter_id && <> · {project.chapters.find((chapter) => chapter.id === failedPipelineJob.chapter_id)?.title || failedPipelineJob.chapter_id}</>}
            {failedPipelineJob.error?.code && <> · {failedPipelineJob.error.code.replace(/_/g, ' ')}</>}
            <> · {failedPipelineJob.error?.message || 'Open the job queue for details.'}</>
            {failedPipelineJob.attempts !== undefined && <> · attempt {failedPipelineJob.attempts}/{failedPipelineJob.max_attempts}</>}
            {failedPipelineJob.error?.retryable !== undefined && <> · {failedPipelineJob.error.retryable ? 'retryable' : 'manual retry required'}</>}
            {failedPipelineJob.can_retry && <button type="button" disabled={busy}
              onClick={() => void action(() => omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/jobs/${encodeURIComponent(failedPipelineJob.id)}/retry`, {}), 'Pipeline retry queued.')}>Retry stage</button>}
            <a href="/jobs">Diagnostics</a>
          </div>}
          <nav className="audiobook-mode-switch audiobook-mode-switch-legacy" aria-label="Audiobook workspace mode">
            <button type="button" aria-current={workspaceMode === 'review' ? 'page' : undefined}
              onClick={() => { setWorkspaceMode('review'); if (librarySection === 'exports') setLibrarySection('projects'); }}><strong>Book &amp; Review</strong><small>Read, cast, resolve, audition</small></button>
            <button type="button" aria-current={workspaceMode === 'production' ? 'page' : undefined}
              onClick={() => { setWorkspaceMode('production'); setLibrarySection('exports'); }}><strong>Production</strong><small>Render, master, export</small></button>
          </nav>
          {workspaceMode === 'review' && librarySection === 'books' && <section className="audiobook-card audiobook-books-panel">
            <div className="audiobook-section-title"><div><p className="eyebrow">Library</p><h2>Books &amp; chapters</h2><p className="audiobook-subtitle">Open a chapter to review its manuscript, cast, and audio.</p></div><label className="audiobook-search-field">Search books or chapters<input aria-label="Search books or chapters" value={bookSearch} onChange={(event) => setBookSearch(event.target.value)} placeholder="Search books or chapters…" /></label></div>
            <div className="audiobook-book-grid">
              {project.chapters.filter((chapter) => chapter.title.toLowerCase().includes(bookSearch.toLowerCase())).map((chapter) => {
                const render = project.render_jobs.find((job) => job.chapter_id === chapter.id);
                return <article className="audiobook-book-card" key={chapter.id}>
                  {project.cover_asset_id ? <img src={`${base}/projects/${encodeURIComponent(project.id)}/cover`} alt="" /> : <div className="audiobook-chapter-placeholder">{chapter.ordinal + 1}</div>}
                  <div className="audiobook-book-card-copy"><small>CHAPTER {chapter.ordinal + 1}</small><h3>{chapter.title}</h3><span>{chapter.character_count.toLocaleString()} characters · {render?.status ?? 'Draft'}</span>
                    <div><button type="button" onClick={() => { setChapterId(chapter.id); navigateLibrary('projects'); }}>Continue</button><button type="button" disabled={busy} onClick={() => void action(async () => { const modelRevision = await getInstalledModelRevision(); const detail = chapter.id === selectedChapter?.id ? selectedChapter : await queryClient.fetchQuery({ queryKey: ['audiobook', 'chapter', project.id, chapter.id], queryFn: () => omnixApiClient.get<Chapter>(`${base}/projects/${encodeURIComponent(project.id)}/chapters/${encodeURIComponent(chapter.id)}`) }); const span = detail.spans[0]; if (!span) throw new Error('This chapter has no speech spans yet.'); await omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/preview`, { chapter_id: chapter.id, span_id: span.id, model_revision: modelRevision.trim() }); setChapterId(chapter.id); setSelectedSpanId(span.id); navigateLibrary('projects'); }, 'Chapter preview queued.')}>Play</button></div>
                  </div>
                </article>;
              })}
            </div>
            {project.chapters.length === 0 && <p>Upload a source book to extract chapters.</p>}
            {project.chapters.length > 0 && !project.chapters.some((chapter) => chapter.title.toLowerCase().includes(bookSearch.toLowerCase())) && <p>No chapters match “{bookSearch}”.</p>}
          </section>}
          {workspaceMode === 'review' && librarySection === 'chapters' && (() => {
            const chapters = project.chapters.filter((chapter) => {
              const matchesSearch = `${chapter.title} ${chapter.ordinal + 1}`.toLowerCase().includes(bookSearch.toLowerCase());
              return matchesSearch && (chapterStatusFilter === 'all' || chapterStatus(chapter) === chapterStatusFilter);
            });
            return <section className="audiobook-card audiobook-chapters-panel">
              <div className="audiobook-section-title"><div><p className="eyebrow">Audiobook project</p><h2>Chapters</h2><p className="audiobook-subtitle">Manage chapters, track production progress, and organize your audiobook.</p></div><button type="button" className="audiobook-primary-action" onClick={() => openSourceUpload(project.id)}>Replace source</button></div>
              <div className="audiobook-table-toolbar"><label className="audiobook-search-field">Search chapters by title, content, or tags<input aria-label="Search chapters" value={bookSearch} onChange={(event) => setBookSearch(event.target.value)} placeholder="Search chapters by title, content, or tags…" /></label><label>Status<select aria-label="Chapter status" value={chapterStatusFilter} onChange={(event) => setChapterStatusFilter(event.target.value)}><option value="all">All statuses</option><option value="Draft">Draft</option><option value="In Review">In Review</option><option value="In Progress">In Progress</option><option value="Queued">Queued</option><option value="Rendered">Rendered</option><option value="Needs attention">Needs attention</option></select></label><button type="button" className={chapterView === 'list' ? 'selected' : ''} aria-label="List view" onClick={() => setChapterView('list')}>☷</button><button type="button" className={chapterView === 'grid' ? 'selected' : ''} aria-label="Grid view" onClick={() => setChapterView('grid')}>▦</button></div>
              {chapterView === 'list' ? <div className="audiobook-chapter-table" role="table" aria-label="Audiobook chapters"><div className="audiobook-chapter-table-head" role="row"><span>#</span><span>Chapter title</span><span>Status</span><span>Spans</span><span>Words</span><span>Est. runtime</span><span>Cast / voices</span><span>Review</span><span>Actions</span></div>{chapters.map((chapter) => { const status = chapterStatus(chapter); const issues = project.review_issues.filter((issue) => issue.chapter_id === chapter.id); return <div className="audiobook-chapter-table-row" role="row" key={chapter.id}><span className="chapter-number">{chapter.ordinal + 1}</span><button type="button" className="chapter-title-button" onClick={() => startChapter(chapter)}><strong>{chapter.title}</strong><small>{chapter.character_count.toLocaleString()} characters</small></button><span className={`audiobook-status-pill status-${status.toLowerCase().replaceAll(' ', '-')}`}>{status}</span><span>{chapter.span_count ?? '—'}</span><span>{chapter.word_count?.toLocaleString() ?? '—'}</span><span>{formatDuration(chapter.estimated_runtime_seconds)}</span><span>{castLabel}<small>{assignedVoiceCount}/{project.speakers.length} voices assigned</small></span><span className={issues.length ? 'review-pending' : 'review-approved'}>{issues.length ? `${issues.length} open` : ['ready_to_render', 'rendering', 'mastering', 'ready_to_export', 'exported'].includes(project.state) ? 'Approved' : 'Pending'}</span><div className="audiobook-row-actions"><button type="button" aria-label={`Preview first span of ${chapter.title}`} disabled={busy} onClick={() => void action(() => queueChapterPreview(chapter), 'Chapter preview queued.')}>▶</button></div></div>; })}</div> : <div className="audiobook-chapter-grid">{chapters.map((chapter) => <article className="audiobook-chapter-grid-card" key={chapter.id}><div className="audiobook-chapter-grid-cover">{project.cover_asset_id && <img src={`${base}/projects/${encodeURIComponent(project.id)}/cover`} alt="" />}<b>{chapter.ordinal + 1}</b></div><div><span className="audiobook-status-pill">{chapterStatus(chapter)}</span><h3>{chapter.title}</h3><p>{chapter.character_count.toLocaleString()} characters · {`Est. ${formatDuration(chapter.estimated_runtime_seconds)}`}</p><button type="button" onClick={() => startChapter(chapter)}>Open in editor</button></div></article>)}</div>}
              {chapters.length === 0 && <p className="audiobook-empty-state">No chapters match the current filters.</p>}
            </section>;
          })()}
          {workspaceMode === 'review' && librarySection === 'assets' && (() => {
            const assets = workspaceAssetList().filter((asset) => {
              const matchesSearch = `${asset.name} ${asset.detail} ${asset.chapters ?? ''}`.toLowerCase().includes(assetSearch.toLowerCase());
              const matchesFilter = assetFilter === 'all' || (assetFilter === 'audio' && asset.type === 'Audio') || (assetFilter === 'images' && asset.type === 'Cover Art') || (assetFilter === 'documents' && asset.type === 'Document') || (assetFilter === 'references' && asset.type === 'Reference');
              return matchesSearch && matchesFilter;
            });
            return <section className="audiobook-card audiobook-assets-panel">
              <div className="audiobook-section-title"><div><p className="eyebrow">Audiobook project</p><h2>Project Assets</h2><p className="audiobook-subtitle">View the stored source, cover, and finished exports. Uploading a new source replaces the current manuscript.</p></div><div className="audiobook-section-actions"><label className="audiobook-search-field">Search assets by name or type<input aria-label="Search assets" value={assetSearch} onChange={(event) => setAssetSearch(event.target.value)} placeholder="Search assets by name, tag, or type…" /></label><label className="audiobook-file-button">Upload source or cover<input id="audiobook-asset-import" type="file" accept={`${sourceAccept},image/jpeg,image/png`} onChange={(event) => { const file = event.currentTarget.files?.[0]; if (file) importProjectFile(file); event.currentTarget.value = ''; }} /></label></div></div>
              <div className="audiobook-filter-row">{([['all', 'All Assets'], ['audio', 'Audio'], ['images', 'Images'], ['documents', 'Documents'], ['references', 'References']] as [string, string][]).map(([key, label]) => <button type="button" key={key} className={assetFilter === key ? 'selected' : ''} onClick={() => setAssetFilter(key)}>{label}<span>{key === 'all' ? workspaceAssetList().length : workspaceAssetList().filter((asset) => key === 'audio' ? asset.type === 'Audio' : key === 'images' ? asset.type === 'Cover Art' : key === 'documents' ? asset.type === 'Document' : asset.type === 'Reference').length}</span></button>)}</div>
              <div className="audiobook-asset-grid">{assets.map((asset) => <article className={`audiobook-asset-card${selectedAssetId === asset.id ? ' selected' : ''}`} key={asset.id} onClick={() => setSelectedAssetId(asset.id)}><div className={`audiobook-asset-preview asset-${asset.type.toLowerCase().replaceAll(' ', '-')}`}>{asset.image && project.cover_asset_id ? <img src={`${base}/projects/${encodeURIComponent(project.id)}/cover`} alt="" /> : <span>{asset.type === 'Audio' ? '◖' : asset.type === 'Document' ? '▤' : '▧'}</span>}</div><strong>{asset.name}</strong><small>{asset.detail}</small><small>{asset.chapters ?? '—'}</small><div><em className={`asset-status asset-${asset.status.toLowerCase()}`}>{asset.status}</em></div></article>)}</div>
              {assets.length === 0 && <p className="audiobook-empty-state">No assets match the current filters.</p>}
            </section>;
          })()}
          {workspaceMode === 'review' && librarySection === 'documents' && (() => {
            const documents = workspaceDocumentList();
            const filteredDocuments = documents.filter((document) => `${document.title} ${document.type} ${document.author}`.toLowerCase().includes(documentSearch.toLowerCase()) && (documentTypeFilter === 'all' || document.type === documentTypeFilter));
            const selectedDocument = documents.find((document) => document.id === selectedDocumentId) ?? documents[0];
            return <section className="audiobook-card audiobook-documents-panel">
              <div className="audiobook-section-title"><div><p className="eyebrow">Audiobook project</p><h2>Project Documents</h2><p className="audiobook-subtitle">Inspect the current manuscript and completed export reports. Uploading a source replaces the current manuscript.</p></div><div className="audiobook-section-actions"><label className="audiobook-file-button">Replace manuscript<input id="audiobook-document-import" type="file" accept={sourceAccept} onChange={(event) => { const file = event.currentTarget.files?.[0]; if (file) importProjectFile(file); event.currentTarget.value = ''; }} /></label></div></div>
              <div className="audiobook-document-categories">{([['all', 'All Documents'], ['Manuscript', 'Manuscript'], ['Export Notes', 'Export Reports']] as [string, string][]).map(([key, label]) => <button type="button" key={key} className={documentTypeFilter === key || (key === 'all' && documentTypeFilter === 'all') ? 'selected' : ''} onClick={() => setDocumentTypeFilter(key)}>{label}<span>{key === 'all' ? documents.length : documents.filter((document) => document.type === key).length}</span></button>)}</div>
              <div className="audiobook-document-toolbar"><label className="audiobook-search-field">Search documents<input aria-label="Search documents" value={documentSearch} onChange={(event) => setDocumentSearch(event.target.value)} placeholder="Search documents…" /></label><label>Type<select aria-label="Document type" value={documentTypeFilter} onChange={(event) => setDocumentTypeFilter(event.target.value)}><option value="all">All types</option>{Array.from(new Set(documents.map((document) => document.type))).map((type) => <option key={type} value={type}>{type}</option>)}</select></label><button type="button" className={documentView === 'list' ? 'selected' : ''} aria-label="Document list view" onClick={() => setDocumentView('list')}>☷</button><button type="button" className={documentView === 'grid' ? 'selected' : ''} aria-label="Document grid view" onClick={() => setDocumentView('grid')}>▦</button></div>
              <div className={`audiobook-document-layout ${documentView === 'grid' ? 'document-grid-view' : ''}`}><div className="audiobook-document-list" role="table" aria-label="Project documents"><div className="audiobook-document-list-head"><span>Title</span><span>Type</span><span>Last edited</span><span>Author / source</span><span>Linked</span><span>Status</span><span>Actions</span></div>{filteredDocuments.map((document) => <div className={`audiobook-document-row${selectedDocument?.id === document.id ? ' selected' : ''}`} key={document.id} onClick={() => setSelectedDocumentId(document.id)}><button type="button" onClick={() => setSelectedDocumentId(document.id)}><strong>{document.title}</strong><small>{document.type}</small></button><span>{document.type}</span><span>{document.lastEdited}</span><span>{document.author}</span><span>{document.linked}</span><span className={`audiobook-status-pill status-${document.status.toLowerCase().replaceAll(' ', '-')}`}>{document.status}</span><div className="audiobook-row-actions"><button type="button" onClick={() => { setSelectedDocumentId(document.id); setDocumentDetailTab('preview'); }}>…</button></div></div>)}</div><aside className="audiobook-document-inline-details"><p className="eyebrow">Document details</p><h3>{selectedDocument?.title ?? 'No document selected'}</h3><p>{selectedDocument?.preview ?? 'Select a document to preview it.'}</p><div className="audiobook-card-actions"><button type="button" className="audiobook-primary-action" disabled={!selectedDocument} onClick={() => { if (selectedDocument) openDocument(selectedDocument); }}>↗ Open section</button>{selectedDocument?.href && <a className="audiobook-button-link" href={selectedDocument.href}>{selectedDocument.id === 'manuscript' ? 'Download source' : 'View report'}</a>}</div></aside></div>
            </section>;
          })()}
          {workspaceMode === 'review' && librarySection === 'characters' && <section className="audiobook-card audiobook-characters-panel" id="audiobook-cast-main">
            <div className="audiobook-section-title"><div><p className="eyebrow">Cast &amp; voice tools</p><h2>Character-to-voice mapping</h2><p className="audiobook-subtitle">Assign voices, add aliases, and audition the cast against real manuscript spans.</p></div><form className="audiobook-inline audiobook-add-inline" onSubmit={submitSpeaker}><label>New speaker<input aria-label="New speaker" value={speakerName} onChange={(event) => setSpeakerName(event.target.value)} placeholder="Character or narrator" /></label><button disabled={busy || !speakerName.trim()}>＋ Add character</button></form></div>
            <div className="audiobook-cast-grid">{project.speakers.map((speaker) => <article className="audiobook-cast-card" key={speaker.id}><div><p className="audiobook-avatar">{speaker.canonical_name.slice(0, 1).toUpperCase()}</p><h3>{speaker.canonical_name}</h3><small>{speaker.kind} · {speaker.status === 'proposed' ? 'Detected · assign a voice to confirm' : speaker.casting ? 'Voice assigned' : 'Needs a voice'}</small>{speaker.analysis_metadata && (speaker.analysis_metadata.role || speaker.analysis_metadata.estimated_age || speaker.analysis_metadata.gender_presentation || speaker.analysis_metadata.traits?.length) && <p className="audiobook-hint">{[speaker.analysis_metadata.role, speaker.analysis_metadata.estimated_age, speaker.analysis_metadata.gender_presentation, ...(speaker.analysis_metadata.traits ?? []).slice(0, 3)].filter(Boolean).join(' · ')}</p>}{speaker.proposed_aliases?.length ? <div className="audiobook-proposed-aliases"><small>Suggested aliases</small>{speaker.proposed_aliases.map((alias) => <button type="button" key={alias} disabled={busy} aria-label={`Confirm alias ${alias} for ${speaker.canonical_name}`} onClick={() => void action(() => omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/speakers/${encodeURIComponent(speaker.id)}/aliases`, { alias }), `Alias ${alias} confirmed for ${speaker.canonical_name}.`)}>{alias} · confirm</button>)}</div> : null}</div>
              <label>Assigned voice<select value={speaker.casting?.voice_profile_id ?? ''} disabled={busy} aria-label={`Main voice for ${speaker.canonical_name}`} onChange={(event) => { const voice_profile_id = event.currentTarget.value; if (voice_profile_id) void action(() => omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/speakers/${encodeURIComponent(speaker.id)}/casting`, { voice_profile_id }), `Voice assigned to ${speaker.canonical_name}.`); }}><option value="">{speaker.status === 'proposed' ? 'Choose voice · confirms character' : 'Choose voice'}</option>{voicesQuery.data?.voices.map((voice) => <option key={voice.id} value={voice.id}>{voice.name}{voice.language ? ` · ${voice.language}` : ''}</option>)}</select></label>
              <div className="audiobook-card-actions"><button type="button" disabled={busy} onClick={() => void action(async () => { const location = await findSpeakerSpan(speaker.id); setChapterId(location.chapterId); setSelectedSpanId(location.spanId); navigateLibrary('projects'); }, `Located ${speaker.canonical_name}.`)}>Find span</button><button type="button" disabled={busy || !speaker.casting || !modelRevision.trim()} onClick={() => void action(async () => { const location = await findSpeakerSpan(speaker.id); await omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/preview`, { chapter_id: location.chapterId, span_id: location.spanId, model_revision: modelRevision.trim() }); }, `Audition queued for ${speaker.canonical_name}.`)}>Audition</button></div>
              <div className="audiobook-alias-controls"><input aria-label={`Main alias for ${speaker.canonical_name}`} placeholder="Add alias" value={aliasNames[speaker.id] ?? ''} onChange={(event) => setAliasNames((previous) => ({ ...previous, [speaker.id]: event.target.value }))} /><button type="button" disabled={busy || !aliasNames[speaker.id]?.trim()} onClick={() => void action(async () => { await omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/speakers/${encodeURIComponent(speaker.id)}/aliases`, { alias: aliasNames[speaker.id].trim() }); setAliasNames((previous) => ({ ...previous, [speaker.id]: '' })); }, 'Speaker alias confirmed.')}>Add alias</button></div>
            </article>)}</div>
            {proposedSpeakers.length > 0 && <div className="audiobook-message" role="status"><strong>{proposedSpeakers.length} detected speaker{proposedSpeakers.length === 1 ? '' : 's'} awaiting confirmation.</strong> Assigning a voice confirms a detected character automatically, or confirm one now without casting.<div className="audiobook-card-actions">{proposedSpeakers.map((speaker) => <button type="button" key={speaker.id} disabled={busy} onClick={() => confirmProposedSpeaker(speaker)}>Confirm {speaker.canonical_name}{speaker.occurrence_count ? ` (${speaker.occurrence_count} spans)` : ''}</button>)}</div></div>}
            {project.review_issues.length > 0 && <div className="audiobook-message" role="status"><strong>Human review required · {project.review_issues.length} open issue{project.review_issues.length === 1 ? '' : 's'}</strong><p>Resolve low-confidence, ambiguous, or contradictory span interpretations before rendering.</p><button type="button" onClick={() => navigateLibrary('projects')}>Open human review queue</button></div>}
            {project.speakers.length === 0 && <p>No speakers have been detected yet. Upload a source book or add one above.</p>}
          </section>}
          {workspaceMode === 'review' && librarySection === 'voices' && <section className="audiobook-card audiobook-voices-panel">
            <div className="audiobook-section-title"><div><p className="eyebrow">Voice library</p><h2>Choose a voice</h2><p className="audiobook-subtitle">Use installed voice profiles and preview them against a cast member.</p></div><label>Assign to speaker<select aria-label="Voice assignment target" value={voiceTargetSpeakerId} onChange={(event) => setVoiceTargetSpeakerId(event.target.value)}><option value="">Choose speaker</option>{castableSpeakers.map((speaker) => <option key={speaker.id} value={speaker.id}>{speaker.canonical_name}{speaker.status === 'proposed' ? ' · detected' : ''}</option>)}</select></label></div>
            <div className="audiobook-voice-grid">{voicesQuery.data?.voices.map((voice) => <article className={`audiobook-voice-card${voice.id === selectedVoiceId ? ' selected' : ''}`} key={voice.id} onClick={() => setSelectedVoiceId(voice.id)}><div className="audiobook-voice-icon">◉</div><div><h3>{voice.name}</h3><p>{voice.language || 'Language unspecified'}</p></div><div className="audiobook-card-actions"><button type="button" disabled={busy || !voiceTargetSpeakerId} onClick={() => { setSelectedVoiceId(voice.id); void action(() => omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/speakers/${encodeURIComponent(voiceTargetSpeakerId)}/casting`, { voice_profile_id: voice.id }), 'Voice assigned.'); }}>Use voice</button><button type="button" disabled={busy || !voiceTargetSpeakerId || !modelRevision.trim()} onClick={() => void action(async () => { const location = await findSpeakerSpan(voiceTargetSpeakerId); await omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/preview`, { chapter_id: location.chapterId, span_id: location.spanId, model_revision: modelRevision.trim() }); }, 'Voice preview queued.')}>Preview</button></div></article>)}</div>
            {voicesQuery.data?.voices.length === 0 && <p className="audiobook-hint">No local voices are installed. Add a voice profile in Voice Cloning to cast speakers.</p>}
          </section>}
          {workspaceMode === 'review' && librarySection === 'pronunciations' && <section className="audiobook-card audiobook-pronunciations-panel" id="audiobook-pronunciations-main">
            <div className="audiobook-section-title"><div><p className="eyebrow">Speech plan</p><h2>Pronunciations</h2><p className="audiobook-subtitle">Keep names, places, and unique terms consistent across the audiobook.</p></div><label className="audiobook-search-field">Search pronunciations<input aria-label="Search pronunciations" value={pronunciationSearch} onChange={(event) => setPronunciationSearch(event.target.value)} placeholder="Search names, places, terms…" /></label></div>
            <form className="audiobook-pronunciation-form" onSubmit={submitPronunciation}><label>Source term<input value={sourceTerm} onChange={(event) => setSourceTerm(event.target.value)} maxLength={128} placeholder="Hollow Bay" /></label><label>Spoken term<input value={spokenTerm} onChange={(event) => setSpokenTerm(event.target.value)} maxLength={256} placeholder="Hollow Bay" /></label><button disabled={busy || !sourceTerm.trim() || !spokenTerm.trim()}>＋ Add pronunciation</button></form>
            <div className="audiobook-pronunciation-table"><div className="audiobook-pronunciation-table-head"><span>Source term</span><span>Spoken term</span><span>Revision</span><span>Status</span></div>{project.pronunciations?.filter((entry) => `${entry.source_term} ${entry.spoken_term}`.toLowerCase().includes(pronunciationSearch.toLowerCase())).map((entry) => <div className="audiobook-pronunciation-table-row" key={entry.source_term}><strong>{entry.source_term}</strong><span>{entry.spoken_term}</span><span>v{entry.revision}</span><em>● Verified</em></div>)}</div>
            {project.pronunciations?.length === 0 && <p>No pronunciations saved yet.</p>}
          </section>}
          {workspaceMode === 'review' && librarySection === 'projects' &&
          <section className="audiobook-card audiobook-manuscript" id="audiobook-manuscript">
            <div className="audiobook-section-title"><div><p className="eyebrow">Canonical source</p><h2>{selectedChapter?.title ?? project.chapters.find((chapter) => chapter.id === activeChapterId)?.title ?? 'Awaiting extraction'}</h2></div><span>{project.chapters.length} chapters</span></div>
            {selectedChapter ? <>
              <div className="audiobook-text" aria-label="Canonical chapter text">
                {selectedChapter.spans.map((span) => <span key={span.id} role="button" tabIndex={0}
                  className={`audiobook-source-span${span.id === selectedSpan?.id ? ' selected' : ''}${span.annotation?.review_status === 'review_required' ? ' needs-review' : ''}`}
                  aria-label={`Inspect ${span.annotation?.role ?? span.structural_kind} span: ${span.source_text.slice(0, 64)}`}
                  title="Select a word here to set its pronunciation throughout the book"
                  onMouseUp={(event) => capturePronunciation(span.id, event.currentTarget)}
                  onKeyUp={(event) => capturePronunciation(span.id, event.currentTarget)}
                  onClick={() => { setSelectedSpanId(span.id); setExpandedSpanId(span.id); }}
                  onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelectedSpanId(span.id); setExpandedSpanId(span.id); } }}>
                  {span.source_text}
                </span>)}
              </div>
              <section className="audiobook-spans-section" aria-label="Characterization spans">
                <div className="audiobook-section-title"><div><p className="eyebrow">Speech review</p><h3>Characterization spans</h3><p className="audiobook-subtitle">Select any word in a passage to set its pronunciation throughout the book. Expand a span to edit its character and delivery.</p></div>
                  <button type="button" disabled={busy || reclassificationRunning || !project.current_source_revision_id}
                    onClick={() => void action(() => reclassifyAudiobook(project.id), 'Text classification queued.')}>
                    {reclassificationRunning ? 'Classifying…' : selectedChapter.spans.some((span) => span.annotation) ? 'Reclassify text' : 'Run classification'}
                  </button>
                </div>
                <label className="audiobook-span-filter">Filter by character
                  <select aria-label="Filter spans by character" value={speakerFilter} onChange={(event) => setSpeakerFilter(event.target.value)}>
                    <option value="all">All characters</option><option value="unassigned">Unassigned</option>
                    {project.speakers.map((speaker) => <option key={speaker.id} value={speaker.id}>{speaker.canonical_name}</option>)}
                  </select>
                </label>
                <div className="audiobook-preview-list" aria-label="Span previews">
                  {visibleSpans.map((span) => {
                    const preview = project.preview_jobs?.find((job) => job.span_id === span.id);
                    const speaker = project.speakers.find((item) => item.id === span.annotation?.speaker_id);
                    const expanded = (expandedSpanId === undefined ? selectedChapter.spans[0]?.id : expandedSpanId) === span.id;
                    const edit = selectedSpan?.id === span.id ? selectedEdit : null;
                    const issue = project.review_issues.find((item) => item.span_id === span.id);
                    return <article className="audiobook-preview-row" key={span.id}>
                      <div className="audiobook-span-summary"><div><small>{span.annotation?.role ?? span.structural_kind} · {speaker?.canonical_name ?? span.annotation?.speaker_candidate ?? 'Unassigned'}{span.annotation?.review_status === 'review_required' ? ' · Needs review' : ''}</small>
                        <p>{span.source_text}</p></div>
                        <div className="audiobook-span-actions"><button type="button" aria-expanded={expanded} aria-label={`${expanded ? 'Collapse' : 'Expand'} span ${span.source_text.slice(0, 48)}`}
                          onClick={() => { setExpandedSpanId(expanded ? null : span.id); setSelectedSpanId(span.id); setSelectedPronunciation(null); }}>{expanded ? 'Collapse' : 'Expand'}</button>
                          <button type="button" disabled={busy || !span.speech_plan.tts_input_text.trim()}
                            title={span.speech_plan.tts_input_text.trim() ? 'Preview this spoken span' : 'Skipped by the current reading policy'}
                            onClick={() => void action(async () => {
                              const modelRevision = await getInstalledModelRevision();
                              return omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/preview`,
                                { chapter_id: selectedChapter.id, span_id: span.id, model_revision: modelRevision.trim() });
                            }, 'Span preview queued.')}>Preview</button></div></div>
                      {preview && <small role="status">{preview.status}{preview.error?.message ? ` · ${preview.error.message}` : ''}</small>}
                      {preview?.status === 'completed' && <audio controls preload="none" src={`${base}/projects/${encodeURIComponent(project.id)}/previews/${encodeURIComponent(preview.id)}/audio`} aria-label={`Preview ${span.source_text.slice(0, 48)}`} />}
                      {expanded && <div className="audiobook-span-details">
                        <p className="audiobook-span-selectable" tabIndex={0} onMouseUp={(event) => capturePronunciation(span.id, event.currentTarget)} onKeyUp={(event) => capturePronunciation(span.id, event.currentTarget)}>{span.source_text}</p>
                        <small>Select a word in the passage to set its pronunciation throughout this book.</small>
                        {selectedPronunciation?.spanId === span.id && <form className="audiobook-span-pronunciation" onSubmit={submitPronunciation}>
                          <label>Written word<input aria-label="Selected written word" value={sourceTerm} readOnly /></label>
                          <label>Spoken as<input aria-label="Spoken as" value={spokenTerm} maxLength={256} onChange={(event) => setSpokenTerm(event.target.value)} /></label>
                          <button disabled={busy || !spokenTerm.trim()}>Save for whole book</button>
                        </form>}
                        <p className="audiobook-span-spoken"><strong>Spoken text</strong> {span.speech_plan.tts_input_text}</p>
                        {span.speech_plan.transformations.length > 0 && <small>Speech changes: {span.speech_plan.transformations.map((item) => `${item.source} → ${item.spoken}`).join(', ')}</small>}
                        {issue && <p className="audiobook-review-reason"><strong>Review: {issue.reason}</strong> {JSON.stringify(issue.evidence ?? {})}</p>}
                        {edit && <div className="audiobook-annotation-controls" aria-label="Span interpretation controls">
                          <label>Speaker<select aria-label="Selected span speaker" value={edit.speaker_id} onChange={(event) => changeSpanEdit({ speaker_id: event.target.value })}>
                            <option value="">Choose speaker</option>{project.speakers.map((item) => <option key={item.id} value={item.id}>{item.canonical_name}</option>)}
                          </select></label>
                          <label>Role<select aria-label="Selected span role" value={edit.role} onChange={(event) => changeSpanEdit({ role: event.target.value })}>
                            {['narration', 'dialogue', 'heading', 'other'].map((role) => <option key={role} value={role}>{role}</option>)}
                          </select></label>
                          <label>Delivery or emotion<input aria-label="Selected span delivery" value={edit.delivery} maxLength={512} placeholder="e.g. softly, excited, hesitant" onChange={(event) => changeSpanEdit({ delivery: event.target.value })} /></label>
                          <button type="button" disabled={busy || !edit.speaker_id} onClick={() => void action(async () => {
                            const url: `/api/${string}` = issue
                              ? `${base}/projects/${encodeURIComponent(project.id)}/review/${encodeURIComponent(issue.id)}`
                              : `${base}/projects/${encodeURIComponent(project.id)}/spans/${encodeURIComponent(span.id)}/annotation`;
                            await omnixApiClient.post(url, edit);
                            setSpanEdits((previous) => { const next = { ...previous }; delete next[span.id]; return next; });
                          }, issue ? 'Review decision saved.' : 'Span interpretation saved. Render again to update affected audio.')}>Save interpretation</button>
                        </div>}
                      </div>}
                    </article>;
                  })}
                  {visibleSpans.length === 0 && <p>No spans match this character.</p>}
                </div>
              </section>
            </> : project.chapters.length ? <p>{chapterQuery.isError ? 'Could not load this chapter.' : 'Loading chapter…'}</p> : <p>Upload a source file to extract chapters. The original text remains available throughout production.</p>}
          </section>}
          {workspaceMode === 'production' && <>
          <section className="audiobook-card audiobook-render-dashboard">
            <div className="audiobook-render-banner"><div><p className="eyebrow">Production</p><h2>Render &amp; Export</h2><p>Batch rendering, chapter mastering, and multi-format export for your audiobook.</p></div><button type="button" onClick={() => setProjectSettingsOpen(true)}>⚙ Open advanced tools</button></div>
            <div className="audiobook-render-metrics"><article><span>▣</span><div><small>Render Queue</small><strong>{renderProgressPercent}%</strong><em>{completedRenderChapters} / {renderChapterCount} audiobook chapters · {renderStateLabel}{skippedRenderChapterCount ? ` · ${skippedRenderChapterCount} skipped by policy` : ''}</em></div></article><article><span>◉</span><div><small>Cache Hits</small><strong>{cacheHits}</strong><em>Completed render units</em></div></article><article><span>▱</span><div><small>Source Size</small><strong>{project.source_size_bytes ? `${(project.source_size_bytes / 1048576).toFixed(1)} MB` : '—'}</strong><em>Original source</em></div></article><article><span>△</span><div><small>Failed / Retryable</small><strong>{failedRenderJobs} failed · {retryableRenderJobs} retry</strong><em>View and retry →</em></div></article><article><span>◷</span><div><small>Estimated Remaining</small><strong>—</strong><em>{Math.max(0, renderChapterCount - completedRenderChapters)} audiobook chapters left · estimate unavailable</em></div></article></div>
            <div className="audiobook-render-columns"><section className="audiobook-render-queue"><div className="audiobook-section-title"><h3>▤ &nbsp;Render Queue</h3><span>{runningRenderJobs} running · {queuedRenderJobs} queued · {pausedRenderJobs} paused</span><div className="audiobook-row-actions"><button type="button" disabled={busy || !(runningRenderJobs + queuedRenderJobs)} onClick={pauseAllRenderJobs}>Pause all chapters</button><button type="button" disabled={busy || !pausedRenderJobs} onClick={resumeAllRenderJobs}>Resume all chapters</button><button type="button" disabled={busy || !(runningRenderJobs + queuedRenderJobs + pausedRenderJobs)} onClick={stopAllRenderJobs}>Stop all chapters</button></div></div>{!renderJobs.length && project.state === 'ready_to_render' && <p className="audiobook-hint">No render run is active. Select Render book to queue all chapters.</p>}<div className="audiobook-render-table"><div className="audiobook-render-table-head"><span>#</span><span>Chapter</span><span>Status</span><span>Progress</span><span>Time</span><span>Actions</span></div>{project.chapters.map((chapter) => { const job = project.render_jobs.find((candidate) => candidate.chapter_id === chapter.id); const policySkipped = isPolicySkippedChapter(chapter.id); const status = policySkipped ? 'Skipped' : renderJobLabel(job, project.state); const progress = policySkipped ? 0 : renderJobProgress(job, project.state); return <div className="audiobook-render-row" key={chapter.id}><b>{chapter.ordinal + 1}</b><span>{chapter.title}</span><em className={`render-status-${status.toLowerCase()}`}>{status}{policySkipped && <small> by reading policy</small>}</em><div className="render-row-progress">{policySkipped ? <small>Not rendered</small> : <><progress max={100} value={progress} /><small>{progress}%</small></>}</div><span>{'—'}</span><div className="audiobook-row-actions">{job && CONTROLLABLE_RENDER_STATUSES.has(job.status) ? <>{job.status === 'paused' ? <button type="button" aria-label="Resume chapter" disabled={busy} onClick={() => void action(() => omnixApiClient.post(renderJobEndpoint(job.id, 'resume'), {}), 'Chapter resumed.')}>Resume</button> : <button type="button" aria-label="Pause chapter" disabled={busy} onClick={() => void action(() => omnixApiClient.post(renderJobEndpoint(job.id, 'pause'), {}), 'Chapter paused.')}>Pause</button>}<button type="button" aria-label="Stop chapter" disabled={busy} onClick={() => void action(() => omnixApiClient.post(renderJobEndpoint(job.id, 'cancel'), {}), 'Chapter stopped.')}>Stop</button></> : job?.status === 'cancel_requested' ? <button type="button" aria-label="Stopping chapter" disabled>Stopping…</button> : <button type="button" aria-label="Open chapter" onClick={() => startChapter(chapter)}>▶</button>}</div></div>; })}</div></section><section className="audiobook-mastering"><div className="audiobook-section-title"><h3>Chapter Assembly</h3></div>{project.chapters.map((chapter) => { const policySkipped = isPolicySkippedChapter(chapter.id); const assemblyJob = project.pipeline_jobs?.find((candidate) => candidate.type === 'audiobook.assemble-chapter' && candidate.chapter_id === chapter.id); const assemblyStatus = policySkipped ? 'Skipped by policy' : assemblyJob ? renderJobLabel(assemblyJob, project.state) : project.state === 'ready_to_render' ? 'Waiting for render' : project.state === 'rendering' ? 'Waiting for audio' : project.state === 'mastering' ? 'Mastering' : 'Not started'; return <article className="audiobook-mastering-card" key={chapter.id}><div className="audiobook-mastering-card-head"><strong>Chapter {chapter.ordinal + 1} - {chapter.title}</strong><span>{assemblyStatus}</span></div><div className="audiobook-mastering-checks"><span>Chapter assembly <b>{assemblyStatus}</b></span><span>Audio artifact <b>{policySkipped ? 'Not applicable' : assemblyStatus === 'Completed' ? 'Ready' : 'Pending'}</b></span></div></article>; })}</section></div>
            <div className="audiobook-render-footer"><label>Installed model revision<input value={modelRevision} readOnly placeholder={modelQuery.isFetching ? 'Checking installed model' : 'Computed when rendering'} /></label><button type="button" className="audiobook-primary-action" disabled={busy || !canRender} onClick={() => void action(async () => { const modelRevision = await getInstalledModelRevision(); return omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/render`, { model_revision: modelRevision.trim() }); }, 'Chapter render jobs queued.')}>{project.state === 'rendering' ? 'Retry render' : 'Render book'}</button><label>Format<select value={exportFormat} onChange={(event) => setExportFormat(event.target.value)}><option value="m4b">M4B</option><option value="flac">FLAC</option><option value="wav">WAV</option><option value="mp3">MP3</option></select></label><button type="button" disabled={busy || !['ready_to_export', 'exported'].includes(project.state)} onClick={() => void action(() => omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/exports`, { format: exportFormat }), `${exportFormat.toUpperCase()} export queued.`)}>Export Now</button></div>
          </section>
          </>}
        </>}
      </div>

      <aside id="audiobook-outline-rail" className={`audiobook-rail audiobook-inspector audiobook-inspector-${librarySection}${mobileRail === 'outline' ? ' mobile-open' : ''}`} aria-label={librarySection === 'voices' ? 'Voice details' : librarySection === 'characters' ? 'Character details' : librarySection === 'pronunciations' ? 'Pronunciation details' : 'Chapter and cast inspector'}>
        <button className="audiobook-mobile-close" type="button" onClick={() => setMobileRail(null)}>Close outline</button>
        {project && librarySection === 'voices' && <section className="audiobook-special-inspector"><div className="audiobook-panel-heading"><p className="eyebrow">Voice details</p><h2>{selectedVoice?.name ?? 'Choose a voice'}</h2></div><p className="audiobook-detail-muted">{selectedVoice?.language || 'Language unspecified'}</p><p className="audiobook-special-copy">Preview an installed voice and assign it to the selected speaker.</p><button type="button" className="audiobook-primary-action" disabled={busy || !voiceTargetSpeakerId || !selectedVoice} onClick={() => void action(() => omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/speakers/${encodeURIComponent(voiceTargetSpeakerId)}/casting`, { voice_profile_id: selectedVoice?.id }), 'Voice assigned.')}>Use this voice</button></section>}
        {project && librarySection === 'characters' && <section className="audiobook-special-inspector"><div className="audiobook-panel-heading"><p className="eyebrow">Character details</p><h2>{project.speakers[0]?.canonical_name ?? 'No characters yet'}</h2></div>{project.speakers[0] ? <><p className="audiobook-detail-muted">{project.speakers[0].kind} · {project.speakers[0].casting ? 'Voice assigned' : 'Needs review'}</p><p className="audiobook-special-copy">Character registry and casting for your audiobook. Use the main cast view to assign voices, aliases, and auditions.</p><div className="audiobook-detail-list"><p><strong>Voice assignment</strong><span>{project.speakers[0].casting?.voice_profile_id ?? 'Unassigned'}</span></p><p><strong>Aliases</strong><span>{project.speakers[0].aliases?.length ?? 0}</span></p><p><strong>Review issues</strong><span>{project.review_issues.length}</span></p></div><button type="button" onClick={() => navigateLibrary('voices')}>Manage voice assignment</button></> : <p>No speakers have been detected yet.</p>}</section>}
        {project && librarySection === 'pronunciations' && <section className="audiobook-special-inspector"><div className="audiobook-panel-heading"><p className="eyebrow">Pronunciation details</p><h2>{sourceTerm || 'Select a term'}</h2></div><form className="audiobook-form" onSubmit={submitPronunciation}><label>Source term<input value={sourceTerm} onChange={(event) => setSourceTerm(event.target.value)} placeholder="Hollow Bay" /></label><label>Spoken term<input value={spokenTerm} onChange={(event) => setSpokenTerm(event.target.value)} placeholder="Hollow Bay" /></label><button className="audiobook-primary-action" disabled={busy || !sourceTerm.trim() || !spokenTerm.trim()}>Save changes</button></form><p className="audiobook-detail-muted">Leave affected chapters blank to apply this pronunciation throughout the book.</p></section>}
         {project ? <section className="audiobook-outline-inspector"><div className="audiobook-panel-heading"><p className="eyebrow">Outline</p><h2>Chapters</h2></div>
          <div className="audiobook-outline">{project.chapters.map((chapter) => {
            const issues = project.review_issues.filter((issue) => issue.chapter_id === chapter.id).length;
            const render = project.render_jobs.find((job) => job.chapter_id === chapter.id);
            return <button type="button" key={chapter.id} className={chapter.id === activeChapterId ? 'selected' : ''} onClick={() => { setChapterId(chapter.id); setLibrarySection('projects'); setWorkspaceMode('review'); }}><small>{String(chapter.ordinal + 1).padStart(2, '0')} · {issues ? `${issues} to review` : render?.status || 'ready'}</small>{chapter.title}</button>;
          })}
            {project.chapters.length === 0 && <p>No chapters yet.</p>}</div><button className="audiobook-outline-add" type="button" onClick={() => openSourceUpload(project.id)}>Open source upload</button></section> : ebookLibraryOpen ? <section className="audiobook-library-inspector"><div className="audiobook-panel-heading"><p className="eyebrow">Library summary</p><h2>Your audiobooks</h2></div><div className="audiobook-detail-list"><p><strong>Total audiobooks</strong><span>{libraryProjects.length}</span></p><p><strong>Ready to export</strong><span>{libraryProjects.filter((item) => libraryProjectStatus(item) === 'Ready').length}</span></p><p><strong>In progress</strong><span>{libraryProjects.filter((item) => libraryProjectStatus(item) === 'In progress').length}</span></p><p><strong>Needs review</strong><span>{libraryProjects.filter((item) => libraryProjectStatus(item) === 'Review required').length}</span></p></div><p className="audiobook-detail-muted">Select an audiobook to open its manuscript, chapters, voices, assets, documents, and delivery tools.</p><button type="button" className="audiobook-primary-action" onClick={() => { setEbookLibraryOpen(false); setLibrarySection('projects'); }}>＋ Create audiobook</button></section> : <section className="audiobook-get-started"><div className="audiobook-panel-heading"><p className="eyebrow">Get started</p><h2>Stories sound better here.</h2></div><ol><li><strong>Add your content</strong><small>Import a file, paste text, or start from a blank project.</small></li><li><strong>Set project details</strong><small>Choose title, author, language, and voice settings.</small></li><li><strong>Create and edit</strong><small>Review your manuscript, fine-tune narration, and make edits.</small></li><li><strong>Generate your audiobook</strong><small>Render and export in M4B, MP3, or other formats.</small></li></ol></section>}
         {project && librarySection === 'books' && <section className="audiobook-book-inspector"><div className="audiobook-panel-heading"><p className="eyebrow">Book details</p><h2>{project.title}</h2></div><div className="audiobook-detail-list"><p><strong>Title</strong><span>{project.title}</span></p><p><strong>Author</strong><span>{project.author || 'Unknown author'}</span></p><p><strong>Language</strong><span>{project.language === 'en' ? 'English' : project.language}</span></p><p><strong>Total words</strong><span>{formatCount(project.word_count)}</span></p><p><strong>Estimated runtime</strong><span>{formatDuration(project.estimated_runtime_seconds)}</span></p></div><div className="audiobook-quick-actions"><button type="button" className="audiobook-primary-action" onClick={() => navigateLibrary('exports')}>Open Render &amp; Export</button><button type="button" onClick={() => navigateLibrary('exports')}>Open exports</button><button type="button" onClick={() => setProjectSettingsOpen(true)}>⚙ Project Settings</button></div></section>}
         {project && librarySection === 'chapters' && <section className="audiobook-chapter-inspector"><div className="audiobook-panel-heading"><p className="eyebrow">Chapter summary</p><h2>{project.chapters.find((chapter) => chapter.id === activeChapterId)?.title ?? 'No chapter selected'}</h2></div><p>{project.chapters.find((chapter) => chapter.id === activeChapterId)?.character_count === undefined ? '—' : project.chapters.find((chapter) => chapter.id === activeChapterId)?.character_count.toLocaleString()} characters</p><p>{project.review_issues.filter((issue) => issue.chapter_id === activeChapterId).length} review issues</p><button type="button" className="audiobook-primary-action" onClick={() => startChapter(project.chapters.find((chapter) => chapter.id === activeChapterId) ?? project.chapters[0])} disabled={!activeChapterId}>▣ Open in editor</button><div className="audiobook-quick-actions"><button type="button" onClick={() => setProjectSettingsOpen(true)}>Replace source</button><button type="button" disabled={busy || !activeChapterId} onClick={() => { const chapter = project.chapters.find((item) => item.id === activeChapterId); if (chapter) void action(() => queueChapterPreview(chapter), 'Chapter preview queued.'); }}>Preview first span</button></div>{selectedChapter?.document_blocks?.some((block) => block.render_action === 'SKIP') && <div className="audiobook-detail-list" aria-label="Skipped audiobook content"><p><strong>Skipped by reading policy</strong><span>{selectedChapter.document_blocks.filter((block) => block.render_action === 'SKIP').length}</span></p>{selectedChapter.document_blocks.filter((block) => block.render_action === 'SKIP').slice(0, 8).map((block) => <p key={block.id} title={block.provenance.map((item) => `${item.source ?? 'rule'}:${item.signal ?? 'evidence'}`).join(', ')}><strong>{block.original_text || '(blank block)'}</strong><span>{block.effective_role.replaceAll('_', ' ')} · {Math.round(block.confidence * 100)}%</span><button type="button" disabled={busy} aria-label={`Read skipped block ${block.original_text}`} onClick={() => void action(() => setDocumentBlockAction(project.id, block.id, 'READ'), 'Block will be read.')}>Read</button><button type="button" disabled={busy} aria-label={`Use automatic policy for ${block.original_text}`} onClick={() => void action(() => setDocumentBlockAction(project.id, block.id, 'DEFAULT'), 'Block returned to automatic policy.')}>Default</button></p>)}</div>}</section>}
         {project && librarySection === 'assets' && <section className="audiobook-asset-inspector"><div className="audiobook-panel-heading"><p className="eyebrow">Asset details</p><h2>{workspaceAssetList().find((asset) => asset.id === selectedAssetId)?.name ?? workspaceAssetList()[0]?.name ?? 'No assets yet'}</h2></div>{(() => { const asset = workspaceAssetList().find((item) => item.id === selectedAssetId) ?? workspaceAssetList()[0]; return asset ? <><div className="audiobook-asset-detail-preview">{asset.image && project.cover_asset_id ? <img src={`${base}/projects/${encodeURIComponent(project.id)}/cover`} alt="" /> : <span>{asset.type}</span>}</div><p className="audiobook-detail-muted">{asset.detail}</p><div className="audiobook-detail-list"><p><strong>Usage</strong><span>{asset.status} · {asset.chapters ?? 'Not linked'}</span></p><p><strong>Project</strong><span>{project.title}</span></p><p><strong>Format</strong><span>{asset.format ?? '—'}</span></p></div><div className="audiobook-card-actions">{asset.href && <a className="audiobook-button-link" href={asset.href} download>Download</a>}{asset.deletable && <button type="button" className="audiobook-danger-action" disabled={busy} onClick={() => setAssetDeleteConfirmation(asset)}>Delete</button>}</div></> : <p>No assets are associated with this project yet.</p>; })()}</section>}
         {project && librarySection === 'documents' && <section className="audiobook-document-inspector"><div className="audiobook-panel-heading"><p className="eyebrow">Document details</p><h2>{workspaceDocumentList().find((document) => document.id === selectedDocumentId)?.title ?? workspaceDocumentList()[0]?.title ?? 'No documents yet'}</h2></div>{(() => { const document = workspaceDocumentList().find((item) => item.id === selectedDocumentId) ?? workspaceDocumentList()[0]; return document ? <><div className="audiobook-detail-tabs">{(['preview', 'details', 'versions'] as const).map((tab) => <button key={tab} type="button" className={documentDetailTab === tab ? 'selected' : ''} onClick={() => setDocumentDetailTab(tab)}>{tab}</button>)}</div>{documentDetailTab === 'preview' && <div className="audiobook-document-preview"><h3>{project.title}</h3><p>{document.preview}</p></div>}{documentDetailTab === 'details' && <div className="audiobook-detail-list"><p><strong>Type</strong><span>{document.type}</span></p><p><strong>Linked chapters</strong><span>{document.linked}</span></p><p><strong>Author / source</strong><span>{document.author}</span></p><p><strong>Status</strong><span>{document.status}</span></p></div>}{documentDetailTab === 'versions' && <p className="audiobook-detail-muted">The source is immutable. Uploading a replacement creates a new source revision; generated views reflect current project state.</p>}<button type="button" className="audiobook-primary-action" onClick={() => { openDocument(document); }}>↗ Open section</button><div className="audiobook-card-actions">{document.href && <a className="audiobook-button-link" href={document.href}>{document.id === 'manuscript' ? 'Download source' : 'View report'}</a>}</div></> : <p>Select a document to inspect it.</p>; })()}</section>}
         {project && librarySection === 'exports' && <section className="audiobook-export-inspector"><div className="audiobook-panel-heading"><p className="eyebrow">Export summary</p><h2>Delivery</h2></div><p>Audiobook chapters <strong>{renderChapterCount}</strong></p><p>Skipped by reading policy <strong>{skippedRenderChapterCount}</strong></p><p>Completed renders <strong>{completedRenderChapters}</strong></p><p>In progress <strong>{project.render_jobs.filter((job) => ['running', 'leased', 'retrying'].includes(job.status)).length}</strong></p><p>Queued <strong>{project.render_jobs.filter((job) => ['queued', 'waiting'].includes(job.status)).length}</strong></p><p>Failed <strong className="review-pending">{project.render_jobs.filter((job) => ['failed', 'dead_letter'].includes(job.status)).length}</strong></p><hr /><h3>Export Formats</h3><p className="audiobook-detail-muted">Select one or more export formats.</p>{(['m4b', 'flac', 'wav', 'mp3'] as const).map((format) => <label className="audiobook-format-check" key={format}><input type="radio" name="export-format" checked={exportFormat === format} onChange={() => setExportFormat(format)} />{format.toUpperCase()} <small>{format === 'm4b' ? 'Audiobook Standard' : format === 'flac' ? 'Lossless Archive' : format === 'wav' ? 'Uncompressed' : 'Wide Compatibility'}</small></label>)}<button type="button" className="audiobook-primary-action" disabled={busy || !['ready_to_export', 'exported'].includes(project.state)} onClick={() => void action(() => omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/exports`, { format: exportFormat }), `${exportFormat.toUpperCase()} export queued.`)}>⇧ Generate Export Manifest</button><button type="button" disabled={busy || !['ready_to_export', 'exported'].includes(project.state)} onClick={() => void action(() => omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/exports`, { format: exportFormat }), `${exportFormat.toUpperCase()} export queued.`)}>⇧ Export Now</button><button type="button" onClick={() => setProjectSettingsOpen(true)}>⚙ Project Settings</button></section>}
         {project && <><section className="audiobook-project-status" aria-label="Project status"><div className="audiobook-panel-heading"><p className="eyebrow">Status</p><h2>Project status</h2></div>
          <p>Canonical source: {project.current_source_revision_id ? 'extracted' : 'awaiting import'}</p>
          <p>Review issues: {project.review_issues.length}</p>
          <p>Rendered coverage: {completedRenderChapters} / {renderChapterCount} audiobook chapters{skippedRenderChapterCount ? ` · ${skippedRenderChapterCount} source chapters skipped by policy` : ''}</p>
          <p>Words: {formatCount(project.word_count)}</p>
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
              <button type="button" aria-label={`Audition voice for ${speaker.canonical_name}`} disabled={busy} onClick={() => void action(async () => {
                const modelRevision = await getInstalledModelRevision();
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
          {project.review_issues.map((issue) => <article className="audiobook-review" key={issue.id}><small>{issue.chapter_title} · {issue.reason === 'POSSIBLE_MISSED_DIALOGUE' ? 'Possible missed dialogue' : issue.reason}{issue.speaker_candidate ? ` · proposed: ${issue.speaker_candidate}` : ''}</small><p>{issue.reason === 'POSSIBLE_MISSED_DIALOGUE' && typeof issue.evidence?.excerpt === 'string' ? issue.evidence.excerpt : issue.source_text}</p>
            {issue.reason === 'POSSIBLE_MISSED_DIALOGUE' && <p className="audiobook-detail-muted">This passage contains a speech cue but was extracted as narration. Confirm it as narration only if that is correct. Speech inside a narration span needs corrected source segmentation before it can be voiced as dialogue.</p>}
            {issue.speaker_candidate && <button type="button" disabled={busy} onClick={() => setSpeakerName(issue.speaker_candidate || '')}>Use proposed speaker name</button>}
            <select aria-label={`Speaker for review ${issue.id}`} value={reviewSpeakers[issue.id] ?? issue.speaker_id ?? ''} onChange={(event) => setReviewSpeakers((previous) => ({ ...previous, [issue.id]: event.target.value }))}><option value="">Choose speaker</option>{project.speakers.map((speaker) => <option key={speaker.id} value={speaker.id}>{speaker.canonical_name}</option>)}</select>
            <button type="button" disabled={busy || !(reviewSpeakers[issue.id] ?? issue.speaker_id)} onClick={() => void action(() => omnixApiClient.post(`${base}/projects/${encodeURIComponent(project.id)}/review/${encodeURIComponent(issue.id)}`, { speaker_id: reviewSpeakers[issue.id] ?? issue.speaker_id, role: issue.structural_kind || 'narration' }), 'Review decision saved.')}>
              {issue.reason === 'POSSIBLE_MISSED_DIALOGUE' ? 'Confirm narration' : 'Confirm speaker'}
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
