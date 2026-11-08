import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { liveCallPresentationStore } from '../workspace';
import { LiveMuteButton } from './LiveMuteButton';

afterEach(() => liveCallPresentationStore.resetForTests());

describe('the call mute button', () => {
  it('is absent when the capture controller does not own the microphone', () => {
    render(<LiveMuteButton />);

    expect(screen.queryByRole('button', { name: 'Mute microphone' })).toBeNull();
  });

  it('waits for a running call', () => {
    act(() => liveCallPresentationStore.update({ captureOwned: true }));
    render(<LiveMuteButton />);

    expect(screen.getByRole('button', { name: 'Mute microphone' })).toBeDisabled();
  });

  it('mutes and unmutes the running call', () => {
    act(() => liveCallPresentationStore.update({ captureOwned: true, captureActive: true }));
    render(<LiveMuteButton />);

    fireEvent.click(screen.getByRole('button', { name: 'Mute microphone' }));
    const unmute = screen.getByRole('button', { name: 'Unmute microphone' });
    expect(unmute).toHaveAttribute('aria-pressed', 'true');
    expect(unmute).toHaveTextContent('Unmute');
    expect(liveCallPresentationStore.getState().micMuted).toBe(true);

    fireEvent.click(unmute);
    expect(liveCallPresentationStore.getState().micMuted).toBe(false);
  });
});
