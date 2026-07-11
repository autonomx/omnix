import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  invokeExistingLiveCallControl,
  readLiveCallSnapshot,
  readLiveChatMirroredAvatar,
  readLiveChatMirroredMessages,
  submitLiveChatMessageThroughExistingComposer,
} from './live-chat-runtime-adapters';

describe('Live Chat fullscreen runtime adapters', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  it('mirrors messages and avatar presentation without creating a session owner', () => {
    document.body.innerHTML = `
      <div class="assistant-chat-messages">
        <article class="assistant-chat-message assistant">
          <div class="assistant-chat-bubble"><header><strong>Maya</strong><time datetime="2026-07-11T12:00:00Z">12:00</time></header><p>Welcome to the observatory.</p></div>
        </article>
        <article class="assistant-chat-message user">
          <div class="assistant-chat-bubble"><header><strong>You</strong></header><p>Tell me about the stars.</p></div>
        </article>
      </div>
      <figure class="assistant-live-character-avatar" data-mouth-frame="medium" data-voice-mode="speaking" style="background-image: url('/scene.png')">
        <img src="/avatar.png" alt="Maya live avatar" />
      </figure>
    `;

    expect(readLiveChatMirroredMessages()).toEqual([
      expect.objectContaining({ role: 'assistant', label: 'Maya', text: 'Welcome to the observatory.' }),
      expect.objectContaining({ role: 'user', label: 'You', text: 'Tell me about the stars.' }),
    ]);
    expect(readLiveChatMirroredAvatar()).toMatchObject({
      imageUrl: expect.stringContaining('/avatar.png'),
      alt: 'Maya live avatar',
      mouthFrame: 'medium',
      voiceMode: 'speaking',
    });
  });

  it('delegates call control and text submission to the existing workspace elements', () => {
    document.body.innerHTML = `
      <section class="assistant-live-card">
        <span class="assistant-live-identity">Talking to Maya</span>
        <div class="assistant-live-state"><span>Listening</span></div>
        <button type="button">Start Call</button>
      </section>
      <form class="assistant-composer"><textarea></textarea></form>
    `;
    const callButton = document.querySelector<HTMLButtonElement>('.assistant-live-card button')!;
    const callClick = vi.spyOn(callButton, 'click');
    const form = document.querySelector<HTMLFormElement>('.assistant-composer')!;
    const submit = vi.fn();
    form.requestSubmit = submit;

    expect(readLiveCallSnapshot()).toMatchObject({ connected: false, identity: 'Talking to Maya', state: 'Listening' });
    expect(invokeExistingLiveCallControl()).toBe(true);
    expect(callClick).toHaveBeenCalledTimes(1);
    expect(submitLiveChatMessageThroughExistingComposer('Hello from fullscreen')).toBe(true);
    expect(document.querySelector<HTMLTextAreaElement>('.assistant-composer textarea')).toHaveValue('Hello from fullscreen');
    expect(submit).toHaveBeenCalledTimes(1);
  });

  it('fails safely when legacy presentation owners are not mounted', () => {
    expect(invokeExistingLiveCallControl()).toBe(false);
    expect(submitLiveChatMessageThroughExistingComposer('Hello')).toBe(false);
    expect(readLiveChatMirroredMessages()).toEqual([]);
    expect(readLiveChatMirroredAvatar().imageUrl).toBeNull();
  });
});
