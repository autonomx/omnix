// Errors raised by the Omnix API clients (api/client.ts and api/http.ts).

export class ApiError extends Error {
  readonly status: number;
  readonly body: string;
  /** The gateway's X-Request-ID for the failed call; its log lines carry it. */
  readonly requestId: string | undefined;
  /** The gateway's `detail` (or `error`), or the body text when it is not JSON. */
  readonly detail: string;
  /** The response's Retry-After, in milliseconds, when it had one in seconds. */
  readonly retryAfterMs: number | undefined;

  constructor(status: number, body: string, requestId?: string, retryAfter?: string | null) {
    let detail = '';
    try {
      const parsed = JSON.parse(body) as { detail?: unknown; error?: unknown };
      const candidate = parsed.detail ?? parsed.error;
      detail = typeof candidate === 'string'
        ? candidate
        : candidate && typeof candidate === 'object'
          ? JSON.stringify(candidate)
          : '';
    } catch {
      detail = body.trim();
    }
    // The id lets a user's report be matched to the gateway's log lines.
    super(`Omnix API request failed with status ${status}${detail ? `: ${detail}` : ''}${requestId ? ` (request id ${requestId})` : ''}`);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
    this.requestId = requestId;
    this.detail = detail;
    const seconds = retryAfter ? Number(retryAfter) : Number.NaN;
    this.retryAfterMs = Number.isFinite(seconds) && seconds >= 0 ? seconds * 1000 : undefined;
  }
}

/**
 * A failed gateway call reworded for its caller (`unwrapAs`, `unwrapLabelled`). It keeps the HTTP
 * status, so callers branch on `errorStatus`/`isConflict` rather than on the message text.
 */
export class GatewayCallError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(message: string, cause: ApiError) {
    super(message, { cause });
    this.name = 'GatewayCallError';
    this.status = cause.status;
    this.detail = cause.detail;
  }
}

/** The HTTP status of a failed gateway call, or undefined for any other error. */
export function errorStatus(error: unknown): number | undefined {
  return error instanceof ApiError || error instanceof GatewayCallError ? error.status : undefined;
}

/** True when the gateway refused the call with 409: a revision conflict, or work already running. */
export function isConflict(error: unknown): boolean {
  return errorStatus(error) === 409;
}

export class ApiTimeoutError extends Error {
  readonly timeoutMs: number;

  constructor(timeoutMs: number, message?: string) {
    super(message ?? `Omnix API request timed out after ${Math.round(timeoutMs / 1000)}s.`);
    this.name = 'ApiTimeoutError';
    this.timeoutMs = timeoutMs;
  }
}
