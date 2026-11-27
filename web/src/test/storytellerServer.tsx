/** The Storyteller workspace's in-memory server and render helpers, shared by its test files. */
import { MantineProvider } from '@mantine/core';
import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import { vi } from 'vitest';
import { omnixModules } from '../app/modules';
import { omnixTheme } from '../design/theme';
import { omnixEventClient } from '../events/eventClient';
import { createTestQueryClient } from './renderWithProviders';
import { StorytellerWorkspace } from '../features/storyteller/StorytellerWorkspace';

export const now = '2026-11-26T00:00:00Z';

export function renderStoryteller() {
  const queryClient = createTestQueryClient();
  const module = omnixModules.find((entry) => entry.id === 'storyteller');
  if (!module) throw new Error('Storyteller module is missing');
  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      <QueryClientProvider client={queryClient}>
        <StorytellerWorkspace module={module} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

export type Page = ReturnType<typeof page>;
export type Selection = { page_id: string; start: number; end: number; original: Block[]; proposed: Block[]; status: string };
export type Version = { id: string; kind: string; title: string; version_number: number; source_job_id: string | null; created_at: string; pages: Page[]; selection?: Selection | null };
export type Project = ReturnType<typeof project>;
export type Block = { kind: string; text: string; speaker_id: string | null; attribution: string | null };
export type Character = { id: string; name: string; aliases: string[]; description: string; traits: string[]; role: string; suggested: boolean };
export type Note = { id: string; kind: string; title: string; body: string; tone: string; writing_style: string; created_at: string; updated_at: string };
export type Beat = { id: string; text: string; page_id: string | null };
export type OutlineChapter = { chapter: number; title: string; beats: Beat[] };
export type Move = { id: string; page_id: string | null; player_text: string; chosen_suggestion: string; parent_move_id: string | null; created_at: string };

export function page(id: string, text: string, { chapter = 1, position = 1, title = '', blocks, parent = null, moves = [] }: {
  chapter?: number; position?: number; title?: string; blocks?: Block[]; parent?: string | null; moves?: string[];
} = {}) {
  return {
    id, chapter, position, title, hidden: false, source_job_id: null as string | null, created_at: now,
    parent_page_id: parent, suggested_moves: moves,
    blocks: blocks ?? text.split('\n\n').map((paragraph): Block => ({ kind: 'narration', text: paragraph, speaker_id: null, attribution: null })),
  };
}

export function character(id: string, name: string, overrides: Partial<Character> = {}): Character {
  return { id, name, aliases: [], description: '', traits: [], role: '', suggested: false, ...overrides };
}

export function project(id: string, overrides: Partial<{ title: string; premise: string; mode: string; pages: Page[]; characters: Character[]; notes: Note[]; moves: Move[]; outline: OutlineChapter[] }> = {}) {
  return {
    id,
    title: overrides.title ?? 'The Glass Orchard',
    premise: overrides.premise ?? 'A city grows fruit made of memory.',
    mode: overrides.mode ?? 'writing',
    tone: '',
    writing_style: '',
    preset_id: '',
    outline: overrides.outline ?? [],
    read_settings: {} as Record<string, unknown>,
    origin_kind: 'new',
    origin_ref: id,
    created_at: now,
    updated_at: now,
    deleted_at: null as string | null,
    pages: overrides.pages ?? [page(`${id}-p1`, 'The orchard rang like crystal at sunset.\n\nEach branch remembered a name.')],
    versions: [] as Version[],
    characters: overrides.characters ?? [],
    notes: overrides.notes ?? [],
    moves: overrides.moves ?? [],
  };
}

export function words(item: Project) {
  return item.pages.flatMap((entry) => entry.blocks).reduce((total, block) => total + block.text.split(/\s+/).length, 0);
}

export function summary(item: Project) {
  const { pages, versions, characters, notes, moves, ...rest } = item;
  void versions; void characters; void notes; void moves;
  return { ...rest, page_count: pages.length, word_count: words(item) };
}

export function detail(item: Project) {
  return { ...summary(item), pages: item.pages, versions: item.versions.map(({ pages, ...rest }) => (void pages, rest)), characters: item.characters, notes: item.notes, moves: item.moves };
}

export function move(id: string, pageId: string, text: string): Move {
  return { id, page_id: pageId, player_text: text, chosen_suggestion: '', parent_move_id: null, created_at: now };
}

export const visibleOf = (item: Project) => item.pages.filter((entry) => !entry.hidden);

/** Shows the chain of pages ending at `pageId` and hides the rest, as the server's open route does. */
export function showRunTo(item: Project, pageId: string) {
  const byId = new Map(item.pages.map((entry) => [entry.id, entry]));
  const run = new Set<string>();
  for (let current = byId.get(pageId); current; current = byId.get(current.parent_page_id ?? '')) run.add(current.id);
  for (const entry of item.pages) entry.hidden = !run.has(entry.id);
}

/**
 * An in-memory story server: the project routes, and a jobs route that writes what a finished
 * `story.generate` job writes (a page, a chapter, or a version). With `holdJobs`, a job stays queued
 * until the test finishes it.
 */
export function storyServer({ projects = [project('project-1')], legacyJobs = [] as unknown[], assets = [] as unknown[], holdJobs = false } = {}) {
  const store = new Map<string, Project>(projects.map((item) => [item.id, item]));
  const jobs = new Map<string, Record<string, unknown>>();
  const held = new Map<string, () => void>();
  let created = 0;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input instanceof Request ? input.url : input.toString());
    const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
    const rawBody = init?.body ?? (input instanceof Request && method !== 'GET' ? await input.clone().text() : null);
    const body = rawBody ? JSON.parse(String(rawBody)) as Record<string, unknown> : {};
    const path = url.pathname;
    if (path === '/api/providers') {
      return Response.json({ providers: [{ id: 'lmstudio', label: 'LM Studio', family: 'llm', source: 'settings', status: 'configured', capabilities: ['chat', 'completion'] }], models: [] });
    }
    if (path === '/api/settings/profile') return Response.json({ settings: {} });
    if (path === '/api/assets') return Response.json({ assets });
    if (path === '/api/audiobook/projects/import-story' && method === 'POST') {
      return Response.json({ id: 'ab:project:story', title: body.title, job_id: 'ab:ingest:1', source_asset_id: 'ab:source:1' }, { status: 202 });
    }
    if (path === '/api/story/projects' && method === 'GET') {
      const trashed = url.searchParams.get('trashed') === 'true';
      return Response.json({ projects: [...store.values()].filter((item) => Boolean(item.deleted_at) === trashed).map(summary) });
    }
    if (path === '/api/story/projects' && method === 'POST') {
      created += 1;
      const item = project(`project-new-${created}`, { title: String(body.title ?? ''), premise: String(body.premise ?? ''), mode: String(body.mode ?? 'writing'), pages: [] });
      store.set(item.id, item);
      return Response.json(detail(item));
    }
    if (path === '/api/story/projects/import') {
      const items = body.items as Array<Record<string, unknown>>;
      const ids = items.map((item, index) => {
        const imported = project(`project-imported-${index}`, { title: String(item.title ?? ''), premise: String(item.premise ?? ''), pages: [page(`imported-${index}`, String(item.text))] });
        imported.origin_kind = String(item.origin_kind);
        imported.origin_ref = String(item.origin_ref);
        store.set(imported.id, imported);
        return imported.id;
      });
      return Response.json({ created: ids, existing: [] });
    }
    const match = path.match(/^\/api\/story\/projects\/([^/]+)(?:\/(.*))?$/);
    if (match) {
      const item = store.get(decodeURIComponent(match[1]));
      if (!item) return new Response('not found', { status: 404 });
      const rest = match[2] ?? '';
      if (!rest && method === 'GET') return Response.json(detail(item));
      const exportMatch = rest.match(/^export\/(epub|docx|pdf)$/);
      if (exportMatch) {
        return new Response(new Blob([`book of ${item.title}`]), {
          headers: { 'Content-Type': 'application/pdf', 'Content-Disposition': `attachment; filename="${item.id}.${exportMatch[1]}"` },
        });
      }
      if (!rest && method === 'PATCH') {
        // Choosing a preset gives the story its tone and style, as the server does (ST-5.2).
        const preset = item.notes.find((note) => note.kind === 'preset' && note.id === body.preset_id);
        Object.assign(item, body, preset ? { tone: preset.tone, writing_style: preset.writing_style } : {});
        return Response.json(detail(item));
      }
      if (rest === 'characters' && method === 'PUT') {
        item.characters = body.characters as Character[];
        return Response.json(detail(item));
      }
      if (rest === 'notes' && method === 'PUT') {
        item.notes = (body.notes as Array<Partial<Note>>).map((note, index) => ({
          id: note.id ?? `note-${index + 1}`, kind: note.kind ?? 'world', title: note.title ?? '', body: note.body ?? '',
          tone: note.tone ?? '', writing_style: note.writing_style ?? '', created_at: now, updated_at: now,
        }));
        return Response.json(detail(item));
      }
      if (rest === 'outline' && method === 'PUT') {
        const known = new Map(item.outline.flatMap((chapter) => chapter.beats).map((beat) => [beat.id, beat]));
        let made = 0;
        item.outline = (body.chapters as Array<{ title?: string; beats?: Array<{ id?: string | null; text: string }> }>).map((chapter, index) => ({
          chapter: index + 1,
          title: chapter.title ?? '',
          beats: (chapter.beats ?? []).map((beat) => {
            made += 1;
            const id = beat.id && known.has(beat.id) ? beat.id : `beat-new-${made}`;
            return { id, text: beat.text, page_id: known.get(id)?.page_id ?? null };
          }),
        }));
        return Response.json(detail(item));
      }
      if (!rest && method === 'DELETE') {
        store.delete(item.id);
        return Response.json({ id: item.id, deleted: true });
      }
      if (rest === 'undo') {
        const last = visibleOf(item).at(-1);
        if (!last || !item.moves.some((entry) => entry.page_id === last.id)) return Response.json({ detail: 'story_no_move_to_undo' }, { status: 409 });
        last.hidden = true;
        return Response.json(detail(item));
      }
      if (rest === 'speech-plan') {
        const spoken = item.pages.find((entry) => entry.id === body.page_id);
        if (!spoken) return new Response('not found', { status: 404 });
        return Response.json({
          project_id: item.id, page_id: spoken.id,
          segments: spoken.blocks.map((block, index) => ({
            block_index: index, speaker_id: block.kind === 'dialogue' ? block.speaker_id : 'narrator', voice_id: 'v-warm',
            sentences: [block.text], unknown_speaker: false,
          })).filter((segment) => segment.sentences[0].trim()),
        });
      }
      if (rest === 'speech-audio') {
        return new Response(new Int16Array([1, 2, 3]).buffer, { headers: { 'X-Omnix-Sample-Rate': '24000' } });
      }
      const pageMatch = rest.match(/^pages\/([^/]+)$/);
      if (pageMatch && method === 'PATCH') {
        const edited = item.pages.find((entry) => entry.id === decodeURIComponent(pageMatch[1]));
        if (!edited) return new Response('not found', { status: 404 });
        // The edit applies only to the page it was opened on, as the server checks (ST-6.1).
        if (JSON.stringify(body.base_blocks) !== JSON.stringify(edited.blocks)) {
          return Response.json({ detail: 'story_page_changed' }, { status: 409 });
        }
        edited.blocks = body.blocks as Block[];
        return Response.json(detail(item));
      }
      const versionMatch = rest.match(/^versions\/([^/]+)(?:\/(accept|reject))?$/);
      const answered = versionMatch?.[2] ? item.versions.find((entry) => entry.id === decodeURIComponent(versionMatch[1])) : null;
      if (versionMatch && !versionMatch[2] && method === 'GET') {
        const version = item.versions.find((entry) => entry.id === decodeURIComponent(versionMatch[1]));
        return version ? Response.json(version) : new Response('not found', { status: 404 });
      }
      if (answered?.selection && versionMatch?.[2] === 'reject') {
        answered.selection.status = 'rejected';
        return Response.json(detail(item));
      }
      if (answered?.selection && versionMatch?.[2] === 'accept') {
        // Accepting keeps the story before it as a version, then puts the proposal in place of the range (ST-6.2).
        const { page_id: pageId, start, end, proposed } = answered.selection;
        item.versions.push({ id: `${item.id}-v${item.versions.length + 1}`, kind: 'manual', title: `Before accepting version ${answered.version_number}`, version_number: item.versions.length + 1, source_job_id: null, created_at: now, pages: item.pages });
        item.pages = item.pages.map((entry) => (entry.id === pageId ? { ...entry, blocks: [...entry.blocks.slice(0, start), ...proposed, ...entry.blocks.slice(end)] } : entry));
        answered.selection.status = 'accepted';
        return Response.json(detail(item));
      }
      const openMatch = rest.match(/^pages\/([^/]+)\/open$/);
      if (openMatch) {
        showRunTo(item, decodeURIComponent(openMatch[1]));
        return Response.json(detail(item));
      }
      if (rest === 'trash') item.deleted_at = now;
      else if (rest === 'restore') item.deleted_at = null;
      else if (rest === 'versions') {
        item.versions.push({ id: `${item.id}-v${item.versions.length + 1}`, kind: String(body.kind ?? 'manual'), title: String(body.title ?? ''), version_number: item.versions.length + 1, source_job_id: null, created_at: now, pages: item.pages });
      } else if (rest.startsWith('versions/') && rest.endsWith('/restore')) {
        const version = item.versions.find((entry) => entry.id === decodeURIComponent(rest.split('/')[1]));
        if (version) item.pages = version.pages;
      } else return new Response('not found', { status: 404 });
      return Response.json(detail(item));
    }
    if (path === '/api/jobs' && method === 'POST') {
      const payload = body.input_payload as Record<string, unknown>;
      const id = `job-${jobs.size + 1}`;
      const target = store.get(String(payload.project_id));
      const text = `Written by ${id}: the lantern flared beside the door.`;
      const write = () => {
        if (!target) return;
        const action = String(payload.action);
        if (action === 'outline') {
          target.outline = [
            { chapter: 1, title: 'The Orchard', beats: [{ id: 'beat-1', text: 'Mira finds a fruit that remembers her.', page_id: null }] },
            { chapter: 2, title: 'The Market', beats: [{ id: 'beat-2', text: 'She trades it for a lullaby.', page_id: null }] },
          ];
          return;
        }
        const beatChapter = target.outline.find((entry) => entry.beats.some((beat) => beat.id === payload.beat_id));
        if (beatChapter) {
          const beat = beatChapter.beats.find((entry) => entry.id === payload.beat_id);
          target.pages = [...target.pages, page(`${id}-page`, text, { chapter: beatChapter.chapter, position: target.pages.length + 1 })];
          if (beat) beat.page_id = `${id}-page`;
          return;
        }
        const range = payload.selection as { page_id: string; start: number; end: number } | null | undefined;
        const reworked = range ? target.pages.find((entry) => entry.id === range.page_id) : null;
        if (range && reworked) {
          // A selection job proposes blocks for the range and leaves the page as it is (ST-6.2).
          const proposed: Block[] = [{ kind: 'narration', text, speaker_id: null, attribution: null }];
          const pages = target.pages.map((entry) => (entry === reworked ? { ...entry, blocks: [...entry.blocks.slice(0, range.start), ...proposed, ...entry.blocks.slice(range.end)] } : entry));
          target.versions.push({
            id: `${target.id}-v${target.versions.length + 1}`, kind: action, title: '', version_number: target.versions.length + 1, source_job_id: id, created_at: now, pages,
            selection: { page_id: range.page_id, start: range.start, end: range.end, original: reworked.blocks.slice(range.start, range.end), proposed, status: 'pending' },
          });
          return;
        }
        if (['rewrite', 'expand', 'dialogue', 'summarize'].includes(action)) {
          target.versions.push({ id: `${target.id}-v${target.versions.length + 1}`, kind: action, title: '', version_number: target.versions.length + 1, source_job_id: id, created_at: now, pages: [page(`${id}-page`, text)] });
          return;
        }
        const last = visibleOf(target).at(-1);
        const chapter = payload.new_chapter ? (last?.chapter ?? 0) + 1 : last?.chapter ?? 1;
        const interactive = payload.interaction_mode === 'story';
        target.pages = [...target.pages, page(`${id}-page`, text, {
          chapter, position: target.pages.length + 1, title: payload.new_chapter ? 'The Lantern Road' : '', parent: last?.id ?? null,
          moves: interactive ? ['Follow the lantern', 'Call out'] : [],
        })];
        if (interactive && payload.user_response) {
          target.moves.push({ ...move(`${id}-move`, `${id}-page`, String(payload.user_response)), chosen_suggestion: String(payload.chosen_suggestion ?? '') });
        }
        if (!target.title) target.title = 'A Titled Story';
      };
      const job = { id, module: 'storyteller', type: 'story.generate', status: holdJobs ? 'queued' : 'completed', resource_class: 'gpu:llm', created_at: now, updated_at: now, priority: 0, progress: { current: 2, total: 2 }, input_payload: payload, output_refs: [{ kind: 'story', project_id: payload.project_id, content: text }], logs: [], stages: [] };
      jobs.set(id, job);
      if (holdJobs) held.set(id, () => { write(); job.status = 'completed'; });
      else write();
      return Response.json(job);
    }
    if (path === '/api/jobs') return Response.json({ jobs: legacyJobs });
    const jobMatch = path.match(/^\/api\/jobs\/([^/]+)$/);
    if (jobMatch && jobs.has(decodeURIComponent(jobMatch[1]))) return Response.json(jobs.get(decodeURIComponent(jobMatch[1])));
    return new Response('not found', { status: 404 });
  });
  vi.stubGlobal('fetch', fetchMock);
  const calls = (method: string, pattern: RegExp) => fetchMock.mock.calls.filter(([input, init]) => {
    const url = typeof input === 'string' ? input : input instanceof Request ? input.url : input.toString();
    const callMethod = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
    return callMethod === method && pattern.test(new URL(url, 'http://localhost').pathname);
  });
  const jobPayload = () => {
    const call = calls('POST', /^\/api\/jobs$/)[0];
    return call ? (JSON.parse(String(call[1]?.body)) as { input_payload: Record<string, unknown>; stages: Array<{ label: string }> }) : null;
  };
  const setJobStatus = (id: string, status: string) => {
    const job = jobs.get(id);
    if (!job) throw new Error(`No job ${id}`);
    if (status === 'completed') held.get(id)?.();
    else job.status = status;
  };
  return { store, calls, jobPayload, setJobStatus };
}

/** Captures the `/events` subscriptions, so a test can send a job's lifecycle events. */
export function jobEvents() {
  const handlers = new Map<string, Array<(payload: unknown) => void>>();
  vi.spyOn(omnixEventClient, 'subscribe').mockImplementation((eventName, handler) => {
    handlers.set(eventName, [...(handlers.get(eventName) ?? []), handler as (payload: unknown) => void]);
    return () => undefined;
  });
  return (eventName: string, payload: unknown) => handlers.get(eventName)?.forEach((handler) => handler(payload));
}

export function library() {
  return screen.getByRole('complementary', { name: 'Story library' });
}

export function recentStories() {
  const section = within(library()).getByText('Recent stories').closest('section');
  if (!section) throw new Error('Recent stories section is missing');
  return section as HTMLElement;
}
