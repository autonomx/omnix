/** Story text: the outline, suggested moves and the Markdown export. */
import { ManuscriptOutlineChapter } from './storyModel';

export function deriveStoryOutline(text: string | null, fallbackTitle: string): ManuscriptOutlineChapter[] {
  if (!text?.trim()) {
    return [{ id: 'story-chapter-1', number: 1, label: 'Chapter 1', title: fallbackTitle, scenes: [{ id: 'story-scene-1-1', label: 'Scene 1', title: 'Opening' }] }];
  }
  const chapters: ManuscriptOutlineChapter[] = [];
  let current: ManuscriptOutlineChapter | null = null;
  let sawContentBeforeFirstChapter = false;
  text.split(/\n+/).forEach((line) => {
    const cleaned = line.replace(/^#{1,4}\s*/, '').trim();
    const chapterMatch = cleaned.match(/^chapter\s+(\d+)\s*[:\-–—]?\s*(.*)$/i);
    const sceneMatch = cleaned.match(/^scene\s+(\d+)\s*[:\-–—]?\s*(.*)$/i);
    if (chapterMatch) {
      const number = Number(chapterMatch[1]);
      if (!chapters.length && sawContentBeforeFirstChapter && number !== 1) {
        chapters.push({
          id: 'story-chapter-1',
          number: 1,
          label: 'Chapter 1',
          title: fallbackTitle,
          scenes: [{ id: 'story-scene-1-1', label: 'Scene 1', title: 'Opening' }],
        });
      }
      current = {
        id: `story-chapter-${number}`,
        number,
        label: `Chapter ${number}`,
        title: chapterMatch[2]?.trim() || `Chapter ${number}`,
        scenes: [],
      };
      chapters.push(current);
      return;
    }
    if (cleaned && !current && !chapters.length && !sceneMatch) {
      sawContentBeforeFirstChapter = true;
    }
    if (sceneMatch && !current) {
      current = {
        id: 'story-chapter-1',
        number: 1,
        label: 'Chapter 1',
        title: fallbackTitle,
        scenes: [],
      };
      chapters.push(current);
    }
    if (sceneMatch && current) {
      const sceneNumber = Number(sceneMatch[1]);
      current.scenes.push({
        id: `story-scene-${current.number}-${sceneNumber}`,
        label: `Scene ${sceneNumber}`,
        title: sceneMatch[2]?.trim() || `Scene ${sceneNumber}`,
      });
    }
  });
  if (!chapters.length) {
    chapters.push({
      id: 'story-chapter-1',
      number: 1,
      label: 'Chapter 1',
      title: fallbackTitle,
      scenes: [{ id: 'story-scene-1-1', label: 'Scene 1', title: 'Opening' }],
    });
  }
  return chapters.map((chapter) => ({
    ...chapter,
    scenes: chapter.scenes.length ? chapter.scenes : [{ id: `story-scene-${chapter.number}-1`, label: 'Scene 1', title: 'Opening', placeholder: true }],
  }));
}

export function formatStoryMarkdown({ title, premise, providerLabel, wordCount, chapterCount, text }: {
  title: string;
  premise: string;
  providerLabel: string;
  wordCount: number;
  chapterCount: number;
  text: string;
}): string {
  return [
    `# ${title}`,
    '',
    `- Provider: ${providerLabel}`,
    `- Words: ${wordCount}`,
    `- Chapters: ${chapterCount}`,
    premise ? `- Premise: ${premise}` : null,
    '',
    '---',
    '',
    text,
    '',
  ].filter((line) => line !== null).join('\n');
}
