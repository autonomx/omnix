import type { StoryAudioManifest, StoryDocument } from './storyDocument';

export type StoryRemoteStoreResult = {
  ok: boolean;
  status: number;
  message: string;
};

export async function tryStoreStoryDocument(document: StoryDocument): Promise<StoryRemoteStoreResult> {
  return postJson('/api/storyteller/documents', document, 'Story document backend endpoint is not available yet.');
}

export async function tryStoreStoryAudioManifest(manifest: StoryAudioManifest): Promise<StoryRemoteStoreResult> {
  return postJson('/api/storyteller/audio-manifests', manifest, 'Story audio metadata backend endpoint is not available yet.');
}

export function validateStoryDocumentForRemote(document: StoryDocument): string[] {
  const issues: string[] = [];
  if (!document.id) issues.push('Story id is missing.');
  if (!document.title) issues.push('Story title is missing.');
  if (!document.cast.some((character) => character.id === 'narrator')) issues.push('Narrator cast member is missing.');
  for (const chapter of document.chapters) {
    if (!chapter.id) issues.push('Chapter id is missing.');
    for (const block of chapter.blocks) {
      if (!document.cast.some((character) => character.id === block.speakerId)) issues.push(`Block ${block.id} references an unknown speaker.`);
    }
  }
  return issues;
}

async function postJson(url: string, payload: unknown, fallbackMessage: string): Promise<StoryRemoteStoreResult> {
  try {
    const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    if (!response.ok) return { ok: false, status: response.status, message: response.status === 404 ? fallbackMessage : `Backend returned HTTP ${response.status}.` };
    return { ok: true, status: response.status, message: 'Stored successfully.' };
  } catch (error) {
    return { ok: false, status: 0, message: error instanceof Error ? error.message : fallbackMessage };
  }
}
