import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { omnixApiClient } from '../../api/client';
import {
  type StoryBlock, type StoryCharacterInput, type StoryNoteInput, type StoryOutlineChapterInput, type StoryProject, type StoryProjectSummary,
  storyApiClient,
} from './api/storyClient';
import { importLegacyStories, storyImportDone } from './storyImport';
import { libraryEntry } from './storyProjectModel';

export const storyProjectKeys = {
  all: ['story', 'projects'] as const,
  list: (trashed: boolean) => ['story', 'projects', 'list', trashed ? 'trash' : 'live'] as const,
  detail: (projectId: string) => ['story', 'projects', 'detail', projectId] as const,
};
const noSummaries: StoryProjectSummary[] = [];

/**
 * The account's story projects (ST-1.2): the library, the trash, the project being read, and the one-time
 * import of what the browser held before (ST-1.4).
 */
export function useStoryProjects() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [isNewDraft, setIsNewDraft] = useState(false);
  const listQuery = useQuery({ queryKey: storyProjectKeys.list(false), queryFn: () => storyApiClient.listProjects(false) });
  const trashQuery = useQuery({ queryKey: storyProjectKeys.list(true), queryFn: () => storyApiClient.listProjects(true) });
  const legacyImport = useLegacyImport(listQuery.data, trashQuery.data);

  const entries = useMemo(() => (listQuery.data ?? []).map(libraryEntry), [listQuery.data]);
  const trashEntries = useMemo(() => (trashQuery.data ?? []).map(libraryEntry), [trashQuery.data]);
  const activeId = isNewDraft ? null : selectedId ?? entries[0]?.id ?? null;
  const projectQuery = useQuery({
    queryKey: storyProjectKeys.detail(activeId ?? ''),
    queryFn: () => storyApiClient.getProject(activeId ?? ''),
    enabled: Boolean(activeId),
  });
  const project = activeId && projectQuery.data?.id === activeId ? projectQuery.data : null;

  const refresh = () => queryClient.invalidateQueries({ queryKey: storyProjectKeys.all });
  const select = (projectId: string | null) => {
    setIsNewDraft(projectId === null);
    setSelectedId(projectId);
  };
  /** The project a call changed, shown at once and then refetched with the lists. */
  const applied = async (changed: StoryProject) => {
    queryClient.setQueryData(storyProjectKeys.detail(changed.id), changed);
    await refresh();
    return changed;
  };
  // A project's updates go one at a time, so a quick run of them (a speed slider) lands in the order sent.
  const updates = useRef(new Map<string, Promise<unknown>>());

  return {
    entries,
    /** The live stories as listed, for the library view. */
    summaries: listQuery.data ?? noSummaries,
    trashEntries,
    project,
    activeId,
    isNewDraft,
    isLoading: projectQuery.isLoading && Boolean(activeId),
    error: listQuery.error ?? trashQuery.error ?? projectQuery.error ?? legacyImport.error,
    select,
    refresh,
    trash: async (projectId: string) => {
      await storyApiClient.trashProject(projectId);
      if (projectId === activeId) setSelectedId(null);
      await refresh();
    },
    restore: async (projectId: string) => applied(await storyApiClient.restoreProject(projectId)),
    purge: async (projectId: string) => {
      await storyApiClient.purgeProject(projectId);
      queryClient.removeQueries({ queryKey: storyProjectKeys.detail(projectId) });
      await refresh();
    },
    saveVersion: async (projectId: string) => applied(await storyApiClient.saveVersion(projectId)),
    /** "Keep this run": the interactive run as it stands, kept as a finished story (ST-3.6). */
    keepRun: async (projectId: string, title: string) =>
      applied(await storyApiClient.saveVersion(projectId, title, 'kept_run')),
    undoMove: async (projectId: string) => applied(await storyApiClient.undoMove(projectId)),
    openPage: async (projectId: string, pageId: string) => applied(await storyApiClient.openPage(projectId, pageId)),
    /** A page as the writer edited it (ST-6.1). */
    updatePage: async (projectId: string, pageId: string, blocks: StoryBlock[], baseBlocks: StoryBlock[]) =>
      applied(await storyApiClient.updatePage(projectId, pageId, blocks, baseBlocks)),
    /** The writer's answer to a proposed selection change (ST-6.2). */
    acceptSelection: async (projectId: string, versionId: string) =>
      applied(await storyApiClient.acceptSelection(projectId, versionId)),
    rejectSelection: async (projectId: string, versionId: string) =>
      applied(await storyApiClient.rejectSelection(projectId, versionId)),
    restoreVersion: async (projectId: string, versionId: string) =>
      applied(await storyApiClient.restoreVersion(projectId, versionId)),
    /** Shown at once, so a second change made before the first returns builds on it. */
    update: async (projectId: string, body: Parameters<typeof storyApiClient.updateProject>[1]) => {
      queryClient.setQueryData<StoryProject>(storyProjectKeys.detail(projectId), (current) =>
        (current ? { ...current, ...body } as StoryProject : current));
      const previous = updates.current.get(projectId) ?? Promise.resolve();
      const sent = previous.catch(() => undefined).then(() => storyApiClient.updateProject(projectId, body));
      updates.current.set(projectId, sent);
      try {
        const changed = await sent;
        // A later update already queued for this project has the newer state; its reply is applied instead.
        if (updates.current.get(projectId) !== sent) return changed;
        return await applied(changed);
      } catch (error) {
        // The change did not take: read the project again, so the screen does not keep showing it.
        void queryClient.invalidateQueries({ queryKey: storyProjectKeys.detail(projectId) });
        throw error;
      }
    },
    /** The whole cast, as the writer left it: accepted characters and the suggestions still waiting. */
    replaceCharacters: async (projectId: string, characters: StoryCharacterInput[]) =>
      applied(await storyApiClient.replaceCharacters(projectId, characters)),
    replaceNotes: async (projectId: string, notes: StoryNoteInput[]) =>
      applied(await storyApiClient.replaceNotes(projectId, notes)),
    /** The plan as the writer left it (ST-5.1). */
    replaceOutline: async (projectId: string, chapters: StoryOutlineChapterInput[]) =>
      applied(await storyApiClient.replaceOutline(projectId, chapters)),
    /** A project a job just made: select it before the list knows it. */
    adopt: (projectId: string) => {
      setIsNewDraft(false);
      setSelectedId(projectId);
    },
  };
}

/** Runs the legacy import once both project lists have loaded, then refreshes them. */
function useLegacyImport(live: StoryProjectSummary[] | undefined, trashed: StoryProjectSummary[] | undefined) {
  const queryClient = useQueryClient();
  const [pending] = useState(() => !storyImportDone());
  const started = useRef(false);
  const [error, setError] = useState<Error | null>(null);
  const jobsQuery = useQuery({
    queryKey: ['story', 'legacy-import', 'jobs'],
    queryFn: () => omnixApiClient.listJobs({ module: 'storyteller', type: 'story.generate', full: true }),
    enabled: pending,
  });
  const assetsQuery = useQuery({
    queryKey: ['story', 'legacy-import', 'assets'],
    queryFn: () => omnixApiClient.listAssets(),
    enabled: pending,
  });
  useEffect(() => {
    if (!pending || started.current || !live || !trashed || !jobsQuery.data || !assetsQuery.data) return;
    started.current = true;
    const known = [...live, ...trashed];
    void importLegacyStories({ jobs: jobsQuery.data.jobs, assets: assetsQuery.data.assets, known })
      .then((created) => (created ? queryClient.invalidateQueries({ queryKey: storyProjectKeys.all }) : undefined))
      .catch((caught: unknown) => {
        // Nothing was marked done, so the next visit tries again.
        setError(caught instanceof Error ? caught : new Error('Your earlier stories could not be imported.'));
      });
  }, [pending, live, trashed, jobsQuery.data, assetsQuery.data, queryClient]);
  return { error: error ?? jobsQuery.error ?? assetsQuery.error };
}
