/** WebSocket.OPEN, which test doubles of the constructor do not always carry. */
export const WEBSOCKET_OPEN = 1;

// A socket refused before it opened is asked again, this long apart: on a speaker swap the gateway can still hold
// the previous speaker's call slot for a moment (it answers 429, which a browser sees only as a close).
const SOCKET_REFUSED_RETRY_DELAYS_MS = [250, 500, 1000] as const;

export type RefusableSocketEvents = {
  isClosed: () => boolean;
  opened: (attempt: number) => void;
  message: (event: MessageEvent<string | ArrayBuffer>) => void;
  closed: (event: CloseEvent, attempt: number) => void;
  retrying: (attempt: number, delayMs: number) => void;
  failed: (error: Error) => void;
};

/**
 * A live voice session's websocket, asked again while retries remain when it is refused before opening. Every
 * handler is for the current socket only: a refused one's late events go nowhere.
 */
export function connectRefusableSocket(
  create: () => WebSocket,
  on: RefusableSocketEvents,
): { socket: () => WebSocket; close: (reason: string) => void } {
  let socket = create();
  let attempt = 0;
  let opened = false;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  const retryRemains = (): boolean => !on.isClosed() && attempt < SOCKET_REFUSED_RETRY_DELAYS_MS.length;
  const retry = (): void => {
    const delayMs = SOCKET_REFUSED_RETRY_DELAYS_MS[attempt];
    attempt += 1;
    on.retrying(attempt, delayMs);
    retryTimer = setTimeout(() => {
      retryTimer = null;
      if (on.isClosed()) return;
      socket = create();
      listen(socket);
    }, delayMs);
  };
  const listen = (target: WebSocket): void => {
    target.addEventListener('open', () => {
      if (target !== socket) return;
      if (on.isClosed()) {
        target.close(1000, 'session-closed');
        return;
      }
      opened = true;
      on.opened(attempt);
    }, { once: true });
    target.addEventListener('message', (event: MessageEvent<string | ArrayBuffer>) => {
      if (target === socket && !on.isClosed()) on.message(event);
    });
    target.addEventListener('error', () => {
      // A refusal before opening is followed by its close, which asks again while it may.
      if (target !== socket || (!opened && retryRemains())) return;
      on.failed(new Error('Live voice session WebSocket failed.'));
    });
    target.addEventListener('close', (event: CloseEvent) => {
      if (target !== socket) return;
      on.closed(event, attempt);
      if (on.isClosed()) return;
      if (!opened && retryRemains()) retry();
      else on.failed(new Error('Live voice session WebSocket closed before completion.'));
    });
  };
  listen(socket);
  return {
    socket: () => socket,
    close: (reason) => {
      if (retryTimer) clearTimeout(retryTimer);
      retryTimer = null;
      if (socket.readyState === WEBSOCKET_OPEN) {
        try { socket.send(JSON.stringify({ type: 'close', reason })); } catch { /* ignore close send */ }
        socket.close(1000, reason);
      } else {
        try { socket.close(); } catch { /* ignore close failures */ }
      }
    },
  };
}
