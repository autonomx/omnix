import {
  StreamingSttWebSocketClient,
  getDefaultStreamingSttWebSocketUrl,
  type StreamingSttWebSocketClientOptions,
} from './live-voice-websocket';
import type { AcceptedVoiceFinal } from './live-accepted-final';

export const LIVE_STT_SPECULATION_PARTIAL_EVENT = 'omnix:live-stt-speculation-partial';
export const LIVE_STT_SPECULATION_CANDIDATE_EVENT = 'omnix:live-stt-speculation-candidate';
export const LIVE_STT_SPECULATION_FINAL_EVENT = 'omnix:live-stt-speculation-final';
const LIVE_VOICE_PERF_EVENT = 'omnix:assistant-voice-perf';
const INSTALLED_KEY = '__omnixLiveSttAuthorityInstalled';
const DEFAULT_ENDPOINT_THRESHOLD = 0.75;
const MAX_BUFFERED_AUTHORITY_FRAMES = 250;

type AuthorityMode = 'observational' | 'test' | 'auto';

type AuthorityResponse = {
  eligible?: boolean;
  ok?: boolean;
  reasons?: string[];
  mode?: string;
};

export type AuthoritySelection = {
  websocketUrl: string;
  authorityEnabled: boolean;
  mode: AuthorityMode;
  endpointThreshold: number;
  fallbackUsed: boolean;
  reasons: string[];
};

type BufferedAudio = {
  audio: Float32Array;
  sampleRate: number;
};

type RuntimeClient = StreamingSttWebSocketClient & {
  options: StreamingSttWebSocketClientOptions;
  handleMessage: (rawData: string) => Promise<void>;
  deliverAcceptedFinal: (final: AcceptedVoiceFinal) => Promise<void>;
};

type ClientAuthorityState = {
  resolved: boolean;
  enabled: boolean;
  mode: AuthorityMode;
  endpointThreshold: number;
  finalPending: boolean;
  bufferedAudio: BufferedAudio[];
};

type AuthorityWindow = Window & typeof globalThis & {
  __omnixLiveSttAuthorityInstalled?: boolean;
};

const clientStates = new WeakMap<StreamingSttWebSocketClient, ClientAuthorityState>();

function clientState(client: StreamingSttWebSocketClient): ClientAuthorityState {
  const existing = clientStates.get(client);
  if (existing) return existing;
  const created: ClientAuthorityState = {
    resolved: false,
    enabled: false,
    mode: 'observational',
    endpointThreshold: DEFAULT_ENDPOINT_THRESHOLD,
    finalPending: false,
    bufferedAudio: [],
  };
  clientStates.set(client, created);
  return created;
}

export async function resolveAuthoritySelection(
  configuredUrl: string,
  locationLike: Pick<Location, 'protocol' | 'hostname'>,
  fetchImpl: typeof fetch,
): Promise<AuthoritySelection> {
  const configured = new URL(configuredUrl, `${locationLike.protocol}//${locationLike.hostname}`);
  const mode = normalizeMode(configured.searchParams.get('authority'));
  const endpointThreshold = boundedProbability(configured.searchParams.get('endpoint_threshold'));
  const primaryUrl = getDefaultStreamingSttWebSocketUrl(locationLike, configured.toString());
  if (mode === 'observational') {
    return {
      websocketUrl: primaryUrl,
      authorityEnabled: false,
      mode,
      endpointThreshold,
      fallbackUsed: false,
      reasons: ['observational_mode'],
    };
  }

  const language = configured.searchParams.get('language')?.trim() || 'en';
  const authorityUrl = new URL('/authorityz', configured);
  authorityUrl.protocol = authorityUrl.protocol === 'wss:' ? 'https:'
    : authorityUrl.protocol === 'ws:' ? 'http:' : authorityUrl.protocol;
  authorityUrl.search = '';
  authorityUrl.searchParams.set('language', language);
  authorityUrl.searchParams.set('mode', mode);

  let response: AuthorityResponse = {};
  let reasons: string[] = [];
  try {
    const authorityResponse = await fetchImpl(authorityUrl.toString(), {
      method: 'GET',
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    });
    response = await authorityResponse.json() as AuthorityResponse;
    if (!authorityResponse.ok) reasons.push(`authority_http_${authorityResponse.status}`);
  } catch (error) {
    reasons.push(error instanceof Error ? error.message : 'authority_probe_failed');
  }
  reasons = [...reasons, ...(response.reasons ?? [])];
  if (response.eligible === true && response.ok !== false) {
    return {
      websocketUrl: primaryUrl,
      authorityEnabled: true,
      mode,
      endpointThreshold,
      fallbackUsed: false,
      reasons,
    };
  }

  const fallback = configured.searchParams.get('fallback')?.trim();
  if (!fallback) {
    throw new Error(`Kyutai authority gate failed: ${reasons.join(', ') || 'not eligible'}`);
  }
  return {
    websocketUrl: getDefaultStreamingSttWebSocketUrl(locationLike, fallback),
    authorityEnabled: false,
    mode,
    endpointThreshold,
    fallbackUsed: true,
    reasons: reasons.length ? reasons : ['authority_not_eligible'],
  };
}

export function initializeLiveSttAuthorityController(): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const authorityWindow = window as AuthorityWindow;
  if (authorityWindow[INSTALLED_KEY]) return () => undefined;
  authorityWindow[INSTALLED_KEY] = true;

  const prototype = StreamingSttWebSocketClient.prototype as unknown as RuntimeClient;
  const originalConnect = prototype.connect;
  const originalSendAudio = prototype.sendAudio;
  const originalHandleMessage = prototype.handleMessage;
  const originalDeliverAcceptedFinal = prototype.deliverAcceptedFinal;

  prototype.connect = async function patchedConnect(this: RuntimeClient): Promise<void> {
    const state = clientState(this);
    if (!state.resolved) {
      const configuredUrl = configuredSttUrl();
      if (configuredUrl) {
        const selection = await resolveAuthoritySelection(configuredUrl, window.location, window.fetch.bind(window));
        this.options.url = selection.websocketUrl;
        state.enabled = selection.authorityEnabled;
        state.mode = selection.mode;
        state.endpointThreshold = selection.endpointThreshold;
        dispatchPerformance('stt_authority_selected', {
          mode: selection.mode,
          authorityEnabled: selection.authorityEnabled,
          fallbackUsed: selection.fallbackUsed,
          reasons: selection.reasons,
          websocketHost: new URL(selection.websocketUrl).host,
        });
      }
      state.resolved = true;
    }
    return originalConnect.call(this);
  };

  prototype.sendAudio = function patchedSendAudio(
    this: RuntimeClient,
    audio: Float32Array,
    sampleRate: number,
  ): void {
    const state = clientState(this);
    if (!state.finalPending) {
      originalSendAudio.call(this, audio, sampleRate);
      return;
    }
    state.bufferedAudio.push({ audio: new Float32Array(audio), sampleRate });
    while (state.bufferedAudio.length > MAX_BUFFERED_AUTHORITY_FRAMES) state.bufferedAudio.shift();
  };

  prototype.handleMessage = async function patchedHandleMessage(
    this: RuntimeClient,
    rawData: string,
  ): Promise<void> {
    const parsed = parseMessage(rawData);
    const state = clientState(this);
    if (parsed?.type === 'partial' && typeof parsed.text === 'string') {
      dispatchInternal(LIVE_STT_SPECULATION_PARTIAL_EVENT, {
        chatSessionId: this.options.chatSessionId,
        segmentId: parsed.segmentId,
        sourceSequence: parsed.sequence,
        text: parsed.text,
      });
    }
    if (parsed?.type === 'endpoint_candidate') {
      dispatchInternal(LIVE_STT_SPECULATION_CANDIDATE_EVENT, {
        chatSessionId: this.options.chatSessionId,
        segmentId: parsed.segmentId,
        sourceSequence: parsed.sequence,
        probability: parsed.probability,
        modelTimeMs: parsed.modelTimeMs,
      });
    }
    if (parsed?.type === 'result_available' && typeof parsed.text === 'string') {
      dispatchInternal(LIVE_STT_SPECULATION_FINAL_EVENT, {
        chatSessionId: this.options.chatSessionId,
        segmentId: parsed.segmentId,
        sourceSequence: parsed.sequence,
        text: parsed.text,
        provider: parsed.provider,
      });
    }
    await originalHandleMessage.call(this, rawData);
    if (
      parsed?.type === 'endpoint_candidate'
      && state.enabled
      && !state.finalPending
      && typeof parsed.probability === 'number'
      && parsed.probability >= state.endpointThreshold
    ) {
      const attemptId = this.sendFinal();
      if (attemptId) {
        state.finalPending = true;
        dispatchPerformance('stt_endpoint_committed', {
          provider: 'kyutai',
          mode: state.mode,
          segmentId: parsed.segmentId,
          sourceSequence: parsed.sequence,
          probability: parsed.probability,
          finalizeRequestId: attemptId,
        });
      }
    }
    if (parsed?.type === 'segment_error' || parsed?.type === 'error') {
      releaseBufferedAudio(this, state, originalSendAudio);
    }
  };

  prototype.deliverAcceptedFinal = async function patchedDeliverAcceptedFinal(
    this: RuntimeClient,
    final: AcceptedVoiceFinal,
  ): Promise<void> {
    try {
      await originalDeliverAcceptedFinal.call(this, final);
    } finally {
      releaseBufferedAudio(this, clientState(this), originalSendAudio);
    }
  };

  return () => {
    prototype.connect = originalConnect;
    prototype.sendAudio = originalSendAudio;
    prototype.handleMessage = originalHandleMessage;
    prototype.deliverAcceptedFinal = originalDeliverAcceptedFinal;
    authorityWindow[INSTALLED_KEY] = false;
  };
}

function releaseBufferedAudio(
  client: RuntimeClient,
  state: ClientAuthorityState,
  sendAudio: StreamingSttWebSocketClient['sendAudio'],
): void {
  if (!state.finalPending && !state.bufferedAudio.length) return;
  const buffered = state.bufferedAudio;
  state.bufferedAudio = [];
  state.finalPending = false;
  for (const frame of buffered) sendAudio.call(client, frame.audio, frame.sampleRate);
}

function configuredSttUrl(): string | null {
  const env = (import.meta as unknown as { env?: Record<string, string | undefined> }).env;
  return env?.VITE_ASSISTANT_STT_URL?.trim() || null;
}

function normalizeMode(value: string | null): AuthorityMode {
  return value === 'test' || value === 'auto' ? value : 'observational';
}

function boundedProbability(value: string | null): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return DEFAULT_ENDPOINT_THRESHOLD;
  return Math.max(0.5, Math.min(0.99, parsed));
}

function parseMessage(rawData: string): Record<string, any> | null {
  try {
    const value = JSON.parse(rawData) as unknown;
    return value && typeof value === 'object' ? value as Record<string, any> : null;
  } catch {
    return null;
  }
}

function dispatchInternal(type: string, detail: Record<string, unknown>): void {
  window.dispatchEvent(new CustomEvent(type, { detail }));
}

function dispatchPerformance(stage: string, detail: Record<string, unknown>): void {
  window.dispatchEvent(new CustomEvent(LIVE_VOICE_PERF_EVENT, {
    detail: { stage, timestamp: new Date().toISOString(), ...detail },
  }));
}
