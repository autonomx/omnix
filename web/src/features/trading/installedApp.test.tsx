import { act, cleanup, fireEvent, render, renderHook, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { tradingCommandAvailability } from './commands/useTradingCommands';
import { InstallAppNote } from './InstallAppNote';
import { isInstalledApp, setInstallPromptForTests, useInstalledAppCommandKeys } from './installedApp';

afterEach(() => {
  cleanup();
  act(() => setInstallPromptForTests(null));
});

function media(standalone: boolean) {
  const changeListeners: Array<() => void> = [];
  let matches = standalone;
  const query = (text: string) => ({
    get matches() { return text === '(display-mode: standalone)' && matches; },
    addEventListener: (_: string, listener: () => void) => { changeListeners.push(listener); },
    removeEventListener: vi.fn(),
  }) as unknown as MediaQueryList;
  return { query, setStandalone(next: boolean) { matches = next; changeListeners.forEach((listener) => listener()); } };
}

describe('installed app (TVP-4.5)', () => {
  it('detects the app window by its display mode', () => {
    expect(isInstalledApp(media(true).query)).toBe(true);
    expect(isInstalledApp(media(false).query)).toBe(false);
  });

  it('switches the trading keys to the app keys in the app window, and back', () => {
    const window = media(false);
    const hook = renderHook(() => useInstalledAppCommandKeys(window.query));
    expect(tradingCommandAvailability()).toBe('browser');
    act(() => window.setStandalone(true));
    expect(tradingCommandAvailability()).toBe('installed');
    hook.unmount();
    expect(tradingCommandAvailability()).toBe('browser');
  });

  it('offers the browser install prompt in the shortcut dialog', async () => {
    const prompt = vi.fn(async () => undefined);
    act(() => setInstallPromptForTests({ prompt, userChoice: Promise.resolve({ outcome: 'accepted' as const }) } as never));
    render(<InstallAppNote availability="browser" />);
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Install app' })));
    expect(prompt).toHaveBeenCalled();
    expect(await screen.findByRole('status')).toHaveTextContent('Installed');
  });

  it('explains the app keys without a prompt, and says nothing in the app', () => {
    const view = render(<InstallAppNote availability="browser" />);
    expect(screen.getByText(/browser’s menu/)).toBeInTheDocument();
    view.rerender(<InstallAppNote availability="installed" />);
    expect(view.container).toBeEmptyDOMElement();
  });
});
