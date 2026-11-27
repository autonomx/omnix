/**
 * A story's read settings (ST-1.7): the account default from Settings, with the project's own override on top.
 * The override uses the settings profile's names, so the audiobook reads both the same way.
 */
export type StoryReadSettings = {
  readSpeed: number;
  pauseParagraphMs: number;
  pauseChapterMs: number;
  readChapterTitles: boolean;
  readStylePreset: string;
  pronunciation: Record<string, string>;
};

export function storyReadSettings(defaults: StoryReadSettings, override: Record<string, unknown> | null | undefined): StoryReadSettings {
  const value = override ?? {};
  const number = (key: keyof StoryReadSettings, fallback: number) =>
    typeof value[key] === 'number' && Number.isFinite(value[key]) ? value[key] as number : fallback;
  return {
    readSpeed: number('readSpeed', defaults.readSpeed),
    pauseParagraphMs: number('pauseParagraphMs', defaults.pauseParagraphMs),
    pauseChapterMs: number('pauseChapterMs', defaults.pauseChapterMs),
    readChapterTitles: typeof value.readChapterTitles === 'boolean' ? value.readChapterTitles : defaults.readChapterTitles,
    readStylePreset: typeof value.readStylePreset === 'string' && value.readStylePreset.trim()
      ? value.readStylePreset : defaults.readStylePreset,
    pronunciation: isStringRecord(value.pronunciation) ? value.pronunciation : defaults.pronunciation,
  };
}

/** The word notes as the panel edits them: one "word: how to say it" per line. */
export function pronunciationText(pronunciation: Record<string, string>): string {
  return Object.entries(pronunciation).map(([word, note]) => `${word}: ${note}`).join('\n');
}

export function pronunciationFromText(text: string): Record<string, string> {
  const notes: Record<string, string> = {};
  for (const line of text.split(/\r?\n/)) {
    const index = line.indexOf(':');
    if (index <= 0) continue;
    const word = line.slice(0, index).trim();
    const note = line.slice(index + 1).trim();
    if (word && note) notes[word] = note;
  }
  return notes;
}

function isStringRecord(value: unknown): value is Record<string, string> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value) &&
    Object.values(value as Record<string, unknown>).every((entry) => typeof entry === 'string');
}
