import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { RpgAuthoringEntityCard, RpgAuthoringTopic } from '../../api/rpgWorldAuthoringClient';
import { RpgWorldEntityEditor } from './RpgWorldEntityEditor';

const entity: RpgAuthoringEntityCard = {
  id: 'npc:bran',
  title: 'Bran',
  summary: 'A practical innkeeper.',
  kind: 'npc',
  metadata: { id: 'npc:bran', name: 'Bran', kind: 'npc', goals: ['protect the inn'] },
};

const topic: RpgAuthoringTopic = {
  topic_id: 'npcs',
  draft_revision: 4,
  source: 'ai',
  status: 'ready',
  content: { entities: [entity.metadata, { id: 'npc:elara', name: 'Elara' }] },
  directives: {},
  dependency_hashes: {},
  input_hash: 'sha256:input',
  content_hash: 'sha256:old',
  provenance: {},
  updated_at: '2026-07-20T00:00:00Z',
};

function response(value: unknown): Response {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

function renderEditor() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <RpgWorldEntityEditor entity={entity} topic={topic} worldId="world:aurelia" />
    </QueryClientProvider>,
  );
}

describe('RpgWorldEntityEditor', () => {
  const requests: Array<{ url: string; init?: RequestInit }> = [];

  beforeEach(() => {
    requests.length = 0;
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      requests.push({ url, init });
      if (init?.method === 'PATCH') {
        return response({ ok: true, topic: { ...topic, content_hash: 'sha256:new' }, entity: entity.metadata, stale_topic_ids: ['quests'], stale_entity_ids: ['quest:road'] });
      }
      if (init?.method === 'POST') {
        return response({ ok: true, topic: { ...topic, content_hash: 'sha256:regen' }, entity: { ...entity.metadata, personality: 'steadfast' }, stale_topic_ids: [], stale_entity_ids: [] });
      }
      return response({
        ok: true,
        world: { id: 'world:aurelia' },
        topic,
        entity: entity.metadata,
        history: [{ history_sequence: 1, operation: 'manual_edit', before: entity.metadata, after: entity.metadata, topic_content_hash: topic.content_hash, metadata: {}, created_at: '2026-07-20T00:00:00Z' }],
      });
    }));
  });

  afterEach(() => vi.unstubAllGlobals());

  it('saves one entity with topic concurrency tokens', async () => {
    renderEditor();
    fireEvent.click(screen.getByText('Edit or regenerate'));
    const editor = await screen.findByLabelText('Entity JSON for Bran');
    fireEvent.change(editor, {
      target: { value: JSON.stringify({ ...entity.metadata, goals: ['protect every traveler'] }) },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save Entity' }));

    await waitFor(() => expect(requests.some((request) => request.init?.method === 'PATCH')).toBe(true));
    const saved = requests.find((request) => request.init?.method === 'PATCH');
    expect(saved?.url).toContain('/topics/npcs/entities/npc%3Abran');
    expect(JSON.parse(String(saved?.init?.body))).toMatchObject({
      expected_draft_revision: 4,
      expected_content_hash: 'sha256:old',
      changes: { id: 'npc:bran', goals: ['protect every traveler'] },
    });
    expect(await screen.findByText(/1 dependent entities need review/)).toBeInTheDocument();
  });

  it('regenerates only the selected entity with directives', async () => {
    renderEditor();
    fireEvent.click(screen.getByText('Edit or regenerate'));
    await screen.findByLabelText('Regeneration directives for Bran');
    fireEvent.change(screen.getByLabelText('Regeneration directives for Bran'), {
      target: { value: '{"focus":"deepen motives"}' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Regenerate This Entity' }));

    await waitFor(() => expect(requests.some((request) => request.init?.method === 'POST')).toBe(true));
    const regenerated = requests.find((request) => request.init?.method === 'POST');
    expect(regenerated?.url).toContain('/entities/npc%3Abran/regenerate');
    expect(JSON.parse(String(regenerated?.init?.body))).toEqual({
      expected_draft_revision: 4,
      expected_content_hash: 'sha256:old',
      directives: { focus: 'deepen motives' },
    });
    expect(await screen.findByText(/preserving 1 sibling entities/)).toBeInTheDocument();
  });
});
