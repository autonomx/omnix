import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RpgLoreReviewPanel } from './RpgLoreReviewPanel';
import { effectRow, storedEffect } from './rpgPlaySectionFields';

const DRAFT = {
  id: 7, world_id: 'world:a', campaign_id: 'rpg_1', entry_id: 'gm:rpg_1:tamsin-reed', family: 'person',
  name: 'Tamsin Reed', group_key: 'tamsin reed', entry: { row: { description: 'A ferrywoman.' }, play: {} },
  provenance: { campaign_id: 'rpg_1', turn: 12, reason: 'the village needs a messenger' }, status: 'pending',
  findings: { findings: [{ kind: 'duplicate', detail: 'Orik already carries word.' }], checked: true },
  canon_id: '', linked_to: null, created_at: '2026-10-30T00:00:00Z', decided_at: null,
};

describe('RpgLoreReviewPanel', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('shows a draft with its provenance and findings, and approves it', async () => {
    const posted: Array<{ url: string; body: unknown }> = [];
    let status = 'pending';
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const isRequest = typeof input === 'object' && 'method' in input;
      const method = (isRequest ? (input as Request).method : init?.method) ?? 'GET';
      const url = decodeURIComponent((isRequest ? (input as Request).url : String(input)).replace(/^https?:\/\/[^/]+/, ''));
      if (method === 'POST') {
        const text = isRequest ? await (input as Request).clone().text() : String(init?.body ?? '');
        posted.push({ url, body: text ? JSON.parse(text) : undefined });
        status = 'approved';
        return new Response(JSON.stringify({ ok: true, world_id: 'world:a', draft: { ...DRAFT, status } }), { status: 200 });
      }
      return new Response(JSON.stringify({ ok: true, world_id: 'world:a', groups: [
        { group_key: 'tamsin reed', drafts: [{ ...DRAFT, status, canon_id: status === 'approved' ? 'npc:tamsin-reed' : '' }] }] }),
      { status: 200 });
    }));

    render(<RpgLoreReviewPanel worldId="world:a" />);
    await waitFor(() => expect(screen.getByText(/the village needs a messenger/)).toBeInTheDocument());
    expect(screen.getByRole('list', { name: 'Findings on Tamsin Reed' })).toHaveTextContent('Orik already carries word.');
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Tamsin Reed: approved.'));
    expect(posted[0]).toEqual({ url: '/api/rpg/worlds/world:a/lore-review/7/decision', body: { decision: 'approve' } });
    await waitFor(() => expect(screen.getByText(/Status: approved \(npc:tamsin-reed\)/)).toBeInTheDocument());
  });
});

describe('the consequences section', () => {
  it('reads a stored effect as a flat row and writes it back', () => {
    const stored = { when: { engine_fate: 'guild' }, quest: { closes: 'quest:crown' }, told: 'The crown closes its doors.' };
    const row = effectRow(stored);
    expect(row).toEqual({ when: { engine_fate: 'guild' }, effect: 'quest', told: 'The crown closes its doors.',
      closes_quest: 'quest:crown' });
    expect(storedEffect(row)).toEqual(stored);
  });
});
