import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { storyImportMarkerKey } from './storyImport';
import { now, renderStoryteller, page, character, project, move, storyServer, jobEvents, library, recentStories, type Block } from '../../test/storytellerServer';

/** Each sink opened to read a line aloud; a line is heard until the test lets it end. */
const sinks: Array<{ samples: number; stopped: boolean; paused: boolean; heard: () => void }> = [];
vi.mock('../assistant', async (original) => ({
  ...await original<typeof import('../assistant')>(),
  openPcmSink: async () => {
    let heard = () => undefined as void;
    const ended = new Promise<void>((resolve) => { heard = resolve; });
    const sink = { samples: 0, stopped: false, paused: false, heard: () => heard() };
    sinks.push(sink);
    return {
      push: (samples: Int16Array) => { sink.samples += samples.length; },
      end: () => ended,
      pause: () => { sink.paused = true; },
      resume: () => { sink.paused = false; },
      stop: () => { sink.stopped = true; heard(); },
    };
  },
}));


beforeEach(() => {
  window.localStorage.setItem(storyImportMarkerKey, now);
});

afterEach(() => {
  sinks.length = 0;
  window.history.replaceState(null, '', '/');
  window.localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('StorytellerWorkspace', () => {
  it('shows the selected project as the manuscript', async () => {
    storyServer();
    renderStoryteller();
    const manuscript = await screen.findByRole('region', { name: 'Story manuscript' });
    expect(await within(manuscript).findByText('The orchard rang like crystal at sunset.')).toBeInTheDocument();
    expect(screen.getByRole('complementary', { name: 'Story controls' })).toBeInTheDocument();
    expect(screen.getByRole('complementary', { name: 'Story outline' })).toBeInTheDocument();
    expect(within(recentStories()).getByRole('button', { name: /The Glass Orchard/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Continue story/ })).toBeInTheDocument();
  });

  it('shows no fake controls and no developer panels', async () => {
    storyServer();
    renderStoryteller();
    expect(await screen.findByText('The orchard rang like crystal at sunset.')).toBeInTheDocument();
    // ST-0.3: no fake version strip, genre tags, Output "Clear", chapter media "Play", "Queue chapter".
    expect(screen.queryByRole('region', { name: 'Recent versions' })).not.toBeInTheDocument();
    expect(screen.queryByText(/^v7$/)).not.toBeInTheDocument();
    for (const tag of ['Fantasy', 'Slice of Life']) expect(screen.queryByText(tag)).not.toBeInTheDocument();
    for (const name of ['Clear', 'Play', 'Queue chapter']) expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
    // ST-0.4: one module title; ST-4.5: the developer audio panels are gone with the parallel audio code.
    expect(screen.getAllByRole('heading', { level: 2, name: 'Storyteller' })).toHaveLength(1);
    expect(screen.queryByRole('region', { name: 'Story remote status' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Story audio mapping JSON')).not.toBeInTheDocument();
    // ST-0.5: the empty library sections are hidden.
    for (const name of ['Characters', 'World Notes', 'Prompts']) expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: 'Show developer details' })).not.toBeInTheDocument();
  });

  it('shows an empty manuscript before the first story', async () => {
    storyServer({ projects: [] });
    renderStoryteller();
    expect((await screen.findAllByText(/Start with a premise/)).length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: 'Save version' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Export Markdown' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Move to Trash' })).toBeDisabled();
  });

  it('sorts projects into Stories and Interactive, and starts a new draft', async () => {
    storyServer({ projects: [project('project-1'), project('project-2', { title: 'The Brass Door', mode: 'interactive' })] });
    renderStoryteller();
    const sections = await within(await screen.findByRole('complementary', { name: 'Story library' })).findByRole('navigation', { name: 'Story library sections' });
    expect(within(sections).getAllByRole('button').map((button) => button.textContent)).toEqual(['Stories', 'Interactive']);
    const storiesPane = await within(library()).findByRole('region', { name: 'Stories library pane' });
    expect(await within(storiesPane).findByRole('button', { name: /The Glass Orchard/ })).toBeInTheDocument();
    expect(within(storiesPane).queryByRole('button', { name: /The Brass Door/ })).not.toBeInTheDocument();
    fireEvent.click(within(sections).getByRole('button', { name: 'Interactive' }));
    const interactivePane = await within(library()).findByRole('region', { name: 'Interactive library pane' });
    expect(within(interactivePane).getByRole('button', { name: /The Brass Door/ })).toBeInTheDocument();

    fireEvent.click(within(library()).getByRole('button', { name: 'New story draft' }));
    expect(await screen.findByText('New draft ready. Add a premise to begin.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save version' })).toBeDisabled();
  });

  it('creates a project for a new draft and shows the page its job wrote', async () => {
    const server = storyServer({ projects: [] });
    renderStoryteller();
    expect(await screen.findByText('LM Studio')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Provider'), { target: { value: 'lmstudio' } });
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'The Glass Orchard' } });
    fireEvent.change(screen.getByLabelText(/Premise/), { target: { value: 'A city grows fruit made of memory.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Queue story' }));

    expect(await screen.findByText('Story generated: job-1')).toBeInTheDocument();
    const createBody = JSON.parse(String(server.calls('POST', /^\/api\/story\/projects$/)[0]?.[1]?.body)) as Record<string, unknown>;
    expect(createBody).toMatchObject({ title: 'The Glass Orchard', premise: 'A city grows fruit made of memory.', mode: 'writing' });
    const body = server.jobPayload();
    expect(body?.stages.map((stage) => stage.label)).toEqual(['Write story', 'Store story']);
    expect(body?.input_payload).toMatchObject({ action: 'draft', interaction_mode: 'writing', project_id: 'project-new-1', provider_id: 'lmstudio' });
    for (const key of ['source_text', 'source_job_id', 'source_library_item_id', 'generate_title', 'prompt_template_id', 'suggested_choice']) {
      expect(body?.input_payload).not.toHaveProperty(key);
    }
    const manuscript = screen.getByRole('region', { name: 'Story manuscript' });
    expect(await within(manuscript).findByText(/Written by job-1/)).toBeInTheDocument();
  });

  it('moves the project to Trash, restores it, and deletes forever', async () => {
    const server = storyServer({ projects: [project('project-1', { title: 'Flying Cat' }), project('project-2', { title: 'Moon Bakery' })] });
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderStoryteller();
    expect(await screen.findByText('The orchard rang like crystal at sunset.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Move to Trash' }));

    expect(await screen.findByText('Moved "Flying Cat" to Trash.')).toBeInTheDocument();
    await waitFor(() => expect(within(recentStories()).queryByRole('button', { name: /Flying Cat/ })).not.toBeInTheDocument());
    expect(within(recentStories()).getByRole('button', { name: /Moon Bakery/ })).toBeInTheDocument();
    const trashPane = within(library()).getByRole('region', { name: 'Trash library pane' });
    fireEvent.click(await within(trashPane).findByRole('button', { name: 'Restore Flying Cat' }));
    expect(await screen.findByText('Restored "Flying Cat".')).toBeInTheDocument();
    expect(await within(recentStories()).findByRole('button', { name: /Flying Cat/ })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Move to Trash' })).not.toBeDisabled());

    fireEvent.click(screen.getByRole('button', { name: 'Move to Trash' }));
    const trash = await within(library()).findByRole('region', { name: 'Trash library pane' });
    fireEvent.click(await within(trash).findByRole('button', { name: 'Delete Flying Cat forever' }));
    expect(await screen.findByText('Deleted "Flying Cat" forever.')).toBeInTheDocument();
    expect(server.calls('DELETE', /^\/api\/story\/projects\/project-1$/)).toHaveLength(1);
    expect(server.store.has('project-1')).toBe(false);
  });

  it('keeps one panel beside the manuscript, with a tab for writing, the cast, the world and audio', async () => {
    storyServer();
    renderStoryteller();
    expect(await screen.findByText('The orchard rang like crystal at sunset.')).toBeInTheDocument();
    const tabs = within(screen.getByRole('tablist', { name: 'Story panel' })).getAllByRole('tab');
    expect(tabs.map((tab) => tab.textContent)).toEqual(['Write', 'Characters', 'World', 'Audio']);
    expect(screen.getByRole('tabpanel', { name: 'Write' })).toContainElement(screen.getByRole('complementary', { name: 'Story controls' }));
    // The arrow keys move between tabs, and only the chosen tab's panel shows.
    fireEvent.keyDown(tabs[0], { key: 'ArrowLeft' });
    expect(tabs[3]).toHaveAttribute('aria-selected', 'true');
    expect(tabs[3]).toHaveFocus();
    expect(screen.getByRole('tabpanel', { name: 'Audio' })).toBeVisible();
    expect(screen.queryByRole('tabpanel', { name: 'Write' })).not.toBeInTheDocument();
    fireEvent.keyDown(tabs[3], { key: 'Home' });
    expect(screen.getByRole('complementary', { name: 'Story controls' })).toBeVisible();
  });

  it('exports the story as an EPUB, Word or PDF book the server builds', async () => {
    const createObjectUrl = vi.fn(() => 'blob:story-book');
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectUrl });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });
    const downloads: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) { downloads.push(this.download); });
    const server = storyServer();
    renderStoryteller();
    expect(await screen.findByText('The orchard rang like crystal at sunset.')).toBeInTheDocument();
    for (const [label, format] of [['Export EPUB', 'epub'], ['Export Word (DOCX)', 'docx'], ['Export PDF', 'pdf']]) {
      fireEvent.click(screen.getByRole('button', { name: label }));
      expect(await screen.findByText(`Exported project-1.${format}.`)).toBeInTheDocument();
    }
    expect(downloads).toEqual(['project-1.epub', 'project-1.docx', 'project-1.pdf']);
    expect(server.calls('GET', /^\/api\/story\/projects\/project-1\/export\/pdf$/)).toHaveLength(1);
  });

  it('saves a version, restores it, and exports Markdown', async () => {
    const createObjectUrl = vi.fn(() => 'blob:story-export');
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectUrl });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    const server = storyServer({ projects: [project('project-1', { title: 'Saved Orchard' })] });
    renderStoryteller();
    expect(await screen.findByText('The orchard rang like crystal at sunset.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Export Markdown' }));
    expect(await screen.findByText('Exported saved-orchard.md.')).toBeInTheDocument();
    expect(createObjectUrl).toHaveBeenCalledTimes(1);
    expect(clickSpy).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: 'Save version' }));
    expect(await screen.findByText('Saved version 1 of "Saved Orchard".')).toBeInTheDocument();
    const versions = await screen.findByRole('region', { name: 'Story versions' });
    expect(within(versions).getByText('Saved')).toBeInTheDocument();
    fireEvent.click(within(versions).getByRole('button', { name: 'Restore version 1' }));
    expect(await screen.findByText('Restored version 1.')).toBeInTheDocument();
    expect(server.calls('POST', /^\/api\/story\/projects\/project-1\/versions\/project-1-v1\/restore$/)).toHaveLength(1);
  });

  it('shows each spoken line with its speaker, flags one outside the cast, and exports both', async () => {
    let exported: Blob | null = null;
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn((blob: Blob) => { exported = blob; return 'blob:story-export'; }) });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    storyServer({
      projects: [project('project-1', {
        characters: [character('mira', 'Mira')],
        pages: [page('p1', '', {
          blocks: [
            { kind: 'narration', text: 'The gate creaked open.', speaker_id: null, attribution: null },
            { kind: 'dialogue', text: 'Who goes there?', speaker_id: 'mira', attribution: 'tagged' },
            { kind: 'dialogue', text: 'Only the wind.', speaker_id: 'stranger', attribution: 'unverified' },
          ],
        })],
      })],
    });
    renderStoryteller();
    const manuscript = await screen.findByRole('region', { name: 'Story manuscript' });
    const tagged = (await within(manuscript).findByText('Who goes there?')).closest('p');
    expect(tagged).not.toHaveClass('storyteller-line-unverified');
    expect(within(tagged as HTMLElement).getByText('Mira')).toBeInTheDocument();
    const flagged = within(manuscript).getByText('Only the wind.').closest('p');
    expect(flagged).toHaveClass('storyteller-line-unverified');
    expect(within(flagged as HTMLElement).getByText('not in cast')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Export Markdown' }));
    await screen.findByText(/^Exported /);
    const markdown = await new Promise<string>((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.readAsText(exported as unknown as Blob);
    });
    expect(markdown).toContain('**Mira:** Who goes there?');
    expect(markdown).toContain('**stranger (unverified):** Only the wind.');
  });

  it('accepts and dismisses suggested characters, adds one, and adds a world note', async () => {
    const server = storyServer({
      projects: [project('project-1', {
        characters: [character('mira', 'Mira', { role: 'lead' }), character('tobin', 'Tobin', { suggested: true }), character('ghost', 'Ghost', { suggested: true })],
      })],
    });
    renderStoryteller();
    // A page's suggestions show as a count on the Characters tab (ST-6.4).
    const charactersTab = await screen.findByRole('tab', { name: /Characters/ });
    await within(charactersTab).findByText('2');
    fireEvent.click(charactersTab);
    expect(charactersTab).toHaveAttribute('aria-selected', 'true');
    const suggestions = await screen.findByRole('list', { name: 'Suggested characters' });
    fireEvent.click(within(suggestions).getByRole('button', { name: 'Accept Tobin' }));
    // Each save finishes (its buttons come back) before the next change, which builds on the saved cast.
    await waitFor(() => expect(screen.getByRole('button', { name: 'Remove Tobin' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss Ghost' }));
    await waitFor(() => expect(screen.queryByRole('list', { name: 'Suggested characters' })).not.toBeInTheDocument());
    await waitFor(() => expect(screen.getByRole('button', { name: 'Remove Tobin' })).toBeEnabled());
    expect(server.store.get('project-1')?.characters.map((entry) => entry.id)).toEqual(['mira', 'tobin']);
    expect(server.store.get('project-1')?.characters[1].suggested).toBe(false);

    const add = screen.getByRole('form', { name: 'Add character' });
    fireEvent.change(within(add).getByLabelText('Character name'), { target: { value: 'Old Wren' } });
    fireEvent.change(within(add).getByLabelText('Also called'), { target: { value: 'Wren, the keeper' } });
    fireEvent.click(within(add).getByRole('button', { name: 'Add character' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Remove Old Wren' })).toBeEnabled());
    expect(server.store.get('project-1')?.characters).toHaveLength(3);
    expect(server.store.get('project-1')?.characters[2]).toMatchObject({ id: 'old-wren', name: 'Old Wren', aliases: ['Wren', 'the keeper'], suggested: false });

    fireEvent.click(screen.getByRole('tab', { name: 'World' }));
    const note = screen.getByRole('form', { name: 'Add note' });
    fireEvent.change(within(note).getByLabelText('Note title'), { target: { value: 'The orchard' } });
    fireEvent.change(within(note).getByLabelText('Note text'), { target: { value: 'Fruit holds one memory each.' } });
    fireEvent.click(within(note).getByRole('button', { name: 'Add note' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Remove The orchard' })).toBeEnabled());
    expect(server.store.get('project-1')?.notes).toMatchObject([{ kind: 'world', title: 'The orchard', body: 'Fruit holds one memory each.' }]);
    expect(server.calls('PUT', /^\/api\/story\/projects\/project-1\/characters$/)).toHaveLength(3);
  });

  it('keeps what the writer typed in a bible form when the save fails', async () => {
    storyServer({ projects: [project('project-1', { characters: [character('mira', 'Mira')] })] });
    const answer = globalThis.fetch;
    vi.stubGlobal('fetch', (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof Request ? input.url : input.toString();
      const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
      return method === 'PUT' && url.endsWith('/characters')
        ? Promise.resolve(Response.json({ detail: 'The story bible is not available.' }, { status: 503 }))
        : answer(input, init);
    });
    renderStoryteller();
    fireEvent.click(await screen.findByRole('tab', { name: /Characters/ }));
    await screen.findByRole('button', { name: 'Edit Mira' });
    const add = screen.getByRole('form', { name: 'Add character' });
    fireEvent.change(within(add).getByLabelText('Character name'), { target: { value: 'Old Wren' } });
    fireEvent.click(within(add).getByRole('button', { name: 'Add character' }));
    await waitFor(() => expect(within(add).getByRole('button', { name: 'Add character' })).toBeEnabled());
    expect(within(add).getByLabelText('Character name')).toHaveValue('Old Wren');

    fireEvent.click(screen.getByRole('button', { name: 'Edit Mira' }));
    const edit = screen.getByRole('form', { name: 'Save Mira' });
    fireEvent.change(within(edit).getByLabelText('Character name'), { target: { value: 'Mira Vale' } });
    fireEvent.click(within(edit).getByRole('button', { name: 'Save Mira' }));
    await waitFor(() => expect(within(edit).getByRole('button', { name: 'Save Mira' })).toBeEnabled());
    expect(screen.getByRole('form', { name: 'Save Mira' })).toBeInTheDocument();
    expect(within(edit).getByLabelText('Character name')).toHaveValue('Mira Vale');
  });

  it('plans the story, saves the edited plan, and drafts a beat into its chapter', async () => {
    const server = storyServer();
    renderStoryteller();
    expect(await screen.findByText('The orchard rang like crystal at sunset.')).toBeInTheDocument();
    const start = screen.getByRole('form', { name: 'Plan the story' });
    fireEvent.change(within(start).getByLabelText('Chapters'), { target: { value: '2' } });
    fireEvent.click(within(start).getByRole('button', { name: 'Plan the story' }));

    expect(await screen.findByText('The plan is ready: edit it, then draft it beat by beat.')).toBeInTheDocument();
    expect(server.jobPayload()?.input_payload).toMatchObject({ action: 'outline', outline_chapters: 2, project_id: 'project-1' });
    expect(server.jobPayload()?.stages[0].label).toBe('Plan story');
    const beat = await screen.findByLabelText('Chapter 2, beat 1');
    expect(beat).toHaveValue('She trades it for a lullaby.');

    // An unsaved edit holds back planning and drafting until it is saved.
    fireEvent.change(beat, { target: { value: 'She trades it for her mother’s lullaby.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add beat to chapter 2' }));
    fireEvent.change(screen.getByLabelText('Chapter 2, beat 2'), { target: { value: 'The market closes.' } });
    expect(screen.getByRole('button', { name: 'Draft Chapter 2, beat 1' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Plan again' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Save plan' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save plan' })).toBeDisabled());
    const saved = server.calls('PUT', /^\/api\/story\/projects\/project-1\/outline$/);
    expect(saved).toHaveLength(1);
    expect(JSON.parse(String(saved[0][1]?.body)).chapters[1].beats).toEqual([
      { id: 'beat-2', text: 'She trades it for her mother’s lullaby.' }, { id: null, text: 'The market closes.' },
    ]);
    expect(server.store.get('project-1')?.outline[1].beats.map((entry) => entry.id)).toEqual(['beat-2', expect.stringMatching(/^beat-new-/)]);

    fireEvent.click(screen.getByRole('button', { name: 'Draft Chapter 2, beat 1' }));
    expect(await screen.findByText(/Drafted in chapter 2: Written by job-2/)).toBeInTheDocument();
    const payload = (JSON.parse(String(server.calls('POST', /^\/api\/jobs$/)[1][1]?.body)) as { input_payload: Record<string, unknown> }).input_payload;
    expect(payload).toMatchObject({ action: 'continue', beat_id: 'beat-2', project_id: 'project-1', interaction_mode: 'writing' });
    expect(screen.queryByRole('button', { name: 'Draft Chapter 2, beat 1' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Draft Chapter 2, beat 2' })).toBeEnabled();
    const outline = screen.getByRole('complementary', { name: 'Story outline' });
    expect(await within(outline).findByRole('button', { name: /Chapter 2/ })).toBeInTheDocument();
  });

  it('keeps presets with their tone and style, and tells the story with the one in use', async () => {
    const server = storyServer();
    renderStoryteller();
    expect(await screen.findByText('The orchard rang like crystal at sunset.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'World' }));
    const add = screen.getByRole('form', { name: 'Add preset' });
    fireEvent.change(within(add).getByLabelText('Preset name'), { target: { value: 'Noir' } });
    fireEvent.change(within(add).getByLabelText('Preset tone'), { target: { value: 'Bleak' } });
    fireEvent.change(within(add).getByLabelText('Preset writing style'), { target: { value: 'Terse' } });
    fireEvent.change(within(add).getByLabelText('Preset instructions'), { target: { value: 'Short sentences.' } });
    fireEvent.click(within(add).getByRole('button', { name: 'Add preset' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Use Noir' })).toBeEnabled());
    expect(server.store.get('project-1')?.notes).toMatchObject([
      { kind: 'preset', title: 'Noir', tone: 'Bleak', writing_style: 'Terse', body: 'Short sentences.' },
    ]);

    fireEvent.click(screen.getByRole('button', { name: 'Use Noir' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Stop using Noir' })).toBeEnabled());
    expect(server.store.get('project-1')).toMatchObject({ preset_id: 'note-1', tone: 'Bleak', writing_style: 'Terse' });
    // The preset's own tone and style become the story's, offered beside the usual ones.
    fireEvent.click(screen.getByRole('tab', { name: 'Write' }));
    expect(screen.getByRole('button', { name: 'Bleak' })).toHaveClass('active');
    expect(screen.getByRole('combobox', { name: 'Writing style' })).toHaveValue('Terse');
    fireEvent.click(screen.getByRole('button', { name: /Continue story/ }));
    await waitFor(() => expect(server.jobPayload()).not.toBeNull());
    expect(server.jobPayload()?.input_payload).toMatchObject({ tone: 'Bleak', writing_style: 'Terse' });

    fireEvent.click(screen.getByRole('tab', { name: 'World' }));
    fireEvent.click(screen.getByRole('button', { name: 'Stop using Noir' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Use Noir' })).toBeEnabled());
    expect(server.store.get('project-1')?.preset_id).toBe('');
  });

  it('builds the outline from the project chapters', async () => {
    storyServer({
      projects: [project('project-1', {
        pages: [
          page('p1', 'The orchard rang like crystal at sunset.', { title: 'The Glass Orchard' }),
          page('p2', 'Mira traded a silver thread for a forgotten lullaby.', { chapter: 2, position: 2, title: 'The Memory Market' }),
        ],
      })],
    });
    renderStoryteller();
    const outline = await screen.findByRole('complementary', { name: 'Story outline' });
    const chapterTwo = await within(outline).findByRole('button', { name: /Chapter 2 The Memory Market/ });
    expect(within(outline).getByRole('button', { name: /Chapter 1 The Glass Orchard/ })).toBeInTheDocument();
    fireEvent.click(chapterTwo);
    const manuscript = screen.getByRole('region', { name: 'Story manuscript' });
    expect((await within(manuscript).findAllByRole('heading', { name: 'The Memory Market' })).length).toBeGreaterThan(0);
  });

  it('asks the job for a new chapter and shows the chapter it wrote', async () => {
    const server = storyServer();
    renderStoryteller();
    expect(await screen.findByText('The orchard rang like crystal at sunset.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'New chapter' }));

    expect(await screen.findByText('Added a new chapter.')).toBeInTheDocument();
    expect(server.jobPayload()?.input_payload).toMatchObject({ action: 'continue', new_chapter: true, project_id: 'project-1' });
    const outline = screen.getByRole('complementary', { name: 'Story outline' });
    expect(await within(outline).findByRole('button', { name: /Chapter 2 The Lantern Road/ })).toBeInTheDocument();
  });

  it('continues the story from its project, not from text the browser sends', async () => {
    const server = storyServer();
    renderStoryteller();
    const manuscript = await screen.findByRole('region', { name: 'Story manuscript' });
    expect(await within(manuscript).findByText('The orchard rang like crystal at sunset.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Continue story/ }));

    expect((await within(manuscript).findAllByText(/Written by job-1/)).length).toBeGreaterThan(0);
    const payload = server.jobPayload()?.input_payload;
    expect(payload).toMatchObject({ action: 'continue', interaction_mode: 'writing', project_id: 'project-1', premise: 'A city grows fruit made of memory.', new_chapter: false });
    expect(payload).not.toHaveProperty('source_text');
    expect(within(recentStories()).getAllByRole('button')).toHaveLength(1);
  });

  it('saves a rewrite as a version and leaves the manuscript as it was', async () => {
    const server = storyServer();
    renderStoryteller();
    expect(await screen.findByText('The orchard rang like crystal at sunset.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Rewrite whole story/ }));

    expect(await screen.findByText('The rewrite was saved as a new version; restore it from Story versions to use it.')).toBeInTheDocument();
    expect(server.jobPayload()?.input_payload).toMatchObject({ action: 'rewrite', project_id: 'project-1' });
    const versions = await screen.findByRole('region', { name: 'Story versions' });
    expect(within(versions).getByText('Rewrite')).toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: 'Story manuscript' })).queryByText(/Written by job-1/)).not.toBeInTheDocument();
    expect(screen.getByText('The orchard rang like crystal at sunset.')).toBeInTheDocument();
    expect(screen.queryByText('Enter a premise before generating a story.')).not.toBeInTheDocument();
  });

  it('opens an interactive story in story mode and shows the whole run with the move before its page', async () => {
    const server = storyServer({
      projects: [project('project-1', { mode: 'interactive', pages: [page('p1', 'A secret door opened below the oldest glass tree.')] })],
    });
    renderStoryteller();
    const reader = await screen.findByRole('region', { name: 'Interactive story mode' });
    expect(await within(reader).findByText('A secret door opened below the oldest glass tree.')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Interactive story mode response'), { target: { value: 'I light a lantern and step through.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue with my response' }));

    const second = await within(reader).findByRole('article', { name: 'Page 2' });
    expect(within(second).getByText('I light a lantern and step through.')).toBeInTheDocument();
    expect(within(second).getByText(/Written by job-1/)).toBeInTheDocument();
    // The run keeps its earlier pages; the first can be continued from, the newest cannot.
    const first = within(reader).getByRole('article', { name: 'Page 1' });
    expect(within(first).getByText('A secret door opened below the oldest glass tree.')).toBeInTheDocument();
    expect(within(first).getByRole('button', { name: 'Continue from here' })).toBeInTheDocument();
    expect(within(second).queryByRole('button', { name: 'Continue from here' })).not.toBeInTheDocument();
    expect(within(screen.getByRole('navigation', { name: 'Pages of this run' })).getByRole('button', { name: /2\. I light a lantern/ })).toBeInTheDocument();
    expect(server.jobPayload()?.input_payload).toMatchObject({
      action: 'continue', interaction_mode: 'story', project_id: 'project-1',
      user_response: 'I light a lantern and step through.', chosen_suggestion: null,
    });
  });

  it('offers the moves the model suggested with the newest page, and sends one as the chosen suggestion', async () => {
    const server = storyServer({
      projects: [project('project-1', { mode: 'interactive', pages: [page('p1', 'A secret door opened.', { moves: ['Open the door carefully', 'Walk away'] })] })],
    });
    renderStoryteller();
    fireEvent.click(await screen.findByRole('button', { name: 'Open the door carefully' }));
    await waitFor(() => expect(server.jobPayload()?.input_payload).toMatchObject({
      interaction_mode: 'story', user_response: 'Open the door carefully', chosen_suggestion: 'Open the door carefully',
    }));
    // The next page brings its own suggestions in place of the first page's.
    expect(await screen.findByRole('button', { name: 'Follow the lantern' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Walk away' })).not.toBeInTheDocument();
  });

  it('starts a new interactive project when a move is made with no story open', async () => {
    const server = storyServer({ projects: [] });
    renderStoryteller();
    fireEvent.click(await screen.findByRole('button', { name: /Interactive Story Mode/ }));
    expect(screen.queryByRole('region', { name: 'Other branches' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Undo last move' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Interactive story mode response'), { target: { value: 'I wake in a lighthouse.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue with my response' }));

    expect(await within(screen.getByRole('region', { name: 'Interactive story mode' })).findByText(/Written by job-1/)).toBeInTheDocument();
    const createBody = JSON.parse(String(server.calls('POST', /^\/api\/story\/projects$/)[0]?.[1]?.body)) as Record<string, unknown>;
    expect(createBody.mode).toBe('interactive');
    expect(server.jobPayload()?.input_payload).toMatchObject({ project_id: 'project-new-1', interaction_mode: 'story', title: null });
  });

  it('undoes the last move, keeps its page as a branch, and opens it again', async () => {
    const server = storyServer({
      projects: [project('project-1', {
        mode: 'interactive',
        pages: [page('p1', 'The tide went out.'), page('p2', 'The boat drifted to the reef.', { parent: 'p1', position: 2 })],
        moves: [move('m2', 'p2', 'I row for the reef')],
      })],
    });
    renderStoryteller();
    const reader = await screen.findByRole('region', { name: 'Interactive story mode' });
    expect(await within(reader).findByText('The boat drifted to the reef.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Undo last move' }));

    await waitFor(() => expect(within(reader).queryByText('The boat drifted to the reef.')).not.toBeInTheDocument());
    expect(server.store.get('project-1')?.pages.map((entry) => entry.hidden)).toEqual([false, true]);
    expect(await screen.findByText(/Undid the last move/)).toBeInTheDocument();
    // The opening page has no move, so there is nothing more to undo.
    expect(screen.getByRole('button', { name: 'Undo last move' })).toBeDisabled();
    const branches = screen.getByRole('region', { name: 'Other branches' });
    expect(within(branches).getByText('After page 1: I row for the reef')).toBeInTheDocument();

    fireEvent.click(within(branches).getByRole('button', { name: 'Open the branch I row for the reef' }));
    expect(await within(reader).findByText('The boat drifted to the reef.')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Other branches' })).not.toBeInTheDocument();
  });

  it('continues from an earlier page, and the next move starts a branch beside the old one', async () => {
    const server = storyServer({
      projects: [project('project-1', {
        mode: 'interactive',
        pages: [page('p1', 'The tide went out.'), page('p2', 'The boat drifted to the reef.', { parent: 'p1', position: 2 })],
        moves: [move('m2', 'p2', 'I row for the reef')],
      })],
    });
    renderStoryteller();
    const reader = await screen.findByRole('region', { name: 'Interactive story mode' });
    const first = await within(reader).findByRole('article', { name: 'Page 1' });
    fireEvent.click(within(first).getByRole('button', { name: 'Continue from here' }));
    await waitFor(() => expect(within(reader).queryByText('The boat drifted to the reef.')).not.toBeInTheDocument());
    expect(server.calls('POST', /^\/api\/story\/projects\/project-1\/pages\/p1\/open$/)).toHaveLength(1);

    fireEvent.change(screen.getByLabelText('Interactive story mode response'), { target: { value: 'I swim for the shore.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue with my response' }));
    expect(await within(reader).findByText('I swim for the shore.')).toBeInTheDocument();
    expect(server.store.get('project-1')?.pages.at(-1)?.parent_page_id).toBe('p1');
    expect(within(screen.getByRole('region', { name: 'Other branches' })).getByText('After page 1: I row for the reef')).toBeInTheDocument();
  });

  it('shows "writing…" while the page is written and the page when its job completes', async () => {
    const emit = jobEvents();
    const server = storyServer({
      holdJobs: true,
      projects: [project('project-1', { mode: 'interactive', pages: [page('p1', 'The tide went out.')] })],
    });
    renderStoryteller();
    const reader = await screen.findByRole('region', { name: 'Interactive story mode' });
    await within(reader).findByText('The tide went out.');
    fireEvent.change(screen.getByLabelText('Interactive story mode response'), { target: { value: 'I wait for the moon.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue with my response' }));
    const controls = screen.getByRole('complementary', { name: 'Interactive story mode controls' });
    expect(await within(controls).findByText('continuing')).toBeInTheDocument();

    server.setJobStatus('job-1', 'running');
    emit('job.running', { job_id: 'job-1' });
    expect(await within(controls).findByText('writing…')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Undo last move' })).toBeDisabled();

    server.setJobStatus('job-1', 'completed');
    emit('job.completed', { job_id: 'job-1' });
    expect(await within(reader).findByText(/Written by job-1/)).toBeInTheDocument();
    expect(await within(controls).findByText('ready')).toBeInTheDocument();
  });

  it('reads each new page aloud once asked to, marks the line being heard, and stops when the player types', async () => {
    const server = storyServer({ projects: [project('project-1', { mode: 'interactive', pages: [page('p1', 'The tide went out.')] })] });
    renderStoryteller();
    const reader = await screen.findByRole('region', { name: 'Interactive story mode' });
    await within(reader).findByText('The tide went out.');
    const aloud = screen.getByRole('region', { name: 'Read aloud' });
    const autoplay = within(aloud).getByLabelText('Read new pages aloud');
    expect(autoplay).not.toBeChecked();
    fireEvent.click(autoplay);

    fireEvent.change(screen.getByLabelText('Interactive story mode response'), { target: { value: 'I wait for the moon.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue with my response' }));
    const line = await within(reader).findByText(/Written by job-1/);
    await waitFor(() => expect(line).toHaveAttribute('aria-current', 'true'));
    const plans = server.calls('POST', /\/speech-plan$/);
    expect(JSON.parse(String(plans[0][1]?.body))).toEqual({ page_id: 'job-1-page' });
    await waitFor(() => expect(sinks[0].samples).toBe(3));
    expect(within(reader).getByText('The tide went out.')).not.toHaveAttribute('aria-current');

    fireEvent.change(screen.getByLabelText('Interactive story mode response'), { target: { value: 'I' } });
    await waitFor(() => expect(line).not.toHaveAttribute('aria-current'));
    expect(sinks[0].stopped).toBe(true);
    expect(within(aloud).getByRole('button', { name: 'Read the newest page' })).toBeInTheDocument();
  });

  it('reads an earlier page aloud on request, and can be paused and stopped', async () => {
    storyServer({ projects: [project('project-1', { mode: 'interactive', pages: [page('p1', 'The tide went out.\n\nGulls cried.')] })] });
    renderStoryteller();
    const reader = await screen.findByRole('region', { name: 'Interactive story mode' });
    fireEvent.click(await within(reader).findByRole('button', { name: 'Read page 1 aloud' }));
    const first = within(reader).getByText('The tide went out.');
    await waitFor(() => expect(first).toHaveAttribute('aria-current', 'true'));
    const aloud = screen.getByRole('region', { name: 'Read aloud' });
    fireEvent.click(within(aloud).getByRole('button', { name: 'Pause' }));
    expect(within(aloud).getByRole('button', { name: 'Resume' })).toBeInTheDocument();
    await waitFor(() => expect(sinks[0].paused).toBe(true));
    fireEvent.click(within(aloud).getByRole('button', { name: 'Resume' }));
    await waitFor(() => expect(sinks[0].paused).toBe(false));
    await waitFor(() => expect(sinks[0].samples).toBe(3));
    sinks[0].heard();
    await waitFor(() => expect(within(reader).getByText('Gulls cried.')).toHaveAttribute('aria-current', 'true'));
    fireEvent.click(within(aloud).getByRole('button', { name: 'Stop' }));
    await waitFor(() => expect(within(reader).getByText('Gulls cried.')).not.toHaveAttribute('aria-current'));
  });

  it('keeps the run as a finished story version', async () => {
    const server = storyServer({
      projects: [project('project-1', { mode: 'interactive', title: 'Low Tide', pages: [page('p1', 'The tide went out.')] })],
    });
    renderStoryteller();
    await screen.findByText('The tide went out.');
    fireEvent.click(screen.getByRole('button', { name: 'Keep this run' }));

    expect(await screen.findByText('Kept this run as version 1; find it in Story versions.')).toBeInTheDocument();
    const kept = server.calls('POST', /^\/api\/story\/projects\/project-1\/versions$/)[0];
    expect(JSON.parse(String(kept?.[1]?.body))).toEqual({ title: 'Low Tide', kind: 'kept_run' });
    expect(within(screen.getByRole('region', { name: 'Story versions' })).getByText('Low Tide')).toBeInTheDocument();
  });

  it('hands the story to Audiobook with its cast, its spoken lines and who said them, and opens the book', async () => {
    const dialogue = (text: string, speaker: string | null, attribution: string | null = 'confident'): Block => ({ kind: 'dialogue', text, speaker_id: speaker, attribution });
    const server = storyServer({
      projects: [project('project-1', {
        title: 'Low Tide',
        characters: [character('c-mara', 'Mara', { aliases: ['the captain'] }), character('c-ghost', 'Ghost', { suggested: true })],
        pages: [
          page('p1', '', { title: 'The Shore', blocks: [
            { kind: 'narration', text: 'The tide went out.', speaker_id: null, attribution: null },
            dialogue('“Hold fast.”', 'c-mara'),
            dialogue('“Boo.”', 'c-ghost'),
          ] }),
          page('p2', '', { chapter: 2, blocks: [dialogue('“Who are you?”', 'c-mara', 'unverified')] }),
        ],
      })],
    });
    renderStoryteller();
    await screen.findByText('The tide went out.');
    fireEvent.click(screen.getByRole('button', { name: 'Narrate in Audiobook' }));

    await waitFor(() => expect(window.location.pathname).toBe('/audiobook'));
    expect(new URL(window.location.href).searchParams.get('project')).toBe('ab:project:story');
    const sent = server.calls('POST', /^\/api\/audiobook\/projects\/import-story$/)[0];
    expect(JSON.parse(String(sent?.[1]?.body))).toEqual({
      title: 'Low Tide',
      story_project_id: 'project-1',
      story_version_id: null,
      chapters: [
        { title: 'The Shore', blocks: [
          { kind: 'narration', text: 'The tide went out.' },
          { kind: 'dialogue', text: '“Hold fast.”', speaker: 'Mara', unverified: false },
          // A suggested character is not in the cast yet: Audiobook's classifier decides.
          { kind: 'dialogue', text: '“Boo.”', speaker: null, unverified: true },
        ] },
        { title: '', blocks: [{ kind: 'dialogue', text: '“Who are you?”', speaker: 'Mara', unverified: true }] },
      ],
      cast: [{ name: 'Mara', aliases: ['the captain'] }],
    });
  });

  it('keeps a run before narrating it, so the book is that version of the story', async () => {
    const server = storyServer({
      projects: [project('project-1', { mode: 'interactive', title: 'Low Tide', pages: [page('p1', 'The tide went out.')] })],
    });
    renderStoryteller();
    await screen.findByText('The tide went out.');
    const controls = screen.getByRole('complementary', { name: 'Interactive story mode controls' });
    fireEvent.click(within(controls).getByRole('button', { name: 'Narrate in Audiobook' }));

    await waitFor(() => expect(window.location.pathname).toBe('/audiobook'));
    const kept = server.calls('POST', /^\/api\/story\/projects\/project-1\/versions$/)[0];
    expect(JSON.parse(String(kept?.[1]?.body))).toEqual({ title: 'Low Tide', kind: 'kept_run' });
    const sent = JSON.parse(String(server.calls('POST', /^\/api\/audiobook\/projects\/import-story$/)[0]?.[1]?.body));
    expect(sent).toMatchObject({ story_version_id: 'project-1-v1', chapters: [{ blocks: [{ kind: 'narration', text: 'The tide went out.' }] }] });
  });

  it('saves read settings on the project', async () => {
    const server = storyServer();
    renderStoryteller();
    expect(await screen.findByText('The orchard rang like crystal at sunset.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Audio' }));
    await waitFor(() => expect(screen.getByLabelText('Story read speed')).not.toBeDisabled());
    fireEvent.change(screen.getByLabelText('Story read speed'), { target: { value: '1.2' } });
    await waitFor(() => expect(server.store.get('project-1')?.read_settings).toMatchObject({ readSpeed: 1.2 }));
    fireEvent.change(screen.getByLabelText('Word notes'), { target: { value: 'Mira: MEER-ah' } });
    fireEvent.blur(screen.getByLabelText('Word notes'));
    await waitFor(() => expect(server.store.get('project-1')?.read_settings).toMatchObject({ readSpeed: 1.2, pronunciation: { Mira: 'MEER-ah' } }));
  });

  it('imports the stories the browser held once, then forgets the old keys', async () => {
    window.localStorage.removeItem(storyImportMarkerKey);
    window.localStorage.setItem('omnix:storyteller:last-draft', JSON.stringify({ title: 'Kept Draft', premise: 'A draft premise.', savedAt: '2026-06-01T00:00:00Z', content: 'The draft began by the river.' }));
    window.localStorage.setItem('omnix:storyteller:trash', JSON.stringify([{ id: 'job:job-old', title: 'Old Story', content: null }]));
    const legacyJob = {
      id: 'job-old', module: 'storyteller', type: 'story.generate', status: 'completed', resource_class: 'gpu:llm',
      created_at: now, updated_at: now, priority: 0, progress: { current: 2, total: 2 },
      input_payload: { title: 'Old Story', premise: 'An old premise.', action: 'draft' },
      output_refs: [{ kind: 'text', content: 'The old story opened at dawn.' }], logs: [], stages: [],
    };
    const server = storyServer({ projects: [], legacyJobs: [legacyJob] });
    renderStoryteller();

    expect((await within(library()).findAllByRole('button', { name: /Kept Draft/ })).length).toBeGreaterThan(0);
    const importBody = JSON.parse(String(server.calls('POST', /^\/api\/story\/projects\/import$/)[0]?.[1]?.body)) as { items: Array<Record<string, unknown>> };
    expect(importBody.items).toEqual([
      expect.objectContaining({ origin_kind: 'local', origin_ref: 'draft:2026-06-01T00:00:00Z', title: 'Kept Draft', text: 'The draft began by the river.', trashed: false }),
      expect.objectContaining({ origin_kind: 'job', origin_ref: 'job-old', title: 'Old Story', text: 'The old story opened at dawn.', trashed: true }),
    ]);
    expect(window.localStorage.getItem('omnix:storyteller:last-draft')).toBeNull();
    expect(window.localStorage.getItem('omnix:storyteller:trash')).toBeNull();
    expect(window.localStorage.getItem(storyImportMarkerKey)).not.toBeNull();
  });
});
