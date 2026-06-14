export type OmnixEventHandler<TPayload = unknown> = (payload: TPayload) => void;

export interface OmnixEventClientOptions {
  endpoint?: string;
}

export class OmnixEventClient {
  private readonly endpoint: string;
  private source: EventSource | null = null;

  constructor(options: OmnixEventClientOptions = {}) {
    this.endpoint = options.endpoint ?? '/events';
  }

  connect() {
    if (this.source) {
      return this.source;
    }

    this.source = new EventSource(this.endpoint);
    return this.source;
  }

  subscribe<TPayload = unknown>(eventName: string, handler: OmnixEventHandler<TPayload>) {
    const source = this.connect();

    const listener = (event: Event) => {
      const message = event as MessageEvent<string>;
      handler(JSON.parse(message.data) as TPayload);
    };

    source.addEventListener(eventName, listener);

    return () => {
      source.removeEventListener(eventName, listener);
    };
  }

  close() {
    this.source?.close();
    this.source = null;
  }
}

export const omnixEventClient = new OmnixEventClient();
