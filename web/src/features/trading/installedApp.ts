// The installed app (TVP-4.5): Omnix Trading installed from the browser runs
// in its own window (a web app manifest, no native wrapper, decision D-8).
// There the browser-reserved keys (Ctrl+T, Ctrl+W, Ctrl+Tab, Ctrl+1..9)
// reach the page, so the trading commands switch to TradingView's keys.
import { useEffect, useState, useSyncExternalStore } from 'react';
import { setTradingCommandAvailability } from './commands/useTradingCommands';

/** The display modes of an installed app's own window. */
const INSTALLED_QUERIES = ['(display-mode: standalone)', '(display-mode: window-controls-overlay)', '(display-mode: fullscreen)'] as const;

type MediaQueries = (query: string) => Pick<MediaQueryList, 'matches' | 'addEventListener' | 'removeEventListener'>;

const browserQueries: MediaQueries = (query) => window.matchMedia(query);

/** Whether this page runs in the installed app's window. */
export function isInstalledApp(media: MediaQueries = browserQueries): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false;
  return INSTALLED_QUERIES.some((query) => media(query).matches);
}

/** Keeps the trading commands' keys in step with the window: app keys in the installed app, browser keys otherwise. */
export function useInstalledAppCommandKeys(media: MediaQueries = browserQueries): void {
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const update = () => setTradingCommandAvailability(isInstalledApp(media) ? 'installed' : 'browser');
    update();
    const lists = INSTALLED_QUERIES.map((query) => media(query));
    lists.forEach((list) => list.addEventListener('change', update));
    return () => {
      lists.forEach((list) => list.removeEventListener('change', update));
      setTradingCommandAvailability('browser');
    };
  }, [media]);
}

/** The browser's install prompt (Chromium's `beforeinstallprompt`), kept until used. */
type InstallPromptEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }> };

let deferred: InstallPromptEvent | null = null;
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((listener) => listener());

if (typeof window !== 'undefined') {
  window.addEventListener('beforeinstallprompt', (event) => {
    // Keep the browser's own mini-infobar quiet; the shortcut dialog offers the install instead.
    event.preventDefault();
    deferred = event as InstallPromptEvent;
    notify();
  });
  window.addEventListener('appinstalled', () => {
    deferred = null;
    notify();
  });
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Installs the app through the browser's prompt; null when the browser offers none (installed, or not supported). */
export function useInstallApp(): (() => Promise<boolean>) | null {
  const prompt = useSyncExternalStore(subscribe, () => deferred, () => null);
  const [, setUsed] = useState(0);
  if (!prompt) return null;
  return async () => {
    const event = prompt;
    deferred = null;
    notify();
    await event.prompt();
    const choice = await event.userChoice;
    setUsed((value) => value + 1);
    return choice.outcome === 'accepted';
  };
}

/** Tests only: a captured install prompt. */
export function setInstallPromptForTests(event: InstallPromptEvent | null): void {
  deferred = event;
  notify();
}
