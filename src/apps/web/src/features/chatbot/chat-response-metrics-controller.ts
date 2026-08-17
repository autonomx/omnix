import { createLiveCallDiagnosticsReporter } from '../assistant-workspace/live-call-diagnostics-client';

type JsonRecord = Record<string, unknown>;

type ChatResponseMetrics = {
  tokensPerSecond?: number;
  outputTokens?: number;
  generationTimeSeconds?: number;
  timeToFirstTokenSeconds?: number;
  stopReason?: string;
};

type AssistantMessageSnapshot = {
  id: string;
  metrics: ChatResponseMetrics | null;
};

type ChatMetricsWindow = Window & typeof globalThis & {
  __omnixChatResponseMetricsInstalled?: boolean;
};

const CHAT_SESSION_PATH = /^\/api\/chat\/sessions\/[^/]+$/;
const CHAT_STREAM_PATH = /^\/api\/chat\/sessions\/[^/]+\/messages\/stream$/;
const LIVE_VOICE_PERF_EVENT = 'omnix:assistant-voice-perf';
const METRICS_ROW_CLASS = 'assistant-response-metrics';

let originalFetch: typeof window.fetch | null = null;
let observer: MutationObserver | null = null;
let assistantMessages: AssistantMessageSnapshot[] = [];
let renderQueued = false;

function record(value: unknown): JsonRecord {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as JsonRecord : {};
}

function finiteNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function nonNegativeInteger(value: unknown): number | undefined {
  const parsed = finiteNumber(value);
  if (parsed === undefined || parsed < 0) return undefined;
  return Math.round(parsed);
}

function nonEmptyText(value: unknown): string | undefined {
  const text = typeof value === 'string' ? value.trim() : '';
  return text || undefined;
}

export function readChatResponseMetrics(metadataValue: unknown): ChatResponseMetrics | null {
  const metadata = record(metadataValue);
  const providerMetrics = record(metadata.provider_metrics);
  const usage = record(metadata.usage);
  const provider = nonEmptyText(providerMetrics.provider)?.toLocaleLowerCase();

  const metrics: ChatResponseMetrics = {
    tokensPerSecond: finiteNumber(providerMetrics.tokens_per_second),
    outputTokens: nonNegativeInteger(
      providerMetrics.output_tokens
      ?? usage.completion_tokens
      ?? usage.output_tokens,
    ),
    generationTimeSeconds: finiteNumber(
      providerMetrics.generation_time_seconds
      ?? providerMetrics.generation_time,
    ),
    timeToFirstTokenSeconds: finiteNumber(
      providerMetrics.time_to_first_token_seconds
      ?? providerMetrics.time_to_first_token,
    ),
    stopReason: nonEmptyText(providerMetrics.stop_reason ?? providerMetrics.finish_reason),
  };

  const hasMetric = Object.values(metrics).some((value) => value !== undefined);
  if (!hasMetric || (provider && provider !== 'lmstudio')) return null;
  return metrics;
}

export function formatLmStudioStopReason(value: string): string {
  const normalized = value.trim();
  const known: Record<string, string> = {
    eosfound: 'EOS Token Found',
    stopstringfound: 'Stop String Found',
    maxpredictedtokensreached: 'Max Tokens Reached',
    userstopped: 'Stopped by User',
    stop: 'Stop',
    length: 'Max Tokens Reached',
    tool_calls: 'Tool Call',
  };
  const compact = normalized.replace(/[^a-z0-9]+/gi, '').toLocaleLowerCase();
  if (known[compact]) return known[compact];
  return normalized
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (character) => character.toLocaleUpperCase());
}

function formatSeconds(value: number): string {
  return `${value < 10 ? value.toFixed(2) : value.toFixed(1)}s`;
}

function metricChip(icon: string, label: string, title?: string): HTMLSpanElement {
  const chip = document.createElement('span');
  chip.className = 'assistant-response-metric';
  if (title) chip.title = title;

  const iconNode = document.createElement('span');
  iconNode.className = 'assistant-response-metric-icon';
  iconNode.setAttribute('aria-hidden', 'true');
  iconNode.textContent = icon;

  const labelNode = document.createElement('span');
  labelNode.textContent = label;
  chip.append(iconNode, labelNode);
  return chip;
}

function metricsSignature(metrics: ChatResponseMetrics): string {
  return JSON.stringify(metrics);
}

function populateMetricsRow(row: HTMLDivElement, metrics: ChatResponseMetrics): void {
  const signature = metricsSignature(metrics);
  if (row.dataset.metricsSignature === signature) return;
  row.dataset.metricsSignature = signature;
  row.replaceChildren();

  if (metrics.tokensPerSecond !== undefined) {
    row.append(metricChip('◴', `${metrics.tokensPerSecond.toFixed(2)} tok/sec`, 'LM Studio generation speed'));
  }
  if (metrics.outputTokens !== undefined) {
    row.append(metricChip('▤', `${metrics.outputTokens} tokens`, 'LM Studio output tokens'));
  }
  if (metrics.generationTimeSeconds !== undefined) {
    row.append(metricChip('◷', formatSeconds(metrics.generationTimeSeconds), 'LM Studio generation time'));
  }
  if (metrics.stopReason) {
    row.append(metricChip('', `Stop reason: ${formatLmStudioStopReason(metrics.stopReason)}`));
  }
  if (metrics.timeToFirstTokenSeconds !== undefined) {
    row.dataset.timeToFirstTokenSeconds = String(metrics.timeToFirstTokenSeconds);
    row.title = `Time to first token: ${formatSeconds(metrics.timeToFirstTokenSeconds)}`;
  } else {
    delete row.dataset.timeToFirstTokenSeconds;
    row.removeAttribute('title');
  }
}

export function captureChatSessionResponseMetrics(sessionValue: unknown): void {
  const session = record(sessionValue);
  const messages = Array.isArray(session.messages) ? session.messages : [];
  assistantMessages = messages
    .map((value) => record(value))
    .filter((message) => message.role === 'assistant')
    .map((message, index) => ({
      id: nonEmptyText(message.id) ?? `assistant:${index}`,
      metrics: readChatResponseMetrics(message.metadata),
    }));
  scheduleMetricsRender();
}

export function renderChatResponseMetrics(root: ParentNode = document): void {
  const articles = Array.from(
    root.querySelectorAll<HTMLElement>('.assistant-chat-messages .assistant-chat-message.assistant'),
  );
  articles.forEach((article, index) => {
    const bubble = article.querySelector<HTMLElement>('.assistant-chat-bubble');
    if (!bubble) return;
    const metrics = assistantMessages[index]?.metrics ?? null;
    const existing = bubble.querySelector<HTMLDivElement>(`:scope > .${METRICS_ROW_CLASS}`);
    if (!metrics) {
      existing?.remove();
      return;
    }

    const row = existing ?? document.createElement('div');
    row.className = METRICS_ROW_CLASS;
    row.setAttribute('aria-label', 'LM Studio response metrics');
    populateMetricsRow(row, metrics);
    if (!existing) {
      const actions = bubble.querySelector<HTMLElement>(':scope > .assistant-message-actions');
      bubble.insertBefore(row, actions);
    }
  });
}

function scheduleMetricsRender(): void {
  if (renderQueued) return;
  renderQueued = true;
  queueMicrotask(() => {
    renderQueued = false;
    renderChatResponseMetrics();
  });
}

function requestVoiceTurnId(input: RequestInfo | URL, init?: RequestInit): string | undefined {
  const body = init?.body;
  if (typeof body === 'string') {
    try {
      return nonEmptyText(record(JSON.parse(body)).live_voice_turn_id);
    } catch {
      return undefined;
    }
  }
  if (input instanceof Request) {
    return nonEmptyText(input.headers.get('x-omnix-live-voice-turn-id'));
  }
  return undefined;
}

function dispatchSseTransportObservation(response: Response, turnId?: string): void {
  const detail = {
    stage: 'chat_sse_transport_response_observed',
    timestamp: new Date().toISOString(),
    turnId,
    transportVersion: response.headers.get('x-omnix-sse-transport'),
    contentType: response.headers.get('content-type'),
    responseCloned: false,
  };
  window.dispatchEvent(new CustomEvent(LIVE_VOICE_PERF_EVENT, { detail }));
  if (!turnId) return;
  const reporter = createLiveCallDiagnosticsReporter(`live-call:${turnId}`);
  reporter.record('chat_sse_transport_response_observed', {
    transport_version: detail.transportVersion,
    content_type: detail.contentType,
    response_cloned: false,
  }, 'chat_response_metrics');
  void reporter.flush();
}

async function interceptChatMetricsFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const fetchImpl = originalFetch ?? window.fetch.bind(window);
  const response = await fetchImpl(input, init);
  if (!response.ok) return response;

  const rawUrl = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
  const url = new URL(rawUrl, window.location.origin);
  const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();

  if (method === 'GET' && CHAT_SESSION_PATH.test(url.pathname)) {
    void response.clone().json()
      .then(captureChatSessionResponseMetrics)
      .catch(() => undefined);
  } else if (method === 'POST' && CHAT_STREAM_PATH.test(url.pathname)) {
    dispatchSseTransportObservation(response, requestVoiceTurnId(input, init));
  }
  // Never clone or consume a live SSE response here. The session query is
  // invalidated after the stream completes and supplies the same persisted
  // metrics without teeing the latency-critical response body.
  return response;
}

export function initializeChatResponseMetricsController(): () => void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return () => undefined;
  const metricsWindow = window as ChatMetricsWindow;
  if (metricsWindow.__omnixChatResponseMetricsInstalled) return () => undefined;

  metricsWindow.__omnixChatResponseMetricsInstalled = true;
  originalFetch = window.fetch.bind(window);
  window.fetch = interceptChatMetricsFetch;
  observer = new MutationObserver(scheduleMetricsRender);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  scheduleMetricsRender();

  return () => {
    observer?.disconnect();
    observer = null;
    if (window.fetch === interceptChatMetricsFetch && originalFetch) window.fetch = originalFetch;
    originalFetch = null;
    metricsWindow.__omnixChatResponseMetricsInstalled = false;
  };
}

export function resetChatResponseMetricsForTests(): void {
  const metricsWindow = window as ChatMetricsWindow;
  if (window.fetch === interceptChatMetricsFetch && originalFetch) window.fetch = originalFetch;
  originalFetch = null;
  metricsWindow.__omnixChatResponseMetricsInstalled = false;
  assistantMessages = [];
  renderQueued = false;
  observer?.disconnect();
  observer = null;
}
