/** The audiobook feature's public API (WP-9.7). */
import type { components } from './api/generated';
import { audiobookApi } from './audiobookApi';

export { audiobookModule } from './module';

/** The book a story is handed over as: chapters of narration and spoken lines, and the story's cast (ST-4.4). */
export type AudiobookStoryImport = components['schemas']['StoryImport'];

/** Creates an Audiobook project from a story; the project opens at `audiobookProjectHref(id)`. */
export function importStoryToAudiobook(story: AudiobookStoryImport): Promise<{ id: string }> {
  return audiobookApi.importStory(story);
}

export function audiobookProjectHref(projectId: string): string {
  return `/audiobook?project=${encodeURIComponent(projectId)}`;
}
