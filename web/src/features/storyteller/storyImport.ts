/**
 * The one-time import of the stories this browser knew before story projects (ST-1.4, Q-ST3).
 *
 * The browser's draft, its trash and the scenes it appended, the account's story assets and its finished
 * story jobs become projects. The server makes each origin once, so running the import again creates
 * nothing; once it succeeds the legacy keys are removed and a marker stops it running again, so a project
 * the writer deletes forever is not brought back.
 */
import { omnixApiClient, type JobRecord } from '../../api/client';
import { type StoryImportItem, type StoryProjectSummary, storyApiClient } from './api/storyClient';

const draftKey = 'omnix:storyteller:last-draft';
const trashKey = 'omnix:storyteller:trash';
const sceneAdditionsKey = 'omnix:storyteller:scene-additions';
export const storyImportMarkerKey = 'omnix:storyteller:imported-v1';

type LegacyDraft = { title: string; premise: string; savedAt: string | null; content: string };
type LegacyTrashEntry = { id: string; title: string; content: string | null };
type LegacySceneAddition = {
  sourceItemId: string;
  chapterNumber: number;
  sceneNumber: number;
  title: string;
  chapterTitle: string | null;
  startsNewChapter: boolean;
  content: string;
  createdAt: string;
};
type LegacyAsset = { id: string; type: string; module?: string | null; file_name?: string | null };

export function storyImportDone(): boolean {
  return readStorage(storyImportMarkerKey) !== null;
}

/** Imports what the browser and the account still hold; resolves to the number of projects created. */
export async function importLegacyStories(
  { jobs, assets, known }: { jobs: JobRecord[]; assets: LegacyAsset[]; known: StoryProjectSummary[] },
): Promise<number> {
  const items = await legacyImportItems({ jobs, assets, known });
  const created = items.length ? (await storyApiClient.importStories(items)).created.length : 0;
  for (const key of [draftKey, trashKey, sceneAdditionsKey]) removeStorage(key);
  writeStorage(storyImportMarkerKey, new Date().toISOString());
  return created;
}

/** The import items for the legacy stories no project covers yet. */
export async function legacyImportItems(
  { jobs, assets, known }: { jobs: JobRecord[]; assets: LegacyAsset[]; known: StoryProjectSummary[] },
): Promise<StoryImportItem[]> {
  const covered = new Set(known.map((project) => `${project.origin_kind}:${project.origin_ref}`));
  const trash = readTrash();
  const trashed = new Set(trash.map((entry) => entry.id));
  const additions = readSceneAdditions();
  const withScenes = (legacyId: string, text: string) => applySceneAdditions(
    text, additions.filter((addition) => addition.sourceItemId === legacyId));
  const items: StoryImportItem[] = [];
  const seen = new Set<string>();
  const add = (legacyId: string, item: StoryImportItem) => {
    const origin = `${item.origin_kind}:${item.origin_ref}`;
    seen.add(legacyId);
    if (covered.has(origin) || !item.text?.trim()) return;
    covered.add(origin);
    items.push({ ...item, text: withScenes(legacyId, item.text), trashed: trashed.has(legacyId) });
  };

  const draft = readDraft();
  if (draft) {
    add('draft:last', { origin_kind: 'local', origin_ref: `draft:${draft.savedAt ?? 'last'}`, title: draft.title,
      premise: draft.premise, text: draft.content });
  }
  for (const job of jobs) {
    if (!isLegacyStoryJob(job)) continue;
    const text = jobText(job);
    if (!text) continue;
    add(`job:${job.id}`, {
      origin_kind: 'job', origin_ref: job.id, title: jobString(job, 'title') ?? jobTitle(job) ?? '',
      premise: jobString(job, 'premise') ?? '', text,
      mode: jobString(job, 'interaction_mode') === 'story' ? 'interactive' : 'writing',
    });
  }
  for (const asset of assets) {
    if (!(asset.type === 'story' || (asset.type === 'export' && asset.module === 'storyteller'))) continue;
    if (covered.has(`asset:${asset.id}`)) continue;
    let content: string | null = null;
    try {
      content = (await omnixApiClient.getAssetContent(asset.id)).content ?? null;
    } catch {
      continue; // An asset that can't be read as text stays an asset.
    }
    if (!content) continue;
    add(`asset:${asset.id}`, { origin_kind: 'asset', origin_ref: asset.id, title: assetTitle(asset.file_name),
      text: content });
  }
  // A binned story whose job or asset is gone survives in the trash entry's own copy.
  for (const entry of trash) {
    if (seen.has(entry.id) || !entry.content?.trim()) continue;
    add(entry.id, { origin_kind: 'local', origin_ref: `trash:${entry.id}`, title: entry.title, text: entry.content });
  }
  return items;
}

/** A finished story job from before projects that wasn't a scene appended to another story. */
function isLegacyStoryJob(job: JobRecord): boolean {
  if (job.module !== 'storyteller' || job.type !== 'story.generate' || job.status !== 'completed') return false;
  const refs = (job.output_refs ?? []) as Array<Record<string, unknown>>;
  if (refs.some((ref) => typeof ref.project_id === 'string')) return false;
  if (jobString(job, 'project_id')) return false;
  return !(jobString(job, 'action') === 'continue' && jobString(job, 'source_library_item_id'));
}

function jobText(job: JobRecord): string | null {
  const refs = (job.output_refs ?? []) as Array<Record<string, unknown>>;
  const logs = (job.logs ?? []) as Array<Record<string, unknown>>;
  const content = refs.find((ref) => typeof ref.content === 'string')?.content ??
    logs.find((log) => typeof log.content === 'string')?.content;
  return typeof content === 'string' && content.trim() ? content : null;
}

function jobTitle(job: JobRecord): string | null {
  const refs = (job.output_refs ?? []) as Array<Record<string, unknown>>;
  const title = refs.find((ref) => typeof ref.title === 'string')?.title;
  return typeof title === 'string' && title.trim() ? title.trim() : null;
}

function jobString(job: JobRecord, key: string): string | null {
  const value = (job.input_payload as Record<string, unknown> | undefined)?.[key];
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function assetTitle(fileName: string | null | undefined): string {
  const name = fileName?.split(/[\\/]/).pop() ?? '';
  return name.replace(/\.[^.]+$/, '').replace(/[-_]+/g, ' ').trim();
}

/** The legacy story text with the scenes and chapters the browser appended to it, in the order they were added. */
export function applySceneAdditions(text: string, additions: LegacySceneAddition[]): string {
  return additions
    .slice()
    .sort((left, right) => left.createdAt.localeCompare(right.createdAt))
    .reduce((story, addition) => {
      const chapter = addition.startsNewChapter
        ? `Chapter ${addition.chapterNumber}: ${addition.chapterTitle ?? `Chapter ${addition.chapterNumber}`}` : null;
      const scene = addition.content.trim() ? `Scene ${addition.sceneNumber}: ${addition.title}\n\n${addition.content.trim()}` : null;
      return [story, chapter, scene].filter(Boolean).join('\n\n');
    }, text.trim());
}

function readDraft(): LegacyDraft | null {
  const record = readJson(draftKey);
  if (!record || typeof record !== 'object') return null;
  const draft = record as Record<string, unknown>;
  if (typeof draft.content !== 'string' || !draft.content.trim()) return null;
  return {
    title: typeof draft.title === 'string' && draft.title !== 'Saved local draft' ? draft.title : '',
    premise: typeof draft.premise === 'string' ? draft.premise : '',
    savedAt: typeof draft.savedAt === 'string' ? draft.savedAt : null,
    content: draft.content,
  };
}

function readTrash(): LegacyTrashEntry[] {
  const parsed = readJson(trashKey);
  if (!Array.isArray(parsed)) return [];
  return parsed.flatMap((value) => {
    const entry = value as Record<string, unknown> | null;
    if (!entry || typeof entry.id !== 'string') return [];
    return [{ id: entry.id, title: typeof entry.title === 'string' ? entry.title : '',
      content: typeof entry.content === 'string' ? entry.content : null }];
  });
}

function readSceneAdditions(): LegacySceneAddition[] {
  const parsed = readJson(sceneAdditionsKey);
  if (!Array.isArray(parsed)) return [];
  return parsed.flatMap((value) => {
    const record = value as Record<string, unknown> | null;
    if (!record || typeof record.sourceItemId !== 'string' || typeof record.content !== 'string') return [];
    return [{
      sourceItemId: record.sourceItemId,
      chapterNumber: typeof record.chapterNumber === 'number' ? record.chapterNumber : 1,
      sceneNumber: typeof record.sceneNumber === 'number' ? record.sceneNumber : 1,
      title: typeof record.title === 'string' && record.title.trim() ? record.title : 'Continuation',
      chapterTitle: typeof record.chapterTitle === 'string' && record.chapterTitle.trim() ? record.chapterTitle : null,
      startsNewChapter: record.startsNewChapter === true,
      content: record.content,
      createdAt: typeof record.createdAt === 'string' ? record.createdAt : '',
    }];
  });
}

function readJson(key: string): unknown {
  const raw = readStorage(key);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function readStorage(key: string): string | null {
  try {
    return typeof window === 'undefined' ? null : window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Without storage the import runs again next time; the server makes nothing twice.
  }
}

function removeStorage(key: string): void {
  try {
    window.localStorage.removeItem(key);
  } catch {
    // As above.
  }
}
