import createClient, { type Client } from 'openapi-fetch';
import { ApiError, ApiTimeoutError } from './errors';
import type { paths } from './generated/types';

/**
 * The typed gateway client (WP-9.3): paths, parameters, bodies and responses
 * are checked against the generated OpenAPI types.
 *
 *   const jobs = await unwrap(api.GET('/api/jobs', { params: { query: { limit: 50 } } }));
 */
export type GatewayClient = Client<paths>;

/** A Request that remembers its init, so the original body (a string or FormData) is sent unchanged. */
class GatewayRequest extends Request {
  readonly gatewayInit: RequestInit;

  constructor(input: RequestInfo | URL, init: RequestInit = {}) {
    super(input, init);
    this.gatewayInit = init;
  }
}

/**
 * openapi-fetch hands over a Request; the call is re-issued as (path, init) so the
 * fetch pipeline's middleware and the tests see the same calls as handwritten ones.
 */
function gatewayFetch(fetchImpl: () => typeof fetch) {
  return (request: Request): Promise<Response> => {
    const url = new URL(request.url);
    const sameOrigin = typeof window !== 'undefined' && url.origin === window.location.origin;
    const target = sameOrigin ? `${url.pathname}${url.search}` : request.url;
    const init = request instanceof GatewayRequest ? request.gatewayInit : {};
    const headers: Record<string, string> = {};
    new Headers(init.headers).forEach((value, name) => {
      headers[name === 'content-type' ? 'Content-Type' : name] = value;
    });
    return fetchImpl()(target, {
      method: request.method,
      ...(Object.keys(headers).length ? { headers } : {}),
      ...(init.body !== undefined ? { body: init.body } : {}),
      ...(init.signal ? { signal: init.signal } : {}),
    });
  };
}

export function createGatewayClient(options: { baseUrl?: string; fetchImpl?: typeof fetch } = {}): GatewayClient {
  // Resolve fetch per call: the fetch pipeline may be installed after this module loads.
  const fetchImpl = () => options.fetchImpl ?? globalThis.fetch;
  return createClient<paths>({
    baseUrl: options.baseUrl ?? (typeof window !== 'undefined' ? window.location.origin : 'http://localhost'),
    fetch: gatewayFetch(fetchImpl),
    Request: GatewayRequest,
  });
}

export const api = createGatewayClient();

type GatewayResult<T> = { data?: T; error?: unknown; response: Response };

/** The response body of a successful call; a failed call throws ApiError with the gateway's request id. */
export async function unwrap<T>(call: Promise<GatewayResult<T>>): Promise<T> {
  const { data, error, response } = await call;
  if (!response.ok) {
    const body = typeof error === 'string' ? error : error === undefined ? '' : JSON.stringify(error);
    throw new ApiError(response.status, body, response.headers?.get('x-request-id') ?? undefined);
  }
  return data as T;
}

/** An AbortSignal that fires after `timeoutMs`, and the error to raise when it did. */
export function requestTimeout(timeoutMs: number, message?: string): { signal: AbortSignal; timedOut: (error: unknown) => unknown; clear: () => void } {
  const controller = new AbortController();
  let fired = false;
  const timer = setTimeout(() => {
    fired = true;
    controller.abort();
  }, timeoutMs);
  return {
    signal: controller.signal,
    timedOut: (error) => (fired ? new ApiTimeoutError(timeoutMs, message) : error),
    clear: () => clearTimeout(timer),
  };
}
