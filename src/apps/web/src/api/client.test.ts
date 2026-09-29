import { expect, test, vi } from 'vitest';
import { OmnixApiClient } from './client';

test('chat session listing follows summary cursors until the workspace is complete', async () => {
  const requested: string[] = [];
  const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), 'http://localhost');
    requested.push(`${url.pathname}${url.search}`);
    if (url.searchParams.get('cursor') === 'next/page') {
      return Response.json({ sessions: [{ id: 'chat:older', title: 'Older' }], next_cursor: null });
    }
    return Response.json({
      sessions: [{ id: 'chat:newer', title: 'Newer' }],
      next_cursor: 'next/page',
    });
  });
  const client = new OmnixApiClient({ fetchImpl: fetchImpl as typeof fetch });

  const response = await client.listChatSessions();

  expect(response.sessions.map((session) => session.id)).toEqual([
    'chat:newer',
    'chat:older',
  ]);
  expect(response.next_cursor).toBeNull();
  expect(requested).toEqual([
    '/api/chat/sessions',
    '/api/chat/sessions?limit=100&cursor=next%2Fpage',
  ]);
});
