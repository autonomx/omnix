import { ASSISTANT_LIVE_VOICE_CALL_START_EVENT, ASSISTANT_LIVE_VOICE_CALL_START_FAILED_EVENT, ASSISTANT_LIVE_VOICE_STOP_EVENT, ASSISTANT_VOICE_PERF_EVENT, emitOmnixEvent } from '../../../events/bus';
import { registerFetchMiddleware, type FetchMiddleware } from '../../../api/fetchPipeline';
import { liveCallPresentationStore } from './live-call-presentation-store';

/**
 * What went wrong during a call, counted per kind so it shows instead of staying in the console. A failure is
 * a kind and an HTTP status (or none), never content. While a call runs, the first failure of each kind shows in
 * the call's status line; after the call, one line lists them until the next call starts. The call's durable
 * evaluation carries the counts (`failure_<kind>_count`, `failure_count`).
 */
export const LIVE_CALL_FAILURE_KINDS = [
  'speculation_start',
  'speculation_accept',
  'evaluation_save',
  'prewarm',
  'overlap_judgement',
  'greeting',
  'camera_glance',
  'screen_glance',
  'avatar',
  'call_route_split',
] as const;

export type LiveCallFailureKind = (typeof LIVE_CALL_FAILURE_KINDS)[number];

const FAILURE_LABELS: Record<LiveCallFailureKind, string> = {
  speculation_start: 'Early reply start',
  speculation_accept: 'Early reply accept',
  evaluation_save: 'Saving the call evaluation',
  prewarm: 'Call warm-up',
  overlap_judgement: 'Interruption check',
  greeting: 'Greeting',
  camera_glance: 'Camera glance',
  screen_glance: 'Screen glance',
  avatar: 'Portrait stream',
  call_route_split: 'Call routing (requests reached two servers)',
};

type FailureEntry = { count: number; lastStatus: number | null };

let failures: Partial<Record<LiveCallFailureKind, FailureEntry>> = {};
let callOpen = false;
let callRan = false;
let callNode: string | null = null;

/**
 * The kinds that still belong to the call once it ended (its evaluation is saved after the stop). Any other kind
 * outside a call is not the call's: the podcast's portrait stream, a camera glance while typing.
 */
const AFTER_CALL_KINDS: ReadonlySet<LiveCallFailureKind> = new Set(['evaluation_save']);

/**
 * The routes whose state lives in one gateway process for the whole call (deploy/gateway-route-policy.json's
 * `live_call_bound_pattern`; src/tests/app/test_gateway_route_policy.py keeps the two equal).
 */
export const LIVE_CALL_BOUND_PATTERN = '^(?:/api/tts/live-call/avatar-websocket|/api/live/speculation/(?:tts-prefetch(?:/[^/]+/(?:accept|cancel))?|sessions/[^/]+/(?:start|start-stream|stream|[^/]+/(?:stream|accept|cancel)))|/api/live-call/sessions/[^/]+/(?:prewarm|overlap-judgement)|/api/chat/sessions/[^/]+/(?:(?:camera|screen)/glance|live-call/greeting/stream))$';
const CALL_BOUND = new RegExp(LIVE_CALL_BOUND_PATTERN);
const NODE_HEADER = 'x-omnix-node';

/** Counts one failure of the running call, or a late one (its evaluation's save) of the call that just ended. */
export function reportLiveCallFailure(kind: LiveCallFailureKind, { status = null }: { status?: number | null } = {}): void {
  if (!callOpen && !(callRan && AFTER_CALL_KINDS.has(kind))) return;
  const entry = failures[kind] ?? { count: 0, lastStatus: null };
  entry.count += 1;
  if (typeof status === 'number' && Number.isFinite(status)) entry.lastStatus = status;
  failures[kind] = entry;
  emitOmnixEvent(ASSISTANT_VOICE_PERF_EVENT, {
    stage: 'live_call_failure',
    failure_kind: kind,
    status: entry.lastStatus,
    timestamp: new Date().toISOString(),
  });
  if (callOpen && entry.count === 1) {
    liveCallPresentationStore.update({ callHealth: `${FAILURE_LABELS[kind]} failed${statusSuffix(entry.lastStatus)}.` });
  } else if (!callOpen) {
    liveCallPresentationStore.update({ callHealth: liveCallHealthSummary() });
  }
}

/** The HTTP status a failed gateway call carries (ApiError, GatewayCallError), or null. */
export function failureStatus(error: unknown): number | null {
  const status = (error as { status?: unknown } | null)?.status;
  return typeof status === 'number' && Number.isFinite(status) ? status : null;
}

/** The counts the durable evaluation stores: one key per kind and the total. */
export function liveCallFailureMetrics(): Record<string, number> {
  const metrics: Record<string, number> = {};
  let total = 0;
  for (const kind of LIVE_CALL_FAILURE_KINDS) {
    const count = failures[kind]?.count ?? 0;
    metrics[`failure_${kind}_count`] = count;
    total += count;
  }
  metrics.failure_count = total;
  return metrics;
}

/** One line naming what failed in the call, or null when nothing did. */
export function liveCallHealthSummary(): string | null {
  const parts = LIVE_CALL_FAILURE_KINDS.flatMap((kind) => {
    const entry = failures[kind];
    if (!entry?.count) return [];
    return [`${FAILURE_LABELS[kind]} failed ${timesLabel(entry.count)}${statusSuffix(entry.lastStatus)}`];
  });
  return parts.length ? `Call problems: ${parts.join('; ')}.` : null;
}

/**
 * The route check: every call-bound response names the gateway process that answered it. A call whose call-bound
 * requests (those naming the call by its header or cookie) reach two processes is split (a speculation started on one cannot be accepted on the other): counted once
 * per call as `call_route_split`.
 */
export const liveCallRouteCheck: FetchMiddleware = async (input, init, next) => {
  const response = await next(input, init);
  if (!callOpen || !CALL_BOUND.test(requestPath(input)) || !carriesCallAffinity(input, init)) return response;
  const node = response.headers?.get?.(NODE_HEADER)?.trim();
  if (!node) return response;
  if (callNode === null) callNode = node;
  else if (callNode !== node && !failures.call_route_split) reportLiveCallFailure('call_route_split');
  return response;
};

// Without the call's header or cookie a call-bound path goes wherever the proxy sends it (the call's first prewarm
// warms the worker on purpose), so only a request that names its call is checked.
function carriesCallAffinity(input: RequestInfo | URL, init: RequestInit | undefined): boolean {
  const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined));
  if (headers.has('x-omnix-call-id')) return true;
  return typeof document !== 'undefined' && document.cookie.split(';').some((part) => part.trim().startsWith('omnix_call_affinity='));
}

function requestPath(input: RequestInfo | URL): string {
  const raw = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
  try {
    return new URL(raw, window.location.origin).pathname;
  } catch {
    return '';
  }
}

export function initializeLiveCallHealth(): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const removeRouteCheck = registerFetchMiddleware('live-call-route-check', liveCallRouteCheck, { layer: 'transport' });
  const handleStart = () => {
    failures = {};
    callNode = null;
    callOpen = true;
    callRan = true;
    liveCallPresentationStore.update({ callHealth: null });
  };
  const handleStop = () => {
    if (!callOpen) return;
    callOpen = false;
    liveCallPresentationStore.update({ callHealth: liveCallHealthSummary() });
  };
  window.addEventListener(ASSISTANT_LIVE_VOICE_CALL_START_EVENT, handleStart);
  window.addEventListener(ASSISTANT_LIVE_VOICE_STOP_EVENT, handleStop);
  window.addEventListener(ASSISTANT_LIVE_VOICE_CALL_START_FAILED_EVENT, handleStop);  // no call runs
  return () => {
    removeRouteCheck();
    window.removeEventListener(ASSISTANT_LIVE_VOICE_CALL_START_EVENT, handleStart);
    window.removeEventListener(ASSISTANT_LIVE_VOICE_STOP_EVENT, handleStop);
    window.removeEventListener(ASSISTANT_LIVE_VOICE_CALL_START_FAILED_EVENT, handleStop);
    resetLiveCallHealthForTests();
  };
}

export function resetLiveCallHealthForTests(): void {
  failures = {};
  callNode = null;
  callOpen = false;
  callRan = false;
}

function statusSuffix(status: number | null): string {
  return status === null ? '' : ` (${status})`;
}

function timesLabel(count: number): string {
  return count === 1 ? 'once' : count === 2 ? 'twice' : `${count} times`;
}
