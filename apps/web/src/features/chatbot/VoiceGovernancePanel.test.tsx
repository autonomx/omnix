import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { VoiceGovernancePanel } from './VoiceGovernancePanel';
import type { CharacterProfile } from './characterClient';

function renderPanel(assetId = 'voice-cloning:maya', character?: CharacterProfile) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><VoiceGovernancePanel assetId={assetId} character={character} /></QueryClientProvider>);
}

const mayaCharacter: CharacterProfile = {
  id: 'maya', display_name: 'Maya', description: '', personality_prompt: '', default_greeting: '',
  default_voice_asset_id: 'voice-cloning:maya', speech_style: {}, identity_policy: {}, shared_memory_policy: {},
  active_version: 8, enabled: true, status: 'active',
  created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-02T00:00:00Z',
};

const governedVoiceMetadata = {
  voice_governance: {
    consent_status: 'granted', deletion_state: 'active', allowed_uses: ['character', 'live_call'],
  },
};

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

  it('shows that the selected voice is already active instead of presenting an inert action', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const path = new URL(input.toString(), 'http://localhost').pathname;
      if (path === '/api/assets') return Response.json({
        assets: [{ id: 'voice-cloning:maya', module: 'voice-cloning', type: 'voice_profile', metadata: governedVoiceMetadata }],
      });
      if (path === '/api/voice-profiles/voice-cloning%3Amaya/governance') return Response.json({
        asset_id: 'voice-cloning:maya', subject_owner: 'Maya', source_type: 'user_recording', source_reference: '',
        creator_id: 'local-user', consent_status: 'granted', consent_recorded_at: '2026-01-01T00:00:00Z',
        allowed_uses: ['character', 'live_call'], source_sha256: 'a'.repeat(64), deletion_state: 'active',
        deletion_reason: '', updated_at: '2026-01-01T00:00:00Z',
      });
      return new Response('not found', { status: 404 });
    }));

    renderPanel('voice-cloning:maya', mayaCharacter);

    const button = await screen.findByRole('button', { name: 'Currently used for live calls' });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('title', "maya is already used for this character's live calls.");
  });

  it('assigns a different governed voice to the current character', async () => {
    const updateBodies: Array<Record<string, unknown>> = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(input.toString(), 'http://localhost').pathname;
      if (path === '/api/assets') return Response.json({ assets: [
        { id: 'voice-cloning:maya', module: 'voice-cloning', type: 'voice_profile', metadata: governedVoiceMetadata },
        { id: 'voice-cloning:anaka', module: 'voice-cloning', type: 'voice_profile', metadata: governedVoiceMetadata },
      ] });
      if (path === '/api/voice-profiles/voice-cloning%3Amaya/governance') return Response.json({
        asset_id: 'voice-cloning:maya', subject_owner: 'Maya', source_type: 'user_recording', source_reference: '',
        creator_id: 'local-user', consent_status: 'granted', allowed_uses: ['character', 'live_call'],
        deletion_state: 'active', deletion_reason: '', updated_at: '2026-01-01T00:00:00Z',
      });
      if (path === '/api/characters/maya' && init?.method === 'PATCH') {
        updateBodies.push(JSON.parse(String(init.body)) as Record<string, unknown>);
        return Response.json({ ...mayaCharacter, default_voice_asset_id: 'voice-cloning:anaka', active_version: 9 });
      }
      return new Response('not found', { status: 404 });
    }));

    renderPanel('voice-cloning:maya', mayaCharacter);
    await screen.findByRole('option', { name: 'anaka' });
    fireEvent.change(screen.getByLabelText('Character live-call voice'), { target: { value: 'voice-cloning:anaka' } });
    const assignButton = screen.getByRole('button', { name: 'Use for character live calls' });
    await waitFor(() => expect(assignButton).toBeEnabled());
    fireEvent.click(assignButton);

    await waitFor(() => expect(updateBodies).toEqual([{
      expected_version: 8,
      default_voice_asset_id: 'voice-cloning:anaka',
    }]));
    expect(await screen.findByRole('status')).toHaveTextContent("anaka is now Maya's live-call voice");
  });
});
