import { sendGatewayCall } from '../../api/http';
import { api } from './api/gateway';
import type { components } from './api/generated';

export type PodcastResearch = components['schemas']['PodcastResearchResponse'];

/** How much of the source notes the script reads (story/podcast_script.py SOURCE_LIMIT). */
export const sourceNotesLimit = 8000;

// One web search and the pages it reads; research's own deadline is shorter.
const RESEARCH_WAIT_MS = 60000;

/** Source notes for the episode from one web search on its title and brief (story's `/api/podcast/research`). */
export function researchPodcastTopic(title: string, brief: string): Promise<PodcastResearch> {
  return sendGatewayCall(
    (signal) => api.POST('/api/podcast/research', { body: { title: title.trim(), brief: brief.trim() }, signal }),
    { timeoutMs: RESEARCH_WAIT_MS, timeoutMessage: 'The web search took too long. Try again.' },
  );
}

/** The producer's notes with the research added after them; notes already there are kept. */
export function withResearchNotes(current: string, research: string): string {
  const mine = current.trim();
  return mine ? `${mine}\n\n${research}` : research;
}
