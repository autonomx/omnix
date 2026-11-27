/** Storyteller's types, settings and small helpers (WP-9.5 split them out of StorytellerWorkspace). */
import type { JobRecord, ProviderFacadePayload, omnixApiClient } from '../../api/client';

export interface StorytellerFormValues {
  providerId: string;
  title: string;
  premise: string;
}

export type StoryActionMode = 'draft' | 'continue' | 'rewrite' | 'expand' | 'dialogue' | 'summarize' | 'outline';

export type StoryQuickActionMode = Exclude<StoryActionMode, 'draft' | 'outline'>;

export type SaveFeedbackKind = 'saved' | 'exported' | 'error';

export type StoryWorkspaceMode = 'writing' | 'story';

/** The library's panes: writing projects, interactive ones, and the server's trash (ST-1.2). */
export type StoryLibrarySection = 'stories' | 'interactive' | 'trash';

/** One request to write: the job's action, the project it writes into, and a player's move. */
export interface StoryGenerationRequest {
  values: StorytellerFormValues;
  action: StoryActionMode;
  /** The project the job writes into; none makes a new one first. */
  projectId: string | null;
  interactionMode?: StoryWorkspaceMode;
  userResponse?: string | null;
  chosenSuggestion?: string | null;
  /** A continue that opens the next chapter. */
  newChapter?: boolean;
  /** The beat of the plan a page is drafted from (ST-5.1). */
  beatId?: string | null;
  /** How many chapters an `outline` job plans. */
  outlineChapters?: number | null;
  /** The blocks of one page a rewrite, expand or dialogue job reworks, rather than the whole story (ST-6.2). */
  selection?: StorySelectionRange | null;
}

/** Blocks `[start, end)` of a page, by their index in the page's blocks, with the text they held when chosen. */
export type StorySelectionRange = { pageId: string; start: number; end: number; texts: string[] };

/** The actions that rework a selection or a page (ST-6.2). */
export type StorySelectionAction = 'rewrite' | 'expand' | 'dialogue';

/** What a request queued: the job and the project it writes into. */
export interface StoryGenerationResult {
  job: JobRecord;
  projectId: string;
}

/** The manuscript's own chapters and scenes, read from its headings for the navigator; the plan is `project.outline`. */
export interface ManuscriptOutlineScene {
  id: string;
  label: string;
  title: string;
  placeholder?: boolean;
}

export interface ManuscriptOutlineChapter {
  id: string;
  number: number;
  label: string;
  title: string;
  scenes: ManuscriptOutlineScene[];
}

export interface SaveFeedback {
  kind: SaveFeedbackKind;
  message: string;
}

/** The server rejects a longer premise (`story/prompts.PREMISE_MAX_CHARS`). */
export const premiseMaxChars = 500;

export const toneOptions = ['Cozy', 'Hopeful', 'Gentle', 'Mystery'];

export const styleOptions = ['Lyrical & Descriptive', 'Fast-paced', 'Dialogue-heavy', 'Cinematic', 'Literary'];

export const quickActions: Array<{ mode: StoryQuickActionMode; label: string; description: string }> = [
  { mode: 'continue', label: 'Continue story', description: 'Write what happens next' },
  { mode: 'rewrite', label: 'Rewrite whole story', description: 'Clearer telling, saved as a new version' },
  { mode: 'expand', label: 'Expand whole story', description: 'More detail, saved as a new version' },
  { mode: 'dialogue', label: 'Polish all dialogue', description: 'Sharper voices, saved as a new version' },
  { mode: 'summarize', label: 'Summarize whole story', description: 'A short summary, saved as a new version' },
];

export const librarySections: Array<{ id: StoryLibrarySection; label: string }> = [
  { id: 'stories', label: 'Stories' },
  { id: 'interactive', label: 'Interactive' },
];
// Characters, World Notes and Prompts return when the story bible fills them (roadmap Phase 2).

export function librarySectionLabel(section: StoryLibrarySection): string {
  return librarySections.find((entry) => entry.id === section)?.label ?? 'Trash';
}

export function llmCapableProviders(payload: ProviderFacadePayload | undefined) {
  return payload?.providers.filter((provider) => provider.capabilities.includes('chat') || provider.capabilities.includes('completion')) ?? [];
}

export function storyDisplayTitle(title: string | null | undefined, storyText: string | null): string {
  return cleanStoryTitle(title) ?? titleFromStoryText(storyText) ?? 'Untitled story';
}

export function cleanStoryTitle(value: string | null | undefined): string | null {
  const title = value?.trim();
  if (!title || /^untitled story\b/i.test(title)) return null;
  return title;
}

export function titleFromStoryText(text: string | null): string | null {
  const heading = text?.split(/\r?\n/).map((line) => line.trim()).find((line) => /^#\s+\S/.test(line));
  return cleanStoryTitle(heading?.replace(/^#\s+/, ''));
}

export function providerDisplayName(providers: Array<{ id: string; label: string }>, selectedProviderId: string): string {
  return providers.find((provider) => provider.id === selectedProviderId)?.label ?? 'Omnix LLM';
}

export function countWords(text: string): number { return text.trim() ? text.trim().split(/\s+/).length : 0; }

export function truncate(text: string, length: number): string { return text.length > length ? `${text.slice(0, length)}…` : text; }

export function slugify(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'story';
}

/** The text a story job returned, shown on its status card. */
export function jobOutputText(job: { output_refs?: Array<{ content?: unknown }>; logs?: Array<{ content?: unknown }> }): string | null {
  const content = job.output_refs?.find((ref) => typeof ref.content === 'string')?.content ??
    job.logs?.find((log) => typeof log.content === 'string')?.content;
  return typeof content === 'string' && content.trim() ? content : null;
}

const writeStageLabels: Record<StoryActionMode, string> = {
  draft: 'Write story',
  continue: 'Continue story',
  rewrite: 'Rewrite story',
  expand: 'Expand story',
  dialogue: 'Polish dialogue',
  summarize: 'Summarize story',
  outline: 'Plan story',
};

/** The settings a story job carries besides the request: tone, writing style and chapter. */
export type StoryJobSettings = { tone: string; writingStyle: string; chapter: number };

/**
 * The `story.generate` job for one request: a Write stage on the LLM and a Store stage. The job reads the
 * story so far from its project and writes its page or version there (ST-1.3), so it carries no story text.
 */
export function storyJobRequest(
  { values, action, projectId, interactionMode, userResponse, chosenSuggestion, newChapter, beatId, outlineChapters, selection }: StoryGenerationRequest,
  settings: StoryJobSettings,
): Parameters<typeof omnixApiClient.createJob>[0] {
  return {
    module: 'storyteller',
    type: 'story.generate',
    resource_class: 'gpu:llm',
    priority: 0,
    input_payload: {
      project_id: projectId,
      title: values.title || null,
      premise: values.premise,
      provider_id: values.providerId || null,
      action,
      interaction_mode: interactionMode ?? 'writing',
      user_response: userResponse ?? null,
      chosen_suggestion: chosenSuggestion ?? null,
      new_chapter: Boolean(newChapter),
      beat_id: beatId ?? null,
      outline_chapters: outlineChapters ?? null,
      selection: selection ? { page_id: selection.pageId, start: selection.start, end: selection.end, texts: selection.texts } : null,
      tone: settings.tone,
      writing_style: settings.writingStyle,
      chapter: settings.chapter,
    },
    stages: [
      { id: 'write', label: writeStageLabels[action], resource_class: 'gpu:llm', status: 'queued' },
      { id: 'store-story', label: 'Store story', resource_class: 'cpu', status: 'queued' },
    ],
  };
}
