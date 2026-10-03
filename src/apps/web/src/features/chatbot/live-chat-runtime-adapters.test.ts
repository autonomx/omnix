import { beforeEach, describe, expect, it } from 'vitest';

import { readLiveChatMirroredAvatar } from './live-chat-runtime-adapters';

describe('Live Chat avatar mirror', () => {
  beforeEach(() => {
    document.body.replaceChildren();
  });

  it('mirrors the avatar bridge presentation', () => {
    const host = document.createElement('figure');
    host.className = 'assistant-live-character-avatar';
    host.dataset.mouthFrame = 'medium';
    host.dataset.voiceMode = 'speaking';
    host.style.backgroundImage = "url('/scene.png')";
    const image = document.createElement('img');
    image.src = '/avatar.png';
    image.alt = 'Maya live avatar';
    host.append(image);
    document.body.append(host);

    expect(readLiveChatMirroredAvatar()).toMatchObject({
      imageUrl: expect.stringContaining('/avatar.png'),
      alt: 'Maya live avatar',
      mouthFrame: 'medium',
      voiceMode: 'speaking',
    });
  });

  it('falls back when no avatar is rendered', () => {
    expect(readLiveChatMirroredAvatar()).toMatchObject({ imageUrl: null, mouthFrame: 'closed', voiceMode: 'idle' });
  });
});
