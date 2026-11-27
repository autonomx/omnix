import { useRouter, type AnyRouter } from '@tanstack/react-router';
import { useCallback } from 'react';
import { audiobookProjectHref, importStoryToAudiobook } from '../audiobook';
import type { StoryPage, StoryProject } from './api/storyClient';
import { storyAudiobookImport } from './storyAudiobook';

/** Hands these pages of a story to Audiobook and opens the book they became; nothing to report once it opens. */
export type NarrateInAudiobook = (
  project: StoryProject, pages: StoryPage[], options?: { title?: string; versionId?: string | null },
) => Promise<null>;

/** "Narrate in Audiobook" (ST-4.4), from writing mode and from a kept run. */
export function useNarrateInAudiobook(): NarrateInAudiobook {
  const router = useRouter({ warn: false }) as AnyRouter | undefined;
  return useCallback<NarrateInAudiobook>(async (project, pages, options) => {
    const book = await importStoryToAudiobook(storyAudiobookImport(project, pages, options));
    if (router) await router.navigate({ to: '/audiobook', search: { project: book.id } } as never);
    else window.history.pushState(window.history.state, '', audiobookProjectHref(book.id));
    return null;
  }, [router]);
}
