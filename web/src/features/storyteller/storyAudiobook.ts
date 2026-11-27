/**
 * A story handed to Audiobook (ST-4.4): the pages as chapters of narration and spoken lines, each spoken line
 * with the cast member the story recorded, and the cast as the book's speakers.
 *
 * Audiobook gives a spoken line to its speaker without a model when the speaker is in the cast; a line whose
 * speaker the story could not confirm (unverified, a suggested character, or nobody) goes to its classifier.
 */
import type { AudiobookStoryImport } from '../audiobook';
import type { StoryPage, StoryProject } from './api/storyClient';

type ImportChapter = AudiobookStoryImport['chapters'][number];
type ImportBlock = NonNullable<ImportChapter['blocks']>[number];

const titleMax = 200;
const nameMax = 120;
const aliasMax = 20;
const castMax = 60;

const clip = (text: string, max: number) => text.trim().slice(0, max);

export function storyAudiobookImport(project: StoryProject, pages: StoryPage[], options: { title?: string; versionId?: string | null } = {}): AudiobookStoryImport {
  const cast = (project.characters ?? []).filter((character) => !character.suggested && character.name.trim());
  const names = new Map(cast.map((character) => [character.id, clip(character.name, nameMax)]));
  const chapters: ImportChapter[] = [];
  let chapterNumber: number | null = null;
  for (const page of pages) {
    if (page.chapter !== chapterNumber || !chapters.length) {
      chapterNumber = page.chapter;
      chapters.push({ title: clip(page.title, titleMax), blocks: [] });
    }
    const blocks = chapters[chapters.length - 1].blocks as ImportBlock[];
    for (const block of page.blocks) {
      const text = block.text.trim();
      if (!text) continue;
      if (block.kind !== 'dialogue') {
        blocks.push({ kind: 'narration', text });
        continue;
      }
      const speaker = names.get(block.speaker_id?.trim() ?? '');
      blocks.push({ kind: 'dialogue', text, speaker: speaker ?? null, unverified: block.attribution === 'unverified' || !speaker });
    }
  }
  return {
    title: clip(options.title ?? project.title, titleMax) || 'Untitled story',
    story_project_id: project.id,
    story_version_id: options.versionId ?? null,
    chapters,
    cast: cast.slice(0, castMax).map((character) => ({
      name: clip(character.name, nameMax),
      aliases: (character.aliases ?? []).map((alias) => clip(alias, nameMax)).filter(Boolean).slice(0, aliasMax),
    })),
  };
}
