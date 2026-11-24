import { afterEach, describe, expect, it, vi } from 'vitest';
import { saveRunScript } from './podcastTakes';

type Call = { method: string; path: string; body: unknown };

function stubScripts(lines: Array<{ id: string; speaker: string; text: string }> | null) {
  const calls: Call[] = [];
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    // The gateway client re-issues each call as (path, init).
    const method = init?.method ?? 'GET';
    calls.push({ method, path: new URL(String(input), 'http://localhost').pathname, body: init?.body ? JSON.parse(String(init.body)) : null });
    if (method === 'DELETE') return new Response(null, { status: 204 });
    if (!lines) return Response.json({ detail: 'Scripts need PostgreSQL.' }, { status: 503 });
    return Response.json({ id: 'script-1', title: 'x', revision: 1, lines: lines.map((line, position) => ({ ...line, position, takes: [] })) });
  }));
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

describe('saveRunScript', () => {
  it('saves the run as a script and names each segment\'s line', async () => {
    const calls = stubScripts([{ id: 'l1', speaker: 'Ada', text: 'Hello.' }, { id: 'l2', speaker: 'Ben', text: 'Hi.' }]);
    expect(await saveRunScript(' Show ', [{ speaker: 'Ada', text: 'Hello.' }, { speaker: 'Ben', text: ' Hi. ' }])).toEqual({ scriptId: 'script-1', lineIds: ['l1', 'l2'] });
    expect(calls).toHaveLength(1);
    expect(calls[0].body).toMatchObject({ title: 'Show (podcast)', text: 'Ada: Hello.\nBen:  Hi. ', settings: { source: 'podcast' } });
  });

  it('deletes a script whose lines do not match the run, and renders as before', async () => {
    const calls = stubScripts([{ id: 'l1', speaker: 'Ada', text: 'Hello. Hi.' }]);
    expect(await saveRunScript('Show', [{ speaker: 'Ada', text: 'Hello.' }, { speaker: 'Ada', text: 'Hi.' }])).toBeNull();
    expect(calls.map((call) => `${call.method} ${call.path}`)).toEqual(['POST /api/voice/scripts', 'DELETE /api/voice/scripts/script-1']);
  });

  it('renders as before when scripts cannot be saved', async () => {
    stubScripts(null);
    expect(await saveRunScript('', [{ speaker: 'Ada', text: 'Hello.' }])).toBeNull();
  });
});
