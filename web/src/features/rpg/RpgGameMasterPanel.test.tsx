import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RpgGameMasterPanel } from './RpgGameMasterPanel';

describe('RpgGameMasterPanel', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it('asks the game master, shows its answer, and offers its wish as a card to confirm', async () => {
    window.localStorage.setItem('omnix:rpg:selected-session-id', 'campaign:test');
    const calls: Array<{ url: string; body: unknown }> = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const isRequest = typeof input === 'object' && 'method' in input;
      const method = (isRequest ? (input as Request).method : init?.method) ?? 'GET';
      const raw = isRequest ? (input as Request).url : String(input);
      const url = decodeURIComponent(raw.replace(/^https?:\/\/[^/]+/, ''));
      const text = method === 'POST' ? (isRequest ? await (input as Request).clone().text() : String(init?.body ?? '')) : '';
      const body = text ? JSON.parse(text) : undefined;
      calls.push({ url: `${method} ${url}`, body });
      if (method === 'GET') {
        return new Response(JSON.stringify({ ok: true, session_id: 'campaign:test', entries: [] }), { status: 200 });
      }
      if (url.endsWith('/game-master')) {
        return new Response(JSON.stringify({
          ok: true, session_id: 'campaign:test',
          entry: { id: 1, question: 'I want more danger.', answer: 'Then the road will bite harder.', withheld: false,
                   wish: { kind: 'danger', value: 'more' } },
        }), { status: 200 });
      }
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    }));

    render(<RpgGameMasterPanel />);
    fireEvent.change(screen.getByLabelText('Ask the game master'), { target: { value: 'I want more danger.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }));

    await waitFor(() => expect(screen.getByText(/Then the road will bite harder/)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Note: more danger?' }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Noted: more danger.'));
    const turn = calls.find((call) => call.url === 'POST /api/rpg/sessions/campaign:test/turn');
    expect(turn?.body).toEqual({ command: 'Note: more danger.', preference: { kind: 'danger', value: 'more' } });
  });
});
