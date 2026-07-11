import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { liveConversationStore } from '../assistant-workspace/live-conversation-store';
import { LiveChatFullscreenShell } from './LiveChatFullscreenShell';
import {
  enterLiveChatFullscreen,
  exitLiveChatFullscreen,
  initializeLiveChatFullscreenController,
  resetLiveChatFullscreenStateForTests,
} from './live-chat-fullscreen-controller';

const sourceCallClick = vi.fn();
const sourceSubmit = vi.fn();

describe('LiveChatFullscreenShell', () => {
  let dispose: () => void;

  beforeEach(() => {
    document.body.innerHTML = `
      <div class="assistant-chat-messages">
        <article class="assistant-chat-message assistant"><div class="assistant-chat-bubble"><header><strong>Maya</strong></header><p>Welcome to our corner of the stars.</p></div></article>
        <article class="assistant-chat-message user"><div class="assistant-chat-bubble"><header><strong>You</strong></header><p>Can you tell me a story?</p></div></article>
      </div>
      <section class="assistant-live-card"><button type="button">End Call</button></section>
      <form class="assistant-composer"><textarea></textarea></form>
      <figure class="assistant-live-character-avatar" data-mouth-frame="medium" data-voice-mode="speaking"><img src="/maya.png" alt="Maya live avatar" /></figure>
    `;
    sourceCallClick.mockReset();
    sourceSubmit.mockReset();
    document.querySelector<HTMLButtonElement>('.assistant-live-card button')!
      .addEventListener('click', () => sourceCallClick());
    document.querySelector<HTMLFormElement>('.assistant-composer')!.requestSubmit = () => sourceSubmit();
    Object.defineProperty(document.documentElement, 'requestFullscreen', { configurable: true, value: undefined });
    vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    });
    resetLiveChatFullscreenStateForTests();
    dispose = initializeLiveChatFullscreenController();
    liveConversationStore.reset();
    liveConversationStore.dispatch({ type: 'identity', identity: { characterId: 'maya', displayName: 'Maya' } });
    liveConversationStore.dispatch({ type: 'conversation', event: { type: 'connection', value: 'connected' } });
    liveConversationStore.dispatch({ type: 'conversation', event: { type: 'assistant_turn', value: 'speaking' } });
    liveConversationStore.dispatch({ type: 'conversation', event: { type: 'delivery', value: 'audio_started' } });
    liveConversationStore.dispatch({ type: 'conversation', event: { type: 'floor_owner', value: 'assistant' } });
    liveConversationStore.dispatch({ type: 'duplex', duplex: { resolvedMode: 'echo_aware', reason: 'calibration_confident' } });
  });

  afterEach(async () => {
    await exitLiveChatFullscreen();
    dispose();
    cleanup();
    liveConversationStore.reset();
    document.body.innerHTML = '';
    vi.restoreAllMocks();
  });

  it('renders a character-first stage and conversation rail from existing owners', () => {
    enterLiveChatFullscreen('header');
    render(<LiveChatFullscreenShell />);

    const dialog = screen.getByRole('dialog', { name: 'Immersive Live Chat with Maya' });
    const fullscreen = within(dialog);
    expect(dialog).toBeInTheDocument();
    expect(fullscreen.getByAltText('Maya live avatar')).toBeInTheDocument();
    expect(fullscreen.getByText('Welcome to our corner of the stars.')).toBeInTheDocument();
    expect(fullscreen.getByText('Can you tell me a story?')).toBeInTheDocument();
    expect(fullscreen.getByText('Maya is speaking')).toBeInTheDocument();
    expect(fullscreen.getByText(/Microphone listening · Echo-aware/)).toBeInTheDocument();
  });

  it('delegates call and composer actions without creating another runtime', () => {
    enterLiveChatFullscreen('call-card');
    render(<LiveChatFullscreenShell />);

    fireEvent.click(screen.getByRole('button', { name: 'End voice chat' }));
    expect(sourceCallClick).toHaveBeenCalledTimes(1);

    const composer = screen.getByPlaceholderText('Write a message…');
    fireEvent.change(composer, { target: { value: 'A fullscreen message' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send fullscreen Live Chat message' }));
    expect(document.querySelector<HTMLTextAreaElement>('.assistant-composer textarea')).toHaveValue('A fullscreen message');
    expect(sourceSubmit).toHaveBeenCalledTimes(1);
  });

  it('exits the overlay without clicking the existing End Call control', async () => {
    enterLiveChatFullscreen('header');
    render(<LiveChatFullscreenShell />);

    fireEvent.click(screen.getByRole('button', { name: 'Exit fullscreen Live Chat' }));
    await vi.waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(sourceCallClick).not.toHaveBeenCalled();
  });
});
