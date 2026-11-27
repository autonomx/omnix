import { downloadBlob } from '../../shared/download';
import { type StoryExportFormat, type StoryProject, storyApiClient } from './api/storyClient';
import type { SaveFeedback } from './storyModel';
import { slugify } from './storyModel';
import { type ManuscriptItem, manuscriptMarkdown } from './storyProjectModel';
import { formatStoryMarkdown } from './storyTextModel';

/**
 * Exports the story: Markdown is written here from the manuscript; EPUB, Word and PDF are books the server
 * builds from the project's visible pages (ST-6.5).
 */
export function useStoryExport({ project, items, title, premise, providerLabel, wordCount, chapterCount, setSaveFeedback }: {
  project: StoryProject | null;
  items: ManuscriptItem[];
  title: string;
  premise: string;
  providerLabel: string;
  wordCount: number;
  chapterCount: number;
  setSaveFeedback: (feedback: SaveFeedback) => void;
}) {
  return async (format: 'markdown' | StoryExportFormat) => {
    if (!items.length) return;
    if (format === 'markdown') {
      const markdown = formatStoryMarkdown({ title, premise, providerLabel, wordCount, chapterCount, text: manuscriptMarkdown(items) });
      const fileName = `${slugify(title)}.md`;
      downloadBlob(new Blob([markdown], { type: 'text/markdown' }), fileName);
      setSaveFeedback({ kind: 'exported', message: `Exported ${fileName}.` });
      return;
    }
    if (!project) return;
    try {
      const { blob, fileName } = await storyApiClient.exportBook(project.id, format);
      downloadBlob(blob, fileName);
      setSaveFeedback({ kind: 'exported', message: `Exported ${fileName}.` });
    } catch (caught) {
      setSaveFeedback({
        kind: 'error',
        message: caught instanceof Error && caught.message ? caught.message : `The story could not be exported as ${format.toUpperCase()}.`,
      });
    }
  };
}
