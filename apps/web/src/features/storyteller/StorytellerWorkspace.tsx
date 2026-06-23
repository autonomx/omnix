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
type SaveFeedbackKind = 'saved' | 'exported' | 'error';
type StoryLibrarySource = 'draft' | 'job' | 'asset';
type StoryWorkspaceMode = 'writing' | 'story';
type StoryLibrarySection = 'drafts' | 'stories' | 'characters' | 'world-notes' | 'prompts' | 'trash';

interface StoryGenerationRequest {
  values: StorytellerFormValues;
  action: StoryActionMode;
  sourceText: string | null;
  sourceJobId: string | null;
  sourceLibraryItemId?: string | null;
  sourceStoryTitle?: string | null;
  generateTitle?: boolean;
  interactionMode?: StoryWorkspaceMode;
  userResponse?: string | null;
  suggestedChoice?: string | null;
}

interface StoryOutlineScene {
  id: string;
  label: string;
  title: string;
  placeholder?: boolean;
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

interface SaveFeedback {
  kind: SaveFeedbackKind;
  message: string;
}

interface SavedStoryDraft {
  title: string;
  premise?: string;
  providerLabel?: string;
  wordCount?: number;
  chapterCount?: number;
  sourceJobId?: string | null;
  savedAt?: string;
  content: string;
}

interface StoryAssetSummary {
  id: string;
  storage_path: string;
  type: string;
  created_at?: string;
}

interface StoryLibraryItem {
  id: string;
  source: StoryLibrarySource;
  title: string;
  subtitle: string;
  content: string | null;
  jobId: string | null;
  assetId: string | null;
}

interface TrashedStoryLibraryItem extends StoryLibraryItem {
  trashedAt: string;
}

interface StorySceneAddition {
  id: string;
  sourceItemId: string;
  sourceJobId: string;
  chapterNumber: number;
  sceneNumber: number;
  title: string;
  chapterTitle?: string;
  startsNewChapter?: boolean;
  content: string;
  storyTitle: string | null;
  createdAt: string;
}

const storyDraftStorageKey = 'omnix:storyteller:last-draft';
const storyTrashStorageKey = 'omnix:storyteller:trash';
const storySceneAdditionsStorageKey = 'omnix:storyteller:scene-additions';
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
  const [workspaceMode, setWorkspaceMode] = useState<StoryWorkspaceMode>('writing');
  const [activeLibrarySection, setActiveLibrarySection] = useState<StoryLibrarySection>('drafts');
  const [selectedTone, setSelectedTone] = useState('Cozy');
  const [writingStyle, setWritingStyle] = useState(styleOptions[0]);
  const [selectedChapter, setSelectedChapter] = useState(1);
  const [selectedLibraryItemId, setSelectedLibraryItemId] = useState<string | null>(null);
  const [isNewDraft, setIsNewDraft] = useState(false);
  const [savedDraft, setSavedDraft] = useState<SavedStoryDraft | null>(() => readSavedStoryDraft());
  const [trashedLibraryItems, setTrashedLibraryItems] = useState<TrashedStoryLibraryItem[]>(() => readTrashedStoryLibraryItems());
  const [storySceneAdditions, setStorySceneAdditions] = useState<StorySceneAddition[]>(() => readStorySceneAdditions());
  const [saveFeedback, setSaveFeedback] = useState<SaveFeedback | null>(null);
  const [storyModeResponse, setStoryModeResponse] = useState('');

  const providersQuery = useQuery({
    queryKey: ['platform', 'providers'],
    queryFn: () => omnixApiClient.listProviders(),
  });
  const jobsQuery = useQuery({ queryKey: ['platform', 'jobs'], queryFn: () => omnixApiClient.listJobs() });
  const assetsQuery = useQuery({ queryKey: ['platform', 'assets'], queryFn: () => omnixApiClient.listAssets() });
  const { register, handleSubmit, reset, watch, formState: { errors } } = useForm<StorytellerFormValues>({
    defaultValues: { providerId: '', title: '', premise: '' },
  });

  const createJobMutation = useMutation<JobRecord, Error, StoryGenerationRequest>({
    mutationFn: ({
      values,
      action,
      sourceText,
      sourceJobId,
      sourceLibraryItemId,
      sourceStoryTitle,
      generateTitle,
      interactionMode,
      userResponse,
      suggestedChoice,
    }) =>
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
          generate_title: Boolean(generateTitle),
          interaction_mode: interactionMode ?? 'writing',
          user_response: userResponse ?? null,
          suggested_choice: suggestedChoice ?? null,
          source_text: sourceText,
          source_job_id: sourceJobId,
          source_library_item_id: sourceLibraryItemId ?? null,
          source_story_title: sourceStoryTitle ?? null,
          tone: selectedTone,
          writing_style: writingStyle,
          chapter: selectedChapter,
        },
        stages: [
          {
            id: 'outline',
            label: action === 'draft' ? 'Build outline' : `Plan ${actionLabel(action)}`,
            resource_class: 'gpu:llm',
            status: 'queued',
          },
          {
            id: 'draft',
            label: action === 'draft' ? 'Draft story' : actionLabel(action),
            resource_class: 'gpu:llm',
            status: 'queued',
          },
          { id: 'store-story', label: 'Store story asset', resource_class: 'cpu', status: 'queued' },
        ],
      }),
    onSuccess: async (job, request) => {
      reset({ providerId: request.values.providerId, title: request.values.title, premise: request.values.premise });
      setIsNewDraft(false);
      const completedText = fullJobOutputText(job);
      if (job.status === 'completed' && completedText && isSceneAppendRequest(request)) {
        const addition = buildStorySceneAddition(job, request);
        if (addition) {
          setStorySceneAdditions((current) => {
            const next = upsertStorySceneAddition(current, addition);
            persistStorySceneAdditions(next);
            return next;
          });
          setSelectedLibraryItemId(addition.sourceItemId);
          setSelectedChapter(addition.chapterNumber);
          setActiveLibrarySection(addition.sourceItemId.startsWith('draft:') ? 'drafts' : 'stories');
          setSaveFeedback({ kind: 'saved', message: `Added ${addition.title} to ${addition.storyTitle ?? request.sourceStoryTitle ?? 'the story'}.` });
        }
      } else if (job.status === 'completed' && completedText) {
        setSelectedLibraryItemId(libraryJobId(job.id));
        setActiveLibrarySection('stories');
      }
      if (request.interactionMode === 'story') {
        setStoryModeResponse('');
        setWorkspaceMode('story');
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
  const storyJobs = useMemo(
    () => includeMutationJob(queriedStoryJobs, createJobMutation.data ?? null),
    [queriedStoryJobs, createJobMutation.data],
  );
  const completedStoryJobs = storyJobs.filter((job) => job.status === 'completed' && fullJobOutputText(job));
  const libraryStoryJobs = completedStoryJobs.filter((job) =>
    !isStorySceneAppendJob(job) && !storySceneAdditions.some((addition) => addition.sourceJobId === job.id));
  const storyAssets = assetsQuery.data?.assets.filter((asset) => asset.type === 'story' || asset.type === 'export') ?? [];
  const allLibraryItems = useMemo(
    () => buildStoryLibraryItems(savedDraft, libraryStoryJobs, storyAssets as StoryAssetSummary[]),
    [savedDraft, libraryStoryJobs, storyAssets],
  );
  const trashItems = useMemo(
    () => mergeTrashedStoryLibraryItems(trashedLibraryItems, allLibraryItems),
    [trashedLibraryItems, allLibraryItems],
  );
  const libraryItems = useMemo(
    () => allLibraryItems.filter((item) => !trashItems.some((trashedItem) => trashedItem.id === item.id)),
    [allLibraryItems, trashItems],
  );
  const selectableLibraryItems = useMemo(
    () => [...libraryItems, ...trashItems],
    [libraryItems, trashItems],
  );
  const activeLibraryItem = isNewDraft
    ? null
    : selectableLibraryItems.find((item) => item.id === selectedLibraryItemId) ??
      libraryItems.find((item) => item.source === 'job') ??
      libraryItems.find((item) => item.source === 'draft') ??
      null;
  const activeJob = activeLibraryItem?.jobId
    ? completedStoryJobs.find((job) => job.id === activeLibraryItem.jobId) ?? null
    : null;
  const activeAsset = activeLibraryItem?.assetId
    ? (storyAssets as StoryAssetSummary[]).find((asset) => asset.id === activeLibraryItem.assetId) ?? null
    : null;
  const assetContentQuery = useQuery({
    queryKey: ['platform', 'assets', activeAsset?.id, 'content'],
    queryFn: () => omnixApiClient.getAssetContent(activeAsset?.id ?? ''),
    enabled: Boolean(activeAsset?.id),
    retry: false,
  });
  const activeAssetText = activeAsset && assetContentQuery.data?.asset.id === activeAsset.id
    ? assetContentQuery.data.content
    : null;
  const activeItemSceneAdditions = useMemo(
    () => activeLibraryItem ? storySceneAdditions.filter((addition) => addition.sourceItemId === activeLibraryItem.id) : [],
    [activeLibraryItem, storySceneAdditions],
  );
  const baseActiveStoryText = activeLibraryItem?.content ?? activeAssetText ?? null;
  const activeStoryText = useMemo(
    () => applyStorySceneAdditions(baseActiveStoryText, activeItemSceneAdditions),
    [baseActiveStoryText, activeItemSceneAdditions],
  );
  const storyTitle = storyDisplayTitle(
    latestStoryTitleOverride(activeItemSceneAdditions) || activeLibraryItem?.title || watchedTitle,
    activeStoryText,
  );
  const premise = activeLibraryItem?.source === 'draft'
    ? savedDraft?.premise ?? watchedPremise
    : watchedPremise || jobInputString(activeJob, 'premise') || '';
  const providerLabel = providerDisplayName(
    storyProviders,
    watchedProvider || jobInputString(activeJob, 'provider_id') || '',
    activeLibraryItem?.source === 'draft' ? savedDraft?.providerLabel ?? null : null,
  );
  const sourceJobId = activeJob?.id ?? activeLibraryItem?.jobId ?? null;
  const outline = useMemo(() => deriveStoryOutline(activeStoryText, storyTitle), [activeStoryText, storyTitle]);
  const activeChapter = outline.find((chapter) => chapter.number === selectedChapter) ?? outline[0] ?? null;
  const chapterCount = outline.length || Math.max(1, Math.min(12, libraryStoryJobs.length || selectedChapter));
  const wordCount = countWords(activeStoryText ?? watchedPremise ?? '');
  const readingMinutes = Math.max(1, Math.ceil(wordCount / 220));
  const submitStatus = createJobMutation.isPending
    ? 'queueing'
    : createJobMutation.isError
      ? 'error'
      : createJobMutation.data?.status ?? 'ready';
  const canPersistStory = Boolean(activeStoryText?.trim());
  const storyModeChoices = useMemo(() => suggestedStoryMoves(activeStoryText, storyTitle), [activeStoryText, storyTitle]);

  useEffect(() => {
    if (!selectedLibraryItemId) return;
    if (!selectableLibraryItems.some((item) => item.id === selectedLibraryItemId)) {
      setSelectedLibraryItemId(null);
    }
  }, [selectableLibraryItems, selectedLibraryItemId]);

  useEffect(() => {
    if (outline.length && !outline.some((chapter) => chapter.number === selectedChapter)) {
      setSelectedChapter(outline[0].number);
    }
  }, [outline, selectedChapter]);

  const requestValues = ({ allowGeneratedTitle = false }: { allowGeneratedTitle?: boolean } = {}): StorytellerFormValues => {
    const shouldGenerateTitle = allowGeneratedTitle && shouldGenerateStoryTitle(watchedTitle, storyTitle);
    return {
      providerId: watchedProvider,
      title: shouldGenerateTitle ? '' : watchedTitle || storyTitle,
      premise: watchedPremise || premise || 'Continue this interactive story.',
    };
  };

  const submitStoryRequest = (values: StorytellerFormValues, action: StoryActionMode) => {
    const appendToActiveStory = action === 'continue' && Boolean(activeLibraryItem?.id && activeStoryText?.trim());
    const generateTitle = appendToActiveStory && shouldGenerateStoryTitle(watchedTitle, storyTitle);
    setSaveFeedback(null);
    createJobMutation.mutate({
      values: appendToActiveStory ? requestValues({ allowGeneratedTitle: true }) : values,
      action,
      sourceText: activeStoryText,
      sourceJobId,
      sourceLibraryItemId: appendToActiveStory ? activeLibraryItem?.id ?? null : null,
      sourceStoryTitle: appendToActiveStory ? storyTitle : null,
      generateTitle,
      interactionMode: 'writing',
    });
  };

  const submitQuickAction = (action: StoryQuickActionMode) => {
    if (!activeStoryText?.trim()) {
      setSaveFeedback({ kind: 'error', message: 'Select or generate a story before using quick actions.' });
      return;
    }
    submitStoryRequest(requestValues({ allowGeneratedTitle: action === 'continue' }), action);
  };

  const submitStoryModeMove = (moveText: string, suggestedChoice: string | null = null) => {
    const response = moveText.trim();
    if (!response) return;
    const generateTitle = shouldGenerateStoryTitle(watchedTitle, storyTitle);
    setSaveFeedback(null);
    createJobMutation.mutate({
      values: requestValues({ allowGeneratedTitle: true }),
      action: 'continue',
      sourceText: storyModeContext(activeStoryText, response),
      sourceJobId,
      sourceLibraryItemId: activeLibraryItem?.id ?? null,
      sourceStoryTitle: storyTitle,
      generateTitle,
      interactionMode: 'story',
      userResponse: response,
      suggestedChoice,
    });
  };

  const addChapterToActiveStory = () => {
    if (!activeLibraryItem?.id || !activeStoryText?.trim()) {
      setSaveFeedback({ kind: 'error', message: 'Select or generate a story before adding a chapter.' });
      return;
    }
    const chapterNumber = nextChapterNumber(outline);
    const createdAt = new Date().toISOString();
    const addition: StorySceneAddition = {
      id: `chapter:${activeLibraryItem.id}:${createdAt}`,
      sourceItemId: activeLibraryItem.id,
      sourceJobId: `local:${createdAt}`,
      chapterNumber,
      sceneNumber: 1,
      title: 'Opening',
      chapterTitle: 'New chapter',
      startsNewChapter: true,
      content: '',
      storyTitle,
      createdAt,
    };
    setStorySceneAdditions((current) => {
      const next = upsertStorySceneAddition(current, addition);
      persistStorySceneAdditions(next);
      return next;
    });
    setSelectedChapter(chapterNumber);
    setSaveFeedback({ kind: 'saved', message: `Added Chapter ${chapterNumber} to ${storyTitle}.` });
  };

  const selectLibraryItem = (itemId: string) => {
    const item = libraryItems.find((entry) => entry.id === itemId);
    setIsNewDraft(false);
    setSelectedLibraryItemId(itemId);
    setSelectedChapter(1);
    setSaveFeedback(null);
    if (item?.source === 'draft') setActiveLibrarySection('drafts');
    if (item?.source === 'job' || item?.source === 'asset') setActiveLibrarySection('stories');
  };

  const startNewDraft = () => {
    reset({ providerId: watchedProvider, title: '', premise: '' });
    setActiveLibrarySection('drafts');
    setIsNewDraft(true);
    setSelectedLibraryItemId(null);
    setSelectedChapter(1);
    setWorkspaceMode('writing');
    setSaveFeedback({ kind: 'saved', message: 'New draft ready. Add a premise to begin.' });
  };

  const trashActiveStory = () => {
    if (activeLibrarySection === 'trash') {
      setActiveLibrarySection('trash');
      return;
    }

    const item = activeLibraryItem;
    if (!item || trashItems.some((trashedItem) => trashedItem.id === item.id)) {
      setActiveLibrarySection('trash');
      return;
    }

    const nextTrashItems = upsertTrashedStoryLibraryItem(trashedLibraryItems, {
      ...item,
      trashedAt: new Date().toISOString(),
    });
    persistTrashedStoryLibraryItems(nextTrashItems);
    setTrashedLibraryItems(nextTrashItems);
    if (item.source === 'draft') {
      window.localStorage.removeItem(storyDraftStorageKey);
      setSavedDraft(null);
    }
    setIsNewDraft(false);
    setSelectedLibraryItemId(item.id);
    setActiveLibrarySection('trash');
    setSaveFeedback({ kind: 'saved', message: `Moved "${item.title}" to Trash.` });
  };

  const selectOutlineTarget = (chapterNumber: number, targetId: string) => {
    setSelectedChapter(chapterNumber);
    const target = (document.getElementById(targetId) ??
      document.getElementById(`story-chapter-${chapterNumber}`) ??
      document.querySelector('[aria-label="Story manuscript"]')) as
      | (HTMLElement & { scrollIntoView?: (options?: ScrollIntoViewOptions) => void })
      | null;
    target?.scrollIntoView?.({ block: 'start', behavior: 'smooth' });
  };

  const draftForActiveStory = (): SavedStoryDraft => ({
    title: storyTitle,
    premise,
    providerLabel,
    wordCount,
    chapterCount,
    sourceJobId,
    savedAt: new Date().toISOString(),
    content: activeStoryText ?? '',
  });

  const persistLocalDraft = (draft: SavedStoryDraft) => {
    window.localStorage.setItem(storyDraftStorageKey, JSON.stringify(draft));
    setSavedDraft(draft);
  };

  const saveStoryDraft = async () => {
    if (!activeStoryText?.trim()) {
      setSaveFeedback({ kind: 'error', message: 'Generate or select a story version before saving.' });
      return;
    }
    const draft = draftForActiveStory();
    try {
      persistLocalDraft(draft);
      const saved = await omnixApiClient.saveStoryAsset({
        title: storyTitle,
        content: activeStoryText,
        premise,
        provider_label: providerLabel,
        word_count: wordCount,
        chapter_count: chapterCount,
        source_job_id: sourceJobId,
        metadata: { source: activeLibraryItem?.source ?? 'workspace' },
      });
      setSaveFeedback({ kind: 'saved', message: `Saved “${storyTitle}” as a shared story asset.` });
      setIsNewDraft(false);
      setActiveLibrarySection('stories');
      setSelectedLibraryItemId(libraryAssetId(saved.asset.id));
      await queryClient.invalidateQueries({ queryKey: ['platform', 'assets'] });
    } catch {
      try {
        persistLocalDraft(draft);
        setActiveLibrarySection('drafts');
        setSelectedLibraryItemId('draft:last');
        setIsNewDraft(false);
        setSaveFeedback({ kind: 'saved', message: `Saved “${storyTitle}” locally.` });
      } catch (error) {
        setSaveFeedback({
          kind: 'error',
          message: error instanceof Error ? error.message : 'Unable to save story.',
        });
      }
    }
  };

  const exportStoryMarkdown = () => {
    if (!activeStoryText?.trim()) {
      setSaveFeedback({ kind: 'error', message: 'Generate or select a story version before exporting.' });
      return;
    }
    try {
      const markdown = formatStoryMarkdown({
        title: storyTitle,
        premise,
        providerLabel,
        wordCount,
        chapterCount,
        sourceJobId,
        text: activeStoryText,
      });
      const filename = `${slugify(storyTitle || 'story')}.md`;
      if (typeof Blob === 'undefined' || typeof URL === 'undefined' || typeof URL.createObjectURL !== 'function') {
        setSaveFeedback({ kind: 'exported', message: `Prepared Markdown export for ${filename}.` });
        return;
      }
      const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      link.rel = 'noopener';
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setSaveFeedback({ kind: 'exported', message: `Exported ${filename}.` });
    } catch (error) {
      setSaveFeedback({ kind: 'error', message: error instanceof Error ? error.message : 'Unable to export story.' });
    }
  };

  return (
    <WorkspacePanel>
      <h2 id="module-title" className="workspace-module-heading">{module.label}</h2>
      <div className="storyteller-workspace" aria-labelledby="module-title">
        <StoryLibrary
          activeItemId={activeLibraryItem?.id ?? null}
          activeSection={activeLibrarySection}
          items={libraryItems}
          onNewDraft={startNewDraft}
          onSectionChange={setActiveLibrarySection}
          onSelect={selectLibraryItem}
          onTrashActiveItem={trashActiveStory}
          trashItems={trashItems}
        />
        <main className="storyteller-stage">
          <h2 className="storyteller-module-title">{module.label}</h2>
          <StoryProjectHeader
            canPersistStory={canPersistStory}
            chapterCount={chapterCount}
            moduleRoute={module.route}
            onExport={exportStoryMarkdown}
            onSave={saveStoryDraft}
            premise={premise}
            providerLabel={providerLabel}
            saveFeedback={saveFeedback}
            title={storyTitle}
            wordCount={wordCount}
          />
          <StoryModeSwitch mode={workspaceMode} onChange={setWorkspaceMode} />
          {workspaceMode === 'story' ? (
            <StoryModePanel
              activeAsset={activeAsset}
              activeChapterLabel={activeChapter?.label ?? `Chapter ${selectedChapter}`}
              activeStoryText={activeStoryText}
              assetError={assetContentQuery.error}
              isAssetLoading={assetContentQuery.isLoading || assetContentQuery.isFetching}
              module={module}
              onMove={submitStoryModeMove}
              pending={createJobMutation.isPending}
              response={storyModeResponse}
              setResponse={setStoryModeResponse}
              storyTitle={storyTitle}
              suggestedMoves={storyModeChoices}
            />
          ) : (
            <>
              <div className="storyteller-compose-grid">
                <section className="storyteller-manuscript" aria-label="Story manuscript">
                  <div className="storyteller-manuscript-meta">
                    <span>{activeChapter?.label ?? `Chapter ${selectedChapter}`}</span>
                    <span>{readingMinutes} min read</span>
                  </div>
                  <h2>{activeChapter?.title ?? storyTitle}</h2>
                  <div className="storyteller-flourish" aria-hidden="true"><span /><strong>◇</strong><span /></div>
                  {activeStoryText ? (
                    <StoryText outline={outline} text={activeStoryText} />
                  ) : (
                    <StoryEmptyState
                      activeAsset={activeAsset}
                      assetError={assetContentQuery.error}
                      isAssetLoading={assetContentQuery.isLoading || assetContentQuery.isFetching}
                      module={module}
                      storyTitle={storyTitle}
                    />
                  )}
                </section>
                <StoryControls
                  createJobMutation={createJobMutation}
                  errors={errors}
                  handleSubmit={handleSubmit}
                  latestJob={storyJobs[0] ?? null}
                  onAddChapter={addChapterToActiveStory}
                  onGenerate={(values) => submitStoryRequest(values, 'draft')}
                  providers={storyProviders}
                  register={register}
                  selectedChapter={selectedChapter}
                  selectedTone={selectedTone}
                  setSelectedChapter={setSelectedChapter}
                  setSelectedTone={setSelectedTone}
                  setWritingStyle={setWritingStyle}
                  submitStatus={submitStatus}
                  writingStyle={writingStyle}
                />
              </div>
              <StoryActionBar disabled={createJobMutation.isPending} onAction={submitQuickAction} />
              <StoryVersions
                activeJobId={activeJob?.id ?? null}
                jobs={libraryStoryJobs}
                onSelect={(jobId) => selectLibraryItem(libraryJobId(jobId))}
              />
            </>
          )}
        </main>
        <StoryOutline chapters={outline} selectedChapter={selectedChapter} onAddChapter={addChapterToActiveStory} onSelect={selectOutlineTarget} />
      </div>
    </WorkspacePanel>
  );
}

function StoryModeSwitch({ mode, onChange }: { mode: StoryWorkspaceMode; onChange: (mode: StoryWorkspaceMode) => void }) {
  return (
    <section className="storyteller-mode-switch" aria-label="Storyteller mode">
      <button className={mode === 'writing' ? 'active' : ''} type="button" onClick={() => onChange('writing')}>
        <strong>Writing Mode</strong>
        <span>Draft, revise, save, and export manuscripts.</span>
      </button>
      <button className={mode === 'story' ? 'active' : ''} type="button" onClick={() => onChange('story')}>
        <strong>Interactive Story Mode</strong>
        <span>Read a page, make a move, and let AI continue.</span>
      </button>
    </section>
  );
}

function StoryModePanel({
  activeAsset,
  activeChapterLabel,
  activeStoryText,
  assetError,
  isAssetLoading,
  module,
  onMove,
  pending,
  response,
  setResponse,
  storyTitle,
  suggestedMoves,
}: {
  activeAsset: StoryAssetSummary | null;
  activeChapterLabel: string;
  activeStoryText: string | null;
  assetError: Error | null;
  isAssetLoading: boolean;
  module: OmnixModuleDefinition;
  onMove: (moveText: string, suggestedChoice?: string | null) => void;
  pending: boolean;
  response: string;
  setResponse: (value: string) => void;
  storyTitle: string;
  suggestedMoves: string[];
}) {
  const latestPage = activeStoryText ? lastStoryPage(activeStoryText) : null;
  return (
    <section className="story-mode-panel" aria-label="Interactive story mode">
      <div className="story-mode-reader">
        <div className="storyteller-manuscript-meta">
          <span>{activeChapterLabel}</span>
          <span>Interactive page</span>
        </div>
        <h2>{storyTitle}</h2>
        <div className="storyteller-flourish" aria-hidden="true"><span /><strong>◇</strong><span /></div>
        {latestPage ? (
          <div className="story-mode-page">
            {storyParagraphs(latestPage).map((paragraph, index) => (
              <p key={`${paragraph.slice(0, 24)}-${index}`}>{paragraph}</p>
            ))}
          </div>
        ) : (
          <StoryEmptyState
            activeAsset={activeAsset}
            assetError={assetError}
            isAssetLoading={isAssetLoading}
            module={module}
            storyTitle={storyTitle}
          />
        )}
      </div>
      <aside className="story-mode-controls" aria-label="Interactive story mode controls">
        <div className="storyteller-panel-heading">
          <div><p className="eyebrow">Interactive story mode</p><h3>Your next move</h3></div>
          <OmnixStatusPill>{pending ? 'continuing' : 'ready'}</OmnixStatusPill>
        </div>
        <label>
          Write your response
          <textarea
            aria-label="Interactive story mode response"
            onChange={(event) => setResponse(event.target.value)}
            placeholder="I examine the glowing door, but keep one hand on the charm."
            rows={5}
            value={response}
          />
        </label>
        <Button disabled={pending || !response.trim()} loading={pending} onClick={() => onMove(response)} type="button">
          Continue with my response
        </Button>
        <div className="story-mode-suggestions">
          <p className="eyebrow">Suggested next moves</p>
          {suggestedMoves.map((move) => (
            <button disabled={pending} key={move} type="button" onClick={() => onMove(move, move)}>{move}</button>
          ))}
        </div>
      </aside>
    </section>
  );
}

function StoryEmptyState({ activeAsset, assetError, isAssetLoading, module, storyTitle }: {
  activeAsset: StoryAssetSummary | null;
  assetError: Error | null;
  isAssetLoading: boolean;
  module: OmnixModuleDefinition;
  storyTitle: string;
}) {
  if (activeAsset) {
    const message = assetError
      ? 'This story asset could not be loaded as readable text.'
      : isAssetLoading
        ? 'Loading story asset content…'
        : 'This story asset is selected but has no readable manuscript text.';
    return (
      <div className="storyteller-empty-manuscript" role="status">
        <p className="eyebrow">Story asset</p>
        <h3>{storyTitle}</h3>
        <p>{message}</p>
      </div>
    );
  }
  return (
    <div className="storyteller-empty-manuscript" role="status">
      <p className="eyebrow">Feature module</p>
      <h3>{module.label}</h3>
      <p>{module.summary}</p>
      <p>Start with a premise, choose a tone, then generate the first scene.</p>
    </div>
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
  onAddChapter: () => void;
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
  onAddChapter,
  handleSubmit,
  latestJob,
}: StoryControlsProps) {
  return (
    <aside className="storyteller-controls" aria-label="Story controls">
      <div className="storyteller-panel-heading">
        <div><p className="eyebrow">Story controls</p><h3>Guide the next passage</h3></div>
        <OmnixStatusPill>{submitStatus}</OmnixStatusPill>
      </div>
      <form className="storyteller-form" onSubmit={handleSubmit(onGenerate)}>
        <label>
          Provider
          <select {...register('providerId')}>
            <option value="">Default LLM provider</option>
            {providers.map((provider) => <option key={provider.id} value={provider.id}>{provider.label}</option>)}
          </select>
        </label>
        <label>Title<input {...register('title')} placeholder="Untitled story" /></label>
        <label>
          Premise <span>0/500</span>
          <textarea
            aria-invalid={Boolean(errors.premise)}
            placeholder="A young herbalist discovers a small secret that could change her quiet valley."
            rows={4}
            {...register('premise', { required: true })}
          />
        </label>
        <div className="storyteller-control-block">
          <span>Tone & mood</span>
          <div className="storyteller-chip-row">
            {toneOptions.map((tone) => (
              <button className={tone === selectedTone ? 'active' : ''} key={tone} type="button" onClick={() => setSelectedTone(tone)}>{tone}</button>
            ))}
          </div>
        </div>
        <label>
          Writing style
          <select value={writingStyle} onChange={(event) => setWritingStyle(event.target.value)}>
            {styleOptions.map((style) => <option key={style} value={style}>{style}</option>)}
          </select>
        </label>
        <div className="storyteller-chapter-controls">
          <span>Chapter</span>
          <button type="button" onClick={() => setSelectedChapter(Math.max(1, selectedChapter - 1))}>‹</button>
          <strong>{selectedChapter}</strong>
          <button type="button" onClick={() => setSelectedChapter(selectedChapter + 1)}>›</button>
          <button type="button" onClick={onAddChapter}>New chapter</button>
        </div>
        <Button
          aria-label={createJobMutation.isPending ? 'Queueing story' : 'Queue story'}
          className="storyteller-generate"
          type="submit"
          disabled={createJobMutation.isPending}
          loading={createJobMutation.isPending}
        >
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
        <div className="storyteller-panel-heading compact"><p className="eyebrow">Output status</p><button type="button">Clear</button></div>
        {latestJob ? (
          <article className="storyteller-output-card">
            <div><strong>{latestJob.type}</strong><OmnixStatusPill>{latestJob.status}</OmnixStatusPill></div>
            <Progress value={progressPercent(latestJob.progress)} aria-label={`${latestJob.type} progress`} />
            <small>{latestJob.resource_class}</small>
            {fullJobOutputText(latestJob) ? <p>{truncate(fullJobOutputText(latestJob) ?? '', 180)}</p> : null}
          </article>
        ) : <div className="storyteller-empty-small">No generation yet.</div>}
      </div>
    </aside>
  );
}

function StoryProjectHeader({ title, premise, providerLabel, wordCount, chapterCount, moduleRoute, canPersistStory, saveFeedback, onSave, onExport }: {
  title: string;
  premise: string;
  providerLabel: string;
  wordCount: number;
  chapterCount: number;
  moduleRoute: string;
  canPersistStory: boolean;
  saveFeedback: SaveFeedback | null;
  onSave: () => void;
  onExport: () => void;
}) {
  return (
    <header className="storyteller-project-header">
      <div className="storyteller-cover" aria-hidden="true" />
      <div className="storyteller-project-copy">
        <p className="eyebrow">{moduleRoute}</p>
        <h1>{title}</h1>
        <p>{premise || 'A new local-first story draft.'}</p>
        <div className="storyteller-tags"><span>Fantasy</span><span>Cozy</span><span>Mystery</span><span>Slice of Life</span></div>
        {saveFeedback ? <p className={`storyteller-persist-feedback ${saveFeedback.kind}`} role="status">{saveFeedback.message}</p> : null}
      </div>
      <div className="storyteller-project-stats">
        <div><strong>{wordCount.toLocaleString()}</strong><span>Words</span></div>
        <div><strong>{chapterCount}</strong><span>Chapters</span></div>
        <div><strong>{providerLabel}</strong><span>Default provider</span></div>
      </div>
      <div className="storyteller-project-actions">
        <button disabled={!canPersistStory} type="button" onClick={onSave}>Save story</button>
        <button disabled={!canPersistStory} type="button" onClick={onExport}>Export Markdown</button>
      </div>
    </header>
  );
}

function StoryLibrary({
  items,
  activeItemId,
  activeSection,
  trashItems,
  onNewDraft,
  onSectionChange,
  onSelect,
  onTrashActiveItem,
}: {
  items: StoryLibraryItem[];
  activeItemId: string | null;
  activeSection: StoryLibrarySection;
  trashItems: TrashedStoryLibraryItem[];
  onNewDraft: () => void;
  onSectionChange: (section: StoryLibrarySection) => void;
  onSelect: (itemId: string) => void;
  onTrashActiveItem: () => void;
}) {
  const sectionItems = activeSection === 'drafts'
    ? items.filter((item) => item.source === 'draft')
    : activeSection === 'stories'
      ? items.filter((item) => item.source !== 'draft')
      : activeSection === 'trash'
        ? trashItems
        : [];
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
        {sectionItems.length ? (
          <div className="storyteller-recent-list">
            {sectionItems.map((item) => (
              <LibraryItemButton activeItemId={activeItemId} item={item} key={item.id} onSelect={onSelect} />
            ))}
          </div>
        ) : (
          <LibrarySectionEmpty section={activeSection} onNewDraft={onNewDraft} />
        )}
      </section>
      <section>
        <p className="eyebrow">Recent stories</p>
        <div className="storyteller-recent-list">
          {items.length ? (
            items.slice(0, 6).map((item) => (
              <LibraryItemButton activeItemId={activeItemId} item={item} key={item.id} onSelect={onSelect} />
            ))
          ) : (
            <article>
              <span className="storyteller-thumb muted" />
              <div><strong>No stories yet</strong><small>Generate or save a story</small></div>
            </article>
          )}
        </div>
      </section>
      <button
        aria-pressed={activeSection === 'trash'}
        className={`storyteller-trash ${activeSection === 'trash' ? 'active' : ''}`}
        type="button"
        title={activeSection === 'trash' ? 'Trash' : 'Move selected story to Trash'}
        onClick={onTrashActiveItem}
      >
        Trash
      </button>
    </aside>
  );
}

function LibraryItemButton({ item, activeItemId, onSelect }: {
  item: StoryLibraryItem;
  activeItemId: string | null;
  onSelect: (itemId: string) => void;
}) {
  return (
    <button
      aria-pressed={item.id === activeItemId}
      className={item.id === activeItemId ? 'active' : ''}
      type="button"
      onClick={() => onSelect(item.id)}
    >
      <span className={`storyteller-thumb ${item.source === 'asset' ? 'muted' : ''}`} />
      <div><strong>{item.title}</strong><small>{item.subtitle}</small></div>
    </button>
  );
}

function LibrarySectionEmpty({ section, onNewDraft }: { section: StoryLibrarySection; onNewDraft: () => void }) {
  const copy: Record<StoryLibrarySection, { title: string; body: string }> = {
    drafts: { title: 'No saved drafts', body: 'Start a blank draft or save the active manuscript.' },
    stories: { title: 'No story assets yet', body: 'Generated and saved stories will appear here.' },
    characters: { title: 'Characters not created yet', body: 'Character cards will attach cast details to future generations.' },
    'world-notes': { title: 'World notes not created yet', body: 'World notes will collect lore, places, factions, and rules.' },
    prompts: { title: 'Prompt presets not created yet', body: 'Prompt presets will save reusable Storyteller instructions.' },
    trash: { title: 'Trash is empty', body: 'Stories moved to Trash will be hidden from recent stories.' },
  };
  return (
    <article className="storyteller-library-empty" role="status">
      <strong>{copy[section].title}</strong>
      <small>{copy[section].body}</small>
      {section === 'drafts' ? <button type="button" onClick={onNewDraft}>Start blank draft</button> : null}
    </article>
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
  const visibleJobs = jobs.slice(0, 5);
  return (
    <section className="storyteller-versions" aria-label="Recent versions">
      <div><p className="eyebrow">Recent versions</p></div>
      {visibleJobs.length ? visibleJobs.map((job, index) => (
        <button
          aria-pressed={job.id === activeJobId}
          className={job.id === activeJobId ? 'active' : ''}
          key={job.id}
          type="button"
          onClick={() => onSelect(job.id)}
        >
          <strong>{index === 0 ? 'v7' : `v${Math.max(1, 7 - index)}`}</strong>
          <span>{storyVersionTitle(job, index)}</span>
        </button>
      )) : <span>No versions yet</span>}
    </section>
  );
}

function StoryOutline({ chapters, selectedChapter, onAddChapter, onSelect }: {
  chapters: StoryOutlineChapter[];
  selectedChapter: number;
  onAddChapter: () => void;
  onSelect: (chapterNumber: number, targetId: string) => void;
}) {
  const [showScenes, setShowScenes] = useState(true);
  return (
    <aside className="storyteller-outline" aria-label="Story outline">
      <div className="storyteller-panel-heading compact">
        <p className="eyebrow">Outline</p>
        <button
          aria-expanded={showScenes}
          aria-label={showScenes ? 'Collapse outline scenes' : 'Expand outline scenes'}
          type="button"
          onClick={() => setShowScenes((current) => !current)}
        >
          ☰
        </button>
      </div>
      {chapters.map((chapter) => (
        <article className={selectedChapter === chapter.number ? 'active' : ''} key={chapter.id}>
          <button type="button" onClick={() => onSelect(chapter.number, chapter.id)}>
            <strong>{chapter.label}</strong>
            <span>{chapter.title}</span>
          </button>
          {showScenes ? <ol>
            {chapter.scenes.map((scene, sceneIndex) => (
              <li className={selectedChapter === chapter.number && sceneIndex === 0 ? 'active' : ''} key={scene.id}>
                <button type="button" onClick={() => onSelect(chapter.number, scene.id)}>
                  <span>{scene.label}</span>
                  <strong>{scene.title}</strong>
                </button>
              </li>
            ))}
          </ol> : null}
        </article>
      ))}
      <button className="storyteller-add-chapter" type="button" onClick={onAddChapter}>Add chapter</button>
    </aside>
  );
}

function StoryText({ text, outline }: { text: string; outline: StoryOutlineChapter[] }) {
  const blocks = useMemo(() => storyTextBlocks(text, outline), [text, outline]);
  return (
    <div className="storyteller-prose">
      {blocks.map((block, index) => {
        const key = `${block.kind}-${block.id ?? block.text.slice(0, 18)}-${index}`;
        if (block.kind === 'chapter') return <h3 id={block.id} key={key} tabIndex={-1}>{block.text}</h3>;
        if (block.kind === 'scene') return <h4 id={block.id} key={key} tabIndex={-1}>{block.text}</h4>;
        return <p key={key}>{block.text}</p>;
      })}
    </div>
  );
}

const librarySections: Array<{ id: StoryLibrarySection; label: string }> = [
  { id: 'drafts', label: 'Drafts' },
  { id: 'stories', label: 'Stories' },
  { id: 'characters', label: 'Characters' },
  { id: 'world-notes', label: 'World Notes' },
  { id: 'prompts', label: 'Prompts' },
];

function librarySectionLabel(section: StoryLibrarySection): string {
  return librarySections.find((entry) => entry.id === section)?.label ?? 'Trash';
}

function llmCapableProviders(payload: ProviderFacadePayload | undefined) {
  return payload?.providers.filter((provider) => provider.capabilities.includes('chat') || provider.capabilities.includes('completion')) ?? [];
}

function progressPercent(progress: { current: number; total: number } | undefined): number {
  return progress && progress.total > 0 ? Math.min(100, Math.round((progress.current / progress.total) * 100)) : 0;
}

function fullJobOutputText(job: { output_refs?: Array<{ content?: unknown }>; logs?: Array<{ content?: unknown }> }): string | null {
  const content = job.output_refs?.find((ref) => typeof ref.content === 'string')?.content ??
    job.logs?.find((log) => typeof log.content === 'string')?.content;
  return typeof content === 'string' && content.trim() ? content : null;
}

function fullJobOutputTitle(job: { output_refs?: Array<{ title?: unknown }> }): string | null {
  const title = job.output_refs?.find((ref) => typeof ref.title === 'string')?.title;
  return cleanStoryTitle(typeof title === 'string' ? title : null);
}

function includeMutationJob(jobs: JobRecord[], mutationJob: JobRecord | null): JobRecord[] {
  return mutationJob ? [mutationJob, ...jobs.filter((job) => job.id !== mutationJob.id)] : jobs;
}

function buildStoryLibraryItems(savedDraft: SavedStoryDraft | null, jobs: JobRecord[], assets: StoryAssetSummary[]): StoryLibraryItem[] {
  const draftItems: StoryLibraryItem[] = savedDraft?.content ? [{
    id: 'draft:last',
    source: 'draft',
    title: savedDraft.title || 'Saved local draft',
    subtitle: `${countWords(savedDraft.content).toLocaleString()} words • saved draft`,
    content: savedDraft.content,
    jobId: savedDraft.sourceJobId ?? null,
    assetId: null,
  }] : [];
  const jobItems = jobs.map((job) => ({
    id: libraryJobId(job.id),
    source: 'job' as const,
    title: storyJobTitle(job),
    subtitle: `${countWords(fullJobOutputText(job) ?? '').toLocaleString()} words • ${jobInputString(job, 'action') ?? 'draft'}`,
    content: fullJobOutputText(job),
    jobId: job.id,
    assetId: null,
  }));
  const assetItems = assets.map((asset) => ({
    id: libraryAssetId(asset.id),
    source: 'asset' as const,
    title: storyAssetTitle(asset.storage_path),
    subtitle: `${asset.type}${asset.created_at ? ` • ${shortDate(asset.created_at)}` : ''}`,
    content: null,
    jobId: null,
    assetId: asset.id,
  }));
  return [...draftItems, ...jobItems, ...assetItems];
}

function readSavedStoryDraft(): SavedStoryDraft | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(storyDraftStorageKey);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<SavedStoryDraft>;
    if (typeof parsed.content !== 'string' || !parsed.content.trim()) return null;
    return {
      title: typeof parsed.title === 'string' && parsed.title.trim() ? parsed.title : 'Saved local draft',
      premise: typeof parsed.premise === 'string' ? parsed.premise : '',
      providerLabel: typeof parsed.providerLabel === 'string' ? parsed.providerLabel : undefined,
      wordCount: typeof parsed.wordCount === 'number' ? parsed.wordCount : undefined,
      chapterCount: typeof parsed.chapterCount === 'number' ? parsed.chapterCount : undefined,
      sourceJobId: typeof parsed.sourceJobId === 'string' ? parsed.sourceJobId : null,
      savedAt: typeof parsed.savedAt === 'string' ? parsed.savedAt : undefined,
      content: parsed.content,
    };
  } catch {
    return null;
  }
}

function readTrashedStoryLibraryItems(): TrashedStoryLibraryItem[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(storyTrashStorageKey);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.map(toTrashedStoryLibraryItem).filter((item): item is TrashedStoryLibraryItem => Boolean(item));
  } catch {
    return [];
  }
}

function persistTrashedStoryLibraryItems(items: TrashedStoryLibraryItem[]): void {
  if (typeof window === 'undefined') return;
  try {
    if (items.length) {
      window.localStorage.setItem(storyTrashStorageKey, JSON.stringify(items));
    } else {
      window.localStorage.removeItem(storyTrashStorageKey);
    }
  } catch {
    // Best-effort local trash; the visible list still updates from React state.
  }
}

function toTrashedStoryLibraryItem(value: unknown): TrashedStoryLibraryItem | null {
  if (!value || typeof value !== 'object') return null;
  const record = value as Record<string, unknown>;
  if (typeof record.id !== 'string' || !isStoryLibrarySource(record.source)) return null;
  return {
    id: record.id,
    source: record.source,
    title: typeof record.title === 'string' && record.title.trim() ? record.title : 'Untitled story',
    subtitle: typeof record.subtitle === 'string' ? record.subtitle : '',
    content: typeof record.content === 'string' ? record.content : null,
    jobId: typeof record.jobId === 'string' ? record.jobId : null,
    assetId: typeof record.assetId === 'string' ? record.assetId : null,
    trashedAt: typeof record.trashedAt === 'string' ? record.trashedAt : new Date(0).toISOString(),
  };
}

function isStoryLibrarySource(value: unknown): value is StoryLibrarySource {
  return value === 'draft' || value === 'job' || value === 'asset';
}

function upsertTrashedStoryLibraryItem(
  items: TrashedStoryLibraryItem[],
  item: TrashedStoryLibraryItem,
): TrashedStoryLibraryItem[] {
  return [item, ...items.filter((entry) => entry.id !== item.id)];
}

function mergeTrashedStoryLibraryItems(
  trashItems: TrashedStoryLibraryItem[],
  currentItems: StoryLibraryItem[],
): TrashedStoryLibraryItem[] {
  return trashItems.map((trashedItem) => {
    const currentItem = currentItems.find((item) => item.id === trashedItem.id);
    return currentItem ? { ...currentItem, trashedAt: trashedItem.trashedAt } : trashedItem;
  });
}

function readStorySceneAdditions(): StorySceneAddition[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(storySceneAdditionsStorageKey);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.map(toStorySceneAddition).filter((addition): addition is StorySceneAddition => Boolean(addition));
  } catch {
    return [];
  }
}

function persistStorySceneAdditions(additions: StorySceneAddition[]): void {
  if (typeof window === 'undefined') return;
  try {
    if (additions.length) {
      window.localStorage.setItem(storySceneAdditionsStorageKey, JSON.stringify(additions));
    } else {
      window.localStorage.removeItem(storySceneAdditionsStorageKey);
    }
  } catch {
    // Local scene history is best-effort; the active view still updates from React state.
  }
}

function toStorySceneAddition(value: unknown): StorySceneAddition | null {
  if (!value || typeof value !== 'object') return null;
  const record = value as Record<string, unknown>;
  if (
    typeof record.id !== 'string' ||
    typeof record.sourceItemId !== 'string' ||
    typeof record.sourceJobId !== 'string' ||
    typeof record.content !== 'string' ||
    (!record.content.trim() && record.startsNewChapter !== true)
  ) {
    return null;
  }
  return {
    id: record.id,
    sourceItemId: record.sourceItemId,
    sourceJobId: record.sourceJobId,
    chapterNumber: typeof record.chapterNumber === 'number' ? record.chapterNumber : 1,
    sceneNumber: typeof record.sceneNumber === 'number' ? record.sceneNumber : 1,
    title: typeof record.title === 'string' && record.title.trim() ? record.title : 'Continuation',
    chapterTitle: typeof record.chapterTitle === 'string' && record.chapterTitle.trim() ? record.chapterTitle : undefined,
    startsNewChapter: record.startsNewChapter === true,
    content: record.content,
    storyTitle: typeof record.storyTitle === 'string' && record.storyTitle.trim() ? record.storyTitle : null,
    createdAt: typeof record.createdAt === 'string' ? record.createdAt : new Date(0).toISOString(),
  };
}

function isSceneAppendRequest(request: StoryGenerationRequest): boolean {
  return request.action === 'continue' && Boolean(request.sourceLibraryItemId);
}

function isStorySceneAppendJob(job: JobRecord): boolean {
  return jobInputString(job, 'action') === 'continue' && Boolean(jobInputString(job, 'source_library_item_id'));
}

function buildStorySceneAddition(job: JobRecord, request: StoryGenerationRequest): StorySceneAddition | null {
  const sourceItemId = request.sourceLibraryItemId;
  const rawContent = fullJobOutputText(job);
  if (!sourceItemId || !rawContent) return null;
  const storyTitle = cleanStoryTitle(request.values.title) ??
    fullJobOutputTitle(job) ??
    titleFromStoryText(rawContent) ??
    cleanStoryTitle(request.sourceStoryTitle);
  const outline = deriveStoryOutline(request.sourceText, storyTitle ?? request.sourceStoryTitle ?? 'Untitled story');
  const latestChapter = outline[outline.length - 1] ?? { number: 1, scenes: [] };
  const sceneNumber = latestChapter.scenes.filter((scene) => !scene.placeholder).length + 1;
  const normalized = normalizeContinuationSceneContent(rawContent);
  return {
    id: `scene:${sourceItemId}:${job.id}`,
    sourceItemId,
    sourceJobId: job.id,
    chapterNumber: latestChapter.number,
    sceneNumber,
    title: normalized.title ?? sceneTitleFromText(normalized.content) ?? 'Continuation',
    content: normalized.content,
    storyTitle,
    createdAt: new Date().toISOString(),
  };
}

function upsertStorySceneAddition(additions: StorySceneAddition[], addition: StorySceneAddition): StorySceneAddition[] {
  return [...additions.filter((entry) => entry.id !== addition.id), addition];
}

function applyStorySceneAdditions(baseText: string | null, additions: StorySceneAddition[]): string | null {
  if (!additions.length) return baseText;
  return additions
    .slice()
    .sort((left, right) => left.createdAt.localeCompare(right.createdAt))
    .reduce((storyText, addition) => {
      const chapterBlock = addition.startsNewChapter
        ? `Chapter ${addition.chapterNumber}: ${addition.chapterTitle ?? `Chapter ${addition.chapterNumber}`}`
        : null;
      const sceneBlock = [addition.content.trim() || !addition.startsNewChapter ? `Scene ${addition.sceneNumber}: ${addition.title}` : null, addition.content.trim()]
        .filter(Boolean)
        .join('\n\n');
      return [storyText?.trim(), chapterBlock, sceneBlock].filter(Boolean).join('\n\n');
    }, baseText?.trim() ?? '');
}

function latestStoryTitleOverride(additions: StorySceneAddition[]): string | null {
  return additions.slice().reverse().find((addition) => cleanStoryTitle(addition.storyTitle))?.storyTitle ?? null;
}

function normalizeContinuationSceneContent(text: string): { title: string | null; content: string } {
  const lines = text.replace(/\r\n/g, '\n').split('\n');
  while (lines.length && !lines[0].trim()) lines.shift();
  if (lines[0]?.trim().startsWith('# ')) {
    lines.shift();
    while (lines.length && !lines[0].trim()) lines.shift();
  }
  const firstCleaned = lines[0]?.replace(/^#{1,4}\s*/, '').trim() ?? '';
  if (/^chapter\s+\d+/i.test(firstCleaned)) {
    lines.shift();
    while (lines.length && !lines[0].trim()) lines.shift();
  }
  const sceneMatch = lines[0]?.replace(/^#{1,4}\s*/, '').trim().match(/^scene\s+\d+\s*[:\-]?\s*(.*)$/i);
  const title = sceneMatch?.[1]?.trim() || null;
  if (sceneMatch) {
    lines.shift();
    while (lines.length && !lines[0].trim()) lines.shift();
  }
  const content = lines.join('\n').trim() || text.trim();
  return { title: cleanStoryTitle(title), content };
}

function sceneTitleFromText(text: string): string | null {
  const firstParagraph = storyParagraphs(text)[0]?.replace(/^#{1,4}\s*/, '').trim();
  if (!firstParagraph) return null;
  const sentence = firstParagraph.split(/[.!?]/)[0]?.trim();
  return sentence ? truncate(sentence, 48) : null;
}

function libraryJobId(jobId: string): string { return `job:${jobId}`; }
function libraryAssetId(assetId: string): string { return `asset:${assetId}`; }

function jobInputString(job: JobRecord | null, key: string): string | null {
  const input = job?.input_payload;
  if (!input || typeof input !== 'object') return null;
  const value = (input as Record<string, unknown>)[key];
  return typeof value === 'string' && value.trim() ? value : null;
}

function storyAssetTitle(storagePath: string | undefined): string {
  if (!storagePath) return 'Untitled Draft';
  const filename = storagePath.split(/[\\/]/).pop() ?? storagePath;
  return filename.replace(/\.[^.]+$/, '').replace(/[-_]+/g, ' ') || 'Untitled Draft';
}

function storyJobTitle(job: JobRecord): string {
  const text = fullJobOutputText(job);
  return cleanStoryTitle(jobInputString(job, 'title')) ??
    fullJobOutputTitle(job) ??
    titleFromStoryText(text) ??
    'Untitled story';
}

function storyDisplayTitle(title: string | null | undefined, storyText: string | null): string {
  return cleanStoryTitle(title) ?? titleFromStoryText(storyText) ?? 'Untitled story';
}

function shouldGenerateStoryTitle(formTitle: string, displayTitle: string): boolean {
  return !formTitle.trim() && !cleanStoryTitle(displayTitle);
}

function cleanStoryTitle(value: string | null | undefined): string | null {
  const title = value?.trim();
  if (!title || /^untitled story\b/i.test(title)) return null;
  return title;
}

function titleFromStoryText(text: string | null): string | null {
  const heading = text?.split(/\r?\n/).map((line) => line.trim()).find((line) => /^#\s+\S/.test(line));
  return cleanStoryTitle(heading?.replace(/^#\s+/, ''));
}

function providerDisplayName(providers: Array<{ id: string; label: string }>, selectedProviderId: string, fallbackLabel: string | null = null): string {
  return providers.find((provider) => provider.id === selectedProviderId)?.label ?? fallbackLabel ?? 'Omnix LLM';
}

function countWords(text: string): number { return text.trim() ? text.trim().split(/\s+/).length : 0; }
function truncate(text: string, length: number): string { return text.length > length ? `${text.slice(0, length)}…` : text; }

function storyVersionTitle(job: JobRecord, index: number): string {
  return jobInputString(job, 'action') ?? (index === 0 ? 'Just now' : 'Previous');
}

function shortDate(value: string): string {
  return new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function promptTemplateForAction(action: StoryActionMode): string {
  return `storyteller.${action}.v1`;
}

function actionLabel(action: StoryActionMode): string {
  return action === 'dialogue' ? 'polish dialogue' : action;
}

function nextChapterNumber(outline: StoryOutlineChapter[]): number {
  return Math.max(0, ...outline.map((chapter) => chapter.number)) + 1;
}

function deriveStoryOutline(text: string | null, fallbackTitle: string): StoryOutlineChapter[] {
  if (!text?.trim()) {
    return [{ id: 'story-chapter-1', number: 1, label: 'Chapter 1', title: fallbackTitle, scenes: [{ id: 'story-scene-1-1', label: 'Scene 1', title: 'Opening' }] }];
  }
  const chapters: StoryOutlineChapter[] = [];
  let current: StoryOutlineChapter | null = null;
  let sawContentBeforeFirstChapter = false;
  text.split(/\n+/).forEach((line) => {
    const cleaned = line.replace(/^#{1,4}\s*/, '').trim();
    const chapterMatch = cleaned.match(/^chapter\s+(\d+)\s*[:\-–—]?\s*(.*)$/i);
    const sceneMatch = cleaned.match(/^scene\s+(\d+)\s*[:\-–—]?\s*(.*)$/i);
    if (chapterMatch) {
      const number = Number(chapterMatch[1]);
      if (!chapters.length && sawContentBeforeFirstChapter && number !== 1) {
        chapters.push({
          id: 'story-chapter-1',
          number: 1,
          label: 'Chapter 1',
          title: fallbackTitle,
          scenes: [{ id: 'story-scene-1-1', label: 'Scene 1', title: 'Opening' }],
        });
      }
      current = {
        id: `story-chapter-${number}`,
        number,
        label: `Chapter ${number}`,
        title: chapterMatch[2]?.trim() || `Chapter ${number}`,
        scenes: [],
      };
      chapters.push(current);
      return;
    }
    if (cleaned && !current && !chapters.length && !sceneMatch) {
      sawContentBeforeFirstChapter = true;
    }
    if (sceneMatch && !current) {
      current = {
        id: 'story-chapter-1',
        number: 1,
        label: 'Chapter 1',
        title: fallbackTitle,
        scenes: [],
      };
      chapters.push(current);
    }
    if (sceneMatch && current) {
      const sceneNumber = Number(sceneMatch[1]);
      current.scenes.push({
        id: `story-scene-${current.number}-${sceneNumber}`,
        label: `Scene ${sceneNumber}`,
        title: sceneMatch[2]?.trim() || `Scene ${sceneNumber}`,
      });
    }
  });
  if (!chapters.length) {
    chapters.push({
      id: 'story-chapter-1',
      number: 1,
      label: 'Chapter 1',
      title: fallbackTitle,
      scenes: [{ id: 'story-scene-1-1', label: 'Scene 1', title: 'Opening' }],
    });
  }
  return chapters.map((chapter) => ({
    ...chapter,
    scenes: chapter.scenes.length ? chapter.scenes : [{ id: `story-scene-${chapter.number}-1`, label: 'Scene 1', title: 'Opening', placeholder: true }],
  }));
}

function storyTextBlocks(text: string, outline: StoryOutlineChapter[]): StoryTextBlock[] {
  let chapterIndex = 0;
  const sceneIndexByChapter = new Map<number, number>();
  return text.split(/\n{2,}|\r?\n/).map((raw) => raw.trim()).filter(Boolean).map((line) => {
    const cleaned = line.replace(/^#{1,4}\s*/, '').trim();
    const chapterMatch = cleaned.match(/^chapter\s+(\d+)\s*[:\-–—]?\s*(.*)$/i);
    const sceneMatch = cleaned.match(/^scene\s+(\d+)\s*[:\-–—]?\s*(.*)$/i);
    if (chapterMatch) {
      const number = Number(chapterMatch[1]) || ++chapterIndex;
      chapterIndex = number;
      return { kind: 'chapter', id: `story-chapter-${number}`, text: chapterMatch[2]?.trim() || `Chapter ${number}` };
    }
    if (sceneMatch) {
      const activeChapter = outline[Math.max(0, chapterIndex - 1)] ?? outline[0];
      const chapterNumber = activeChapter?.number ?? 1;
      const sceneNumber = Number(sceneMatch[1]) || (sceneIndexByChapter.get(chapterNumber) ?? 0) + 1;
      sceneIndexByChapter.set(chapterNumber, sceneNumber);
      return { kind: 'scene', id: `story-scene-${chapterNumber}-${sceneNumber}`, text: sceneMatch[2]?.trim() || `Scene ${sceneNumber}` };
    }
    return { kind: 'paragraph', text: cleaned };
  });
}

function storyParagraphs(text: string): string[] {
  return text.split(/\n{2,}/).map((paragraph) => paragraph.trim()).filter(Boolean);
}

function lastStoryPage(text: string): string {
  const chunks = storyParagraphs(text);
  return chunks.slice(Math.max(0, chunks.length - 5)).join('\n\n');
}

function suggestedStoryMoves(text: string | null, title: string): string[] {
  if (!text) {
    return ['Begin the story quietly', 'Open with a mystery', 'Introduce the main character'];
  }
  const lower = `${title} ${text}`.toLowerCase();
  if (lower.includes('door')) return ['Open the door carefully', 'Listen before entering', 'Mark the doorway and leave'];
  if (lower.includes('cat')) return ['Follow the cat', 'Offer the cat food', 'Ask why the cat is watching'];
  return ['Investigate the strange clue', 'Ask who is watching', 'Leave quietly before it notices'];
}

function storyModeContext(activeStoryText: string | null, response: string): string {
  return [activeStoryText, `Player response: ${response}`].filter(Boolean).join('\n\n');
}

function formatStoryMarkdown({ title, premise, providerLabel, wordCount, chapterCount, sourceJobId, text }: {
  title: string;
  premise: string;
  providerLabel: string;
  wordCount: number;
  chapterCount: number;
  sourceJobId: string | null;
  text: string;
}): string {
  return [
    `# ${title}`,
    '',
    `- Provider: ${providerLabel}`,
    `- Words: ${wordCount}`,
    `- Chapters: ${chapterCount}`,
    sourceJobId ? `- Source job: ${sourceJobId}` : null,
    premise ? `- Premise: ${premise}` : null,
    '',
    '---',
    '',
    text,
    '',
  ].filter((line) => line !== null).join('\n');
}

function slugify(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'story';
}
