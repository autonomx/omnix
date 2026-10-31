import { describe, expect, it, vi } from 'vitest';

let finishActivation: () => void = () => undefined;

vi.mock('./modules', () => ({
  moduleManifest: () => ({
    activateRuntime: () => new Promise<void>((resolve) => { finishActivation = resolve; }),
  }),
}));

const { activateViewRuntime, viewRuntimeReady } = await import('./viewRuntime');

describe('a workspace runtime still activating', () => {
  it('is waited for, and nothing is waited for once it is gone', async () => {
    // A cold start's live call was started while Chat's controllers still loaded, and took the legacy path.
    let settled = false;
    const runtime = activateViewRuntime('chatbot', { queryClient: {} as never });
    void viewRuntimeReady('chatbot').then(() => { settled = true; });
    await Promise.resolve();
    expect(settled).toBe(false);
    finishActivation();
    await runtime.ready;
    await Promise.resolve();
    expect(settled).toBe(true);
    runtime.dispose();
    await expect(viewRuntimeReady('chatbot')).resolves.toBeUndefined();
  });

  it('waits for the activation that replaced a disposed one (a strict-mode remount)', async () => {
    const first = activateViewRuntime('chatbot', { queryClient: {} as never });
    first.dispose();
    const second = activateViewRuntime('chatbot', { queryClient: {} as never });
    let settled = false;
    void viewRuntimeReady('chatbot').then(() => { settled = true; });
    await Promise.resolve();
    expect(settled).toBe(false);
    finishActivation();
    await second.ready;
    await Promise.resolve();
    expect(settled).toBe(true);
    second.dispose();
  });
});
