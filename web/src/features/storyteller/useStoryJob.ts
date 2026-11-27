/**
 * The story job: starting it (with a project to write into) and following it until it settles (ST-1.3).
 * It is followed on the shared `/events` stream, and polled only while that stream is not open (ST-3.5).
 */
import { useMutation, useQueries, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { omnixApiClient } from '../../api/client';
import { isJobSettled, jobKeys } from '../../api/jobs';
import { useJobEventRefresh, useJobEventsOpen } from '../../events/useJobEvents';
import { POLL_INTERVALS_MS } from '../../shared/timers';
import { storyApiClient } from './api/storyClient';
import { SaveFeedback, StoryActionMode, StoryGenerationRequest, StoryGenerationResult, StoryJobSettings, storyJobRequest } from './storyModel';
import { storyProjectKeys } from './useStoryProjects';

/** A job being watched: the project it writes into and what it was asked to do, so its result can be described. */
type TrackedJob = { jobId: string; projectId: string; action: StoryActionMode; newChapter: boolean; selection: boolean };

const versionActionLabels: Partial<Record<StoryActionMode, string>> = {
  rewrite: 'The rewrite',
  expand: 'The expanded story',
  dialogue: 'The dialogue polish',
  summarize: 'The summary',
};

/** The story's own failure codes, in the writer's words. */
const failureMessages: Record<string, string> = {
  story_selection_page_changed: 'The page changed after that passage was selected. Select it again and retry.',
  story_selection_page_not_found: 'The page with that passage is no longer in the story.',
  story_selection_invalid: 'That passage could not be reworked. Select it again and retry.',
  story_beat_not_found: 'That beat is no longer in the plan.',
  story_project_not_found: 'The story is no longer there.',
  story_project_in_trash: 'The story is in the trash. Restore it to write in it.',
};

/** A job's failure as the writer reads it: a known code is explained, and an unknown bare code is not shown raw. */
export function jobFailureMessage(error?: string): string {
  if (!error) return 'The story job did not finish.';
  return failureMessages[error] ?? (/^[a-z]+(?:_[a-z]+)+$/.test(error) ? 'The story job did not finish.' : error);
}

/** What a settled job did, in the writer's words; null when the manuscript itself shows it. */
export function settledJobFeedback(action: StoryActionMode, newChapter: boolean, status: string, error?: string, selection = false): SaveFeedback | null {
  if (status !== 'completed') return { kind: 'error', message: jobFailureMessage(error) };
  if (action === 'outline') return { kind: 'saved', message: 'The plan is ready: edit it, then draft it beat by beat.' };
  if (selection) return { kind: 'saved', message: 'The proposed change is ready: accept or reject it above the manuscript.' };
  const versionLabel = versionActionLabels[action];
  if (versionLabel) return { kind: 'saved', message: `${versionLabel} was saved as a new version; restore it from Story versions to use it.` };
  return newChapter ? { kind: 'saved', message: 'Added a new chapter.' } : null;
}

/**
 * Starts story jobs and follows each until it settles. Every job is followed, so starting a second one, or
 * opening another story, does not lose the first: its project is refreshed when it settles, and the writer
 * hears how it went while that story is open. The workspace shows the open story's latest job.
 */
export function useStoryJob({ projectId, settings, onStarted, onFeedback }: {
  /** The story open in the workspace. */
  projectId: string | null;
  settings: StoryJobSettings;
  /** Called once the job exists, with the project it writes into, unless another story was opened meanwhile. */
  onStarted: (request: StoryGenerationRequest, projectId: string) => void;
  onFeedback: (feedback: SaveFeedback) => void;
}) {
  const queryClient = useQueryClient();
  const [tracked, setTracked] = useState<TrackedJob[]>([]);
  const openProject = useRef(projectId);
  useEffect(() => { openProject.current = projectId; }, [projectId]);
  const reported = useRef(new Set<string>());

  const createJobMutation = useMutation<StoryGenerationResult, Error, StoryGenerationRequest>({
    mutationFn: async (request) => {
      // A request with no project starts one; the job then writes its first page into it.
      const created = request.projectId ? null : await storyApiClient.createProject({
        title: request.values.title,
        premise: request.values.premise,
        mode: request.interactionMode === 'story' ? 'interactive' : 'writing',
        tone: settings.tone,
        writing_style: settings.writingStyle,
      });
      const target = request.projectId ?? created?.id ?? '';
      try {
        const job = await omnixApiClient.createJob(storyJobRequest({ ...request, projectId: target }, settings));
        return { job, projectId: target };
      } catch (error) {
        // The story was made but its first job was not: list it, so it is not left out of sight.
        if (created) void queryClient.invalidateQueries({ queryKey: storyProjectKeys.all });
        throw error;
      }
    },
    onSuccess: async ({ job, projectId: target }, request) => {
      queryClient.setQueryData(jobKeys.detail(job.id), job);
      const next = { jobId: job.id, projectId: target, action: request.action, newChapter: Boolean(request.newChapter), selection: Boolean(request.selection) };
      // Jobs already settled and reported are let go; the rest are still followed.
      setTracked((jobs) => [...jobs.filter((item) => !reported.current.has(item.jobId)), next]);
      if (!request.projectId || request.projectId === openProject.current) onStarted(request, target);
      await queryClient.invalidateQueries({ queryKey: storyProjectKeys.all });
      await queryClient.invalidateQueries({ queryKey: jobKeys.all });
    },
  });

  const jobEventsOpen = useJobEventsOpen();
  const jobQueries = useQueries({
    queries: tracked.map((item) => ({
      queryKey: jobKeys.detail(item.jobId),
      queryFn: () => omnixApiClient.getJob(item.jobId),
      refetchInterval: (query: { state: { data?: { status: string } } }) => (
        (query.state.data && isJobSettled(query.state.data.status)) || jobEventsOpen ? false : POLL_INTERVALS_MS.jobWithoutEvents
      ),
    })),
  });
  const jobs = tracked.map((item, index) => {
    const data = jobQueries[index]?.data;
    return { item, job: data?.id === item.jobId ? data : undefined };
  });
  const runningKey = jobs.filter(({ job }) => !job || !isJobSettled(job.status)).map(({ item }) => item.jobId).join(',');
  const running = useMemo(() => (runningKey ? runningKey.split(',') : []), [runningKey]);
  const jobQueryKeys = useMemo(() => running.map((id) => jobKeys.detail(id)), [running]);
  // One running job is followed by its id; several by every job event, each refreshing only these jobs.
  useJobEventRefresh(jobQueryKeys, { jobId: running.length === 1 ? running[0] : null, enabled: running.length > 0 });
  // Read a new job once more now that its events are followed, in case one arrived before they were.
  const newest = tracked.at(-1)?.jobId;
  useEffect(() => {
    if (newest) void queryClient.invalidateQueries({ queryKey: jobKeys.detail(newest) });
  }, [newest, queryClient]);

  const latestJobs = useRef(jobs);
  useEffect(() => { latestJobs.current = jobs; });
  const settledKey = jobs.filter(({ job }) => job && isJobSettled(job.status)).map(({ item }) => item.jobId).join(',');
  useEffect(() => {
    for (const { item, job } of latestJobs.current) {
      if (!job || !isJobSettled(job.status) || reported.current.has(item.jobId)) continue;
      reported.current.add(item.jobId);
      void queryClient.invalidateQueries({ queryKey: storyProjectKeys.all });
      // How a job went is told while its story is open; another story's job only refreshes the library.
      if (item.projectId !== openProject.current) continue;
      const feedback = settledJobFeedback(item.action, item.newChapter, job.status, job.error?.message, item.selection);
      if (feedback) onFeedback(feedback);
    }
  }, [settledKey, queryClient, onFeedback]);

  const current = projectId ? jobs.filter(({ item }) => item.projectId === projectId).at(-1) : undefined;
  return { createJobMutation, trackedJob: current?.job ?? null };
}
