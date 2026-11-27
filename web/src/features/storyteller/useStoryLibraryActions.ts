import type { StoryBlock, StoryProjectSummary, StoryVersionSummary } from './api/storyClient';
import type { SaveFeedback, StoryLibrarySection } from './storyModel';
import type { StoryLibraryEntry } from './storyProjectModel';
import type { useStoryProjects } from './useStoryProjects';

const sectionFor = (entry: { mode: string }): StoryLibrarySection => (entry.mode === 'interactive' ? 'interactive' : 'stories');

/** The writer agrees before a story leaves the library; Trash keeps it restorable for 30 days. */
const confirmTrash = (title: string) => window.confirm(`Move "${title}" to Trash? You can restore it from Trash for 30 days.`);

/** A failed call in the writer's words; a proposal whose page changed since is a conflict (ST-6.2). */
const failure = (caught: unknown, fallback: string) => {
  const message = caught instanceof Error ? caught.message : '';
  if (message.includes('story_selection_page_changed')) {
    return 'The page changed since this was written, so the change was not made. Ask again from the page as it is now.';
  }
  if (message.includes('story_selection_not_pending')) return 'That change was already answered.';
  if (message.includes('story_page_changed')) {
    return 'The page changed while you were editing it, so your edit was not saved. Cancel, then edit the page as it is now.';
  }
  return message || fallback;
};

/**
 * The library's calls as the workspace makes them (trash, restore, versions, settings, presets), each
 * reporting its outcome where the writer is looking.
 */
export function useStoryLibraryActions({ projects, storyTitle, setSaveFeedback, setActiveLibrarySection }: {
  projects: ReturnType<typeof useStoryProjects>;
  storyTitle: string;
  setSaveFeedback: (feedback: SaveFeedback | null) => void;
  setActiveLibrarySection: (section: StoryLibrarySection) => void;
}) {
  const project = projects.project;
  /** Runs a library call, reporting its outcome where the writer is looking. */
  const run = (task: () => Promise<string | null>) => {
    void task()
      .then((message) => (message ? setSaveFeedback({ kind: 'saved', message }) : undefined))
      .catch((caught: unknown) => setSaveFeedback({ kind: 'error', message: failure(caught, 'The story library could not be updated.') }));
  };

  return {
    run,
    sectionFor,
    trashActiveStory: () => {
      if (!project || !confirmTrash(storyTitle)) return;
      run(async () => {
        await projects.trash(project.id);
        setActiveLibrarySection('trash');
        return `Moved "${storyTitle}" to Trash.`;
      });
    },
    /** Any story, from the library view; it stays restorable from Trash for 30 days. */
    trashStory: (story: StoryProjectSummary) => {
      const title = story.title.trim() || 'Untitled story';
      if (!confirmTrash(title)) return;
      run(async () => {
        await projects.trash(story.id);
        return `Moved "${title}" to Trash. Restore it from Trash within 30 days.`;
      });
    },
    /** A story's title and premise, edited in the library view; false keeps the form open with the error shown. */
    saveDetails: async (story: StoryProjectSummary, details: { title: string; premise: string }) => {
      try {
        await projects.update(story.id, details);
      } catch (caught) {
        setSaveFeedback({ kind: 'error', message: failure(caught, 'The story could not be saved.') });
        return false;
      }
      setSaveFeedback({ kind: 'saved', message: `Saved "${details.title || 'Untitled story'}".` });
      return true;
    },
    restoreEntry: (entry: StoryLibraryEntry) => run(async () => {
      await projects.restore(entry.id);
      projects.select(entry.id);
      setActiveLibrarySection(sectionFor(entry));
      return `Restored "${entry.title}".`;
    }),
    purgeEntry: (entry: StoryLibraryEntry) => {
      if (!window.confirm(`Delete "${entry.title}" forever? This cannot be undone.`)) return;
      run(async () => {
        await projects.purge(entry.id);
        return `Deleted "${entry.title}" forever.`;
      });
    },
    saveVersion: () => {
      if (!project) return;
      run(async () => {
        const changed = await projects.saveVersion(project.id);
        const newest = Math.max(0, ...changed.versions.map((version) => version.version_number));
        return `Saved version ${newest} of "${storyTitle}".`;
      });
    },
    restoreVersion: (version: StoryVersionSummary) => {
      if (!project) return;
      run(async () => {
        await projects.restoreVersion(project.id, version.id);
        return `Restored version ${version.version_number}.`;
      });
    },
    /** A page as the writer edited it (ST-6.1); a failure stays in the editor, which shows it. */
    savePage: async (pageId: string, pageNumber: number, blocks: StoryBlock[], baseBlocks: StoryBlock[]) => {
      if (!project) return;
      try {
        await projects.updatePage(project.id, pageId, blocks, baseBlocks);
      } catch (caught) {
        throw new Error(failure(caught, 'The page could not be saved.'));
      }
      setSaveFeedback({ kind: 'saved', message: `Saved page ${pageNumber}.` });
    },
    /** The writer's answer to a proposed change (ST-6.2); accepting keeps the page before it as a version. */
    acceptSelection: async (version: StoryVersionSummary, pageNumber: number) => {
      if (!project) return;
      try {
        await projects.acceptSelection(project.id, version.id);
        setSaveFeedback({ kind: 'saved', message: `Accepted the change to page ${pageNumber}; the story before it is kept in Versions.` });
      } catch (caught) {
        setSaveFeedback({ kind: 'error', message: failure(caught, 'The change could not be accepted.') });
      }
    },
    rejectSelection: async (version: StoryVersionSummary) => {
      if (!project) return;
      try {
        await projects.rejectSelection(project.id, version.id);
        setSaveFeedback({ kind: 'saved', message: 'Rejected the proposed change; the page is as it was.' });
      } catch (caught) {
        setSaveFeedback({ kind: 'error', message: failure(caught, 'The change could not be rejected.') });
      }
    },
    updateReadSettings: (readSettings: Record<string, unknown>) => {
      if (!project) return;
      run(async () => {
        await projects.update(project.id, { read_settings: readSettings });
        return null;
      });
    },
    /** Tells the story with a preset (ST-5.2): the server gives it the preset's tone and style. */
    choosePreset: (projectId: string, presetId: string) => projects.update(projectId, { preset_id: presetId }),
  };
}
