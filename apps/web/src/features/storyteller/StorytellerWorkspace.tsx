import { Button, Progress } from '@mantine/core';
import { useMutation, useQuery, useQueryClient, type UseMutationResult } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { useForm, type FieldErrors, type UseFormHandleSubmit, type UseFormRegister } from 'react-hook-form';
import { omnixApiClient, type JobRecord, type ProviderFacadePayload } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { OmnixStatusPill, WorkspacePanel } from '../../design/primitives';
import { FeatureSubmitFeedback, FeatureValidationMessage } from '../shared/FeatureSubmitFeedback';

interface StorytellerFormValues {
  providerId: string;
  title: string;
  premise: string;
}

type StoryActionMode = 'draft' | 'continue' | 'rewrite' | 'expand' | 'dialogue' | 'summarize';
type StoryQuickActionMode = Exclude<StoryActionMode, 'draft'>;

interface StoryGenerationRequest {
  values: StorytellerFormValues;
  action: StoryActionMode;
  sourceText: string | null;
  sourceJobId: string | null;
}

interface StoryOutlineScene {
  id: string;
  label: string;
  title: string;
}

interface StoryOutlineChapter {
  id: string;
  number: number;
  label: string;
  title: string;
  scenes: StoryOutlineScene[];
}

interface StoryTextBlock {
  id?: string;
  kind: 'chapter' | 'scene' | 'paragraph';
  text: string;
}

const toneOptions = ['Cozy', 'Hopeful', 'Gentle', 'Mystery'];
const styleOptions = ['Lyrical & Descriptive', 'Fast-paced', 'Dialogue-heavy', 'Cinematic', 'Literary'];

const quickActions: Array<{ mode: StoryQuickActionMode; label: string; description: string }> = [
  { mode: 'continue', label: 'Continue Story', description: 'AI continues from here' },
  { mode: 'rewrite', label: 'Rewrite Paragraph', description: 'Improve clarity & flow' },
  { mode: 'expand', label: 'Expand Scene', description: 'Add depth & detail' },
  { mode: 'dialogue', label: 'Dialogue Polish', description: 'Enhance dialogue' },
  { mode: 'summarize', label: 'Summarize', description: 'Condense this section' },
];

export function StorytellerWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const queryClient = useQueryClient();
  const [selectedTone, setSelectedTone] = useState('Cozy');
  const [writingStyle, setWritingStyle] = useState(styleOptions[0]);
  const [selectedChapter, setSelectedChapter] = useState(1);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const providersQuery = useQuery({
    queryKey: ['platform', 'providers'],
    queryFn: () => omnixApiClient.listProviders(),
  });
  const jobsQuery = useQuery({
    queryKey: ['platform', 'jobs'],
    queryFn: () => omnixApiClient.listJobs(),
  });
  const assetsQuery = useQuery({
    queryKey: ['platform', 'assets'],
    queryFn: () => omnixApiClient.listAssets(),
  });
  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors },
  } = useForm<StorytellerFormValues>({
    defaultValues: { providerId: '', title: '', premise: '' },
  });

  const createJobMutation = useMutation<JobRecord, Error, StoryGenerationRequest>({
    mutationFn: ({ values, action, sourceText, sourceJobId }: StoryGenerationRequest) =>
      omnixApiClient.createJob({
        module: 'storyteller',
        type: 'story.generate',
        resource_class: 'gpu:llm',
        priority: 0,
        input_payload: {
          title: values.title || null,
          premise: values.premise,
          provider_id: values.providerId || null,
          prompt_template_id: promptTemplateForAction(action),
          action,
          source_text: sourceText,
          source_job_id: sourceJobId,
          tone: selectedTone,
          writing_style: writingStyle,
          chapter: selectedChapter,
        },
        stages: [
          { id: 'outline', label: action === 'draft' ? 'Build outline' : `Plan ${actionLabel(action)}`, resource_class: 'gpu:llm', status: 'queued' },
          { id: 'draft', label: action === 'draft' ? 'Draft story' : actionLabel(action), resource_class: 'gpu:llm', status: 'queued' },
          { id: 'store-story', label: 'Store story asset', resource_class: 'cpu', status: 'queued' },
        ],
      }),
    onSuccess: async (job, request) => {
      reset({ providerId: request.values.providerId, title: request.values.title, premise: request.values.premise });
      if (job.status === 'completed' && fullJobOutputText(job)) {
        setSelectedJobId(job.id);
      }
      await queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] });
      await queryClient.invalidateQueries({ queryKey: ['platform', 'assets'] });
    },
  });

  const watchedTitle = watch('title');
  const watchedPremise = watch('premise');
  const watchedProvider = watch('providerId');
  const storyProviders = useMemo(() => llmCapableProviders(providersQuery.data), [providersQuery.data]);
  const queriedStoryJobs = jobsQuery.data?.jobs.filter((job) => job.module === 'storyteller') ?? [];
  const storyJobs = useMemo(() => includeMutationJob(queriedStoryJobs, createJobMutation.data ?? null), [queriedStoryJobs, createJobMutation.data]);
  const completedStoryJobs = storyJobs.filter((job) => job.status === 'completed' && fullJobOutputText(job));
  const activeJob = completedStoryJobs.find((job) => job.id === selectedJobId) ?? completedStoryJobs[0] ?? null;
  const activeStoryText = activeJob ? fullJobOutputText(activeJob) : null;
  const storyAssets = assetsQuery.data?.assets.filter((asset) => asset.type === 'story' || asset.type === 'export') ?? [];
  const storyTitle = jobInputString(activeJob, 'title') || watchedTitle || storyAssetTitle(storyAssets[0]?.storage_path) || 'Untitled story';
  const providerLabel = providerDisplayName(storyProviders, watchedProvider || jobInputString(activeJob, 'provider_id') || '');
  const outline = useMemo(() => deriveStoryOutline(activeStoryText, storyTitle), [activeStoryText, storyTitle]);
  const activeChapter = outline.find((chapter) => chapter.number === selectedChapter) ?? outline[0] ?? null;
  const chapterCount = outline.length || Math.max(1, Math.min(12, completedStoryJobs.length || selectedChapter));
  const wordCount = countWords(activeStoryText ?? watchedPremise ?? '');
  const readingMinutes = Math.max(1, Math.ceil(wordCount / 220));
  const submitStatus = createJobMutation.isPending ? 'queueing' : createJobMutation.isError ? 'error' : createJobMutation.data?.status ?? 'ready';

  useEffect(() => {
    if (selectedJobId && !completedStoryJobs.some((job) => job.id === selectedJobId)) {
      setSelectedJobId(null);
    }
  }, [completedStoryJobs, selectedJobId]);

  useEffect(() => {
    if (outline.length && !outline.some((chapter) => chapter.number === selectedChapter)) {
      setSelectedChapter(outline[0].number);
    }
  }, [outline, selectedChapter]);

  const submitStoryRequest = (values: StorytellerFormValues, action: StoryActionMode) => {
    createJobMutation.mutate({
      values,
      action,
      sourceText: activeStoryText,
      sourceJobId: activeJob?.id ?? null,
    });
  };

  const submitQuickAction = (action: StoryQuickActionMode) => {
    void handleSubmit((values) => submitStoryRequest(values, action))();
  };

  const selectOutlineTarget = (chapterNumber: number, targetId: string) => {
    setSelectedChapter(chapterNumber);
    const target = document.getElementById(targetId) as (HTMLElement & { scrollIntoView?: (options?: ScrollIntoViewOptions) => void }) | null;
    target?.scrollIntoView?.({ block: 'start', behavior: 'smooth' });
  };

  return (
    <WorkspacePanel>
      <div className="storyteller-workspace" aria-labelledby="module-title">
        <StoryLibrary storyAssets={storyAssets} completedStoryJobs={completedStoryJobs} activeTitle={storyTitle} />

        <main className="storyteller-stage">
          <StoryProjectHeader
            title={storyTitle}
            premise={watchedPremise || jobInputString(activeJob, 'premise') || ''}
            providerLabel={providerLabel}
            wordCount={wordCount}
            chapterCount={chapterCount}
            moduleRoute={module.route}
          />

          <div className="storyteller-compose-grid">
            <section className="storyteller-manuscript" aria-label="Story manuscript">
              <div className="storyteller-manuscript-meta">
                <span>{activeChapter?.label ?? `Chapter ${selectedChapter}`}</span>
                <span>{readingMinutes} min read</span>
              </div>
              <h2 id="module-title">{activeChapter?.title ?? storyTitle}</h2>
              <div className="storyteller-flourish" aria-hidden="true">
                <span />
                <strong>◇</strong>
                <span />
              </div>
              {activeStoryText ? (
                <StoryText outline={outline} text={activeStoryText} />
              ) : (
                <div className="storyteller-empty-manuscript" role="status">
                  <p className="eyebrow">Feature module</p>
                  <h3>{module.label}</h3>
                  <p>{module.summary}</p>
                  <p>Start with a premise, choose a tone, then generate the first scene. Completed output will appear here as a manuscript instead of a job-card preview.</p>
                </div>
              )}
            </section>

            <StoryControls
              providers={storyProviders}
              register={register}
              errors={errors}
              createJobMutation={createJobMutation}
              submitStatus={submitStatus}
              selectedTone={selectedTone}
              setSelectedTone={setSelectedTone}
              writingStyle={writingStyle}
              setWritingStyle={setWritingStyle}
              selectedChapter={selectedChapter}
              setSelectedChapter={setSelectedChapter}
              onGenerate={(values) => submitStoryRequest(values, 'draft')}
              latestJob={storyJobs[0] ?? null}
              handleSubmit={handleSubmit}
            />
          </div>

          <StoryActionBar disabled={createJobMutation.isPending} onAction={submitQuickAction} />
          <StoryVersions activeJobId={activeJob?.id ?? null} jobs={completedStoryJobs} onSelect={setSelectedJobId} />
        </main>

        <StoryOutline chapters={outline} selectedChapter={selectedChapter} onSelect={selectOutlineTarget} />
      </div>
    </WorkspacePanel>
  );
}

interface StoryControlsProps {
  providers: Array<{ id: string; label: string }>;
  register: UseFormRegister<StorytellerFormValues>;
  errors: FieldErrors<StorytellerFormValues>;
  createJobMutation: UseMutationResult<JobRecord, Error, StoryGenerationRequest>;
  submitStatus: string;
  selectedTone: string;
  setSelectedTone: (tone: string) => void;
  writingStyle: string;
  setWritingStyle: (style: string) => void;
  selectedChapter: number;
  setSelectedChapter: (chapter: number) => void;
  onGenerate: (values: StorytellerFormValues) => void;
  handleSubmit: UseFormHandleSubmit<StorytellerFormValues>;
  latestJob: JobRecord | null;
}

function StoryControls({
  providers,
  register,
  errors,
  createJobMutation,
  submitStatus,
  selectedTone,
  setSelectedTone,
  writingStyle,
  setWritingStyle,
  selectedChapter,
  setSelectedChapter,
  onGenerate,
  handleSubmit,
  latestJob,
}: StoryControlsProps) {
  return (
    <aside className="storyteller-controls" aria-label="Story controls">
      <div className="storyteller-panel-heading">
        <div>
          <p className="eyebrow">Story controls</p>
          <h3>Guide the next passage</h3>
        </div>
        <OmnixStatusPill>{submitStatus}</OmnixStatusPill>
      </div>

      <form className="storyteller-form" onSubmit={handleSubmit(onGenerate)}>
        <label>
          Provider
          <select {...register('providerId')}>
            <option value="">Default LLM provider</option>
            {providers.map((provider) => (
              <option key={provider.id} value={provider.id}>
                {provider.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Title
          <input {...register('title')} placeholder="Untitled story" />
        </label>
        <label>
          Premise <span>0/500</span>
          <textarea rows={4} aria-invalid={Boolean(errors.premise)} {...register('premise', { required: true })} placeholder="A young herbalist discovers a small secret that could change her quiet valley." />
        </label>

        <div className="storyteller-control-block">
          <span>Tone & mood</span>
          <div className="storyteller-chip-row">
            {toneOptions.map((tone) => (
              <button className={tone === selectedTone ? 'active' : ''} key={tone} type="button" onClick={() => setSelectedTone(tone)}>
                {tone}
              </button>
            ))}
          </div>
        </div>

        <label>
          Writing style
          <select value={writingStyle} onChange={(event) => setWritingStyle(event.target.value)}>
            {styleOptions.map((style) => (
              <option key={style} value={style}>
                {style}
              </option>
            ))}
          </select>
        </label>

        <div className="storyteller-chapter-controls">
          <span>Chapter</span>
          <button type="button" onClick={() => setSelectedChapter(Math.max(1, selectedChapter - 1))}>
            ‹
          </button>
          <strong>{selectedChapter}</strong>
          <button type="button" onClick={() => setSelectedChapter(selectedChapter + 1)}>
            ›
          </button>
          <button type="button" onClick={() => setSelectedChapter(selectedChapter + 1)}>
            New chapter
          </button>
        </div>

        <Button className="storyteller-generate" type="submit" disabled={createJobMutation.isPending} loading={createJobMutation.isPending}>
          {createJobMutation.isPending ? 'Generating story…' : 'Generate story'}
        </Button>
      </form>

      <FeatureValidationMessage show={Boolean(errors.premise)} message="Enter a premise before generating a story." />
      <FeatureSubmitFeedback
        error={createJobMutation.error}
        errorPrefix="Story request"
        isError={createJobMutation.isError}
        isPending={createJobMutation.isPending}
        jobId={createJobMutation.data?.id}
        pendingMessage="Generating story…"
        successPrefix={createJobMutation.data?.status === 'completed' ? 'Story generated' : 'Story job queued'}
      />

      <div className="storyteller-output-status">
        <div className="storyteller-panel-heading compact">
          <p className="eyebrow">Output status</p>
          <button type="button">Clear</button>
        </div>
        {latestJob ? (
          <article className="storyteller-output-card">
            <div>
              <strong>{latestJob.type}</strong>
              <OmnixStatusPill>{latestJob.status}</OmnixStatusPill>
            </div>
            <Progress value={progressPercent(latestJob.progress)} aria-label={`${latestJob.type} progress`} />
            <small>{latestJob.resource_class}</small>
            {fullJobOutputText(latestJob) ? <p>{truncate(fullJobOutputText(latestJob) ?? '', 180)}</p> : null}
          </article>
        ) : (
          <div className="storyteller-empty-small">No generation yet.</div>
        )}
      </div>
    </aside>
  );
}

function StoryProjectHeader({
  title,
  premise,
  providerLabel,
  wordCount,
  chapterCount,
  moduleRoute,
}: {
  title: string;
  premise: string;
  providerLabel: string;
  wordCount: number;
  chapterCount: number;
  moduleRoute: string;
}) {
  return (
    <header className="storyteller-project-header">
      <div className="storyteller-cover" aria-hidden="true" />
      <div className="storyteller-project-copy">
        <p className="eyebrow">{moduleRoute}</p>
        <h1>{title}</h1>
        <p>{premise || 'A new local-first story draft.'}</p>
        <div className="storyteller-tags">
          <span>Fantasy</span>
          <span>Cozy</span>
          <span>Mystery</span>
          <span>Slice of Life</span>
        </div>
      </div>
      <div className="storyteller-project-stats">
        <div>
          <strong>{wordCount.toLocaleString()}</strong>
          <span>Words</span>
        </div>
        <div>
          <strong>{chapterCount}</strong>
          <span>Chapters</span>
        </div>
        <div>
          <strong>{providerLabel}</strong>
          <span>Default provider</span>
        </div>
      </div>
      <div className="storyteller-project-actions">
        <button type="button">Save</button>
        <button type="button">Export</button>
      </div>
    </header>
  );
}

function StoryLibrary({
  storyAssets,
  completedStoryJobs,
  activeTitle,
}: {
  storyAssets: Array<{ id: string; storage_path: string; type: string }>;
  completedStoryJobs: JobRecord[];
  activeTitle: string;
}) {
  const recentStories = storyAssets.slice(0, 4);
  return (
    <aside className="storyteller-library" aria-label="Story library">
      <div className="storyteller-panel-heading compact">
        <p className="eyebrow">Library</p>
        <button type="button">+</button>
      </div>
      <nav>
        <a className="active" href="#drafts">Drafts</a>
        <a href="#stories">Stories</a>
        <a href="#characters">Characters</a>
        <a href="#world-notes">World Notes</a>
        <a href="#prompts">Prompts</a>
      </nav>
      <section>
        <p className="eyebrow">Recent stories</p>
        <div className="storyteller-recent-list">
          <article className="active">
            <span className="storyteller-thumb" />
            <div>
              <strong>{activeTitle}</strong>
              <small>{completedStoryJobs.length ? `${countWords(fullJobOutputText(completedStoryJobs[0]) ?? '').toLocaleString()} words` : 'Draft'}</small>
            </div>
          </article>
          {recentStories.map((asset) => (
            <article key={asset.id}>
              <span className="storyteller-thumb muted" />
              <div>
                <strong>{storyAssetTitle(asset.storage_path)}</strong>
                <small>{asset.type}</small>
              </div>
            </article>
          ))}
        </div>
      </section>
      <button className="storyteller-trash" type="button">Trash</button>
    </aside>
  );
}

function StoryActionBar({ disabled, onAction }: { disabled: boolean; onAction: (action: StoryQuickActionMode) => void }) {
  return (
    <section className="storyteller-action-bar" aria-label="Story actions">
      {quickActions.map((action) => (
        <button disabled={disabled} key={action.mode} type="button" onClick={() => onAction(action.mode)}>
          <strong>{action.label}</strong>
          <span>{action.description}</span>
        </button>
      ))}
    </section>
  );
}

function StoryVersions({ activeJobId, jobs, onSelect }: { activeJobId: string | null; jobs: JobRecord[]; onSelect: (jobId: string) => void }) {
  const versionJobs = jobs.slice(0, 5);
  return (
    <section className="storyteller-versions" aria-label="Recent story versions">
      <p className="eyebrow">Recent versions</p>
      {(versionJobs.length ? versionJobs : [null, null, null]).map((job, index) => {
        const version = `v${versionJobs.length ? versionJobs.length - index : index + 1}`;
        const title = storyVersionTitle(job, index);
        return (
          <button
            aria-label={job ? `Select ${version}: ${title}` : `Placeholder ${version}`}
            aria-pressed={Boolean(job && job.id === activeJobId)}
            className={job && job.id === activeJobId ? 'active' : ''}
            disabled={!job}
            key={job?.id ?? `placeholder-${index}`}
            type="button"
            onClick={() => job && onSelect(job.id)}
          >
            <strong>{version}</strong>
            <span>{job ? title : index === 0 ? 'Just now' : 'Draft'}</span>
          </button>
        );
      })}
      <button type="button">View all</button>
    </section>
  );
}

function StoryOutline({ chapters, selectedChapter, onSelect }: { chapters: StoryOutlineChapter[]; selectedChapter: number; onSelect: (chapterNumber: number, targetId: string) => void }) {
  return (
    <aside className="storyteller-outline" aria-label="Story outline">
      <div className="storyteller-panel-heading compact">
        <p className="eyebrow">Outline</p>
        <button type="button">☰</button>
      </div>
      {chapters.map((chapter) => (
        <article className={selectedChapter === chapter.number ? 'active' : ''} key={chapter.id}>
          <button type="button" onClick={() => onSelect(chapter.number, chapter.id)}>
            <strong>{chapter.label}</strong>
            <span>{chapter.title}</span>
          </button>
          <ol>
            {chapter.scenes.map((scene, sceneIndex) => (
              <li className={selectedChapter === chapter.number && sceneIndex === 0 ? 'active' : ''} key={scene.id}>
                <button type="button" onClick={() => onSelect(chapter.number, scene.id)}>
                  <span>{scene.label}</span>
                  <strong>{scene.title}</strong>
                </button>
              </li>
            ))}
          </ol>
        </article>
      ))}
      <button className="storyteller-add-chapter" type="button">Add chapter</button>
    </aside>
  );
}

function StoryText({ text, outline }: { text: string; outline: StoryOutlineChapter[] }) {
  const blocks = useMemo(() => storyTextBlocks(text, outline), [text, outline]);
  return (
    <div className="storyteller-prose">
      {blocks.map((block, index) => {
        const key = `${block.kind}-${block.id ?? block.text.slice(0, 18)}-${index}`;
        if (block.kind === 'chapter') {
          return (
            <h3 id={block.id} key={key} tabIndex={-1}>
              {block.text}
            </h3>
          );
        }
        if (block.kind === 'scene') {
          return (
            <h4 id={block.id} key={key} tabIndex={-1}>
              {block.text}
            </h4>
          );
        }
        return <p key={key}>{block.text}</p>;
      })}
    </div>
  );
}

function llmCapableProviders(payload: ProviderFacadePayload | undefined) {
  return payload?.providers.filter((provider) => provider.capabilities.includes('chat') || provider.capabilities.includes('completion')) ?? [];
}

function progressPercent(progress: { current: number; total: number } | undefined): number {
  if (!progress || progress.total <= 0) {
    return 0;
  }

  return Math.min(100, Math.round((progress.current / progress.total) * 100));
}

function fullJobOutputText(job: { output_refs?: Array<{ content?: unknown }>; logs?: Array<{ content?: unknown }> }): string | null {
  const content = job.output_refs?.find((ref) => typeof ref.content === 'string')?.content ?? job.logs?.find((log) => typeof log.content === 'string')?.content;
  return typeof content === 'string' && content.trim() ? content : null;
}

function includeMutationJob(jobs: JobRecord[], mutationJob: JobRecord | null): JobRecord[] {
  if (!mutationJob) {
    return jobs;
  }
  return [mutationJob, ...jobs.filter((job) => job.id !== mutationJob.id)];
}

function jobInputString(job: JobRecord | null, key: string): string | null {
  const input = job?.input_payload;
  if (!input || typeof input !== 'object') {
    return null;
  }
  const value = (input as Record<string, unknown>)[key];
  return typeof value === 'string' && value.trim() ? value : null;
}

function storyAssetTitle(storagePath: string | undefined): string {
  if (!storagePath) {
    return 'Untitled Draft';
  }
  const filename = storagePath.split(/[\\/]/).pop() ?? storagePath;
  return filename.replace(/\.[^.]+$/, '').replace(/[-_]+/g, ' ') || 'Untitled Draft';
}

function providerDisplayName(providers: Array<{ id: string; label: string }>, selectedProviderId: string): string {
  return providers.find((provider) => provider.id === selectedProviderId)?.label ?? 'Omnix LLM';
}

function countWords(text: string): number {
  return text.trim() ? text.trim().split(/\s+/).length : 0;
}

function truncate(text: string, length: number): string {
  return text.length > length ? `${text.slice(0, length)}…` : text;
}

function storyVersionTitle(job: JobRecord | null, index: number): string {
  if (!job) {
    return index === 0 ? 'Just now' : 'Draft';
  }
  const action = jobInputString(job, 'action');
  const title = jobInputString(job, 'title') || 'Untitled story';
  return action && action !== 'draft' ? `${actionLabel(action as StoryActionMode)} • ${title}` : title;
}

function promptTemplateForAction(action: StoryActionMode): string {
  return `storyteller.${action}.v1`;
}

function actionLabel(action: StoryActionMode): string {
  switch (action) {
    case 'continue':
      return 'Continue story';
    case 'rewrite':
      return 'Rewrite paragraph';
    case 'expand':
      return 'Expand scene';
    case 'dialogue':
      return 'Dialogue polish';
    case 'summarize':
      return 'Summarize';
    case 'draft':
    default:
      return 'Draft story';
  }
}

function deriveStoryOutline(text: string | null, fallbackTitle: string): StoryOutlineChapter[] {
  if (!text?.trim()) {
    return [fallbackChapter(fallbackTitle)];
  }

  const paragraphs = storyParagraphs(text);
  const chapters: StoryOutlineChapter[] = [];
  let currentChapter: StoryOutlineChapter | null = null;

  paragraphs.forEach((paragraph, index) => {
    const heading = headingInfo(paragraph);
    if (heading?.kind === 'chapter') {
      const number = chapters.length + 1;
      currentChapter = {
        id: sectionId('chapter', number, heading.title || `Chapter ${number}`),
        number,
        label: `Chapter ${number}`,
        title: heading.title || `Chapter ${number}`,
        scenes: [],
      };
      chapters.push(currentChapter);
      return;
    }

    if (!currentChapter) {
      currentChapter = {
        id: sectionId('chapter', 1, fallbackTitle),
        number: 1,
        label: 'Chapter 1',
        title: fallbackTitle || 'Untitled story',
        scenes: [],
      };
      chapters.push(currentChapter);
    }

    if (heading?.kind === 'scene') {
      const sceneNumber = currentChapter.scenes.length + 1;
      currentChapter.scenes.push({
        id: sectionId(`chapter-${currentChapter.number}-scene`, sceneNumber, heading.title),
        label: `Scene ${sceneNumber}`,
        title: heading.title,
      });
      return;
    }

    if (currentChapter.scenes.length === 0 && paragraph.length > 40) {
      currentChapter.scenes.push({
        id: sectionId(`chapter-${currentChapter.number}-scene`, 1, paragraph),
        label: 'Scene 1',
        title: sceneTitleFromParagraph(paragraph, index),
      });
    }
  });

  if (chapters.length === 0) {
    return [fallbackChapter(fallbackTitle)];
  }

  return chapters.map((chapter) => ({
    ...chapter,
    scenes: chapter.scenes.length ? chapter.scenes : [{ id: `${chapter.id}-scene-1`, label: 'Scene 1', title: 'Opening passage' }],
  }));
}

function storyTextBlocks(text: string, outline: StoryOutlineChapter[]): StoryTextBlock[] {
  const chaptersByTitle = new Map(outline.map((chapter) => [normalizeHeading(chapter.title), chapter]));
  const scenesByTitle = new Map(outline.flatMap((chapter) => chapter.scenes.map((scene) => [normalizeHeading(scene.title), scene] as const)));
  return storyParagraphs(text).map((paragraph) => {
    const heading = headingInfo(paragraph);
    if (heading?.kind === 'chapter') {
      const chapter = chaptersByTitle.get(normalizeHeading(heading.title));
      return { id: chapter?.id, kind: 'chapter', text: heading.title || paragraph };
    }
    if (heading?.kind === 'scene') {
      const scene = scenesByTitle.get(normalizeHeading(heading.title));
      return { id: scene?.id, kind: 'scene', text: heading.title || paragraph };
    }
    return { kind: 'paragraph', text: paragraph };
  });
}

function headingInfo(paragraph: string): { kind: 'chapter' | 'scene'; title: string } | null {
  const markdown = paragraph.match(/^#{1,4}\s+(.+)$/);
  const text = (markdown?.[1] ?? paragraph).trim();
  const chapter = text.match(/^chapter\s+([\divxlcdm]+)\s*[:.\-–—]?\s*(.*)$/i);
  if (chapter) {
    return { kind: 'chapter', title: chapter[2]?.trim() || `Chapter ${chapter[1]}` };
  }
  const scene = text.match(/^scene\s+([\divxlcdm]+)\s*[:.\-–—]?\s*(.*)$/i);
  if (scene) {
    return { kind: 'scene', title: scene[2]?.trim() || `Scene ${scene[1]}` };
  }
  return null;
}

function storyParagraphs(text: string): string[] {
  return text
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);
}

function fallbackChapter(title: string): StoryOutlineChapter {
  return {
    id: sectionId('chapter', 1, title || 'Untitled story'),
    number: 1,
    label: 'Chapter 1',
    title: title || 'Untitled story',
    scenes: [{ id: sectionId('chapter-1-scene', 1, title || 'Opening passage'), label: 'Scene 1', title: 'Opening passage' }],
  };
}

function sectionId(prefix: string, index: number, value: string): string {
  return `${prefix}-${index}-${slugify(value || 'section')}`;
}

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 40) || 'section';
}

function normalizeHeading(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, ' ');
}

function sceneTitleFromParagraph(paragraph: string, index: number): string {
  const words = paragraph.replace(/[“”"']/g, '').split(/\s+/).filter(Boolean).slice(0, 5).join(' ');
  return words ? `${words}${paragraph.split(/\s+/).length > 5 ? '…' : ''}` : `Scene ${index + 1}`;
}
