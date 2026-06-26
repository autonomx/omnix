export interface SavedDraft {
  id: string;
  title: string;
  text: string;
  updatedAt: string;
}

const STORAGE_KEY = 'omnix.savedDrafts';

export function readSavedDrafts(storage: Storage = window.localStorage): SavedDraft[] {
  const raw = storage.getItem(STORAGE_KEY);
  if (!raw) {
    return [];
  }
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveDraft(text: string, storage: Storage = window.localStorage): SavedDraft {
  const drafts = readSavedDrafts(storage);
  const draft: SavedDraft = {
    id: `draft:${Date.now()}`,
    title: titleFromText(text),
    text,
    updatedAt: new Date().toISOString(),
  };
  storage.setItem(STORAGE_KEY, JSON.stringify([draft, ...drafts].slice(0, 20)));
  return draft;
}

export function titleFromText(text: string): string {
  const firstLine = text.split('\n').find((line) => line.trim());
  return firstLine ? firstLine.trim().slice(0, 48) : 'Untitled script';
}
