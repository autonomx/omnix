import { QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createTestQueryClient } from '../../../../test/renderWithProviders';

const settings = vi.hoisted(() => ({
  loadSettingsProfile: vi.fn(async () => ({ profile: { assistant: { livePortraitEngine: 'flashhead-lite' } } })),
  saveAssistantSettings: vi.fn(async (patch: { livePortraitEngine: string }) => patch),
}));
const loops = vi.hoisted(() => ({ resetMemberLoops: vi.fn() }));
vi.mock('../../../settings', () => settings);
vi.mock('./memberIdleLoops', () => loops);

const { LivePortraitEngineCard } = await import('./LivePortraitEngineCard');

describe('the live portrait engine card', () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('forgets the other engine\'s loaded state and idle loops once a new engine is saved', async () => {
    // Review 2026-11-22: after a switch the video button still said ready and the stage played the old engine's loop.
    const client = createTestQueryClient();
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    render(<QueryClientProvider client={client}><LivePortraitEngineCard /></QueryClientProvider>);

    const float = await screen.findByRole('button', { name: /FLOAT/u });
    await waitFor(() => expect(float).toBeEnabled());
    fireEvent.click(float);

    await screen.findByText('Saved. The next call uses this engine.');
    expect(settings.saveAssistantSettings).toHaveBeenCalledWith({ livePortraitEngine: 'float' });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['feature', 'chatbot', 'portrait-model'] });
    expect(loops.resetMemberLoops).toHaveBeenCalledTimes(1);
    expect(float).toHaveAttribute('aria-pressed', 'true');
  });
});
