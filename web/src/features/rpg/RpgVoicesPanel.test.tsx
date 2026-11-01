import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RpgVoicesPanel } from './RpgVoicesPanel';
import { voiceAutoplay } from './rpgVoices';

const CAST = {
  ok: true, session_id: 'campaign:test',
  cast: [{ speaker_id: 'narrator', name: 'The narrator', voice_id: 'default', chosen_by: 'auto' },
    { speaker_id: 'npc:liora-fen', name: 'Liora Fen', voice_id: 'default', chosen_by: 'auto' }],
  voices: [{ voice_id: 'default', name: 'The narrator’s voice', description: 'clear' },
    { voice_id: 'calm', name: 'Calm', description: 'an adult man, calm' }],
};

describe('RpgVoicesPanel', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it('lists everyone who speaks with a castable voice to choose; auto-play is off until switched on', async () => {
    window.localStorage.setItem('omnix:rpg:selected-session-id', 'campaign:test');
    const puts: Array<{ url: string; body: unknown }> = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const isRequest = typeof input === 'object' && 'method' in input;
      const method = (isRequest ? (input as Request).method : init?.method) ?? 'GET';
      const url = decodeURIComponent((isRequest ? (input as Request).url : String(input)).replace(/^https?:\/\/[^/]+/, ''));
      if (method === 'PUT') {
        const text = isRequest ? await (input as Request).clone().text() : String(init?.body ?? '');
        puts.push({ url, body: JSON.parse(text) });
        return new Response(JSON.stringify({ ...CAST, cast: [CAST.cast[0], { ...CAST.cast[1], voice_id: 'calm', chosen_by: 'player' }] }),
          { status: 200 });
      }
      return new Response(JSON.stringify(CAST), { status: 200 });
    }));

    render(<RpgVoicesPanel />);
    const liora = await screen.findByLabelText('Liora Fen');
    expect(voiceAutoplay()).toBe(false);
    expect(screen.getByRole('checkbox', { name: 'Play each response when it is ready' })).not.toBeChecked();
    fireEvent.change(liora, { target: { value: 'calm' } });
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Voice chosen.'));
    expect(puts).toEqual([{ url: '/api/rpg/sessions/campaign:test/voices/npc:liora-fen', body: { voice_id: 'calm' } }]);
    fireEvent.click(screen.getByRole('checkbox', { name: 'Play each response when it is ready' }));
    expect(voiceAutoplay()).toBe(true);
  });
});
