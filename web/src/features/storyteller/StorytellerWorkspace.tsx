import './StorytellerWorkspace.css';
import './StorytellerSidebar.css';
import './StoryMode.css';
import './StoryThemeThumbnails.css';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { omnixApiClient } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { WorkspacePanel } from '../../design/primitives';
import { GatewayErrorNotice } from '../../shared/GatewayErrorNotice';
import type { StoryProject } from './api/storyClient';
import { StoryCharactersPanel, StoryWorldPanel } from './StoryBible';
import { StoryControls } from './StoryControls';
import { StoryLibrary } from './StoryLibrary';
import { StoryCompare } from './StoryCompare';
import { StoryManuscript } from './StoryManuscript';
import { ManuscriptHeading, StoryActionBar, StoryEmptyState, StoryModeSwitch, StoryOutline, StoryVersions } from './StoryPanels';
import {
  SaveFeedback, StoryLibrarySection, StoryWorkspaceMode,
  StorytellerFormValues, countWords, llmCapableProviders, providerDisplayName, storyDisplayTitle, styleOptions,
} from './storyModel';
import { manuscriptItems, manuscriptText, projectWordCount, visiblePages } from './storyProjectModel';
import { StoryReadPanel } from './StoryReadPanel';
import { StoryModePanel } from './StoryRunReader';
import { StoryPlanPanel } from './StoryPlanPanel';
import { type StorySideTab, StorySidePanel } from './StorySidePanel';
import { StoryTopBar } from './StoryTopBar';
import { deriveStoryOutline } from './storyTextModel';
import { StoryVoicesPanel } from './StoryVoicesPanel';
import { useStoryExport } from './useStoryExport';
import { useStoryJob } from './useStoryJob';
import { useStoryLibraryActions } from './useStoryLibraryActions';
import { useStoryProjects } from './useStoryProjects';
import { useStoryRequests } from './useStoryRequests';
import { useNarrateInAudiobook } from './useNarrateInAudiobook';

export function StorytellerWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const projects = useStoryProjects();
  const project = projects.project;
  const [workspaceMode, setWorkspaceMode] = useState<StoryWorkspaceMode>('writing');
  const [activeLibrarySection, setActiveLibrarySection] = useState<StoryLibrarySection>('stories');
  const [selectedTone, setSelectedTone] = useState('Cozy');
  const [writingStyle, setWritingStyle] = useState(styleOptions[0]);
  const [selectedChapter, setSelectedChapter] = useState(1);
  const [saveFeedback, setSaveFeedback] = useState<SaveFeedback | null>(null);
  const [storyModeResponse, setStoryModeResponse] = useState('');
  const [sideTab, setSideTab] = useState<StorySideTab>('write');
  const [comparingId, setComparingId] = useState<string | null>(null);

  const providersQuery = useQuery({ queryKey: ['platform', 'providers'], queryFn: () => omnixApiClient.listProviders() });
  const { register, handleSubmit, reset, watch, formState: { errors } } = useForm<StorytellerFormValues>({
    defaultValues: { providerId: '', title: '', premise: '' },
  });

  const { createJobMutation, trackedJob } = useStoryJob({
    projectId: projects.activeId,
    settings: { tone: selectedTone, writingStyle, chapter: selectedChapter },
    onStarted: (request, projectId) => {
      if (request.action === 'draft') reset(request.values);
      projects.adopt(projectId);
      if (request.interactionMode === 'story') {
        setStoryModeResponse('');
        setWorkspaceMode('story');
        setActiveLibrarySection('interactive');
      } else if (!request.projectId) {
        setActiveLibrarySection('stories');
      }
    },
    onFeedback: setSaveFeedback,
  });

  const [watchedTitle, watchedPremise, watchedProvider] = watch(['title', 'premise', 'providerId']);
  const storyProviders = useMemo(() => llmCapableProviders(providersQuery.data), [providersQuery.data]);
  const items = useMemo(() => manuscriptItems(project), [project]);
  const manuscript = useMemo(() => manuscriptText(items), [items]);
  const storyTitle = storyDisplayTitle(project ? project.title : watchedTitle, manuscript);
  const premise = project?.premise ?? watchedPremise ?? '';
  const providerLabel = providerDisplayName(storyProviders, watchedProvider);
  const outline = useMemo(() => deriveStoryOutline(manuscript, storyTitle), [manuscript, storyTitle]);
  const activeChapter = outline.find((chapter) => chapter.number === selectedChapter) ?? outline[0] ?? null;
  const chapterCount = outline.length || 1;
  const wordCount = project ? projectWordCount(project) : countWords(watchedPremise ?? '');
  const readingMinutes = Math.max(1, Math.ceil(wordCount / 220));
  const submitStatus = createJobMutation.isPending
    ? 'queueing'
    : createJobMutation.isError
      ? 'error'
      : trackedJob?.status ?? 'ready';
  const canPersistStory = Boolean(manuscript?.trim());
  const requests = useStoryRequests({
    createJobMutation,
    watched: { premise: watchedPremise, providerId: watchedProvider, title: watchedTitle },
    project,
    hasText: canPersistStory,
    setSaveFeedback,
  });
  const library = useStoryLibraryActions({ projects, storyTitle, setSaveFeedback, setActiveLibrarySection });
  /** The tone and style a preset gave the story (ST-5.2). */
  const applyStyle = (changed: StoryProject) => {
    if (changed.tone) setSelectedTone(changed.tone);
    if (changed.writing_style) setWritingStyle(changed.writing_style);
  };

  // A story opens in the mode it was written in, with its own tone and style. Only when another project
  // opens: a refetch of the same one keeps the writer's choices.
  const openedProjectId = useRef<string | null>(null);
  useEffect(() => {
    if (!project || openedProjectId.current === project.id) return;
    openedProjectId.current = project.id;
    setWorkspaceMode(project.mode === 'interactive' ? 'story' : 'writing');
    if (project.tone) setSelectedTone(project.tone);
    if (project.writing_style) setWritingStyle(project.writing_style);
  }, [project]);

  useEffect(() => {
    if (outline.length && !outline.some((chapter) => chapter.number === selectedChapter)) {
      setSelectedChapter(outline[0].number);
    }
  }, [outline, selectedChapter]);

  const narrate = useNarrateInAudiobook();
  const selectEntry = (projectId: string) => {
    const entry = projects.entries.find((candidate) => candidate.id === projectId);
    projects.select(projectId);
    setSelectedChapter(1);
    setSaveFeedback(null);
    if (entry) setActiveLibrarySection(library.sectionFor(entry));
  };

  const startNewDraft = () => {
    reset({ providerId: watchedProvider, title: '', premise: '' });
    projects.select(null);
    openedProjectId.current = null;
    setActiveLibrarySection('stories');
    setSelectedChapter(1);
    setWorkspaceMode('writing');
    setSaveFeedback({ kind: 'saved', message: 'New draft ready. Add a premise to begin.' });
  };

  const exportStory = useStoryExport({
    project, items, title: storyTitle, premise, providerLabel, wordCount, chapterCount, setSaveFeedback,
  });

  const comparing = project?.versions.find((version) => version.id === comparingId) ?? null;
  const selectOutlineTarget = (chapterNumber: number, targetId: string) => {
    setSelectedChapter(chapterNumber);
    scrollToOutlineTarget(chapterNumber, targetId);
  };

  return (
    <WorkspacePanel labelledBy="module-title">
      <h2 id="module-title" className="workspace-module-heading">{module.label}</h2>
      <div className="storyteller-workspace" aria-labelledby="module-title">
        <StoryLibrary
          activeId={projects.activeId}
          activeSection={activeLibrarySection}
          entries={projects.entries}
          onNewDraft={startNewDraft}
          onPurge={library.purgeEntry}
          onRestore={library.restoreEntry}
          onSectionChange={setActiveLibrarySection}
          onSelect={selectEntry}
          onShowTrash={() => setActiveLibrarySection('trash')}
          trashEntries={projects.trashEntries}
        />
        <main className="storyteller-stage">
          <GatewayErrorNotice label="Stories and providers" errors={[projects.error, providersQuery.error]} />
          <StoryTopBar
            canPersistStory={canPersistStory}
            canTrash={Boolean(project)}
            chapterCount={chapterCount}
            onExport={(format) => void exportStory(format)}
            onNarrate={() => project && library.run(() => narrate(project, visiblePages(project), { title: storyTitle }))}
            onSave={library.saveVersion}
            onTrash={library.trashActiveStory}
            premise={premise}
            providerLabel={providerLabel}
            saveFeedback={saveFeedback}
            title={storyTitle}
            wordCount={wordCount}
          />
          <StoryModeSwitch mode={workspaceMode} onChange={setWorkspaceMode} />
          {workspaceMode === 'story' ? (
            <StoryModePanel
              activeChapterLabel={activeChapter?.label ?? `Chapter ${selectedChapter}`}
              isLoading={projects.isLoading}
              job={trackedJob}
              library={projects}
              module={module}
              onMove={requests.submitStoryModeMove}
              pending={createJobMutation.isPending}
              project={project}
              narrate={narrate}
              report={library.run}
              response={storyModeResponse}
              setResponse={setStoryModeResponse}
              storyTitle={storyTitle}
            />
          ) : project && comparing ? (
            <StoryCompare
              disabled={createJobMutation.isPending}
              onClose={() => setComparingId(null)}
              onRestore={(version) => { setComparingId(null); library.restoreVersion(version); }}
              project={project}
              version={comparing}
            />
          ) : (
            <section className="storyteller-manuscript" aria-label="Story manuscript">
              {project && manuscript ? (
                <StoryManuscript
                  disabled={createJobMutation.isPending}
                  items={items}
                  key={project.id}
                  onAccept={library.acceptSelection}
                  onReject={library.rejectSelection}
                  onRework={requests.reworkSelection}
                  onSavePage={library.savePage}
                  project={project}
                >
                  <ManuscriptHeading chapter={activeChapter?.label ?? `Chapter ${selectedChapter}`} minutes={readingMinutes} title={activeChapter?.title ?? storyTitle} />
                </StoryManuscript>
              ) : (
                <>
                  <ManuscriptHeading chapter={activeChapter?.label ?? `Chapter ${selectedChapter}`} minutes={readingMinutes} title={activeChapter?.title ?? storyTitle} />
                  <StoryEmptyState isLoading={projects.isLoading} module={module} />
                </>
              )}
            </section>
          )}
        </main>
        <StorySidePanel
          active={sideTab}
          badges={{ characters: project?.characters.filter((character) => character.suggested).length }}
          onChange={setSideTab}
          panels={{
            write: (
              <>
                {workspaceMode === 'writing' ? (
                  <>
                    <StoryControls
                      createJobMutation={createJobMutation}
                      errors={errors}
                      handleSubmit={handleSubmit}
                      latestJob={trackedJob}
                      onAddChapter={requests.addChapterToActiveStory}
                      onGenerate={requests.submitDraft}
                      premiseLength={(watchedPremise ?? '').length}
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
                    <StoryActionBar disabled={createJobMutation.isPending} onAction={requests.submitQuickAction} />
                  </>
                ) : null}
                <StoryOutline chapters={outline} disabled={createJobMutation.isPending} selectedChapter={selectedChapter} onAddChapter={requests.addChapterToActiveStory} onSelect={selectOutlineTarget} />
                {workspaceMode === 'writing' ? (
                  <StoryPlanPanel
                    onDraftBeat={requests.draftBeat}
                    onFeedback={setSaveFeedback}
                    onPlan={requests.planStory}
                    pending={createJobMutation.isPending}
                    project={project}
                    saveOutline={projects.replaceOutline}
                  />
                ) : null}
                <StoryVersions disabled={createJobMutation.isPending} onCompare={(version) => setComparingId(version.id)} onRestore={library.restoreVersion} versions={project?.versions ?? []} />
              </>
            ),
            characters: <StoryCharactersPanel onFeedback={setSaveFeedback} project={project} replaceCharacters={projects.replaceCharacters} />,
            world: (
              <StoryWorldPanel
                choosePreset={async (projectId, presetId) => applyStyle(await library.choosePreset(projectId, presetId))}
                onFeedback={setSaveFeedback}
                project={project}
                replaceNotes={projects.replaceNotes}
              />
            ),
            audio: (
              <>
                <StoryVoicesPanel project={project} />
                <StoryReadPanel project={project} onChange={library.updateReadSettings} />
              </>
            ),
          }}
        />
      </div>
    </WorkspacePanel>
  );
}

/** Scrolls the manuscript to an outline entry, or its chapter, or the manuscript itself. */
function scrollToOutlineTarget(chapterNumber: number, targetId: string): void {
  const target = (document.getElementById(targetId) ??
    document.getElementById(`story-chapter-${chapterNumber}`) ??
    document.querySelector('[aria-label="Story manuscript"]')) as
    | (HTMLElement & { scrollIntoView?: (options?: ScrollIntoViewOptions) => void })
    | null;
  target?.scrollIntoView?.({ block: 'start', behavior: 'smooth' });
}
