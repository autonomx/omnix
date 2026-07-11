import {
  type ConversationPace,
  type UserFloorState,
  assessSemanticTurn,
  reduceUserFloor,
  semanticFinalizeDelay,
} from './live-voice-floor-manager';
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
  type StreamingSttWebSocketCtor,
} from './live-voice-websocket';
import { liveVoiceVisualScales, smoothLiveVoiceLevel } from './live-voice-level';
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
  speechDetected: boolean;
  finalRequested: boolean;
  silenceTimer: ReturnType<typeof setTimeout> | null;
  finalResponseTimer: ReturnType<typeof setTimeout> | null;
  voiceLevel: number;
  speechFrameCount: number;
  perfTurnId: string | null;
  sttFinalRequestedAt: number | null;
  partialTranscript: string;
  floorState: UserFloorState;
  overlapIntent: OverlapIntent | null;
  interruptionDispatched: boolean;
};

type PendingStart = { card: HTMLElement; token: number };

const ASSISTANT_SETTINGS_STORAGE_KEY = 'omnix.chatbot.assistantSettings';
const DEFAULT_LIVE_VOICE_SENSITIVITY = 55;
const DEFAULT_CONVERSATION_PACE: ConversationPace = 'balanced';
const MIN_SPEECH_RMS_THRESHOLD = 0.012;
const MAX_SPEECH_RMS_THRESHOLD = 0.06;
const INTERRUPT_CONFIRMATION_FRAMES = 3;
const FINAL_RESPONSE_TIMEOUT_MS = 8_000;
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

export function initializeLiveVoiceController(root: ParentNode = document): void {
  if (initialized || typeof window === 'undefined' || typeof document === 'undefined') return;
  initialized = true;
  (window as LiveVoiceWindow).__omnixLiveVoiceControllerInstalled = true;
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
  let stream: MediaStream | null = null;
  let source: MediaStreamAudioSourceNode | null = null;
  let audioPipeline: LiveVoiceAudioPipeline | null = null;
  try {
    const liveWindow = window as LiveVoiceWindow;
    const AudioContextCtor = liveWindow.AudioContext ?? liveWindow.webkitAudioContext;
    const WebSocketCtor = liveWindow.WebSocket as unknown as StreamingSttWebSocketCtor | undefined;
    if (!AudioContextCtor || !WebSocketCtor) throw new Error('Live voice requires browser AudioContext and WebSocket support.');
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
    const runtimeConfig = createAssistantWorkspaceRuntimeConfig();
    const client = new StreamingSttWebSocketClient({
      url: getDefaultStreamingSttWebSocketUrl(window.location, runtimeConfig.sttServiceUrl),
      webSocketCtor: WebSocketCtor,
      onStatusChange: (status) => {
        if (activeSession?.card === card || pendingStart?.card === card) setPanelStatus(card, status);
      },
      onPartialTranscript: (text) => handlePartialTranscript(card, text),
      onFinalTranscript: (text) => handleFinalTranscript(card, text),
      onError: (message) => showLiveVoiceError(card, message),
    });
    const shell = {
      card,
      stream,
      audioContext,
      source,
      client,
      speechDetected: false,
      finalRequested: false,
      silenceTimer: null,
      finalResponseTimer: null,
      voiceLevel: 0,
      speechFrameCount: 0,
      perfTurnId: null,
      sttFinalRequestedAt: null,
      partialTranscript: '',
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
    showLiveVoiceError(card, error instanceof Error ? error.message : 'Could not start live voice.');
  }
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
  const assistantOwnsFloor = liveVoiceAssistantOwnsFloor(session.card);
  const assistantSpeaking = assistantIsSpeaking(session.card);
  const rms = calculateRms(audio);
  updateVoiceVisualizer(session, rms);
  if (session.finalRequested) return;
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
    session.speechDetected = true;
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
    session.floorState = reduceUserFloor(session.floorState, { type: 'pause' });
    scheduleSemanticFinalization(session);
  }
  if (assistantOwnsFloor && !session.speechDetected) return;
  session.client.sendAudio(audio, session.audioContext.sampleRate);
}

function handlePartialTranscript(card: HTMLElement, text: string): void {
  const session = activeSession;
  if (session?.card === card) {
    session.partialTranscript = text.trim();
    if (session.floorState === 'overlap_candidate' && assistantIsSpeaking(card)) {
      assessOverlapCandidate(session);
    }
  }
  renderTranscript(card, 'You', text, 'draft');
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
  const pace = readConversationPace();
  const assessment = assessSemanticTurn(session.partialTranscript, pace);
  const delayMs = semanticFinalizeDelay(session.partialTranscript, pace);
  session.perfTurnId ??= `voice-turn:${Date.now()}`;
  session.floorState = reduceUserFloor(session.floorState, { type: 'completion_check' });
  dispatchLiveVoicePerfEvent({
    stage: 'semantic_turn_assessed',
    turnId: session.perfTurnId,
    timestamp: new Date().toISOString(),
    pace,
    probabilityDone: assessment.probabilityDone,
    reason: assessment.reason,
    delayMs,
    transcriptChars: session.partialTranscript.length,
  });
  session.silenceTimer = setTimeout(() => requestFinalTranscript(session), delayMs);
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

function requestFinalTranscript(session: LiveVoiceSession): void {
  session.silenceTimer = null;
  if (activeSession !== session || session.finalRequested) return;
  if (session.floorState === 'overlap_candidate' && session.partialTranscript) assessOverlapCandidate(session);
  session.floorState = reduceUserFloor(session.floorState, { type: 'commit' });
  session.finalRequested = true;
  session.perfTurnId ??= `voice-turn:${Date.now()}`;
  session.sttFinalRequestedAt = performance.now();
  dispatchLiveVoicePerfEvent({
    stage: 'stt_final_requested',
    turnId: session.perfTurnId,
    timestamp: new Date().toISOString(),
  });
  session.client.sendFinal();
  session.finalResponseTimer = setTimeout(() => {
    if (activeSession !== session) return;
    resetTurnState(session);
    setPanelStatus(session.card, 'connected');
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

function handleFinalTranscript(card: HTMLElement, text: string): void {
  const session = activeSession;
  if (!session || session.card !== card) return;
  const receivedAt = performance.now();
  const transcript = text.trim();
  const overlapIntent = session.overlapIntent;
  const interruptionDispatched = session.interruptionDispatched;
  if (transcript) {
    dispatchLiveVoicePerfEvent({
      stage: 'stt_final_received',
      turnId: session.perfTurnId ?? `voice-turn:${Date.now()}`,
      timestamp: new Date().toISOString(),
      transcriptChars: transcript.length,
      sttFinalizeMs: session.sttFinalRequestedAt === null ? undefined : Math.round(receivedAt - session.sttFinalRequestedAt),
    });
  }
  const suppressTurn = Boolean(
    overlapIntent === 'hard_stop'
    || overlapIntent === 'backchannel'
    || overlapIntent === 'noise'
    || (overlapIntent === 'uncertain' && !interruptionDispatched),
  );
  resetTurnState(session);
  if (!transcript || suppressTurn) {
    setPanelStatus(card, 'connected');
    return;
  }
  renderTranscript(card, 'You', transcript, 'final');
  populateComposer(transcript);
  submitComposer();
  setPanelStatus(card, 'connected');
}

function resetTurnState(session: LiveVoiceSession): void {
  if (session.silenceTimer) clearTimeout(session.silenceTimer);
  if (session.finalResponseTimer) clearTimeout(session.finalResponseTimer);
  session.silenceTimer = null;
  session.finalResponseTimer = null;
  session.speechDetected = false;
  session.speechFrameCount = 0;
  session.finalRequested = false;
  session.perfTurnId = null;
  session.sttFinalRequestedAt = null;
  session.partialTranscript = '';
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

function assistantIsSpeaking(card: HTMLElement): boolean {
  return card.querySelector<HTMLElement>('.assistant-voice-orb')?.dataset.voiceMode === 'speaking';
}

export function liveVoiceAssistantOwnsFloor(card: HTMLElement): boolean {
  return assistantIsSpeaking(card) && card.dataset.liveVoiceOutputKind !== 'greeting';
}

function currentAssistantSpeechText(): string {
  return document.querySelector<HTMLElement>('[data-omnix-live-delivery]')?.textContent ?? '';
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
  resetTurnState(session);
  session.audioPipeline.cleanup();
  session.source.disconnect();
  session.stream.getTracks().forEach((track) => track.stop());
  session.client.disconnect();
  void session.audioContext.close().catch(() => undefined);
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

function populateComposer(text: string): void {
  const textarea = document.querySelector<HTMLTextAreaElement>('.assistant-message-input textarea');
  if (!textarea) return;
  textarea.value = text;
  textarea.dispatchEvent(new Event('input', { bubbles: true }));
}

function submitComposer(): void {
  const form = document.querySelector<HTMLFormElement>('.assistant-composer');
  if (!form) return;
  if (typeof form.requestSubmit === 'function') form.requestSubmit();
  else form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
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

if (typeof window !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => initializeLiveVoiceController(), { once: true });
  } else initializeLiveVoiceController();
}
