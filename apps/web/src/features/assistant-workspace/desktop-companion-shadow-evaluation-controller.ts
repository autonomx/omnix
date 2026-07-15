import {
  DesktopCompanionEvaluationAccumulator,
  type DesktopCompanionEvaluationPayload,
} from './desktop-companion-evaluation';
import {
  DESKTOP_COMPANION_EVALUATION_EVENT,
  type DesktopCompanionEvaluationEvent,
} from './desktop-companion-watch-controller';

const FLUSH_INTERVAL_MS = 60_000;

type BuildIdentity = {
  exact_commit_sha: string;
  app_version: string;
  source: string;
};

type EvaluationIdentity = {
  sessionId: string | null;
  characterId: string;
  modelId: string | null;
  remoteProvider: boolean;
  exactCommitSha: string;
  appVersion: string;
  visionModelHash: string | null;
};

type EvaluationWindow = Window & typeof globalThis & {
  __omnixDesktopCompanionShadowEvaluationInstalled?: boolean;
};

let accumulator: DesktopCompanionEvaluationAccumulator | null = null;
let identity: EvaluationIdentity | null = null;
let recordedEvents = 0;
let startedAt = new Date();
let flushTimer: number | null = null;
let buildIdentityPromise: Promise<BuildIdentity> | null = null;
let eventQueue: Promise<void> = Promise.resolve();

export function initializeDesktopCompanionShadowEvaluationController(): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const target = window as EvaluationWindow;
  if (target.__omnixDesktopCompanionShadowEvaluationInstalled) return () => undefined;
  target.__omnixDesktopCompanionShadowEvaluationInstalled = true;
  const handleEvent = (event: Event) => {
    const detail = normalizeEvaluationEvent((event as CustomEvent<unknown>).detail);
    if (!detail) return;
    eventQueue = eventQueue.then(() => handleEvaluationEvent(detail)).catch(() => undefined);
  };
  const handleUnload = () => {
    const payload = finalizeCurrent();
    if (payload) submitEvaluationKeepalive(payload);
  };
  window.addEventListener(DESKTOP_COMPANION_EVALUATION_EVENT, handleEvent);
  window.addEventListener('beforeunload', handleUnload);
  flushTimer = window.setInterval(() => {
    eventQueue = eventQueue.then(() => flushAndRestart('interval')).catch(() => undefined);
  }, FLUSH_INTERVAL_MS);
  return () => {
    window.removeEventListener(DESKTOP_COMPANION_EVALUATION_EVENT, handleEvent);
    window.removeEventListener('beforeunload', handleUnload);
    if (flushTimer !== null) window.clearInterval(flushTimer);
    flushTimer = null;
    const payload = finalizeCurrent();
    if (payload) void submitEvaluation(payload);
    target.__omnixDesktopCompanionShadowEvaluationInstalled = false;
  };
}

export function normalizeEvaluationEvent(value: unknown): DesktopCompanionEvaluationEvent | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const input = value as Record<string, unknown>;
  const kind = input.kind;
  if (!['watch_started', 'capture', 'vision_result', 'watch_stopped'].includes(String(kind))) return null;
  const sessionId = typeof input.sessionId === 'string' && input.sessionId.trim() ? input.sessionId.trim() : null;
  return {
    kind: kind as DesktopCompanionEvaluationEvent['kind'],
    sessionId,
    characterId: typeof input.characterId === 'string' ? input.characterId.trim() || null : null,
    modelId: typeof input.modelId === 'string' ? input.modelId.trim() || null : null,
    remoteProvider: input.remoteProvider === true,
    scenario: typeof input.scenario === 'string' ? input.scenario.trim() || null : null,
    meaningful: input.meaningful === true,
    latencyMs: finiteNumber(input.latencyMs),
    callsThisMinute: finiteNumber(input.callsThisMinute),
    providerError: input.providerError === true,
    stale: input.stale === true,
    observed: input.observed === true,
    reason: typeof input.reason === 'string' ? input.reason.slice(0, 120) : undefined,
  };
}

async function handleEvaluationEvent(event: DesktopCompanionEvaluationEvent): Promise<void> {
  if (event.kind === 'watch_started') {
    if (identity?.sessionId !== event.sessionId || accumulator) await flushAndRestart('rebind', false);
    await startAccumulator(event);
    return;
  }
  if (event.kind === 'watch_stopped') {
    await flushAndRestart(event.reason ?? 'watch_stopped', false);
    return;
  }
  if (!accumulator || !identity || identity.sessionId !== event.sessionId) return;
  recordedEvents += 1;
  if (event.scenario) accumulator.addScenario(event.scenario);
  if (event.kind === 'capture') {
    accumulator.recordCapture();
    if (event.meaningful) accumulator.recordMeaningfulChange();
    return;
  }
  accumulator.recordVisionRequest({
    latencyMs: event.latencyMs,
    callsThisMinute: event.callsThisMinute,
    providerError: event.providerError,
    stale: event.stale,
  });
  if (event.observed) accumulator.recordObservation();
}

async function startAccumulator(event: DesktopCompanionEvaluationEvent): Promise<void> {
  if (!event.sessionId) return;
  const build = await loadBuildIdentity();
  const modelHash = event.modelId ? await sha256(event.modelId) : null;
  identity = {
    sessionId: event.sessionId,
    characterId: event.characterId || 'system-assistant',
    modelId: event.modelId ?? null,
    remoteProvider: event.remoteProvider === true,
    exactCommitSha: build.exact_commit_sha,
    appVersion: build.app_version,
    visionModelHash: modelHash,
  };
  startedAt = new Date();
  recordedEvents = 0;
  accumulator = createAccumulator(identity, startedAt);
}

async function flushAndRestart(_reason: string, restart = true): Promise<void> {
  const previousIdentity = identity;
  const payload = finalizeCurrent();
  if (payload) await submitEvaluation(payload);
  if (restart && previousIdentity) {
    identity = previousIdentity;
    startedAt = new Date();
    recordedEvents = 0;
    accumulator = createAccumulator(previousIdentity, startedAt);
  }
}

function finalizeCurrent(): DesktopCompanionEvaluationPayload | null {
  if (!accumulator || !identity || recordedEvents === 0) {
    accumulator = null;
    identity = null;
    recordedEvents = 0;
    return null;
  }
  const payload = accumulator.finalize(new Date());
  accumulator = null;
  identity = null;
  recordedEvents = 0;
  return payload;
}

function createAccumulator(value: EvaluationIdentity, start: Date): DesktopCompanionEvaluationAccumulator {
  return new DesktopCompanionEvaluationAccumulator({
    runId: `desktop-shadow:${crypto.randomUUID()}`,
    sessionId: value.sessionId,
    exactCommitSha: value.exactCommitSha,
    appVersion: value.appVersion,
    characterId: value.characterId,
    profileVersion: null,
    observationSchemaVersion: 1,
    attentionPolicyVersion: 1,
    rolloutStage: 'shadow',
    visionProvider: value.remoteProvider ? 'openai-compatible-remote' : 'openai-compatible-local',
    visionModelHash: value.visionModelHash,
    remoteProvider: value.remoteProvider,
    startedAt: start,
  });
}

async function loadBuildIdentity(): Promise<BuildIdentity> {
  if (!buildIdentityPromise) {
    buildIdentityPromise = fetch('/api/desktop-companion/build-identity')
      .then((response) => {
        if (!response.ok) throw new Error(`Build identity failed with status ${response.status}.`);
        return response.json() as Promise<BuildIdentity>;
      })
      .catch(() => ({ exact_commit_sha: 'unknown-local-build', app_version: '1.0.0', source: 'browser-fallback' }));
  }
  return buildIdentityPromise;
}

async function submitEvaluation(payload: DesktopCompanionEvaluationPayload): Promise<void> {
  try {
    await fetch('/api/desktop-companion/evaluations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } catch {
    // Evidence submission must never interrupt Desktop Companion observation.
  }
}

function submitEvaluationKeepalive(payload: DesktopCompanionEvaluationPayload): void {
  try {
    void fetch('/api/desktop-companion/evaluations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      keepalive: true,
    });
  } catch {
    // Browser teardown remains best effort.
  }
}

async function sha256(value: string): Promise<string | null> {
  if (!crypto.subtle) return null;
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map((item) => item.toString(16).padStart(2, '0')).join('');
}

function finiteNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}
