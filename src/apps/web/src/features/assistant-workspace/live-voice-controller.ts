import { readCurrentAssistantDiagnosticText } from './live-conversation-assistant-summary';
import type { AcceptedVoiceFinal, LiveFinalRoutingResult } from './live-accepted-final';
import { acceptedFinalSuppressionReason } from './live-accepted-final-routing';
import {
  createLiveCallDiagnosticsReporter,
  createLiveCallTraceId,
  type LiveCallDiagnosticsReporter,
} from './live-call-diagnostics-client';
import { liveConversationStore } from './live-conversation-store';
import { currentLiveRuntimeProvenance } from './live-runtime-provenance';
import { liveSessionCoordinator } from './live-session-coordinator';
import {
  LIVE_STT_SPECULATION_CANDIDATE_EVENT,
  LIVE_STT_SPECULATION_DELIVERY_SETTLED_EVENT,
  LIVE_STT_SPECULATION_FINAL_EVENT,
  LIVE_STT_SPECULATION_PARTIAL_EVENT,
  type AuthoritySelection,
  resolveAuthoritySelection,
} from './live-stt-authority-controller';
import { liveSttUsesAuthoritativeEou } from './live-stt-capability-state';
import {
  type ConversationPace,
  type UserFloorState,
  assessSemanticTurn,
  reduceUserFloor,
  semanticFinalizeDelay,
} from './live-voice-floor-manager';
import { FinalizationAudioBuffer } from './live-voice-finalization-buffer';
import { LiveVoicePreSpeechBuffer } from './live-voice-pre-speech-buffer';
import {
  type OverlapIntent,
  classifyOverlap,
  shouldConfirmInterruption,
} from './live-voice-overlap-classifier';
import {
  StreamingSttWebSocketClient,
  calculateRms,
  getDefaultStreamingSttWebSocketUrl,
  type StreamingSttConnectionStatus,
  type StreamingSttSegmentState,
  type StreamingSttWebSocketCtor,
} from './live-voice-websocket';
import { liveVoiceVisualScales, smoothLiveVoiceLevel } from './live-voice-level';
import { endpointFusionAction } from './live-voice-turn-coordinator';
import { createAssistantWorkspaceRuntimeConfig } from './runtime-config';

type LiveVoiceWindow = Window & typeof globalThis & {
  AudioContext?: typeof AudioContext;
  webkitAudioContext?: typeof AudioContext;
  __omnixLiveVoiceControllerInstalled?: boolean;
};

type LiveVoiceAudioPipeline = { node: AudioNode; cleanup: () => void };

type LiveVoiceSession = {
  card: HTMLElement;
  stream: MediaStream;
  audioContext: AudioContext;
  source: MediaStreamAudioSourceNode;
  audioPipeline: LiveVoiceAudioPipeline;
  client: StreamingSttWebSocketClient;
  finalizationBuffer: FinalizationAudioBuffer;
  preSpeechBuffer: LiveVoicePreSpeechBuffer;
  reporter: LiveCallDiagnosticsReporter;
  sttAuthority: AuthoritySelection;
  speculationSegmentId: string | null;
  speculationSourceSequence: number | null;
  speechDetected: boolean;
  finalRequested: boolean;
  silenceTimer: ReturnType<typeof setTimeout> | null;
  previewTimer: ReturnType<typeof setTimeout> | null;
  previewRequestId: string | null;
  authoritativePreviewText: string;
  pauseStartedAt: number | null;
  finalResponseTimer: ReturnType<typeof setTimeout> | null;
  voiceLevel: number;
  speechFrameCount: number;
  perfTurnId: string | null;
  sttFinalRequestedAt: number | null;
  partialTranscript: string;
  partialTranscriptUpdatedAt: number;
  floorState: UserFloorState;
  overlapIntent: OverlapIntent | null;
  interruptionDispatched: boolean;
};

type PendingStart = { card: HTMLElement; token: number };

type ProviderEndpointCandidate = {
  provider?: string;
  segmentId: string;
  sequence: number;
  probability: number;
  modelTimeMs?: number;
};

type EndpointCommitState = {
  authorityEnabled: boolean;
  probability: number;
  endpointThreshold: number;
  speechDetected: boolean;
  finalRequested: boolean;
  pausePending: boolean;
  pauseElapsedMs: number;
  transcriptStableMs?: number;
  semanticProbabilityDone?: number;
  transcriptWords?: number;
  correctionPending?: boolean;
};

const ASSISTANT_SETTINGS_STORAGE_KEY = 'omnix.chatbot.assistantSettings';
const LIVE_TASK_INSTRUCTION_STORAGE_KEY = 'omnix.live.taskInstruction';
const DEFAULT_LIVE_VOICE_SENSITIVITY = 55;
const DEFAULT_CONVERSATION_PACE: ConversationPace = 'balanced';
const MIN_SPEECH_RMS_THRESHOLD = 0.012;
const MAX_SPEECH_RMS_THRESHOLD = 0.06;
const INTERRUPT_CONFIRMATION_FRAMES = 3;
const PROVIDER_ENDPOINT_MIN_SILENCE_MS = 160;
const FINAL_RESPONSE_TIMEOUT_MS = 8_000;
const LIVE_SESSION_SELECTION_TIMEOUT_MS = 5_000;
const FINALIZATION_BUFFER_MS = FINAL_RESPONSE_TIMEOUT_MS;
const PRE_SPEECH_BUFFER_MS = 240;
const STT_SEGMENT_TELEMETRY_INTERVAL_MS = 250;
// Start the private high-context preview as soon as a short, real pause is
// established. The result is never committed directly: resumed speech
// invalidates it, and only an exact authoritative final can promote it.
const AUTHORITATIVE_PREVIEW_PAUSE_MS = 40;
const LIVE_VOICE_INTERRUPT_EVENT = 'omnix:assistant-voice-interrupt';
const LIVE_VOICE_PERF_EVENT = 'omnix:assistant-voice-perf';
const LIVE_VOICE_STOP_EVENT = 'omnix:assistant-live-voice-stop';
const LIVE_VOICE_CALL_START_EVENT = 'omnix:assistant-live-voice-call-start';
const LIVE_VOICE_CALL_CONNECTED_EVENT = 'omnix:assistant-live-voice-call-connected';
const LIVE_VOICE_USER_SPEECH_EVENT = 'omnix:assistant-live-voice-user-speech';
const preparedCards = new WeakSet<HTMLElement>();
const panelStatuses = new WeakMap<HTMLElement, StreamingSttConnectionStatus>();
let activeSession: LiveVoiceSession | null = null;
let pendingStart: PendingStart | null = null;
let startToken = 0;
let initialized = false;
let liveVoiceWorkletModuleUrl: string | null = null;
const liveVoiceWorkletContexts = new WeakSet<AudioContext>();

export class LiveSttSegmentTelemetryGate {
  private structuralKey = '';
  private lastReportedAt = Number.NEGATIVE_INFINITY;

  shouldReport(state: StreamingSttSegmentState, now = performance.now()): boolean {
    const structuralKey = [
      state.protocol ?? '',
      state.activeSequence ?? '',
      state.pendingSegments,
      state.queuedSegments,
    ].join(':');
    const structuralChange = structuralKey !== this.structuralKey;
    if (!structuralChange
      && now - this.lastReportedAt < STT_SEGMENT_TELEMETRY_INTERVAL_MS) return false;
    this.structuralKey = structuralKey;
    this.lastReportedAt = now;
    return true;
  }
}

export async function resolveLiveVoiceSttSelection(
  configuredUrl: string | undefined,
  locationLike: Pick<Location, 'protocol' | 'hostname'>,
  fetchImpl: typeof fetch,
): Promise<AuthoritySelection> {
  if (configuredUrl?.trim()) {
    return resolveAuthoritySelection(configuredUrl, locationLike, fetchImpl);
  }
  return {
    websocketUrl: getDefaultStreamingSttWebSocketUrl(locationLike),
    authorityEnabled: false,
    mode: 'observational',
    endpointThreshold: 0.75,
    fallbackUsed: false,
    reasons: ['default_parakeet'],
  };
}

export function shouldCommitProviderEndpoint(state: EndpointCommitState): boolean {
  if (
    !state.authorityEnabled
    || !Number.isFinite(state.probability)
    || !state.speechDetected
    || state.finalRequested
    || !state.pausePending
  ) return false;
  return endpointFusionAction({
    endpointProbability: state.probability,
    endpointThreshold: state.endpointThreshold,
    silenceMs: state.pauseElapsedMs,
    transcriptStableMs: state.transcriptStableMs ?? 80,
    semanticProbabilityDone: state.semanticProbabilityDone ?? 1,
    transcriptWords: state.transcriptWords ?? 2,
    correctionPending: state.correctionPending ?? false,
  }) === 'commit';
}

export function semanticFinalizationRemainingMs(
  text: string,
  pace: ConversationPace,
  pauseElapsedMs: number,
  transcriptStableMs: number = Number.POSITIVE_INFINITY,
): number {
  const targetDelayMs = semanticFinalizeDelay(text, pace);
  const pauseRemainingMs = targetDelayMs - Math.max(0, pauseElapsedMs);
  // When authoritative EOU is negotiated, the semantic timeout is only a
  // watchdog for a missed or delayed EOU. Nemotron partials can legitimately
  // revise late in the acoustic pause; restarting the whole 600 ms watchdog on
  // each revision stretched real traces to ~1 second. Keep the watchdog tied
  // to the microphone pause while the provider endpoint gate still protects
  // short intra-sentence pauses.
  if (liveSttUsesAuthoritativeEou()) return Math.max(0, pauseRemainingMs);
  const transcriptRemainingMs = Number.isFinite(transcriptStableMs)
    ? targetDelayMs - Math.max(0, transcriptStableMs)
    : 0;
  return Math.max(0, pauseRemainingMs, transcriptRemainingMs);
}

export function initializeLiveVoiceController(root: ParentNode = document): void {
  if (initialized || typeof window === 'undefined' || typeof document === 'undefined') return;
  const liveWindow = window as LiveVoiceWindow;
  if (liveWindow.__omnixLiveVoiceControllerInstalled) return;
  initialized = true;
  liveWindow.__omnixLiveVoiceControllerInstalled = true;
  prepareCards(root);
  document.addEventListener('click', handleDocumentClick, true);
  window.addEventListener(LIVE_VOICE_STOP_EVENT, handleExternalStop);
  new MutationObserver(() => prepareCards(root)).observe(document.body, {
    childList: true,
    subtree: true,
    characterData: true,
  });
}

function prepareCards(root: ParentNode): void {
  root.querySelectorAll<HTMLElement>('.assistant-live-card').forEach((card) => {
    if (!preparedCards.has(card)) {
      preparedCards.add(card);
      const stateButton = card.querySelector<HTMLElement>('.assistant-live-state');
      stateButton?.setAttribute('role', 'button');
      stateButton?.setAttribute('tabindex', '0');
      stateButton?.setAttribute('aria-label', 'Start live voice streaming');
      stateButton?.addEventListener('keydown', (event) => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        event.preventDefault();
        if (!isCardStartingOrActive(card)) void startLiveVoice(card);
      });
      ensureLiveTaskPreset(card);
      panelStatuses.set(card, 'idle');
    }
    renderPanelStatus(card, panelStatuses.get(card) ?? 'idle');
  });
}

function handleDocumentClick(event: MouseEvent): void {
  const target = event.target;
  if (!(target instanceof Element)) return;
  const stateButton = target.closest<HTMLElement>('.assistant-live-state');
  if (stateButton) {
    const card = stateButton.closest<HTMLElement>('.assistant-live-card');
    if (card && !isCardStartingOrActive(card)) void startLiveVoice(card);
    return;
  }
  const button = target.closest<HTMLButtonElement>('button');
  if (!button) return;
  if (button.classList.contains('assistant-mic-button')) {
    const card = document.querySelector<HTMLElement>('.assistant-live-card');
    if (card) toggleLiveVoice(card);
    return;
  }
  const label = button.textContent?.trim().toLowerCase() ?? '';
  const voiceContext = button.closest('.assistant-live-card')
    || button.closest('.assistant-view-panel[aria-label="Voice Sessions view"]');
  if ((label !== 'start call' && label !== 'end call') || !voiceContext) return;
  const card = button.closest<HTMLElement>('.assistant-live-card')
    ?? document.querySelector<HTMLElement>('.assistant-live-card');
  if (card) toggleLiveVoice(card);
}

function toggleLiveVoice(card: HTMLElement): void {
  if (isCardStartingOrActive(card)) stopLiveVoice(card, 'idle');
  else void startLiveVoice(card);
}

function isCardStartingOrActive(card: HTMLElement): boolean {
  return activeSession?.card === card || pendingStart?.card === card;
}

async function startLiveVoice(card: HTMLElement): Promise<void> {
  if (isCardStartingOrActive(card)) return;
  if (activeSession) stopLiveVoice(activeSession.card, 'idle');
  const token = ++startToken;
  pendingStart = { card, token };
  setPanelStatus(card, 'connecting');
  dispatchLiveVoiceLifecycleEvent(LIVE_VOICE_CALL_START_EVENT, {
    token,
    timestamp: new Date().toISOString(),
  });
  let audioContext: AudioContext | null = null;
  let sessionReporter: LiveCallDiagnosticsReporter | null = null;
  let stream: MediaStream | null = null;
  let source: MediaStreamAudioSourceNode | null = null;
  let audioPipeline: LiveVoiceAudioPipeline | null = null;
  try {
    const sessionId = await waitForLiveConversationSessionId();
    if (!isCurrentStart(card, token)) return;
    if (!sessionId) throw new Error('Select or create a chat session before starting Live voice.');
    const reporter = createLiveCallDiagnosticsReporter(createLiveCallTraceId(`${sessionId}:capture`));
    sessionReporter = reporter;
    const provenance = currentLiveRuntimeProvenance();
    reporter.record('live_runtime_provenance', provenance, 'live_voice_controller');
    const taskInstruction = readLiveTaskInstruction(card);
    await liveSessionCoordinator.prepareTaskContract(sessionId, taskInstruction);
    const coordination = liveConversationStore.getState().coordination;
    reporter.record('live_task_contract_acknowledged', {
      ...provenance,
      task_instruction_configured: Boolean(taskInstruction),
      task_contract_id: coordination.taskContract.taskContractId,
      task_contract_version: coordination.taskContract.version,
      context_version: coordination.contextVersion,
    }, 'live_voice_controller');
    dispatchLiveVoicePerfEvent({
      stage: 'live_task_contract_acknowledged',
      timestamp: new Date().toISOString(),
      taskInstructionConfigured: Boolean(taskInstruction),
      ...provenance,
    });
    const liveWindow = window as LiveVoiceWindow;
    const AudioContextCtor = liveWindow.AudioContext ?? liveWindow.webkitAudioContext;
    const WebSocketCtor = liveWindow.WebSocket as unknown as StreamingSttWebSocketCtor | undefined;
    if (!AudioContextCtor || !WebSocketCtor) throw new Error('Live voice requires browser AudioContext and WebSocket support.');
    const runtimeConfig = createAssistantWorkspaceRuntimeConfig();
    const sttAuthority = await resolveLiveVoiceSttSelection(
      runtimeConfig.sttServiceUrl,
      window.location,
      window.fetch.bind(window),
    );
    const selectedProvider = sttAuthority.authorityEnabled
      ? 'configured_authoritative'
      : sttAuthority.fallbackUsed
        ? 'fallback'
        : runtimeConfig.sttServiceUrl?.trim()
          ? 'configured_observational'
          : 'default_stt';
    reporter.record('stt_authority_selected', {
      selected_provider: selectedProvider,
      authority_enabled: sttAuthority.authorityEnabled,
      authority_mode: sttAuthority.mode,
      fallback_used: sttAuthority.fallbackUsed,
      endpoint_threshold: sttAuthority.endpointThreshold,
      reasons: sttAuthority.reasons,
    }, 'live_voice_controller');
    dispatchLiveVoicePerfEvent({
      stage: 'stt_authority_selected',
      timestamp: new Date().toISOString(),
      selectedProvider,
      authorityEnabled: sttAuthority.authorityEnabled,
      authorityMode: sttAuthority.mode,
      fallbackUsed: sttAuthority.fallbackUsed,
      endpointThreshold: sttAuthority.endpointThreshold,
      reasons: sttAuthority.reasons,
    });
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('Live voice requires browser microphone access.');
    audioContext = new AudioContextCtor({ latencyHint: 'interactive' });
    await ensureAudioContextRunning(audioContext);
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      video: false,
    });
    if (!isCurrentStart(card, token)) {
      closePendingResources(stream, audioContext, source, audioPipeline);
      return;
    }
    source = audioContext.createMediaStreamSource(stream);
    const segmentTelemetryGate = new LiveSttSegmentTelemetryGate();
    const client = new StreamingSttWebSocketClient({
      url: sttAuthority.websocketUrl,
      webSocketCtor: WebSocketCtor,
      chatSessionId: sessionId,
      onNegotiated: (negotiation) => {
        reporter.record('stt_negotiated', {
          provider: negotiation.provider,
          protocol: negotiation.protocol,
          sample_rate: negotiation.sampleRate,
          frame_samples: negotiation.frameSamples,
          encoding: negotiation.encoding,
          capabilities: negotiation.capabilities,
          config_version: negotiation.configVersion,
          language: negotiation.language,
        }, 'live_voice_controller');
        dispatchLiveVoicePerfEvent({
          stage: 'stt_negotiated',
          timestamp: new Date().toISOString(),
          provider: negotiation.provider,
          protocol: negotiation.protocol,
          sampleRate: negotiation.sampleRate,
          frameSamples: negotiation.frameSamples,
          encoding: negotiation.encoding,
          capabilities: negotiation.capabilities,
          configVersion: negotiation.configVersion,
          language: negotiation.language,
        });
      },
      onEndpointScore: (event) => {
        reporter.record('stt_endpoint_score', {
          provider: event.provider,
          segment_id: event.segmentId,
          source_sequence: event.sequence,
          probability: event.probability,
          model_time_ms: event.modelTimeMs,
          signal: event.signal,
        }, 'live_voice_controller');
        dispatchLiveVoicePerfEvent({
          stage: 'stt_endpoint_score',
          timestamp: new Date().toISOString(),
          provider: event.provider,
          segmentId: event.segmentId,
          sourceSequence: event.sequence,
          probability: event.probability,
          modelTimeMs: event.modelTimeMs,
          signal: event.signal,
        });
      },
      onEndpointCandidate: (event) => handleProviderEndpointCandidate(card, event),
      onPreviewTranscript: (event) => handleAuthoritativePreview(card, event),
      onProviderEvent: (event) => {
        const stage = `stt_${event.type}`;
        reporter.record(stage, {
          provider: event.provider,
          attempt_id: event.attemptId,
          wall_ms: event.wall_ms,
          model_ms: event.model_ms,
          realtime_factor: event.realtime_factor,
        }, 'live_voice_controller');
        dispatchLiveVoicePerfEvent({
          stage,
          timestamp: new Date().toISOString(),
          provider: event.provider,
          attemptId: event.attemptId,
          wallMs: event.wall_ms,
          modelMs: event.model_ms,
          realtimeFactor: event.realtime_factor,
        });
      },
      onStatusChange: (status) => {
        if (activeSession?.card === card || pendingStart?.card === card) setPanelStatus(card, status);
      },
      onPartialTranscript: (text) => handlePartialTranscript(card, text),
      onAcceptedFinal: (final) => handleAcceptedFinal(card, final),
      onFinalRejected: (reason, identity) => {
        reporter.record('stt_final_rejected', {
          reason,
          segment_id: identity.segmentId,
          result_id: identity.resultId,
          finalize_request_id: identity.finalizeRequestId,
          source_sequence: identity.sourceSequence,
          capture_epoch: identity.captureEpoch,
        }, 'live_voice_controller');
        dispatchLiveVoicePerfEvent({ stage: 'stt_final_rejected', timestamp: new Date().toISOString(), reason, segmentId: identity.segmentId, sourceSequence: identity.sourceSequence });
        setPanelStatus(card, 'error');
      },
      onError: (message) => showLiveVoiceError(card, message),
      onSegmentStateChange: (state) => {
        if (!segmentTelemetryGate.shouldReport(state)) return;
        dispatchLiveVoicePerfEvent({
          stage: 'stt_segment_state',
          timestamp: new Date().toISOString(),
          protocol: state.protocol,
          activeSequence: state.activeSequence,
          pendingSegments: state.pendingSegments,
          queuedSegments: state.queuedSegments,
          absoluteSample: state.absoluteSample,
        });
      },
    });
    const shell = {
      card,
      stream,
      audioContext,
      source,
      client,
      finalizationBuffer: new FinalizationAudioBuffer(
        Math.max(1, Math.round(audioContext.sampleRate * FINALIZATION_BUFFER_MS / 1_000)),
      ),
      preSpeechBuffer: new LiveVoicePreSpeechBuffer(
        Math.max(1, Math.round(audioContext.sampleRate * PRE_SPEECH_BUFFER_MS / 1_000)),
      ),
      reporter,
      sttAuthority,
      speculationSegmentId: null,
      speculationSourceSequence: null,
      speechDetected: false,
      finalRequested: false,
      silenceTimer: null,
      previewTimer: null,
      previewRequestId: null,
      authoritativePreviewText: '',
      pauseStartedAt: null,
      finalResponseTimer: null,
      voiceLevel: 0,
      speechFrameCount: 0,
      perfTurnId: null,
      sttFinalRequestedAt: null,
      partialTranscript: '',
      partialTranscriptUpdatedAt: performance.now(),
      floorState: reduceUserFloor('idle', { type: 'listen' }),
      overlapIntent: null,
      interruptionDispatched: false,
    };
    audioPipeline = await createLiveVoiceAudioPipeline(audioContext, (audio) => {
      const session = activeSession;
      if (session?.card === card) processAudioFrame(session, audio);
    });
    source.connect(audioPipeline.node);
    await ensureAudioContextRunning(audioContext);
    const session: LiveVoiceSession = { ...shell, audioPipeline };
    activeSession = session;
    pendingStart = null;
    await client.connect();
    if (activeSession !== session || token !== startToken) {
      cleanupSession(session);
      return;
    }
    setPanelStatus(card, 'connected');
    dispatchLiveVoiceLifecycleEvent(LIVE_VOICE_CALL_CONNECTED_EVENT, {
      token,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    if (activeSession?.card === card) {
      const session = activeSession;
      activeSession = null;
      cleanupSession(session);
    } else closePendingResources(stream, audioContext, source, audioPipeline);
    if (pendingStart?.token === token) pendingStart = null;
    if (sessionReporter) {
      void sessionReporter.close('live_capture_start_failed', {
        error: error instanceof Error ? error.message : String(error),
      });
    }
    showLiveVoiceError(card, error instanceof Error ? error.message : 'Could not start live voice.');
  }
}

export function waitForLiveConversationSessionId(
  timeoutMs = LIVE_SESSION_SELECTION_TIMEOUT_MS,
): Promise<string | null> {
  const selected = liveConversationStore.getState().sessionId;
  if (selected) return Promise.resolve(selected);
  return new Promise((resolve) => {
    let unsubscribe = () => undefined;
    let timerId: ReturnType<typeof window.setTimeout> | null = null;
    let settled = false;
    const finish = (sessionId: string | null) => {
      if (settled) return;
      settled = true;
      unsubscribe();
      if (timerId !== null) window.clearTimeout(timerId);
      resolve(sessionId);
    };
    unsubscribe = liveConversationStore.subscribe(() => {
      const sessionId = liveConversationStore.getState().sessionId;
      if (sessionId) finish(sessionId);
    });
    const sessionId = liveConversationStore.getState().sessionId;
    if (sessionId) {
      finish(sessionId);
      return;
    }
    timerId = window.setTimeout(() => finish(null), Math.max(0, timeoutMs));
  });
}

function isCurrentStart(card: HTMLElement, token: number): boolean {
  return pendingStart?.card === card && pendingStart.token === token && startToken === token;
}

async function ensureAudioContextRunning(audioContext: AudioContext): Promise<void> {
  if (audioContext.state === 'closed') throw new Error('Microphone audio processing closed before capture started.');
  if (audioContext.state !== 'running') await audioContext.resume();
  if (audioContext.state !== 'running') throw new Error('Microphone audio processing is suspended. Allow audio playback and try again.');
}

async function createLiveVoiceAudioPipeline(
  audioContext: AudioContext,
  onAudioFrame: (audio: Float32Array) => void,
): Promise<LiveVoiceAudioPipeline> {
  if ('audioWorklet' in audioContext && typeof AudioWorkletNode !== 'undefined') {
    try {
      await ensureLiveVoiceWorklet(audioContext);
      const node = new AudioWorkletNode(audioContext, 'omnix-live-voice-processor');
      const silentOutput = audioContext.createGain();
      silentOutput.gain.value = 0;
      node.port.onmessage = (event: MessageEvent<Float32Array>) => onAudioFrame(new Float32Array(event.data));
      node.connect(silentOutput);
      silentOutput.connect(audioContext.destination);
      return {
        node,
        cleanup: () => {
          node.port.onmessage = null;
          node.disconnect();
          silentOutput.disconnect();
        },
      };
    } catch {
      // Fall through to ScriptProcessor on browsers that reject dynamic worklets.
    }
  }
  const processor = audioContext.createScriptProcessor(1024, 1, 1);
  const silentOutput = audioContext.createGain();
  silentOutput.gain.value = 0;
  processor.onaudioprocess = (event) => onAudioFrame(new Float32Array(event.inputBuffer.getChannelData(0)));
  processor.connect(silentOutput);
  silentOutput.connect(audioContext.destination);
  return {
    node: processor,
    cleanup: () => {
      processor.onaudioprocess = null;
      processor.disconnect();
      silentOutput.disconnect();
    },
  };
}

async function ensureLiveVoiceWorklet(audioContext: AudioContext): Promise<void> {
  if (liveVoiceWorkletContexts.has(audioContext)) return;
  liveVoiceWorkletModuleUrl ??= URL.createObjectURL(new Blob([`
class OmnixLiveVoiceProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel && channel.length) {
      const audio = new Float32Array(channel);
      this.port.postMessage(audio, [audio.buffer]);
    }
    return true;
  }
  
}
registerProcessor('omnix-live-voice-processor', OmnixLiveVoiceProcessor);
`], { type: 'text/javascript' }));
  await audioContext.audioWorklet.addModule(liveVoiceWorkletModuleUrl);
  liveVoiceWorkletContexts.add(audioContext);
}

function processAudioFrame(session: LiveVoiceSession, audio: Float32Array): void {
  const assistantOwnsFloor = liveVoiceAssistantOwnsFloor();
  const assistantSpeaking = liveVoiceAssistantIsSpeaking();
  const rms = calculateRms(audio);
  updateVoiceVisualizer(session, rms);
  if (session.finalRequested) {
    if (session.client.segmentedProtocolActive) {
      session.client.sendAudio(audio, session.audioContext.sampleRate);
      return;
    }
    const buffered = session.finalizationBuffer.push(audio);
    if (!buffered.accepted) handleFinalizationBufferOverflow(session, buffered.bufferedSamples, buffered.maxSamples);
    return;
  }
  const speechWasDetected = session.speechDetected;
  if (!speechWasDetected) session.preSpeechBuffer.push(audio);
  const speechStarted = rms >= liveVoiceSpeechThreshold();
  session.speechFrameCount = speechStarted ? session.speechFrameCount + 1 : 0;
  const confirmedSpeech = session.speechFrameCount >= INTERRUPT_CONFIRMATION_FRAMES;
  if (confirmedSpeech && !session.speechDetected) {
    dispatchLiveVoiceLifecycleEvent(LIVE_VOICE_USER_SPEECH_EVENT, {
      timestamp: new Date().toISOString(),
      rms,
      assistantSpeaking,
      assistantOwnsFloor,
    });
  }
  if (assistantOwnsFloor && confirmedSpeech && !session.speechDetected) {
    session.overlapIntent = 'uncertain';
    session.floorState = reduceUserFloor(session.floorState, {
      type: 'speech_confirmed',
      assistantSpeaking: true,
    });
    dispatchLiveVoicePerfEvent({
      stage: 'overlap_candidate',
      timestamp: new Date().toISOString(),
      rms,
    });
  }
  if (confirmedSpeech) {
    if (session.pauseStartedAt !== null) clearAuthoritativePreview(session, true);
    session.speechDetected = true;
    session.pauseStartedAt = null;
    if (!assistantOwnsFloor) {
      session.overlapIntent = null;
      session.floorState = reduceUserFloor(session.floorState, {
        type: 'speech_confirmed',
        assistantSpeaking: false,
      });
    }
    if (session.silenceTimer) {
      clearTimeout(session.silenceTimer);
      session.silenceTimer = null;
      session.floorState = reduceUserFloor(session.floorState, { type: 'resume' });
    }
  } else if (session.speechDetected && !session.silenceTimer) {
    session.pauseStartedAt = performance.now();
    session.floorState = reduceUserFloor(session.floorState, { type: 'pause' });
    scheduleSemanticFinalization(session);
    scheduleAuthoritativePreview(session);
  }
  if (!session.speechDetected) return;
  if (!speechWasDetected) {
    const preSpeechFrames = session.preSpeechBuffer.drain();
    const preSpeechSamples = preSpeechFrames.reduce((total, frame) => total + frame.length, 0);
    dispatchLiveVoicePerfEvent({
      stage: 'stt_pre_speech_buffer_flushed',
      timestamp: new Date().toISOString(),
      frames: preSpeechFrames.length,
      samples: preSpeechSamples,
      sampleRate: session.audioContext.sampleRate,
      assistantOwnsFloor,
    });
    preSpeechFrames.forEach((frame) => session.client.sendAudio(frame, session.audioContext.sampleRate));
    return;
  }
  session.client.sendAudio(audio, session.audioContext.sampleRate);
}

function handleFinalizationBufferOverflow(session: LiveVoiceSession, bufferedSamples: number, maxSamples: number): void {
  dispatchLiveVoicePerfEvent({
    stage: 'stt_finalization_buffer_overflow',
    timestamp: new Date().toISOString(),
    bufferedSamples,
    maxSamples,
    sampleRate: session.audioContext.sampleRate,
  });
  stopLiveVoice(session.card, 'error');
  renderTranscript(
    session.card,
    'Omnix',
    'Live voice paused because transcription fell behind. Restart the call to continue; no buffered audio was silently discarded.',
    'final',
  );
}

function dispatchLiveSttSpeculationEvent(type: string, detail: Record<string, unknown>): void {
  window.dispatchEvent(new CustomEvent(type, { detail }));
}

function handleProviderEndpointCandidate(card: HTMLElement, event: ProviderEndpointCandidate): void {
  const session = activeSession;
  if (!session || session.card !== card) return;
  const now = performance.now();
  const candidateText = session.partialTranscript.trim();
  const pauseElapsedMs = session.pauseStartedAt === null
    ? 0
    : Math.max(0, now - session.pauseStartedAt);
  const assessment = assessSemanticTurn(candidateText, readConversationPace());
  const transcriptStableMs = Math.max(0, now - session.partialTranscriptUpdatedAt);
  const transcriptWords = candidateText ? candidateText.split(/\s+/u).length : 0;
  const correctionPending = assessment.reason === 'self_correction';
  const fusionAction = endpointFusionAction({
    endpointProbability: event.probability,
    endpointThreshold: session.sttAuthority.endpointThreshold,
    silenceMs: pauseElapsedMs,
    transcriptStableMs,
    semanticProbabilityDone: assessment.probabilityDone,
    transcriptWords,
    correctionPending,
  });
  session.reporter.record('stt_endpoint_candidate', {
    provider: event.provider,
    segment_id: event.segmentId,
    source_sequence: event.sequence,
    probability: event.probability,
    model_time_ms: event.modelTimeMs,
    transcript_chars: candidateText.length,
    transcript_words: transcriptWords,
    transcript_stable_ms: Math.round(transcriptStableMs),
    semantic_probability_done: assessment.probabilityDone,
    semantic_reason: assessment.reason,
    endpoint_fusion_action: fusionAction,
    authority_enabled: session.sttAuthority.authorityEnabled,
    pause_elapsed_ms: Math.round(pauseElapsedMs),
    endpoint_min_silence_ms: PROVIDER_ENDPOINT_MIN_SILENCE_MS,
  }, 'live_voice_controller');
  dispatchLiveVoicePerfEvent({
    stage: 'stt_endpoint_candidate',
    timestamp: new Date().toISOString(),
    provider: event.provider,
    segmentId: event.segmentId,
    sourceSequence: event.sequence,
    probability: event.probability,
    modelTimeMs: event.modelTimeMs,
    transcriptChars: candidateText.length,
    transcriptWords,
    transcriptStableMs: Math.round(transcriptStableMs),
    semanticProbabilityDone: assessment.probabilityDone,
    semanticReason: assessment.reason,
    endpointFusionAction: fusionAction,
    authorityEnabled: session.sttAuthority.authorityEnabled,
    pauseElapsedMs: Math.round(pauseElapsedMs),
    endpointMinSilenceMs: PROVIDER_ENDPOINT_MIN_SILENCE_MS,
  });
  if (
    session.sttAuthority.authorityEnabled
    && !session.client.authoritativePreviewSupported
    && candidateText
    && fusionAction !== 'continue'
  ) {
    session.speculationSegmentId = event.segmentId;
    session.speculationSourceSequence = event.sequence;
    const detail = {
      chatSessionId: liveConversationStore.getState().sessionId,
      segmentId: event.segmentId,
      sourceSequence: event.sequence,
      text: candidateText,
    };
    dispatchLiveSttSpeculationEvent(LIVE_STT_SPECULATION_PARTIAL_EVENT, detail);
    dispatchLiveSttSpeculationEvent(LIVE_STT_SPECULATION_CANDIDATE_EVENT, {
      ...detail,
      probability: event.probability,
      modelTimeMs: event.modelTimeMs,
    });
  }
  if (!shouldCommitProviderEndpoint({
    authorityEnabled: session.sttAuthority.authorityEnabled,
    probability: event.probability,
    endpointThreshold: session.sttAuthority.endpointThreshold,
    speechDetected: session.speechDetected,
    finalRequested: session.finalRequested,
    pausePending: session.silenceTimer !== null,
    pauseElapsedMs,
    transcriptStableMs,
    semanticProbabilityDone: assessment.probabilityDone,
    transcriptWords,
    correctionPending,
  })) return;
  requestFinalTranscript(session, 'provider_endpoint', event);
}

function handlePartialTranscript(card: HTMLElement, text: string): void {
  const session = activeSession;
  if (session?.card === card) {
    const normalized = text.trim();
    const transcriptChanged = normalized !== session.partialTranscript;
    if (transcriptChanged) {
      session.partialTranscript = normalized;
      session.partialTranscriptUpdatedAt = performance.now();
      if (
        session.silenceTimer
        && session.pauseStartedAt !== null
        && !session.finalRequested
      ) {
        rescheduleSemanticFinalization(session);
      }
    }
    if (
      session.sttAuthority.authorityEnabled
      && session.speculationSegmentId
      && session.speculationSourceSequence !== null
    ) {
      dispatchLiveSttSpeculationEvent(LIVE_STT_SPECULATION_PARTIAL_EVENT, {
        chatSessionId: liveConversationStore.getState().sessionId,
        segmentId: session.speculationSegmentId,
        sourceSequence: session.speculationSourceSequence,
        text: session.authoritativePreviewText && session.pauseStartedAt !== null
          ? session.authoritativePreviewText
          : session.partialTranscript,
      });
    }
    if (session.floorState === 'overlap_candidate' && liveVoiceAssistantIsSpeaking()) {
      assessOverlapCandidate(session);
    }
  }
  renderTranscript(card, 'You', text, 'draft');
}

function scheduleAuthoritativePreview(session: LiveVoiceSession): void {
  if (session.previewTimer || session.previewRequestId || session.finalRequested) return;
  session.previewTimer = setTimeout(() => {
    session.previewTimer = null;
    if (
      activeSession !== session
      || session.finalRequested
      || session.pauseStartedAt === null
      || !session.speechDetected
    ) return;
    session.previewRequestId = session.client.requestAuthoritativePreview();
    dispatchLiveVoicePerfEvent({
      stage: 'stt_authoritative_preview_requested',
      turnId: session.perfTurnId,
      timestamp: new Date().toISOString(),
      requested: session.previewRequestId !== null,
      pauseElapsedMs: Math.round(performance.now() - session.pauseStartedAt),
    });
  }, AUTHORITATIVE_PREVIEW_PAUSE_MS);
}

function handleAuthoritativePreview(
  card: HTMLElement,
  event: {
    segmentId: string;
    sequence: number;
    previewRequestId: string;
    snapshotEndSample: number;
    text: string;
    provider?: string;
    providerMetrics?: Record<string, number>;
  },
): void {
  const session = activeSession;
  const text = event.text.trim();
  if (
    !session
    || session.card !== card
    || (!session.finalRequested && session.pauseStartedAt === null)
    || event.previewRequestId !== session.previewRequestId
    || !text
  ) return;
  session.authoritativePreviewText = text;
  session.speculationSegmentId = event.segmentId;
  session.speculationSourceSequence = event.sequence;
  const detail = {
    chatSessionId: liveConversationStore.getState().sessionId,
    segmentId: event.segmentId,
    sourceSequence: event.sequence,
    text,
  };
  dispatchLiveSttSpeculationEvent(LIVE_STT_SPECULATION_PARTIAL_EVENT, detail);
  dispatchLiveSttSpeculationEvent(LIVE_STT_SPECULATION_CANDIDATE_EVENT, {
    ...detail,
    probability: 1,
    modelTimeMs: event.snapshotEndSample * 1_000 / 16_000,
  });
  dispatchLiveVoicePerfEvent({
    stage: 'stt_authoritative_preview_received',
    turnId: session.perfTurnId,
    timestamp: new Date().toISOString(),
    provider: event.provider,
    segmentId: event.segmentId,
    sourceSequence: event.sequence,
    transcriptChars: text.length,
    providerMetrics: event.providerMetrics,
  });
}

function clearAuthoritativePreview(session: LiveVoiceSession, resumedSpeech = false): void {
  if (resumedSpeech) {
    if (
      session.authoritativePreviewText
      && session.speculationSegmentId
      && session.speculationSourceSequence !== null
      && session.partialTranscript
    ) {
      dispatchLiveSttSpeculationEvent(LIVE_STT_SPECULATION_PARTIAL_EVENT, {
        chatSessionId: liveConversationStore.getState().sessionId,
        segmentId: session.speculationSegmentId,
        sourceSequence: session.speculationSourceSequence,
        text: session.partialTranscript,
      });
    }
    session.speculationSegmentId = null;
    session.speculationSourceSequence = null;
  }
  if (session.previewTimer) clearTimeout(session.previewTimer);
  session.previewTimer = null;
  session.previewRequestId = null;
  session.authoritativePreviewText = '';
}

function assessOverlapCandidate(session: LiveVoiceSession): void {
  const assessment = classifyOverlap(session.partialTranscript, currentAssistantSpeechText());
  session.overlapIntent = assessment.intent;
  dispatchLiveVoicePerfEvent({
    stage: 'overlap_classified',
    timestamp: new Date().toISOString(),
    intent: assessment.intent,
    confidence: assessment.confidence,
    reason: assessment.reason,
    transcriptChars: session.partialTranscript.length,
  });
  if (!session.interruptionDispatched && shouldConfirmInterruption(assessment)) {
    session.interruptionDispatched = true;
    dispatchAssistantVoiceInterrupt(session.card, assessment.intent, assessment.confidence);
  }
}

function scheduleSemanticFinalization(session: LiveVoiceSession): void {
  session.perfTurnId ??= `voice-turn:${Date.now()}`;
  session.floorState = reduceUserFloor(session.floorState, { type: 'completion_check' });
  armSemanticFinalizationTimer(session, 'semantic_turn_assessed');
}

function rescheduleSemanticFinalization(session: LiveVoiceSession): void {
  armSemanticFinalizationTimer(session, 'semantic_turn_rescheduled');
}

function armSemanticFinalizationTimer(
  session: LiveVoiceSession,
  stage: 'semantic_turn_assessed' | 'semantic_turn_rescheduled',
): void {
  const now = performance.now();
  const pace = readConversationPace();
  const assessment = assessSemanticTurn(session.partialTranscript, pace);
  const targetDelayMs = semanticFinalizeDelay(session.partialTranscript, pace);
  const pauseElapsedMs = session.pauseStartedAt === null
    ? 0
    : Math.max(0, now - session.pauseStartedAt);
  const transcriptStableMs = Math.max(0, now - session.partialTranscriptUpdatedAt);
  const remainingMs = semanticFinalizationRemainingMs(
    session.partialTranscript,
    pace,
    pauseElapsedMs,
    transcriptStableMs,
  );
  if (session.silenceTimer) clearTimeout(session.silenceTimer);
  dispatchLiveVoicePerfEvent({
    stage,
    turnId: session.perfTurnId,
    timestamp: new Date().toISOString(),
    pace,
    probabilityDone: assessment.probabilityDone,
    reason: assessment.reason,
    delayMs: targetDelayMs,
    pauseElapsedMs: Math.round(pauseElapsedMs),
    transcriptStableMs: Math.round(transcriptStableMs),
    remainingMs: Math.round(remainingMs),
    transcriptChars: session.partialTranscript.length,
  });
  session.silenceTimer = setTimeout(
    () => requestFinalTranscript(session, 'semantic_timeout'),
    remainingMs,
  );
}

function shouldDeferSemanticTimeout(session: LiveVoiceSession): boolean {
  if (session.pauseStartedAt === null) return false;
  const now = performance.now();
  const pace = readConversationPace();
  const pauseElapsedMs = Math.max(0, now - session.pauseStartedAt);
  const transcriptStableMs = Math.max(0, now - session.partialTranscriptUpdatedAt);
  const remainingMs = semanticFinalizationRemainingMs(
    session.partialTranscript,
    pace,
    pauseElapsedMs,
    transcriptStableMs,
  );
  if (remainingMs <= 1) return false;
  const assessment = assessSemanticTurn(session.partialTranscript, pace);
  dispatchLiveVoicePerfEvent({
    stage: 'semantic_turn_commit_deferred',
    turnId: session.perfTurnId,
    timestamp: new Date().toISOString(),
    pace,
    probabilityDone: assessment.probabilityDone,
    reason: assessment.reason,
    pauseElapsedMs: Math.round(pauseElapsedMs),
    transcriptStableMs: Math.round(transcriptStableMs),
    remainingMs: Math.round(remainingMs),
    transcriptChars: session.partialTranscript.length,
  });
  armSemanticFinalizationTimer(session, 'semantic_turn_rescheduled');
  return true;
}

function handleExternalStop(): void {
  if (activeSession) stopLiveVoice(activeSession.card, 'idle');
  else if (pendingStart) {
    pendingStart = null;
    startToken += 1;
  }
}

function dispatchAssistantVoiceInterrupt(
  card: HTMLElement,
  intent: OverlapIntent = 'interrupt',
  confidence = 1,
): void {
  window.dispatchEvent(new CustomEvent(LIVE_VOICE_INTERRUPT_EVENT, {
    detail: {
      source: 'live-voice',
      status: panelStatuses.get(card) ?? 'connected',
      timestamp: new Date().toISOString(),
      intent,
      confidence,
    },
  }));
}

function requestFinalTranscript(
  session: LiveVoiceSession,
  trigger: 'semantic_timeout' | 'provider_endpoint' = 'semantic_timeout',
  endpoint?: ProviderEndpointCandidate,
): void {
  if (activeSession !== session || session.finalRequested) return;
  if (trigger === 'semantic_timeout' && shouldDeferSemanticTimeout(session)) return;
  if (session.silenceTimer) clearTimeout(session.silenceTimer);
  if (session.previewTimer) clearTimeout(session.previewTimer);
  session.silenceTimer = null;
  session.previewTimer = null;
  session.pauseStartedAt = null;
  if (session.floorState === 'overlap_candidate' && session.partialTranscript) assessOverlapCandidate(session);
  session.floorState = reduceUserFloor(session.floorState, { type: 'commit' });
  session.finalRequested = true;
  session.perfTurnId ??= `voice-turn:${Date.now()}`;
  session.sttFinalRequestedAt = performance.now();
  if (trigger === 'provider_endpoint' && endpoint) {
    session.reporter.record('stt_endpoint_committed', {
      provider: endpoint.provider,
      segment_id: endpoint.segmentId,
      source_sequence: endpoint.sequence,
      probability: endpoint.probability,
      model_time_ms: endpoint.modelTimeMs,
      endpoint_threshold: session.sttAuthority.endpointThreshold,
      endpoint_min_silence_ms: PROVIDER_ENDPOINT_MIN_SILENCE_MS,
    }, 'live_voice_controller');
    dispatchLiveVoicePerfEvent({
      stage: 'stt_endpoint_committed',
      timestamp: new Date().toISOString(),
      turnId: session.perfTurnId,
      provider: endpoint.provider,
      segmentId: endpoint.segmentId,
      sourceSequence: endpoint.sequence,
      probability: endpoint.probability,
      modelTimeMs: endpoint.modelTimeMs,
      endpointThreshold: session.sttAuthority.endpointThreshold,
      endpointMinSilenceMs: PROVIDER_ENDPOINT_MIN_SILENCE_MS,
    });
  }
  dispatchLiveVoicePerfEvent({
    stage: 'stt_final_requested',
    turnId: session.perfTurnId,
    timestamp: new Date().toISOString(),
    trigger,
  });
  session.client.sendFinal();
  session.finalResponseTimer = setTimeout(() => {
    if (activeSession !== session) return;
    const continuation = session.finalizationBuffer.drain();
    resetTurnState(session);
    setPanelStatus(session.card, 'connected');
    replayFinalizationBuffer(session, continuation);
  }, FINAL_RESPONSE_TIMEOUT_MS);
}

function updateVoiceVisualizer(session: LiveVoiceSession, rms: number): void {
  session.voiceLevel = smoothLiveVoiceLevel(session.voiceLevel, rms);
  const scales = liveVoiceVisualScales(session.voiceLevel);
  session.card.style.setProperty('--voice-level', session.voiceLevel.toFixed(3));
  session.card.style.setProperty('--voice-bar-scale', scales.barScale.toFixed(3));
  session.card.style.setProperty('--voice-ambient-scale', scales.ambientScale.toFixed(3));
  session.card.style.setProperty('--voice-core-scale', scales.coreScale.toFixed(3));
  session.card.style.setProperty('--voice-input-scale', scales.inputScale.toFixed(3));
  session.card.dataset.voiceInput = session.voiceLevel >= 0.14 ? 'active' : 'listening';
  setText(session.card.querySelector('.assistant-voice-input-status'), session.voiceLevel >= 0.14 ? 'Hearing you' : 'Listening');
  const orb = session.card.querySelector<HTMLElement>('.assistant-voice-orb');
  if (orb?.dataset.voiceMode !== 'speaking') orb?.setAttribute('data-voice-mode', 'listening');
}

async function handleAcceptedFinal(card: HTMLElement, final: AcceptedVoiceFinal): Promise<LiveFinalRoutingResult> {
  const session = activeSession;
  if (!session || session.card !== card) {
    return failedRoutingResult(final, 'live_capture_session_inactive');
  }
  const receivedAt = performance.now();
  const partialOverlapIntent = session.overlapIntent;
  const finalOverlapAssessment = partialOverlapIntent === 'uncertain'
    ? classifyOverlap(final.text, currentAssistantSpeechText())
    : null;
  const overlapIntent = finalOverlapAssessment?.intent ?? partialOverlapIntent;
  const interruptionDispatched = session.interruptionDispatched;
  const suppressionReason = acceptedFinalSuppressionReason(final.text, overlapIntent);
  const continuation = session.finalizationBuffer.drain();
  dispatchLiveSttSpeculationEvent(LIVE_STT_SPECULATION_FINAL_EVENT, {
    chatSessionId: final.chatSessionId,
    segmentId: final.segmentId,
    sourceSequence: final.sourceSequence,
    text: final.text,
  });
  dispatchLiveVoicePerfEvent({
    stage: 'stt_final_received',
    turnId: session.perfTurnId ?? `voice-turn:${Date.now()}`,
    timestamp: new Date().toISOString(),
    transcriptChars: final.text.trim().length,
    sttFinalizeMs: session.sttFinalRequestedAt === null ? undefined : Math.round(receivedAt - session.sttFinalRequestedAt),
    segmentId: final.segmentId,
    sourceSequence: final.sourceSequence,
    captureEpoch: final.captureEpoch,
  });
  session.reporter.record('stt_final_received', {
    ...currentLiveRuntimeProvenance(),
    chat_session_id: final.chatSessionId,
    stt_session_id: final.sttSessionId,
    capture_epoch: final.captureEpoch,
    segment_id: final.segmentId,
    result_id: final.resultId,
    finalize_request_id: final.finalizeRequestId,
    source_sequence: final.sourceSequence,
    start_sample: final.startSample,
    end_sample: final.endSample,
    protocol: final.protocol,
    transcript_chars: final.text.trim().length,
    stt_finalize_ms: session.sttFinalRequestedAt === null ? undefined : Math.round(receivedAt - session.sttFinalRequestedAt),
    overlap_intent: overlapIntent,
    overlap_confidence: finalOverlapAssessment?.confidence,
    overlap_reason: finalOverlapAssessment?.reason,
    interruption_dispatched: interruptionDispatched,
  }, 'live_voice_controller');
  resetTurnState(session);
  try {
    if (suppressionReason) {
      const result = ignoredRoutingResult(final);
      session.reporter.record('coordination_completed', {
        segment_id: final.segmentId,
        result_id: final.resultId,
        source_sequence: final.sourceSequence,
        outcome: result.outcome,
        suppression_reason: suppressionReason,
        overlap_intent: overlapIntent,
        overlap_confidence: finalOverlapAssessment?.confidence,
        overlap_reason: finalOverlapAssessment?.reason,
      }, 'live_voice_controller');
      return result;
    }
    renderTranscript(card, 'You', final.text, 'final');
    session.reporter.record('coordination_started', {
      segment_id: final.segmentId,
      result_id: final.resultId,
      finalize_request_id: final.finalizeRequestId,
      source_sequence: final.sourceSequence,
      capture_epoch: final.captureEpoch,
      overlap_intent: overlapIntent,
      overlap_confidence: finalOverlapAssessment?.confidence,
      overlap_reason: finalOverlapAssessment?.reason,
      interruption_dispatched: interruptionDispatched,
    }, 'live_voice_controller');
    dispatchLiveVoicePerfEvent({
      stage: 'coordination_started',
      timestamp: new Date().toISOString(),
      segmentId: final.segmentId,
      sourceSequence: final.sourceSequence,
      captureEpoch: final.captureEpoch,
    });
    try {
      const result = await liveSessionCoordinator.routeAcceptedFinal(final);
      session.reporter.record('coordination_completed', {
        segment_id: final.segmentId,
        result_id: final.resultId,
        source_sequence: final.sourceSequence,
        outcome: result.outcome,
        task_contract_id: result.taskContractId,
        task_contract_version: result.taskContractVersion,
        error_code: result.errorCode,
      }, 'live_voice_controller');
      dispatchLiveVoicePerfEvent({
        stage: 'coordination_completed',
        timestamp: new Date().toISOString(),
        segmentId: final.segmentId,
        sourceSequence: final.sourceSequence,
        outcome: result.outcome,
        errorCode: result.errorCode,
      });
      if (result.outcome === 'failed') setPanelStatus(card, 'error');
      else setPanelStatus(card, 'connected');
      return result;
    } catch (error) {
      const result = failedRoutingResult(final, 'live_coordination_failed');
      session.reporter.record('coordination_completed', {
        segment_id: final.segmentId,
        result_id: final.resultId,
        source_sequence: final.sourceSequence,
        outcome: result.outcome,
        error_code: result.errorCode,
        error: error instanceof Error ? error.message : String(error),
      }, 'live_voice_controller');
      setPanelStatus(card, 'error');
      return result;
    }
  } finally {
    dispatchLiveSttSpeculationEvent(LIVE_STT_SPECULATION_DELIVERY_SETTLED_EVENT, {
      chatSessionId: final.chatSessionId,
      segmentId: final.segmentId,
      sourceSequence: final.sourceSequence,
      text: final.text,
    });
    replayFinalizationBuffer(session, continuation);
  }
}

function ignoredRoutingResult(final: AcceptedVoiceFinal): LiveFinalRoutingResult {
  const task = liveConversationStore.getState().coordination.taskContract;
  return { outcome: 'ignored', segmentId: final.segmentId, sourceSequence: final.sourceSequence, taskContractId: task.taskContractId, taskContractVersion: task.version };
}

function failedRoutingResult(final: AcceptedVoiceFinal, errorCode: string): LiveFinalRoutingResult {
  const task = liveConversationStore.getState().coordination.taskContract;
  return { outcome: 'failed', segmentId: final.segmentId, sourceSequence: final.sourceSequence, taskContractId: task.taskContractId, taskContractVersion: task.version, errorCode };
}

function ensureLiveTaskPreset(card: HTMLElement): void {
  if (card.querySelector('[data-live-task-instruction]')) return;
  const select = document.createElement('select');
  select.dataset.liveTaskInstruction = 'true';
  select.setAttribute('aria-label', 'Live task');
  for (const [label, value] of [
    ['Conversation', ''],
    ['Translate Japanese to English', 'Translate Japanese speech into concise English continuously. Keep listening while speaking.'],
    ['Live grammar correction', 'Correct my grammar continuously while I speak.'],
  ] as const) {
    const option = document.createElement('option');
    option.textContent = label;
    option.value = value;
    select.append(option);
  }
  select.value = window.localStorage.getItem(LIVE_TASK_INSTRUCTION_STORAGE_KEY) ?? '';
  select.addEventListener('change', () => window.localStorage.setItem(LIVE_TASK_INSTRUCTION_STORAGE_KEY, select.value));
  card.querySelector('header')?.append(select);
}

function readLiveTaskInstruction(card: HTMLElement): string | undefined {
  const selected = card.querySelector<HTMLSelectElement>('[data-live-task-instruction]')?.value.trim();
  const stored = window.localStorage.getItem(LIVE_TASK_INSTRUCTION_STORAGE_KEY)?.trim();
  return selected || stored || undefined;
}

function replayFinalizationBuffer(session: LiveVoiceSession, frames: Float32Array[]): void {
  if (activeSession !== session || frames.length === 0) return;
  const samples = frames.reduce((total, frame) => total + frame.length, 0);
  dispatchLiveVoicePerfEvent({
    stage: 'stt_finalization_buffer_replayed',
    timestamp: new Date().toISOString(),
    frames: frames.length,
    samples,
    sampleRate: session.audioContext.sampleRate,
  });
  frames.forEach((frame) => processAudioFrame(session, frame));
}

function resetTurnState(session: LiveVoiceSession): void {
  if (session.silenceTimer) clearTimeout(session.silenceTimer);
  if (session.finalResponseTimer) clearTimeout(session.finalResponseTimer);
  session.silenceTimer = null;
  session.pauseStartedAt = null;
  session.finalResponseTimer = null;
  session.speechDetected = false;
  session.speechFrameCount = 0;
  session.preSpeechBuffer.clear();
  clearAuthoritativePreview(session);
  session.finalRequested = false;
  session.perfTurnId = null;
  session.sttFinalRequestedAt = null;
  session.partialTranscript = '';
  session.partialTranscriptUpdatedAt = performance.now();
  session.speculationSegmentId = null;
  session.speculationSourceSequence = null;
  session.overlapIntent = null;
  session.interruptionDispatched = false;
  session.floorState = reduceUserFloor(session.floorState, { type: 'reset' });
  session.floorState = reduceUserFloor(session.floorState, { type: 'listen' });
}

export function liveVoiceSpeechThreshold(): number {
  const normalized = (readLiveVoiceSensitivity() - 1) / 99;
  return MAX_SPEECH_RMS_THRESHOLD - normalized * (MAX_SPEECH_RMS_THRESHOLD - MIN_SPEECH_RMS_THRESHOLD);
}

function readSettings(): Record<string, unknown> {
  try {
    if (typeof window === 'undefined') return {};
    return JSON.parse(window.localStorage.getItem(ASSISTANT_SETTINGS_STORAGE_KEY) || '{}') as Record<string, unknown>;
  } catch {
    return {};
  }
}

function readLiveVoiceSensitivity(): number {
  const value = readSettings().liveVoiceSensitivity;
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed)
    ? Math.min(100, Math.max(1, Math.round(parsed)))
    : DEFAULT_LIVE_VOICE_SENSITIVITY;
}

function readConversationPace(): ConversationPace {
  const value = readSettings().conversationPace;
  return value === 'quick' || value === 'reflective' ? value : DEFAULT_CONVERSATION_PACE;
}

function liveVoiceAssistantIsSpeaking(): boolean {
  return liveConversationStore.getState().conversation.assistantTurn === 'speaking';
}

export function liveVoiceAssistantOwnsFloor(_card?: HTMLElement): boolean {
  const conversation = liveConversationStore.getState().conversation;
  return conversation.assistantTurn === 'speaking' && conversation.floorOwner === 'assistant';
}

function currentAssistantSpeechText(): string {
  return readCurrentAssistantDiagnosticText();
}

function stopLiveVoice(card: HTMLElement, nextStatus: StreamingSttConnectionStatus): void {
  startToken += 1;
  if (pendingStart?.card === card) pendingStart = null;
  const session = activeSession;
  if (session?.card === card) {
    activeSession = null;
    cleanupSession(session);
  }
  setPanelStatus(card, nextStatus);
  resetVoiceVisualizer(card);
}

function cleanupSession(session: LiveVoiceSession): void {
  session.finalizationBuffer.clear();
  resetTurnState(session);
  session.audioPipeline.cleanup();
  session.source.disconnect();
  session.stream.getTracks().forEach((track) => track.stop());
  session.client.disconnect();
  void session.audioContext.close().catch(() => undefined);
  void session.reporter.close('live_capture_session_closed', {
    session_id: liveConversationStore.getState().sessionId,
  });
}

function closePendingResources(
  stream: MediaStream | null,
  audioContext: AudioContext | null,
  source: MediaStreamAudioSourceNode | null,
  audioPipeline: LiveVoiceAudioPipeline | null,
): void {
  audioPipeline?.cleanup();
  source?.disconnect();
  stream?.getTracks().forEach((track) => track.stop());
  if (audioContext) void audioContext.close().catch(() => undefined);
}

function setPanelStatus(card: HTMLElement, status: StreamingSttConnectionStatus): void {
  panelStatuses.set(card, status);
  renderPanelStatus(card, status);
  queueMicrotask(() => renderPanelStatus(card, panelStatuses.get(card) ?? status));
}

function renderPanelStatus(card: HTMLElement, status: StreamingSttConnectionStatus): void {
  const active = isCardStartingOrActive(card);
  const stateText = status === 'connected' ? 'Listening'
    : status === 'connecting' ? 'Connecting'
      : status === 'disconnected' ? 'Reconnecting'
        : status === 'error' ? 'Error' : 'Idle';
  const connectionText = status === 'connected' ? 'Connected'
    : status === 'connecting' || status === 'disconnected' ? 'Connecting' : 'Disconnected';
  const inputText = status === 'connected' ? 'Listening'
    : status === 'connecting' ? 'Requesting mic'
      : status === 'disconnected' ? 'Reconnecting'
        : status === 'error' ? 'Input error' : 'Idle';
  setText(card.querySelector('header strong'), connectionText);
  setText(card.querySelector('.assistant-live-state span:first-child'), stateText);
  setText(card.querySelector('.assistant-voice-status strong'), stateText);
  setText(card.querySelector('.assistant-voice-input-status'), inputText);
  setDataAttribute(card, 'liveVoiceStatus', status);
  setDataAttribute(card, 'voiceInput', status === 'connected' ? 'listening' : status);
  const callButton = findCallButton(card);
  if (callButton) {
    setText(callButton, active ? 'End Call' : 'Start Call');
    callButton.classList.toggle('danger', active);
    callButton.disabled = status === 'connecting';
  }
  const orb = card.querySelector<HTMLElement>('.assistant-voice-orb');
  if (orb && !(status === 'connected' && orb.dataset.voiceMode === 'speaking')) {
    setDataAttribute(orb, 'voiceMode', status === 'connected' ? 'listening' : status === 'error' ? 'error' : 'idle');
  }
}

function findCallButton(card: HTMLElement): HTMLButtonElement | undefined {
  return Array.from(card.querySelectorAll<HTMLButtonElement>('button')).find((button) => {
    const label = button.textContent?.trim().toLowerCase() ?? '';
    return label === 'start call' || label === 'end call';
  });
}

function resetVoiceVisualizer(card: HTMLElement): void {
  for (const property of ['--voice-level', '--voice-bar-scale', '--voice-ambient-scale', '--voice-core-scale', '--voice-input-scale']) {
    card.style.removeProperty(property);
  }
}

function renderTranscript(card: HTMLElement, speaker: 'You' | 'Omnix', text: string, mode: 'draft' | 'final'): void {
  const transcript = text.trim();
  if (!transcript) return;
  const container = card.querySelector<HTMLElement>('.assistant-voice-transcript');
  if (!container) return;
  let row = container.querySelector<HTMLParagraphElement>('p[data-live-voice-id="live-voice-draft"]');
  if (!row || (mode === 'draft' && row.classList.contains('assistant'))) {
    row = document.createElement('p');
    row.className = speaker === 'Omnix' ? 'assistant' : 'user';
    row.dataset.liveVoiceId = mode === 'draft' ? 'live-voice-draft' : `live-voice-${Date.now()}`;
    const header = document.createElement('span');
    const name = document.createElement('strong');
    name.textContent = speaker;
    const time = document.createElement('time');
    const now = new Date();
    time.dateTime = now.toISOString();
    time.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    header.append(name, time);
    row.append(header, document.createTextNode(transcript));
    container.append(row);
  } else {
    const textNode = Array.from(row.childNodes).find((node) => node.nodeType === Node.TEXT_NODE);
    if (textNode) textNode.textContent = transcript;
    else row.append(document.createTextNode(transcript));
  }
  if (mode === 'final') row.dataset.liveVoiceId = `live-voice-${Date.now()}`;
}

function showLiveVoiceError(card: HTMLElement, message: string): void {
  renderTranscript(card, 'Omnix', message, 'final');
  setPanelStatus(card, 'error');
}

function dispatchLiveVoiceLifecycleEvent(type: string, detail: Record<string, unknown>): void {
  window.dispatchEvent(new CustomEvent(type, { detail }));
}

function dispatchLiveVoicePerfEvent(detail: Record<string, unknown>): void {
  window.dispatchEvent(new CustomEvent(LIVE_VOICE_PERF_EVENT, { detail }));
  console.info('[Omnix Voice Perf]', detail);
}

function setText(element: Element | null, value: string): void {
  if (element && element.textContent !== value) element.textContent = value;
}

function setDataAttribute(element: HTMLElement, key: string, value: string): void {
  if (element.dataset[key] !== value) element.dataset[key] = value;
}
