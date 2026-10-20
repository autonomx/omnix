import { MantineProvider } from '@mantine/core';
import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { omnixTheme } from '../../design/theme';
import { createTestQueryClient } from '../../test/renderWithProviders';
import { BlendPanel, blendVoices } from './BlendPanel';

function path(input: RequestInfo | URL): string {
  const value = input instanceof Request ? input.url : String(input);
  return new URL(value, 'http://localhost').pathname;
}

const engine = (voiceBlend: boolean) => ({
  id: 'faster-qwen3-tts', label: 'Faster Qwen3 TTS', description: '', selected: true, installed: true, unavailable_reason: '',
  needs_transcripts: false, delivery_instruction: false, voice_blend: voiceBlend, group: 'clone', voice_controls: [],
});
const library = { assets: [
  { id: 'voice-cloning:Anaka', type: 'voice_profile', mime_type: 'audio/wav', metadata: { profile_name: 'Anaka' } },
  { id: 'voice-cloning:Morgan', type: 'voice_profile', mime_type: 'audio/wav', metadata: { profile_name: 'Morgan' } },
] };

function stub(voiceBlend: boolean, jobs: Record<string, unknown>[]) {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const route = path(input);
    if (route === '/api/tts/engines') return Response.json({ selected: 'faster-qwen3-tts', engines: [engine(voiceBlend)], switch: { provider: null, phase: 'idle', error: null, voices: { prepared: [], failed: [], already_ready: 0 } } });
    if (route === '/api/voice-library') return Response.json(library);
    if (route === '/api/jobs' && (input instanceof Request ? input.method : init?.method) === 'POST') {
      jobs.push((input instanceof Request ? await input.json() : JSON.parse(String(init?.body))) as Record<string, unknown>);
      return Response.json({ id: 'job:blend', module: 'voice', type: 'voice.blend', status: 'queued', resource_class: 'gpu:tts', priority: 0, created_at: '', updated_at: '' });
    }
    return Response.json({ id: 'job:blend', module: 'voice', type: 'voice.blend', status: 'running', resource_class: 'gpu:tts', priority: 0, created_at: '', updated_at: '' });
  }));
}

function renderPanel() {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <MantineProvider theme={omnixTheme}><BlendPanel language="en" onSaved={() => undefined} /></MantineProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('BlendPanel', () => {
  it('mixes two voices with weights that keep both in the blend', () => {
    expect(blendVoices('a', 'b', 0.3)).toEqual([{ voice: 'a', weight: 0.7 }, { voice: 'b', weight: 0.3 }]);
    expect(blendVoices('a', 'b', 1)).toEqual([{ voice: 'a', weight: 0.1 }, { voice: 'b', weight: 0.9 }]);
  });

  it('stays hidden without an engine that blends', async () => {
    stub(false, []);
    renderPanel();
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([input]) => path(input as RequestInfo) === '/api/tts/engines')).toBe(true));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByRole('group', { name: 'Blend voices' })).toBeNull();
  });

  it('blends two library voices into a named voice', async () => {
    const jobs: Record<string, unknown>[] = [];
    stub(true, jobs);
    renderPanel();
    fireEvent.change(await screen.findByLabelText('First voice'), { target: { value: 'voice-cloning:Anaka' } });
    fireEvent.change(screen.getByLabelText('Second voice'), { target: { value: 'voice-cloning:Morgan' } });
    fireEvent.change(screen.getByLabelText('Blended voice name'), { target: { value: 'Anaka x Morgan' } });
    fireEvent.click(screen.getByRole('button', { name: 'Blend and save' }));
    await waitFor(() => expect(jobs).toHaveLength(1));
    expect(jobs[0]).toMatchObject({ type: 'voice.blend', input_payload: {
      voices: [{ voice: 'voice-cloning:Anaka', weight: 0.5 }, { voice: 'voice-cloning:Morgan', weight: 0.5 }],
      profile_name: 'Anaka x Morgan', language: 'en' } });
  });
});
