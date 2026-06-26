import { describe, expect, it } from 'vitest';
import { readSavedDrafts, saveDraft, titleFromText } from './draftStore';

class MemoryStorage implements Storage {
  private values = new Map<string, string>();
  get length() { return this.values.size; }
  clear() { this.values.clear(); }
  getItem(key: string) { return this.values.get(key) ?? null; }
  key(index: number) { return Array.from(this.values.keys())[index] ?? null; }
  removeItem(key: string) { this.values.delete(key); }
  setItem(key: string, value: string) { this.values.set(key, value); }
}

describe('draftStore', () => {
  it('stores drafts newest first', () => {
    const storage = new MemoryStorage();
    saveDraft('first line', storage);
    saveDraft('second line', storage);
    expect(readSavedDrafts(storage).map((draft) => draft.title)).toEqual(['second line', 'first line']);
  });

  it('uses the first non-empty line as title', () => {
    expect(titleFromText('\n  hello there')).toBe('hello there');
  });
});
