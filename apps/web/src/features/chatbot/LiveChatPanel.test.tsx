import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  LiveChatPanel,
  invokeExistingLiveCallControl,
  readLiveCallSnapshot,
} from './LiveChatPanel';

afterEach(() => {
  document.body.innerHTML = '';
  vi.restoreAllMocks();
});

describe('LiveChatPanel', () => {
  it('requires a selected chat session for identity configuration', () => {
    render(<LiveChatPanel sessionId={null} />);
    expect(screen.getByRole('heading', { name: 'Live Chat' })).toBeInTheDocument();
    expect(screen.getByText('Select a Chat session')).toBeInTheDocument();
    expect(screen.getByLabelText('Conversation pace')).toBeInTheDocument();
  });

  it('reuses the existing live-call control instead of creating another voice pipeline', () => {
    const card = document.createElement('section');
    card.className = 'assistant-live-card';
    card.innerHTML = `
      <span class="assistant-live-identity">Talking to Maya</span>
      <div class="assistant-live-state"><span>Listening</span></div>
      <button type="button">Start Call</button>
    `;
    document.body.appendChild(card);
    const click = vi.spyOn(card.querySelector('button')!, 'click');

    expect(readLiveCallSnapshot()).toMatchObject({
      connected: false,
      state: 'Listening',
      identity: 'Talking to Maya',
    });
    expect(invokeExistingLiveCallControl()).toBe(true);
    expect(click).toHaveBeenCalledTimes(1);
  });
});
