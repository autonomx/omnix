import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { VoiceGovernancePanel } from './VoiceGovernancePanel';

function renderPanel(assetId = 'voice-cloning:maya') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><VoiceGovernancePanel assetId={assetId} /></QueryClientProvider>);
}

afterEach(() => vi.unstubAllGlobals());

describe('VoiceGovernancePanel', () => {
  it('loads provenance and saves consent with explicit allowed uses', async () => {
    const bodies: unknown[] = [];
    let governance = {
      asset_id: 'voice-cloning:maya', subject_owner: '', source_type: 'legacy_import',
      source_reference: 'legacy.json', creator_id: '', consent_status: 'unverified',
      consent_recorded_at: null, allowed_uses: [], source_sha256: 'a'.repeat(64),
      deletion_state: 'active', deletion_requested_at: null, deleted_at: null,
      deletion_reason: '', updated_at: '2026-01-01T00:00:00Z',
    };
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(input.toString(), 'http://localhost').pathname;
      expect(path).toBe('/api/voice-profiles/voice-cloning%3Amaya/governance');
      if (init?.method === 'PATCH') {
        const body = JSON.parse(String(init.body));
        bodies.push(body);
        governance = { ...governance, ...body, consent_recorded_at: '2026-01-02T00:00:00Z' };
      }
      return Response.json(governance);
    }));

    renderPanel();
    expect(await screen.findByText('a'.repeat(64))).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Voice subject owner'), { target: { value: 'Maya voice subject' } });
    fireEvent.change(screen.getByLabelText('Voice creator id'), { target: { value: 'user:local' } });
    fireEvent.change(screen.getByLabelText('Voice consent status'), { target: { value: 'granted' } });
    fireEvent.click(screen.getByLabelText('Link to a character'));
    fireEvent.click(screen.getByLabelText('Use in live calls'));
    fireEvent.click(screen.getByRole('button', { name: 'Save voice governance' }));

    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({
      subject_owner: 'Maya voice subject', creator_id: 'user:local', consent_status: 'granted',
      allowed_uses: ['character', 'live_call'], deletion_state: 'active',
    });
    expect(await screen.findByRole('status')).toHaveTextContent('metadata saved');
  });

  it('does not invent governance for an unlinked character', () => {
    renderPanel('');
    expect(screen.getByText('No default voice is linked to this character.')).toBeInTheDocument();
  });
});
