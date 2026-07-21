import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { RpgWorldSummary } from '../../api/rpgWorldLibraryClient';
import { RpgWorldDeleteDialog } from './RpgWorldDeleteDialog';

const world: RpgWorldSummary = {
  id: 'world:disposable',
  title: 'Disposable Draft',
  description: 'A temporary world.',
  status: 'draft',
  source_mode: 'hybrid',
  genre: 'fantasy',
  tone: 'heroic',
  seed: 1,
  draft_revision: 1,
  metadata: {},
  created_at: '2026-07-21T00:00:00Z',
  updated_at: '2026-07-21T00:00:00Z',
};

function renderDialog(onDeleted = vi.fn()) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <RpgWorldDeleteDialog onCancel={vi.fn()} onDeleted={onDeleted} world={world} />
    </QueryClientProvider>,
  );
  return onDeleted;
}

afterEach(() => vi.unstubAllGlobals());

describe('RpgWorldDeleteDialog', () => {
  it('requires an exact typed title before permanently deleting an eligible draft', async () => {
    const requests: Array<{ method: string; body: string }> = [];
    vi.stubGlobal('fetch', vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const method = init?.method ?? 'GET';
      if (method === 'DELETE') {
        requests.push({ method, body: String(init?.body ?? '') });
        return new Response(JSON.stringify({
          ok: true,
          deleted: true,
          world_id: world.id,
          world_title: world.title,
          deleted_counts: { topics: 3 },
          audit_event_id: 42,
        }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      return new Response(JSON.stringify({
        ok: true,
        eligibility: {
          can_delete: true,
          world_id: world.id,
          world_title: world.title,
          world_status: 'draft',
          blockers: [],
          deleted_counts: { topics: 3, generation_runs: 1, scenario_projects: 0 },
        },
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }));
    const onDeleted = renderDialog();

    expect(await screen.findByRole('heading', { name: 'This permanently removes the draft authoring project' })).toBeInTheDocument();
    const submit = screen.getByRole('button', { name: 'Delete Permanently' });
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByLabelText(`Type ${world.title} to confirm deletion`), {
      target: { value: 'Disposable' },
    });
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByLabelText(`Type ${world.title} to confirm deletion`), {
      target: { value: world.title },
    });
    expect(submit).toBeEnabled();
    fireEvent.click(submit);

    await waitFor(() => expect(onDeleted).toHaveBeenCalledTimes(1));
    expect(requests).toHaveLength(1);
    expect(JSON.parse(requests[0].body)).toEqual({
      confirmation_title: world.title,
      acknowledge_permanent: true,
    });
  });

  it('explains why published authority must be archived instead', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      ok: true,
      eligibility: {
        can_delete: false,
        world_id: world.id,
        world_title: world.title,
        world_status: 'published',
        blockers: [{
          code: 'campaign_bindings',
          count: 2,
          message: 'Existing campaigns are pinned to this world and must remain playable.',
        }],
        deleted_counts: {},
      },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })));
    renderDialog();

    expect(await screen.findByRole('heading', { name: 'This world cannot be permanently deleted' })).toBeInTheDocument();
    expect(screen.getByText('Existing campaigns are pinned to this world and must remain playable.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delete Permanently' })).toBeDisabled();
    expect(screen.queryByLabelText(`Type ${world.title} to confirm deletion`)).not.toBeInTheDocument();
  });
});
