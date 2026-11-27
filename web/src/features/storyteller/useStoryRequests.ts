import type { UseMutationResult } from '@tanstack/react-query';
import type { StoryProject } from './api/storyClient';
import {
  SaveFeedback, StoryActionMode, StoryGenerationRequest, StoryGenerationResult, StoryQuickActionMode, StorySelectionAction,
  StorySelectionRange, StorytellerFormValues, premiseMaxChars,
} from './storyModel';

type StoryRequestsOptions = {
  createJobMutation: UseMutationResult<StoryGenerationResult, Error, StoryGenerationRequest>;
  watched: { premise: string; providerId: string; title?: string };
  project: StoryProject | null;
  hasText: boolean;
  setSaveFeedback: (feedback: SaveFeedback | null) => void;
};

/**
 * What the writer asks for: a draft (a new project), a quick action on the project, a player's move,
 * or a new chapter. The job reads the story from its project, so a request names the project, not the text.
 */
export function useStoryRequests({
  createJobMutation,
  watched: { premise: watchedPremise, providerId: watchedProvider, title: watchedTitle = '' },
  project,
  hasText,
  setSaveFeedback,
}: StoryRequestsOptions) {
  const followUpValues = (): StorytellerFormValues => ({
    providerId: watchedProvider,
    // The job keeps the project's title; a follow-up never renames it.
    title: '',
    // A story written before the cap can hold a longer premise; the request carries the capped part.
    premise: (project?.premise || watchedPremise || 'Continue this story.').slice(0, premiseMaxChars),
  });

  const submitDraft = (values: StorytellerFormValues) => {
    setSaveFeedback(null);
    createJobMutation.mutate({ values, action: 'draft', projectId: null, interactionMode: 'writing' });
  };

  const submitFollowUp = (action: Exclude<StoryActionMode, 'draft'>, extra: Partial<StoryGenerationRequest> = {}) => {
    setSaveFeedback(null);
    createJobMutation.mutate({ values: followUpValues(), action, projectId: project?.id ?? null, interactionMode: 'writing', ...extra });
  };

  const submitQuickAction = (action: StoryQuickActionMode) => {
    if (!project || !hasText) {
      setSaveFeedback({ kind: 'error', message: 'Select or generate a story before using quick actions.' });
      return;
    }
    submitFollowUp(action);
  };

  /** Reworks a selection of one page, or a whole page; the result waits as a proposal (ST-6.2). */
  const reworkSelection = (action: StorySelectionAction, selection: StorySelectionRange) => {
    if (!project) return;
    submitFollowUp(action, { selection });
  };

  /** A player's move; with no story selected it begins a new interactive one. */
  const submitStoryModeMove = (moveText: string, { suggested = false }: { suggested?: boolean } = {}) => {
    const response = moveText.trim();
    if (!response) return;
    submitFollowUp('continue', {
      interactionMode: 'story',
      userResponse: response,
      chosenSuggestion: suggested ? response : null,
    });
  };

  const addChapterToActiveStory = () => {
    if (!project || !hasText) {
      setSaveFeedback({ kind: 'error', message: 'Select or generate a story before adding a chapter.' });
      return;
    }
    submitFollowUp('continue', { newChapter: true });
  };

  /** Plans the story as chapters of beats (ST-5.1); with no story selected it plans a new one from the premise. */
  const planStory = (chapters: number) => {
    const premise = (project?.premise || watchedPremise || '').trim();
    if (!premise) {
      setSaveFeedback({ kind: 'error', message: 'Write a premise before planning the story.' });
      return;
    }
    setSaveFeedback(null);
    createJobMutation.mutate({
      values: { providerId: watchedProvider, title: project ? '' : watchedTitle, premise: premise.slice(0, premiseMaxChars) },
      action: 'outline', projectId: project?.id ?? null, interactionMode: 'writing', outlineChapters: chapters,
    });
  };

  /** Drafts one beat of the plan into its chapter; the first beat drafted opens the story. */
  const draftBeat = (beatId: string) => {
    if (!project) return;
    submitFollowUp('continue', { beatId });
  };

  return { submitDraft, submitQuickAction, submitStoryModeMove, addChapterToActiveStory, planStory, draftBeat, reworkSelection };
}
