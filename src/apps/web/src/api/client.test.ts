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

test('asset listing follows page cursors and passes the type filter', async () => {
  const requested: string[] = [];
  const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), 'http://localhost');
    requested.push(`${url.pathname}${url.search}`);
    if (url.searchParams.get('cursor') === 'page-2') {
      return Response.json({ assets: [{ id: 'image:older' }], next_cursor: null, has_more: false });
    }
    return Response.json({ assets: [{ id: 'image:newer' }], next_cursor: 'page-2', has_more: true });
  });
  const client = new OmnixApiClient({ fetchImpl: fetchImpl as typeof fetch });

  const response = await client.listAssets({ type: 'image' });

  expect(response.assets.map((asset) => asset.id)).toEqual(['image:newer', 'image:older']);
  expect(response.has_more).toBe(false);
  expect(requested).toEqual([
    '/api/assets?limit=200&type=image',
    '/api/assets?limit=200&type=image&cursor=page-2',
  ]);
});
