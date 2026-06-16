import { Button, Progress } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { omnixApiClient, type JobRecord, type ProviderFacadePayload } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { OmnixStatusPill, WorkspacePanel } from '../../design/primitives';
import { FeatureSubmitFeedback, FeatureValidationMessage } from '../shared/FeatureSubmitFeedback';

interface StorytellerFormValues {
  providerId: string;
  title: string;
  premise: string;
}

const toneOptions = ['Cozy', 'Hopeful', 'Gentle', 'Mystery'];
const styleOptions = ['Lyrical & Descriptive', 'Fast-paced', 'Dialogue-heavy', 'Cinematic', 'Literary'];

export function StorytellerWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const queryClient = useQueryClient();
  const [selectedTone, setSelectedTone] = useState('Cozy');
  const [writingStyle, setWritingStyle] = useState(styleOptions[0]);
  const [selectedChapter, setSelectedChapter] = useState(1);
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
  const watchedTitle = watch('title');
  const watchedPremise = watch('premise');
  const watchedProvider = watch('providerId');
  const storyProviders = useMemo(() => llmCapableProviders(providersQuery.data), [providersQuery.data]);
  const queriedStoryJobs = jobsQuery.data?.jobs.filter((job) => job.module === 'storyteller') ?? [];
  const storyJobs = useMemo(() => includeMutationJob(queriedStoryJobs, createJobMutationRecord(createJobMutation.data)), [queriedStoryJobs, createJobMutation.data]);
  const completedStoryJobs = storyJobs.filter((job) => job.status === 'completed' && fullJobOutputText(job));
  const activeJob = completedStoryJobs[0] ?? null;
  const activeStoryText = activeJob ? fullJobOutputText(activeJob) : null;
  const storyAssets = assetsQuery.data?.assets.filter((asset) => asset.type === 'story' || asset.type === 'export') ?? [];
  const storyTitle = jobInputString(activeJob, 'title') || watchedTitle || storyAssetTitle(storyAssets[0]?.storage_path) || 'Untitled story';
  const providerLabel = providerDisplayName(storyProviders, watchedProvider);
  const wordCount = countWords(activeStoryText ?? watchedPremise ?? '');
  const readingMinutes = Math.max(1, Math.ceil(wordCount / 220));
  const chapterCount = Math.max(1, Math.min(12, completedStoryJobs.length || selectedChapter));

  const createJobMutation = useMutation({
    mutationFn: (values: StorytellerFormValues) =>
      omnixApiClient.createJob({
        module: 'storyteller',
        type: 'story.generate',
        resource_class: 'gpu:llm',
        priority: 0,
        input_payload: {
          title: values.title || null,
          premise: values.premise,
          provider_id: values.providerId || null,
          prompt_template_id: 'storyteller.draft.v1',
          tone: selectedTone,
          writing_style: writingStyle,
          chapter: selectedChapter,
        },
        stages: [
          { id: 'outline', label: 'Build outline', resource_class: 'gpu:llm', status: 'queued' },
          { id: 'draft', label: 'Draft story', resource_class: 'gpu:llm', status: 'queued' },
          { id: 'store-story', label: 'Store story asset', resource_class: 'cpu', status: 'queued' },
        ],
      }),
    onSuccess: async (_job, values) => {
      reset({ providerId: values.providerId, title: values.title, premise: values.premise });
      await queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] });
      await queryClient.invalidateQueries({ queryKey: ['platform', 'assets'] });
    },
  });
  const submitStatus = createJobMutation.isPending ? 'queueing' : createJobMutation.isError ? 'error' : createJobMutation.data?.status ?? 'ready';

  return (
    <WorkspacePanel>
      <div className="storyteller-workspace" aria-labelledby="module-title">
        <StoryLibrary storyAssets={storyAssets} completedStoryJobs={completedStoryJobs} activeTitle={storyTitle} />

        <main className="storyteller-stage">
          <StoryProjectHeader
            title={storyTitle}
            premise={watchedPremise}
            providerLabel={providerLabel}
            wordCount={wordCount}
            chapterCount={chapterCount}
            moduleRoute={module.route}
          />

          <div className="storyteller-compose-grid">
            <section className="storyteller-manuscript" aria-label="Story manuscript">
              <div className="storyteller-manuscript-meta">
                <span>Chapter {selectedChapter}</span>
                <span>{readingMinutes} min read</span>
              </div>
              <h2 id="module-title">{storyTitle}</h2>
              <div className="storyteller-flourish" aria-hidden="true">
                <span />
                <strong>◇</strong>
                <span />
              </div>
              {activeStoryText ? (
                <StoryText text={activeStoryText} />
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
              handleSubmit={handleSubmit}
              latestJob={storyJobs[0] ?? null}
            />
          </div>

          <StoryActionBar />
          <StoryVersions jobs={completedStoryJobs} />
        </main>

        <StoryOutline activeTitle={storyTitle} selectedChapter={selectedChapter} setSelectedChapter={setSelectedChapter} />
      </div>
    </WorkspacePanel>
  );
}

interface StoryControlsProps {
  providers: Array<{ id: string; label: string }>;
  register: ReturnType<typeof useForm<StorytellerFormValues>>['register'];
  errors: ReturnType<typeof useForm<StorytellerFormValues>>['formState']['errors'];
  createJobMutation: ReturnType<typeof useMutation<JobRecord, Error, StorytellerFormValues>>;
  submitStatus: string;
  selectedTone: string;
  setSelectedTone: (tone: string) => void;
  writingStyle: string;
  setWritingStyle: (style: string) => void;
  selectedChapter: number;
  setSelectedChapter: (chapter: number) => void;
  handleSubmit: ReturnType<typeof useForm<StorytellerFormValues>>['handleSubmit'];
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

      <form className="storyteller-form" onSubmit={handleSubmit((values) => createJobMutation.mutate(values))}>
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

function StoryActionBar() {
  const actions = [
    ['Continue Story', 'AI continues from here'],
    ['Rewrite Paragraph', 'Improve clarity & flow'],
    ['Expand Scene', 'Add depth & detail'],
    ['Dialogue Polish', 'Enhance dialogue'],
    ['Summarize', 'Condense this section'],
  ];
  return (
    <section className="storyteller-action-bar" aria-label="Story actions">
      {actions.map(([label, description]) => (
        <button key={label} type="button">
          <strong>{label}</strong>
          <span>{description}</span>
        </button>
      ))}
    </section>
  );
}

function StoryVersions({ jobs }: { jobs: JobRecord[] }) {
  return (
    <section className="storyteller-versions" aria-label="Recent story versions">
      <p className="eyebrow">Recent versions</p>
      {(jobs.length ? jobs.slice(0, 5) : [null, null, null]).map((job, index) => (
        <button className={index === 0 ? 'active' : ''} key={job?.id ?? `placeholder-${index}`} type="button">
          <strong>v{jobs.length ? jobs.length - index : index + 1}</strong>
          <span>{job ? relativeVersionLabel(index) : index === 0 ? 'Just now' : 'Draft'}</span>
        </button>
      ))}
      <button type="button">View all</button>
    </section>
  );
}

function StoryOutline({
  activeTitle,
  selectedChapter,
  setSelectedChapter,
}: {
  activeTitle: string;
  selectedChapter: number;
  setSelectedChapter: (chapter: number) => void;
}) {
  const chapters = [
    ['Chapter 1', activeTitle, ['The Leaving', 'The Old Path', 'First Sight of Home']],
    ['Chapter 2', 'The Gathering Leaves', ['Market Day', 'A Curious Letter', 'Evening Whispers']],
    ['Chapter 3', 'Under the Briar Moon', ['The Hidden Door', 'What Was Forgotten', 'The Choice']],
    ['Chapter 4', 'Threads of Tomorrow', ['New Roads', 'Quiet Promises', 'Dawn']],
  ];
  return (
    <aside className="storyteller-outline" aria-label="Story outline">
      <div className="storyteller-panel-heading compact">
        <p className="eyebrow">Outline</p>
        <button type="button">☰</button>
      </div>
      {chapters.map(([chapterLabel, chapterTitle, scenes], chapterIndex) => {
        const chapterNumber = chapterIndex + 1;
        return (
          <article className={selectedChapter === chapterNumber ? 'active' : ''} key={chapterLabel as string}>
            <button type="button" onClick={() => setSelectedChapter(chapterNumber)}>
              <strong>{chapterLabel}</strong>
              <span>{chapterTitle}</span>
            </button>
            <ol>
              {(scenes as string[]).map((scene, sceneIndex) => (
                <li className={chapterIndex === 0 && sceneIndex === 0 ? 'active' : ''} key={scene}>
                  <span>Scene {sceneIndex + 1}</span>
                  <strong>{scene}</strong>
                </li>
              ))}
            </ol>
          </article>
        );
      })}
      <button className="storyteller-add-chapter" type="button">Add chapter</button>
    </aside>
  );
}

function StoryText({ text }: { text: string }) {
  return (
    <div className="storyteller-prose">
      {text
        .split(/\n{2,}/)
        .map((paragraph) => paragraph.trim())
        .filter(Boolean)
        .map((paragraph, index) => (
          <p key={`${paragraph.slice(0, 18)}-${index}`}>{paragraph}</p>
        ))}
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

function createJobMutationRecord(job: JobRecord | undefined): JobRecord | null {
  return job ?? null;
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

function relativeVersionLabel(index: number): string {
  if (index === 0) {
    return 'Just now';
  }
  if (index === 1) {
    return '10 min ago';
  }
  return `v${index + 1}`;
}
