import { MantineProvider } from '@mantine/core';
import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { omnixTheme } from '../../../design/theme';
import { createTestQueryClient } from '../../../test/renderWithProviders';
import { CharacterMemoryPanel } from './CharacterMemoryPanel';

const record = {
  id: 'memory:1', owner_type: 'character', owner_id: 'jinx', scope: 'global', scope_id: 'profile', category: 'fact',
  source: 'user_saved', content: 'Lives in Toronto', normalized_content: 'lives in toronto', provenance_type: 'user_message',
  revision: 3, created_at: '2026-11-05T00:00:00Z', updated_at: '2026-11-05T00:00:00Z',
};
const suggestion = {
  id: 'candidate:1', owner_type: 'character', owner_id: 'jinx', proposed_category: 'relationship',
  proposed_content: 'Seems to trust Jinx', status: 'pending', created_at: '2026-11-05T00:00:00Z',
};

type Call = { method: string; path: string; body: unknown; query: string };

function serve(view: { records: unknown[]; suggestions: unknown[] }) {
  const calls: Call[] = [];
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : null;
    const url = new URL(request ? request.url : input.toString(), 'http://localhost');
    const method = request?.method ?? init?.method ?? 'GET';
    const text = request ? await request.clone().text() : String(init?.body ?? '');
    calls.push({ method, path: decodeURIComponent(url.pathname), body: text ? JSON.parse(text) : null, query: url.search });
    if (method === 'GET') return Response.json({ owner_id: 'jinx', ...view });
    if (method === 'DELETE' || url.pathname.endsWith('/reject')) return new Response(null, { status: 204 });
    return Response.json(record);
  }));
  return calls;
}

function renderPanel(ownerId = 'jinx', ownerName = 'Jinx') {
  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      <QueryClientProvider client={createTestQueryClient()}>
        <CharacterMemoryPanel ownerId={ownerId} ownerName={ownerName} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

const understanding = {
  relationship: { statement: 'They trust you enough to complain to you.', closeness: 0.6, trust: 0.7, ease: 0.8, corrected: false },
  person: [{
    key: 'humor', aspect: 'humor', statement: 'Teases back when teased', corrected: false,
    earlier: [{ statement: 'Rarely jokes', until: '2026-11-05T00:00:00Z' }],
  }],
  triggers: [{ key: 'trigger1', emotion: 'stressed', pattern: 'Stressed when deadlines move', about: ['manager', 'deadlines'], seen: 2 }],
  own_side: {
    stance: 'You have started to let them in on your plans.',
    promises: [{ key: 'promise1', what: 'Build them a tracking device', kept: false }],
    jokes: [{ key: 'joke1', joke: 'The chocolate stall', seen: 3 }],
  },
  connections: [{ key: 'link1', subject: 'Anna', relation: 'lives in', object: 'Toronto' }],
  moods: [{ key: 'understanding:mood:1', emotion: 'stressed', at: '2026-11-05T00:00:00Z' }],
  episodes: [{ key: 'understanding:episode:1', title: 'Talked about Anna', summary: 'They complained about Anna moving.', at: '2026-11-05T00:00:00Z' }],
  lessons: [{ key: 'lesson1', aspect: 'what_to_avoid', lesson: 'Shuts down when given solutions', advice: 'Listen first', seen: 3, since: '2026-11-05T00:00:00Z' }],
};
const nothingUnderstood = {
  relationship: null, person: [], connections: [], moods: [], episodes: [], lessons: [], triggers: [],
  own_side: { stance: null, promises: [], jokes: [] },
};

describe('how a memory owner sees you', () => {
  it('shows what it understood, in plain words, and says what to expect when there is nothing', async () => {
    serve({ records: [], suggestions: [], understanding } as never);
    renderPanel();
    expect(await screen.findByText('They trust you enough to complain to you.')).toBeTruthy();
    expect(screen.getByText(/Closeness 60%/)).toBeTruthy();
    expect(screen.getByText('Teases back when teased')).toBeTruthy();
    expect(screen.getByText('Anna lives in Toronto')).toBeTruthy();
    expect(screen.getByText('stressed')).toBeTruthy();
    expect(screen.getByText('They complained about Anna moving.')).toBeTruthy();
    const lesson = screen.getByText('Shuts down when given solutions').closest('li') as HTMLElement;
    expect(within(lesson).getByText(/What to avoid · seen 3 times/)).toBeTruthy();
    expect(within(lesson).getByText('So Jinx will: Listen first')).toBeTruthy();
    expect(within(lesson).queryByRole('button', { name: 'Edit' })).toBeNull();
    const trigger = screen.getByText('Stressed when deadlines move').closest('li') as HTMLElement;
    expect(within(trigger).getByText('Stressed · about manager, deadlines · seen 2 times')).toBeTruthy();
    const before = screen.getByText('Rarely jokes').closest('li') as HTMLElement;
    expect(within(before).getByText(/^Humor · before /)).toBeTruthy();
    expect(within(before).queryByRole('button', { name: 'Edit' })).toBeNull();
    const side = screen.getByRole('list', { name: "Jinx's side" });
    expect(within(side).getByText('You have started to let them in on your plans.')).toBeTruthy();
    expect(within(side).getByText('Build them a tracking device')).toBeTruthy();
    expect(within(side).getByText('Running joke · seen 3 times')).toBeTruthy();
    vi.unstubAllGlobals();

    serve({ records: [], suggestions: [], understanding: nothingUnderstood } as never);
    renderPanel('maya', 'Maya');
    expect(await screen.findByText(/reads it back/)).toBeTruthy();
  });

  it('forgets one item by its key, and asks first', async () => {
    const calls = serve({ records: [], suggestions: [], understanding } as never);
    renderPanel();
    const row = (await screen.findByText('They complained about Anna moving.')).closest('li') as HTMLElement;
    fireEvent.click(within(row).getByRole('button', { name: 'Forget' }));
    expect(calls.filter((call) => call.method === 'DELETE')).toEqual([]);
    fireEvent.click(within(row).getByRole('button', { name: 'Forget' }));
    await waitFor(() => expect(calls.find((call) => call.method === 'DELETE')?.path).toBe(
      '/api/memory-owners/jinx/understanding/episode/understanding:episode:1',
    ));
    const lesson = screen.getByText('Shuts down when given solutions').closest('li') as HTMLElement;
    fireEvent.click(within(lesson).getByRole('button', { name: 'Forget' }));
    fireEvent.click(within(lesson).getByRole('button', { name: 'Forget' }));
    await waitFor(() => expect(calls.filter((call) => call.method === 'DELETE').map((call) => call.path)).toContain(
      '/api/memory-owners/jinx/understanding/lesson/lesson1',
    ));
    for (const [text, path] of [
      ['Stressed when deadlines move', '/api/memory-owners/jinx/understanding/trigger/trigger1'],
      ['Rarely jokes', '/api/memory-owners/jinx/understanding/earlier/humor'],
      ['Build them a tracking device', '/api/memory-owners/jinx/understanding/promise/promise1'],
      ['The chocolate stall', '/api/memory-owners/jinx/understanding/joke/joke1'],
      ['You have started to let them in on your plans.', '/api/memory-owners/jinx/understanding/stance/current'],
    ]) {
      const row = screen.getByText(text).closest('li') as HTMLElement;
      fireEvent.click(within(row).getByRole('button', { name: 'Forget' }));
      fireEvent.click(within(row).getByRole('button', { name: 'Forget' }));
      await waitFor(() => expect(calls.filter((call) => call.method === 'DELETE').map((call) => call.path)).toContain(path));
    }
  });

  it('rewords a note, and offers no rewording of what happened', async () => {
    const calls = serve({ records: [], suggestions: [], understanding } as never);
    renderPanel();
    const note = (await screen.findByText('Teases back when teased')).closest('li') as HTMLElement;
    fireEvent.click(within(note).getByRole('button', { name: 'Edit' }));
    fireEvent.change(within(note).getByRole('textbox'), { target: { value: 'Dry humor' } });
    fireEvent.click(within(note).getByRole('button', { name: 'Save' }));
    await waitFor(() => {
      const call = calls.find((item) => item.method === 'PATCH');
      expect(call?.path).toBe('/api/memory-owners/jinx/understanding/person/humor');
      expect(call?.body).toEqual({ text: 'Dry humor' });
    });
    const episode = screen.getByText('They complained about Anna moving.').closest('li') as HTMLElement;
    expect(within(episode).queryByRole('button', { name: 'Edit' })).toBeNull();
  });
});

describe('a memory owner\'s memory tab', () => {
  it('shows what is remembered, and says so when nothing is', async () => {
    serve({ records: [record], suggestions: [] });
    renderPanel();
    expect(await screen.findByText('Lives in Toronto')).toBeTruthy();
    expect(screen.getByText('1 memory')).toBeTruthy();
    vi.unstubAllGlobals();

    serve({ records: [], suggestions: [] });
    renderPanel('maya', 'Maya');
    expect(await screen.findByText(/Nothing yet/)).toBeTruthy();
  });

  it('corrects a memory, sending the revision it was read at', async () => {
    const calls = serve({ records: [record], suggestions: [] });
    renderPanel();
    await screen.findByText('Lives in Toronto');

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    fireEvent.change(screen.getByLabelText('Edit memory'), { target: { value: 'Lives in Montreal' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(calls.some((call) => call.method === 'PATCH')).toBe(true));
    const patch = calls.find((call) => call.method === 'PATCH');
    expect(patch?.path).toBe('/api/memory-owners/jinx/records/memory:1');
    expect(patch?.body).toEqual({ content: 'Lives in Montreal', expected_revision: 3 });
  });

  it('forgets only after asking', async () => {
    const calls = serve({ records: [record], suggestions: [] });
    renderPanel();
    await screen.findByText('Lives in Toronto');

    fireEvent.click(screen.getByRole('button', { name: 'Forget' }));
    expect(calls.some((call) => call.method === 'DELETE')).toBe(false);
    expect(screen.getByText('Forget this?')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Forget' }));
    await waitFor(() => expect(calls.some((call) => call.method === 'DELETE')).toBe(true));
    expect(calls.find((call) => call.method === 'DELETE')?.query).toContain('expected_revision=3');
  });

  it('keeps or dismisses a suggestion', async () => {
    const calls = serve({ records: [], suggestions: [suggestion] });
    renderPanel();
    const row = (await screen.findByText('Seems to trust Jinx')).closest('li') as HTMLElement;

    fireEvent.click(within(row).getByRole('button', { name: 'Keep' }));
    await waitFor(() => expect(calls.some((call) => call.path.endsWith('/suggestions/candidate:1/approve'))).toBe(true));

    fireEvent.click(within(row).getByRole('button', { name: 'Dismiss' }));
    await waitFor(() => expect(calls.some((call) => call.path.endsWith('/suggestions/candidate:1/reject'))).toBe(true));
  });

  it('adds a memory of the chosen type', async () => {
    const calls = serve({ records: [], suggestions: [] });
    renderPanel();
    await screen.findByText(/Nothing yet/);

    fireEvent.change(screen.getByLabelText('Add a memory'), { target: { value: ' Prefers mornings ' } });
    fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'preference' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));

    await waitFor(() => expect(calls.some((call) => call.method === 'POST')).toBe(true));
    expect(calls.find((call) => call.method === 'POST')?.body).toEqual({ category: 'preference', content: 'Prefers mornings' });
  });

  it('shows the System Assistant through the same routes', async () => {
    const calls = serve({ records: [], suggestions: [] });
    renderPanel('system-assistant', 'System Assistant');
    expect(await screen.findByText('What System Assistant remembers')).toBeTruthy();
    expect(calls[0].path).toBe('/api/memory-owners/system-assistant');
  });
});
