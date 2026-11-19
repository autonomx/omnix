import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { liveCallPresentationStore } from '../workspace';
import { LiveQuietButton } from './LiveQuietButton';

afterEach(() => liveCallPresentationStore.resetForTests());

describe('the call quiet button', () => {
  it('is absent when the capture controller does not own the microphone', () => {
    render(<LiveQuietButton />);

    expect(screen.queryByRole('button', { name: 'Keep the companion quiet this call' })).toBeNull();
  });

  it('waits for a running call', () => {
    act(() => liveCallPresentationStore.update({ captureOwned: true }));
    render(<LiveQuietButton />);

    expect(screen.getByRole('button', { name: 'Keep the companion quiet this call' })).toBeDisabled();
  });

  it('turns quiet on and off for the running call', () => {
    act(() => liveCallPresentationStore.update({ captureOwned: true, captureActive: true }));
    render(<LiveQuietButton />);

    fireEvent.click(screen.getByRole('button', { name: 'Keep the companion quiet this call' }));
    const speakUp = screen.getByRole('button', { name: 'Let the companion speak up' });
    expect(speakUp).toHaveAttribute('aria-pressed', 'true');
    expect(speakUp).toHaveClass('quiet');
    expect(liveCallPresentationStore.getState().companionQuiet).toBe(true);
    // Quiet is not mute: the call still hears the person.
    expect(liveCallPresentationStore.getState().micMuted).toBe(false);

    fireEvent.click(speakUp);
    expect(liveCallPresentationStore.getState().companionQuiet).toBe(false);
  });
});
