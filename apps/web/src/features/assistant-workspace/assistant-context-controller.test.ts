import { describe, expect, it } from 'vitest';

type AssistantContextTestWindow = Window & typeof globalThis & {
  __omnixAssistantContextInitialized?: boolean;
};

(window as AssistantContextTestWindow).__omnixAssistantContextInitialized = true;
const { assistantContextControlsMissing, desktopStatusLabel } = await import('./assistant-context-controller');

describe('assistant context control mounting', () => {
  it('requests injection only while a target is missing its Omnix control', () => {
    const root = document.createElement('div');
    root.innerHTML = `
      <div class="assistant-composer-controls"></div>
      <div class="assistant-composer-actions"></div>
      <div class="assistant-audio-devices"></div>
    `;

    expect(assistantContextControlsMissing(root)).toBe(true);

    const contextControls = document.createElement('div');
    contextControls.setAttribute('data-omnix-context-controls', 'true');
    root.querySelector('.assistant-composer-controls')?.append(contextControls);

    const desktopAction = document.createElement('button');
    desktopAction.setAttribute('data-omnix-desktop-action', 'true');
    root.querySelector('.assistant-composer-actions')?.append(desktopAction);

    const desktopStatus = document.createElement('div');
    desktopStatus.setAttribute('data-omnix-desktop-status', 'true');
    root.querySelector('.assistant-audio-devices')?.append(desktopStatus);

    expect(assistantContextControlsMissing(root)).toBe(false);
  });

  it('does not request injection before the chatbot targets exist', () => {
    const root = document.createElement('div');
    expect(assistantContextControlsMissing(root)).toBe(false);
  });

  it('keeps non-sharing desktop status messages visible', () => {
    expect(desktopStatusLabel(false, 'Off')).toBe('Off');
    expect(desktopStatusLabel(false, 'Screen capture unavailable')).toBe('Screen capture unavailable');
    expect(desktopStatusLabel(true, 'Buffering recent frames')).toBe('Buffering recent frames');
  });
});
