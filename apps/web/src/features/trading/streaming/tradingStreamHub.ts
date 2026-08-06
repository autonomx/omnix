import { tradingStreamUrl } from '../tradingApi';
import type { TradingStreamMessage } from '../tradingTypes';

export type TradingStreamStatus = 'connecting' | 'live' | 'polling' | 'closed' | 'error';

type MessageListener = (message: TradingStreamMessage) => void;
type StatusListener = (status: TradingStreamStatus) => void;

type SocketLike = Pick<WebSocket, 'addEventListener' | 'close'>;
type SocketFactory = (url: string) => SocketLike;

type HubEntry = {
  socket: SocketLike;
  messages: Map<string, MessageListener>;
  statuses: Map<string, StatusListener>;
  status: TradingStreamStatus;
};

export class TradingStreamHub {
  private readonly entries = new Map<string, HubEntry>();

  constructor(private readonly socketFactory: SocketFactory = (url) => new WebSocket(url)) {}

  static key(instrumentId: string, interval: string, bindingId?: string | null): string {
    return `${instrumentId}|${interval}|${bindingId ?? 'default'}`;
  }

  subscribe(
    listenerId: string,
    instrumentId: string,
    interval: string,
    onMessage: MessageListener,
    onStatus?: StatusListener,
    bindingId?: string | null,
  ): () => void {
    const key = TradingStreamHub.key(instrumentId, interval, bindingId);
    let entry = this.entries.get(key);
    if (!entry) {
      const socket = this.socketFactory(tradingStreamUrl(instrumentId, interval, bindingId));
      entry = { socket, messages: new Map(), statuses: new Map(), status: 'connecting' };
      this.entries.set(key, entry);
      const current = entry;
      socket.addEventListener('open', () => this.updateStatus(current, 'live'));
      socket.addEventListener('error', () => this.updateStatus(current, 'error'));
      socket.addEventListener('close', () => this.updateStatus(current, 'closed'));
      socket.addEventListener('message', (event: Event) => {
        const data = 'data' in event ? String((event as MessageEvent).data) : '';
        let message: TradingStreamMessage;
        try {
          message = JSON.parse(data) as TradingStreamMessage;
        } catch {
          message = { type: 'error', code: 'invalid_stream_message', message: 'Trading stream returned invalid JSON.' };
        }
        current.messages.forEach((listener) => listener(message));
      });
    }
    entry.messages.set(listenerId, onMessage);
    if (onStatus) {
      entry.statuses.set(listenerId, onStatus);
      onStatus(entry.status);
    }
    return () => {
      const current = this.entries.get(key);
      if (!current) return;
      current.messages.delete(listenerId);
      current.statuses.delete(listenerId);
      if (current.messages.size === 0) {
        current.socket.close(1000, 'last chart disposed');
        this.entries.delete(key);
      }
    };
  }

  private updateStatus(entry: HubEntry, status: TradingStreamStatus): void {
    entry.status = status;
    entry.statuses.forEach((listener) => listener(status));
  }

  get upstreamCount(): number {
    return this.entries.size;
  }

  listenerCount(instrumentId: string, interval: string, bindingId?: string | null): number {
    return this.entries.get(TradingStreamHub.key(instrumentId, interval, bindingId))?.messages.size ?? 0;
  }

  dispose(): void {
    this.entries.forEach((entry) => entry.socket.close(1000, 'hub disposed'));
    this.entries.clear();
  }
}

export const tradingStreamHub = new TradingStreamHub();
