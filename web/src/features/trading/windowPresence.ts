/**
 * Trading windows (TVP-4.3): each open Trading page says on a BroadcastChannel when it is focused and when it saved a
 * document.
 * - Alert sounds and toasts play only in the most recently focused Trading window (`isAlertWindow`), so several open
 *   windows don't all ring. A window takes part while its Trading workspace is mounted (`useTradingWindowPresence`):
 *   one that navigated to another module, crashed or froze stops counting (goodbye, or no heartbeat for a while).
 * - A window that saved a workspace or watchlist tells the others, which reload it when they have no edits of their own.
 * Without BroadcastChannel (old browsers, tests) the page behaves as the only window.
 */
import { useEffect } from 'react';

export type SavedDocumentKind = 'workspace' | 'watchlist';

type PresenceMessage =
  | { type: 'hello' | 'here' | 'focus'; windowId: string; focusedAt: number }
  | { type: 'bye'; windowId: string }
  | { type: 'saved'; windowId: string; kind: SavedDocumentKind; id: string; revision: number };

const CHANNEL_NAME = 'omnix-trading-windows';
/** A window that hasn't spoken for this long is gone (it heartbeats every HEARTBEAT_MS while open). */
export const HEARTBEAT_MS = 15_000;
export const PRESENCE_TTL_MS = 45_000;

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
type Peer = { focusedAt: number; seenAt: number };

export class TradingWindowPresence {
  readonly windowId = newWindowId();
  /** The other open Trading windows: when each was last focused, and last heard from. */
  private readonly peers = new Map<string, Peer>();
  private readonly savedListeners = new Set<SavedListener>();
  private readonly channel: BroadcastChannel | null;
  private focusedAt = 0;
  private joined = false;

  constructor(channel?: BroadcastChannel | null, private readonly now: () => number = Date.now) {
    this.channel = channel === undefined ? defaultChannel() : channel;
    if (this.channel) this.channel.onmessage = (event: MessageEvent<PresenceMessage>) => this.receive(event.data);
  }

  /** Takes part: says hello (the others answer), focused now when the page has focus. */
  join(): void {
    this.joined = true;
    const focused = typeof document !== 'undefined' && typeof document.hasFocus === 'function' && document.hasFocus();
    if (focused) this.focusedAt = this.now();
    this.post({ type: 'hello', windowId: this.windowId, focusedAt: this.focusedAt });
  }

  /** Stops taking part (its Trading workspace unmounted, or the page is going). */
  leave(): void {
    if (!this.joined) return;
    this.joined = false;
    this.post({ type: 'bye', windowId: this.windowId });
  }

  /** This window was focused now. */
  focus(at = this.now()): void {
    this.focusedAt = at;
    if (this.joined) this.post({ type: 'focus', windowId: this.windowId, focusedAt: at });
  }

  /** Tells the others this window is still here. */
  heartbeat(): void {
    if (this.joined) this.post({ type: 'here', windowId: this.windowId, focusedAt: this.focusedAt });
  }

  /** Whether this window plays alert sounds and toasts: the most recently focused of the open Trading windows. */
  isAlertWindow(): boolean {
    const now = this.now();
    let best: [string, number] = [this.windowId, this.focusedAt];
    for (const [windowId, peer] of this.peers) {
      if (now - peer.seenAt > PRESENCE_TTL_MS) {
        this.peers.delete(windowId);
        continue;
      }
      // Ties go to the smaller id, so exactly one window wins.
      if (peer.focusedAt > best[1] || (peer.focusedAt === best[1] && windowId < best[0])) best = [windowId, peer.focusedAt];
    }
    return best[0] === this.windowId;
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
      this.peers.delete(message.windowId);
      return;
    }
    if (message.type === 'saved') {
      this.savedListeners.forEach((listener) => listener(message.kind, message.id, message.revision));
      return;
    }
    this.peers.set(message.windowId, { focusedAt: message.focusedAt, seenAt: this.now() });
    if (message.type === 'hello' && this.joined) this.post({ type: 'here', windowId: this.windowId, focusedAt: this.focusedAt });
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

/** The page's presence (one per page). */
export function tradingWindowPresence(): TradingWindowPresence {
  shared ??= new TradingWindowPresence();
  return shared;
}

/**
 * Takes part in the Trading windows while mounted (the Trading workspace): follows focus, heartbeats, says goodbye on
 * unmount or when the page goes, and hello again when a page comes back from the back/forward cache.
 */
export function useTradingWindowPresence(): void {
  useEffect(() => {
    const presence = tradingWindowPresence();
    presence.join();
    const onFocus = () => presence.focus();
    const onHide = () => presence.leave();
    const onShow = (event: PageTransitionEvent) => {
      if (event.persisted) presence.join();
    };
    const timer = window.setInterval(() => presence.heartbeat(), HEARTBEAT_MS);
    window.addEventListener('focus', onFocus);
    window.addEventListener('pagehide', onHide);
    window.addEventListener('pageshow', onShow);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener('focus', onFocus);
      window.removeEventListener('pagehide', onHide);
      window.removeEventListener('pageshow', onShow);
      presence.leave();
    };
  }, []);
}

/** The URL that opens a workspace (and optionally one of its tabs) in a new Trading window. */
export function tradingWindowUrl(workspaceId: string, tabId?: string, base: Pick<Location, 'origin' | 'pathname'> = window.location): string {
  const url = new URL(base.pathname, base.origin);
  url.searchParams.set('workspace', workspaceId);
  if (tabId) url.searchParams.set('tab', tabId);
  return url.toString();
}

/** Opens a workspace in a new browser window (a popup-style window, not a tab) (TVP-4.3). */
export function openTradingWindow(workspaceId: string, tabId?: string): void {
  window.open(tradingWindowUrl(workspaceId, tabId), '_blank', 'noopener,popup,width=1400,height=900');
}

/** The workspace and tab a window was opened on (`?workspace=...&tab=...`), if any. */
export function requestedTradingWindow(search: string = typeof window === 'undefined' ? '' : window.location.search): { workspaceId: string | null; tabId: string | null } {
  const params = new URLSearchParams(search);
  return { workspaceId: params.get('workspace'), tabId: params.get('tab') };
}

/** Drops `?workspace=` and `?tab=` once used, so a later reload follows the workspace chosen since. */
export function forgetRequestedTradingWindow(): void {
  if (typeof window === 'undefined') return;
  const url = new URL(window.location.href);
  if (!url.searchParams.has('workspace') && !url.searchParams.has('tab')) return;
  url.searchParams.delete('workspace');
  url.searchParams.delete('tab');
  window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`);
}
