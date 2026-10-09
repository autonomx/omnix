/**
 * Trading windows (TVP-4.3): each open Trading page says on a BroadcastChannel when it is focused and when it saved a
 * document.
 * - Alert sounds and toasts play only in the most recently focused window (`isAlertWindow`), so several open windows
 *   don't all ring.
 * - A window that saved a workspace or watchlist tells the others, which reload it when they have no edits of their own.
 * Without BroadcastChannel (old browsers, tests) the page behaves as the only window.
 */

export type SavedDocumentKind = 'workspace' | 'watchlist';

type PresenceMessage =
  | { type: 'hello' | 'here' | 'focus'; windowId: string; focusedAt: number }
  | { type: 'bye'; windowId: string }
  | { type: 'saved'; windowId: string; kind: SavedDocumentKind; id: string; revision: number };

const CHANNEL_NAME = 'omnix-trading-windows';

function newWindowId(): string {
  return typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `window-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

/** The browser's channel; none under jsdom, whose Node BroadcastChannel would join unrelated test workers. */
function defaultChannel(): BroadcastChannel | null {
  if (typeof window === 'undefined' || typeof BroadcastChannel === 'undefined') return null;
  if (typeof navigator !== 'undefined' && /jsdom/i.test(navigator.userAgent)) return null;
  return new BroadcastChannel(CHANNEL_NAME);
}

type SavedListener = (kind: SavedDocumentKind, id: string, revision: number) => void;

export class TradingWindowPresence {
  readonly windowId = newWindowId();
  /** When each known window (this one included) was last focused. */
  private readonly focusedAt = new Map<string, number>();
  private readonly savedListeners = new Set<SavedListener>();
  private channel: BroadcastChannel | null = null;

  constructor(channel?: BroadcastChannel | null) {
    this.channel = channel === undefined ? defaultChannel() : channel;
    const focused = typeof document !== 'undefined' && typeof document.hasFocus === 'function' && document.hasFocus();
    this.focusedAt.set(this.windowId, focused ? Date.now() : 0);
    if (this.channel) this.channel.onmessage = (event: MessageEvent<PresenceMessage>) => this.receive(event.data);
    this.post({ type: 'hello', windowId: this.windowId, focusedAt: this.focusedAt.get(this.windowId) ?? 0 });
  }

  /** This window was focused now. */
  focus(at = Date.now()): void {
    this.focusedAt.set(this.windowId, at);
    this.post({ type: 'focus', windowId: this.windowId, focusedAt: at });
  }

  /** This window is closing. */
  leave(): void {
    this.post({ type: 'bye', windowId: this.windowId });
  }

  /** Whether this window plays alert sounds and toasts: the most recently focused of the open windows. */
  isAlertWindow(): boolean {
    let best: [string, number] = [this.windowId, this.focusedAt.get(this.windowId) ?? 0];
    for (const [windowId, at] of this.focusedAt) {
      // Ties go to the smaller id, so exactly one window wins.
      if (at > best[1] || (at === best[1] && windowId < best[0])) best = [windowId, at];
    }
    return best[0] === this.windowId;
  }

  get openWindows(): number {
    return this.focusedAt.size;
  }

  announceSaved(kind: SavedDocumentKind, id: string, revision: number): void {
    this.post({ type: 'saved', windowId: this.windowId, kind, id, revision });
  }

  onOtherWindowSaved(listener: SavedListener): () => void {
    this.savedListeners.add(listener);
    return () => this.savedListeners.delete(listener);
  }

  receive(message: PresenceMessage): void {
    if (!message || message.windowId === this.windowId) return;
    if (message.type === 'bye') {
      this.focusedAt.delete(message.windowId);
      return;
    }
    if (message.type === 'saved') {
      this.savedListeners.forEach((listener) => listener(message.kind, message.id, message.revision));
      return;
    }
    this.focusedAt.set(message.windowId, message.focusedAt);
    if (message.type === 'hello') this.post({ type: 'here', windowId: this.windowId, focusedAt: this.focusedAt.get(this.windowId) ?? 0 });
  }

  private post(message: PresenceMessage): void {
    try {
      this.channel?.postMessage(message);
    } catch {
      // A closed channel: this window acts alone.
    }
  }
}

let shared: TradingWindowPresence | null = null;

/** The page's presence, created on first use; it follows the window's focus and says goodbye when the page goes. */
export function tradingWindowPresence(): TradingWindowPresence {
  if (shared) return shared;
  const presence = new TradingWindowPresence();
  shared = presence;
  if (typeof window !== 'undefined') {
    window.addEventListener('focus', () => presence.focus());
    window.addEventListener('pagehide', () => presence.leave());
  }
  return presence;
}

/** The URL that opens a workspace (and optionally one of its tabs) in a new Trading window. */
export function tradingWindowUrl(workspaceId: string, tabId?: string, base: Pick<Location, 'origin' | 'pathname'> = window.location): string {
  const url = new URL(base.pathname, base.origin);
  url.searchParams.set('workspace', workspaceId);
  if (tabId) url.searchParams.set('tab', tabId);
  return url.toString();
}

/** Opens a workspace in a new Trading window (TVP-4.3). */
export function openTradingWindow(workspaceId: string, tabId?: string): void {
  window.open(tradingWindowUrl(workspaceId, tabId), '_blank', 'noopener');
}

/** The workspace and tab a window was opened on (`?workspace=...&tab=...`), if any. */
export function requestedTradingWindow(search: string = typeof window === 'undefined' ? '' : window.location.search): { workspaceId: string | null; tabId: string | null } {
  const params = new URLSearchParams(search);
  return { workspaceId: params.get('workspace'), tabId: params.get('tab') };
}
