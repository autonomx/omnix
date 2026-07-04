import { describe, expect, it } from 'vitest';

import { assistantContextControlsMissing } from './assistant-context-controller';

describe('assistant context control mounting', () => {
  it('requests injection only while a target is missing its Omnix control', () => {
    const root = document.createElement('div');
    root.innerHTML = `
      <div class="assistant-composer-controls"></div>
      <div class="assistant-audio-devices"></div>
    `;

    expect(assistantContextControlsMissing(root)).toBe(true);

    root.querySelector('.assistant-composer-controls')?.append(
      Object.assign(document.createElement('div'), {
        dataset: { omnixContextControls: 'true' },
      }),
    );
    const desktopStatus = document.createElement('div');
    desktopStatus.setAttribute('data-omnix-desktop-status', 'true');
    root.querySelector('.assistant-audio-devices')?.append(desktopStatus);

    expect(assistantContextControlsMissing(root)).toBe(false);
  });

  it('does not request injection before the chatbot targets exist', () => {
    const root = document.createElement('div');
    expect(assistantContextControlsMissing(root)).toBe(false);
  });
});
