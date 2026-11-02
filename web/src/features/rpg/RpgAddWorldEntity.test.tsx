import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RpgAddWorldEntity } from './RpgAddWorldEntity';
import type { RpgAuthoringTopic } from './api/rpgWorldAuthoringClient';

describe('RpgAddWorldEntity', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('adds an entry to the topic with the hash it read', async () => {
    const bodies: unknown[] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const isRequest = typeof input === 'object' && 'method' in input;
      bodies.push(JSON.parse(isRequest ? await (input as Request).clone().text() : String(init?.body ?? '{}')));
      return new Response(JSON.stringify({ ok: true, topic: {}, entity: { id: 'npc:hollis' }, stale_topic_ids: [], stale_entity_ids: [] }),
        { status: 200, headers: { 'content-type': 'application/json' } });
    }));
    const topic = { topic_id: 'characters', draft_revision: 3, content_hash: 'sha256:old' } as unknown as RpgAuthoringTopic;
    render(<QueryClientProvider client={new QueryClient()}><RpgAddWorldEntity label="Characters" topic={topic} worldId="world:a" /></QueryClientProvider>);
    fireEvent.change(screen.getByLabelText('Id'), { target: { value: 'npc:hollis' } });
    fireEvent.change(screen.getByLabelText('Kind'), { target: { value: 'npc' } });
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Hollis Brask' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add entry' }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Added Hollis Brask.'));
    expect(bodies[0]).toEqual({ expected_draft_revision: 3, expected_content_hash: 'sha256:old',
      entity: { id: 'npc:hollis', kind: 'npc', name: 'Hollis Brask' } });
  });
});
