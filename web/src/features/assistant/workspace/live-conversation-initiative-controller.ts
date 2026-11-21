 
import { readEffectiveLiveConversationProfile, type LiveConversationProfile } from '../chat/liveConversationProfileClient';
import { companionInitiativeArbiter, type CompanionInitiativeSource } from './companion-initiative-arbiter';
import type { PresencePolicyValues } from './live-chat-evaluation-client';
import { closeProposalQuestion, markProposalQuestionAudible, noteUserSpeechOnset, openProposalQuestion } from './live-call-proposal-question';
import { callTasksAwaitingReport } from './live-call-tasks-controller';
import { callSceneHasGuests, isSceneTalkReason, isSceneTurnId, SCENE_LINE_REASON, SCENE_REACTION_REASON, SCENE_TALK_REASON, SCENE_TALK_SILENCE_MS } from './live-call-scene';
import { decideInitiative, decideTaskReport, insideQuietHours } from './live-conversation-initiative-policy';
import { liveConversationStore } from './live-conversation-store';
import { controller as liveVoiceCall } from './live-voice-controller-state';
import { ApiError } from '../../../api/errors';
import { unwrap } from '../../../api/http';
import { openStream } from '../../../api/transport';
import { liveCallPresentationStore } from './live-call-presentation-store';
import { readLastProactiveTurnHeard } from './live-voice-delivery-ledger';
import { ASSISTANT_AUDIO_PLAYBACK_STATE_EVENT, ASSISTANT_LIVE_VOICE_CALL_CONNECTED_EVENT, ASSISTANT_LIVE_VOICE_CALL_START_EVENT, ASSISTANT_LIVE_VOICE_STOP_EVENT, ASSISTANT_LIVE_VOICE_USER_SPEECH_EVENT, ASSISTANT_VOICE_INTERRUPT_EVENT, ASSISTANT_VOICE_PERF_EVENT, emitOmnixEvent, LIVE_CHAT_SESSION_CHANGED_EVENT, LIVE_CONVERSATION_PROACTIVE_DELIVERED_EVENT, LIVE_CONVERSATION_PROFILE_CHANGED_EVENT } from '../../../events/bus';
import { startTicker } from '../../../shared/timers';
import { api } from '../api/gateway';

let liveConversationInitiativeInstalled = false;

const SCHEDULER_INTERVAL_MS = 750;
const DEFAULT_COOLDOWN_MS = 30_000;
const AUDIO_START_TIMEOUT_MS = 5_000;
const DESKTOP_CONTEXT_REFRESH_MS = 5_000;
const DESKTOP_CONTEXT_MAX_AGE_MS = 120_000;
// A task's report outranks social initiative and follows another spoken turn after a short gap.
const TASK_REPORT_COOLDOWN_MS = 4_000;
// How long after a reply's audio ends another call member may still react to it (companion 5.4).
export const SCENE_REACTION_WINDOW_MS = 4_000;
const TASK_REPORT_CANDIDATE_REFRESH_MS = 5_000;
// A report that keeps failing to stream or play is given up for this call rather than retried forever.
const TASK_REPORT_MAX_ATTEMPTS = 3;
const TASK_REPORT_REASON_PREFIX = 'task_report:';
// An open loop from the speaker's own memory, named by the server (companion 3.2). The call never builds one.
const OPEN_LOOP_REASON_PREFIX = 'open_loop:';
const OPEN_LOOP_CANDIDATE_TIMEOUT_MS = 1_500;
// A remark the person does not answer within this window after it finishes counts as ignored (companion 3.3).
export const INITIATIVE_ANSWER_WINDOW_MS = 20_000;
const HOUR_MS = 3_600_000;
const DEFAULT_MAX_INITIATIVES_PER_HOUR = 4;
// Stages repeated every scheduler tick: the call log keeps only a change of decision (companion 3.1).
const CHANGE_ONLY_STAGES = new Set(['initiative_policy_decision', 'task_report_policy_decision', 'initiative_global_arbiter_suppressed']);
const USER_HOLDS_FLOOR = new Set(['speech_candidate', 'speaking', 'paused', 'completion_pending', 'finalizing', 'overlap_candidate']);
const ASSISTANT_TURN_IN_FLIGHT = new Set(['planning', 'generating', 'queued', 'speaking']);
const THINKING_PATTERN = /\b(?:give me (?:a )?(?:second|minute|moment)|let me think|one moment|hold on|I need a minute)\b/i;
const SENSITIVE_PATTERN = /\b(?:password|passcode|pin|account|card number|security code|address|phone number|email address)\b|\b\d{4,}\b/i;

type DesktopContext = {
  session_id: string;
  character_id?: string | null;
  observation_id: string;
  scene_summary: string;
  activity_thread: string;
  importance: number;
  observed_at: string;
  observation_count: number;
};

type PendingProactive = {
  sessionId: string;
  turnId: string;
  content: string;
  reason: string;
  audioStarted: boolean;
  committing: boolean;
  initiativeToken: string;
  source: CompanionInitiativeSource;
  /** The person spoke while it played. */
  answered: boolean;
};

export type ParsedProactiveStream = {
  turnId: string;
  content: string;
  initiativeReason: string;
  /** The task whose proposal this report asks about ("Turn off the lamp?"); null for any other turn. */
  proposalTaskId: string | null;
};

export type InitiativePolicyTiming = {
  idleThresholdMs: number;
  cooldownMs: number;
  typicalTurnWords: number | null;
  responseOnsetMs: number | null;
};

let selectedSessionId: string | null = null;
let callConnected = false;
let lastActivityAtMs = 0;
let lastPromptAtMs: number | null = null;
let promptCount = 0;
// Reasons not to raise again this call: an opener the person ignored, or an open loop the model passed on.
const cooledReasons = new Set<string>();
// The last social remark, until the person answers it or its answer window runs out.
let awaitingAnswer: { turnId: string; reason: string; untilMs: number } | null = null;
// When social remarks were delivered, across calls, for the hourly cap.
const deliveredSocialAtMs: number[] = [];
const loggedDecisions = new Map<string, string>();
let requestController: AbortController | null = null;
let requestInitiativeToken: string | null = null;
let pending: PendingProactive | null = null;
let assistantSpeaking = false;
// The unified audio controller has reported playback: its events settle proactive lines from then on.
let playbackReported = false;
let audioStartTimer: ReturnType<typeof setTimeout> | null = null;
let desktopContext: DesktopContext | null = null;
let desktopContextSessionId: string | null = null;
let desktopContextLoadedAtMs = 0;
let desktopContextRequest: Promise<void> | null = null;
// The server's chosen report reason (`initiative-candidate`); the call never builds one itself.
let reportCandidate: { sessionId: string; reason: string } | null = null;
let reportCandidateRequest: Promise<void> | null = null;
let reportCandidateCheckedAtMs = Number.NEGATIVE_INFINITY;
const reportAttempts = new Map<string, number>();
// A reply or a line between members just ended in a call with guests: the server may let another member react or
// say the next line (it decides who, if anyone). After a line, only another line follows (companion 6.4).
let sceneTurnDue: { sessionId: string; sinceMs: number; afterLine: boolean } | null = null;
// When the call last asked a member to start talking: a refused or skipped start waits the level's silence again.
let sceneStartAskedAtMs = Number.NEGATIVE_INFINITY;

export function initializeLiveConversationInitiativeController(): () => void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return () => undefined;
  if (liveConversationInitiativeInstalled) return () => undefined;
  liveConversationInitiativeInstalled = true;
  lastActivityAtMs = performance.now();
  selectedSessionId = liveConversationStore.getState().sessionId;
  callConnected = liveConversationStore.getState().conversation.connection === 'connected';
  assistantSpeaking = isAssistantSpeaking();
  if (selectedSessionId) void refreshDesktopContext(selectedSessionId, true);

  const handleSession = (event: Event) => {
    const detail = (event as CustomEvent<{ sessionId?: unknown }>).detail;
    selectedSessionId = typeof detail?.sessionId === 'string' ? detail.sessionId : selectedSessionId;
    desktopContext = null;
    desktopContextSessionId = null;
    desktopContextLoadedAtMs = 0;
    if (selectedSessionId) void refreshDesktopContext(selectedSessionId, true);
    closeProposalQuestion();
    resetQuietPeriod('session-changed');
  };
  const handleCallStart = () => { callConnected = false; closeProposalQuestion(); resetQuietPeriod('call-started'); };
  const handleCallConnected = () => {
    callConnected = true;
    resetQuietPeriod('call-connected');
    if (selectedSessionId) void refreshDesktopContext(selectedSessionId, true);
  };
  const handleUserSpeech = () => {
    noteUserSpeechOnset();
    const playing = pending?.audioStarted ? pending : null;
    noteAnswered();
    requestController?.abort('user-speech');
    requestController = null;
    releaseRequestInitiative(false);
    // The audio controller stops a proactive turn the moment the person speaks: it is settled now as interrupted,
    // never later as completed when some other turn's audio ends (the 2026-11-20 call's late lines).
    if (playing) void commitPending('interrupted');
    else clearPending('user-spoke-before-playback');
    sceneTurnDue = null;
    lastActivityAtMs = performance.now();
    promptCount = 0;
  };
  const handleInterrupt = () => {
    if (pending?.audioStarted) void commitPending('interrupted');
    else clearPending('interrupted-before-playback');
    lastActivityAtMs = performance.now();
  };
  const handleStop = () => {
    callConnected = false;
    closeProposalQuestion();
    requestController?.abort('call-stopped');
    requestController = null;
    releaseRequestInitiative(false);
    resetQuietPeriod('call-stopped');
  };
  const handleProfile = () => resetQuietPeriod('profile-changed');

  window.addEventListener(LIVE_CHAT_SESSION_CHANGED_EVENT, handleSession);
  window.addEventListener(ASSISTANT_AUDIO_PLAYBACK_STATE_EVENT, handleProactivePlayback);
  window.addEventListener(ASSISTANT_LIVE_VOICE_CALL_START_EVENT, handleCallStart);
  window.addEventListener(ASSISTANT_LIVE_VOICE_CALL_CONNECTED_EVENT, handleCallConnected);
  window.addEventListener(ASSISTANT_LIVE_VOICE_USER_SPEECH_EVENT, handleUserSpeech);
  window.addEventListener(ASSISTANT_VOICE_INTERRUPT_EVENT, handleInterrupt);
  window.addEventListener(ASSISTANT_LIVE_VOICE_STOP_EVENT, handleStop);
  window.addEventListener(LIVE_CONVERSATION_PROFILE_CHANGED_EVENT, handleProfile);

  const unsubscribe = liveConversationStore.subscribe(handleAuthoritativeStateChange);
  handleAuthoritativeStateChange();
  const stopScheduler = startTicker(evaluateInitiative, SCHEDULER_INTERVAL_MS);

  return () => {
    stopScheduler();
    unsubscribe();
    window.removeEventListener(LIVE_CHAT_SESSION_CHANGED_EVENT, handleSession);
    window.removeEventListener(ASSISTANT_AUDIO_PLAYBACK_STATE_EVENT, handleProactivePlayback);
    window.removeEventListener(ASSISTANT_LIVE_VOICE_CALL_START_EVENT, handleCallStart);
    window.removeEventListener(ASSISTANT_LIVE_VOICE_CALL_CONNECTED_EVENT, handleCallConnected);
    window.removeEventListener(ASSISTANT_LIVE_VOICE_USER_SPEECH_EVENT, handleUserSpeech);
    window.removeEventListener(ASSISTANT_VOICE_INTERRUPT_EVENT, handleInterrupt);
    window.removeEventListener(ASSISTANT_LIVE_VOICE_STOP_EVENT, handleStop);
    window.removeEventListener(LIVE_CONVERSATION_PROFILE_CHANGED_EVENT, handleProfile);
    requestController?.abort('controller-disposed');
    requestController = null;
    releaseRequestInitiative(false);
    clearPending('controller-disposed');
    desktopContext = null;
    desktopContextSessionId = null;
    cooledReasons.clear();
    awaitingAnswer = null;
    sceneTurnDue = null;
    playbackReported = false;
    deliveredSocialAtMs.length = 0;
    loggedDecisions.clear();
    liveConversationInitiativeInstalled = false;
  };
}

export function parseProactiveSse(text: string): ParsedProactiveStream | null {
  let turnId = '';
  let content = '';
  let initiativeReason = '';
  let proposalTaskId: string | null = null;
  for (const block of text.split(/\n\n+/)) {
    const data = block.split(/\r?\n/)
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trimStart())
      .join('\n');
    if (!data) continue;
    let event: Record<string, unknown>;
    try { event = JSON.parse(data) as Record<string, unknown>; } catch { continue; }
    if (event.type === 'error') throw new Error(String(event.message || 'Proactive turn failed.'));
    if (event.type === 'initiative') {
      if (typeof event.turn_id === 'string') turnId = event.turn_id;
      if (typeof event.initiative_reason === 'string') initiativeReason = event.initiative_reason;
    }
    if (event.type === 'complete') {
      if (typeof event.content === 'string') content = event.content.trim();
      const metadata = event.metadata as Record<string, unknown> | undefined;
      if (!turnId && typeof metadata?.turn_id === 'string') turnId = metadata.turn_id;
      if (!initiativeReason && typeof metadata?.initiative_reason === 'string') initiativeReason = metadata.initiative_reason;
      if (metadata?.task_report_proposal === true && typeof metadata.task_report_for === 'string') {
        proposalTaskId = metadata.task_report_for;
      }
    }
  }
  return turnId && content
    ? { turnId, content, initiativeReason: initiativeReason || 'continue_current_topic', proposalTaskId }
    : null;
}

export function proactiveReasonFromTranscript(transcript?: string): string | null {
  const latest = (transcript ?? currentDraftOrTranscript()).trim();
  if (!latest) return null;
  return /\?\s*$/.test(latest) ? 'unresolved_question' : 'continue_current_topic';
}

export function resolveInitiativePolicyTiming(
  profileIdleThresholdMs: number,
  policy: PresencePolicyValues | null,
): InitiativePolicyTiming {
  if (!policy) {
    return {
      idleThresholdMs: profileIdleThresholdMs,
      cooldownMs: DEFAULT_COOLDOWN_MS,
      typicalTurnWords: null,
      responseOnsetMs: null,
    };
  }
  return {
    idleThresholdMs: profileIdleThresholdMs,
    cooldownMs: policy.initiative_cooldown_ms,
    typicalTurnWords: policy.typical_turn_words,
    responseOnsetMs: policy.response_onset_ms,
  };
}

function evaluateInitiative(): void {
  const runtime = liveConversationStore.getState();
  const profile = runtime.profile ?? readEffectiveLiveConversationProfile();
  selectedSessionId = runtime.sessionId ?? selectedSessionId;
  callConnected = runtime.conversation.connection === 'connected';
  if (!profile || !selectedSessionId) return;
  const nowMs = performance.now();
  expireUnanswered(nowMs);
  void refreshDesktopContext(selectedSessionId, false);
  const policy = runtime.presencePolicy?.preset === profile.presence_preset
    ? runtime.presencePolicy.values
    : null;
  const timing = resolveInitiativePolicyTiming(profile.idle_threshold_ms, policy);
  if (evaluateTaskReport(selectedSessionId, profile, timing)) {
    // A task's report goes first and ends the members' thread.
    sceneTurnDue = null;
    return;
  }
  if (evaluateSceneTurn(selectedSessionId, profile, timing, nowMs)) return;
  const transcript = currentDraftOrTranscript();
  const userSpeaking = runtime.conversation.userTurn === 'speaking'
    || runtime.conversation.userTurn === 'speech_candidate';
  const visualContext = freshDesktopContext(selectedSessionId);
  const reason = proactiveReasonFromTranscript(transcript)
    ?? (profile.long_pause_behavior === 'reassure'
      ? 'gentle_reassurance'
      : profile.long_pause_behavior === 'ask_to_continue'
        ? 'ask_to_continue'
        : visualContext
          ? 'ambient_visual_presence'
          : null);
  const decision = decideInitiative({
    mode: profile.initiative_mode,
    callConnected,
    assistantActive: isAssistantSpeaking(),
    userSpeaking,
    partialTranscript: userSpeaking ? transcript : '',
    userRequestedTime: THINKING_PATTERN.test(transcript),
    sensitiveDictation: SENSITIVE_PATTERN.test(transcript),
    tabVisible: document.visibilityState === 'visible',
    muted: liveCallPresentationStore.getState().micMuted,
    requestInFlight: Boolean(requestController || pending),
    hasMeaningfulReason: Boolean(reason),
    callQuiet: liveCallPresentationStore.getState().companionQuiet,
    quietHours: Boolean(profile.quiet_hours_enabled)
      && insideQuietHours(profile.quiet_hours_start ?? '', profile.quiet_hours_end ?? '', new Date()),
    reasonCooled: Boolean(reason && cooledReasons.has(reason)),
    initiativesThisHour: socialRemarksInLastHour(nowMs),
    maxInitiativesPerHour: profile.max_initiatives_per_hour ?? DEFAULT_MAX_INITIATIVES_PER_HOUR,
    nowMs,
    lastActivityAtMs,
    lastPromptAtMs,
    idleThresholdMs: timing.idleThresholdMs,
    cooldownMs: timing.cooldownMs,
    promptCount,
    maxPrompts: profile.max_idle_prompts,
  });
  dispatchPerf('initiative_policy_decision', {
    action: decision.action,
    reason: decision.reason,
    eligible_in_ms: decision.eligibleInMs,
    presence_policy_version: runtime.presencePolicy?.version ?? null,
    idle_threshold_ms: timing.idleThresholdMs,
    cooldown_ms: timing.cooldownMs,
    visual_context_available: Boolean(visualContext),
  });
  if (decision.action === 'speak' && reason && isAutoSpeakEnabled()) {
    void startProactiveTurn(selectedSessionId, reason, profile, timing);
    return;
  }
  // A remark due to the person goes before the members start talking among themselves.
  evaluateSceneStart(selectedSessionId, profile, timing, nowMs);
}

/**
 * A settled task waits for its report: ask the server which one is due, then start it when the floor is free.
 * Returns true while a report holds initiative, so social initiative waits behind it.
 */
function evaluateTaskReport(
  sessionId: string,
  profile: LiveConversationProfile,
  timing: InitiativePolicyTiming,
): boolean {
  const awaiting = callTasksAwaitingReport(sessionId)
    .filter((task) => (reportAttempts.get(reportReasonFor(task.task_id)) ?? 0) < TASK_REPORT_MAX_ATTEMPTS);
  if (reportCandidate && reportCandidate.sessionId !== sessionId) reportCandidate = null;
  if (!reportCandidate) {
    if (!awaiting.length) return false;
    void refreshTaskReportCandidate(sessionId);
    return true;
  }
  if ((reportAttempts.get(reportCandidate.reason) ?? 0) >= TASK_REPORT_MAX_ATTEMPTS) {
    reportCandidate = null;
    return false;
  }
  const runtime = liveConversationStore.getState();
  const conversation = runtime.conversation;
  const userHoldsFloor = USER_HOLDS_FLOOR.has(conversation.userTurn);
  const decision = decideTaskReport({
    callConnected,
    autoSpeak: isAutoSpeakEnabled(),
    assistantActive: ASSISTANT_TURN_IN_FLIGHT.has(conversation.assistantTurn) || isAssistantSpeaking(),
    userSpeaking: userHoldsFloor,
    partialTranscript: runtime.transcript.partial,
    requestInFlight: Boolean(requestController || pending),
  });
  dispatchPerf('task_report_policy_decision', { action: decision.action, reason: decision.reason });
  if (decision.action === 'suppress') return false;
  if (decision.action === 'speak') void startProactiveTurn(sessionId, reportCandidate.reason, profile, timing, 'task');
  return true;
}

/**
 * A reply or a line ended in a call with guests: ask once whether another member reacts, or, with talk on, for the
 * next line. The server checks the turn is open and its model picks who (or nobody); the call only waits for the
 * floor. A refusal (409) ends the thread. Returns true while one is due.
 */
function evaluateSceneTurn(
  sessionId: string,
  profile: LiveConversationProfile,
  timing: InitiativePolicyTiming,
  nowMs: number,
): boolean {
  const due = sceneTurnDue;
  if (!due) return false;
  const talking = sceneTalkActive(profile);
  if (due.sessionId !== sessionId || nowMs - due.sinceMs > SCENE_REACTION_WINDOW_MS || !callSceneHasGuests(sessionId)
    || (due.afterLine && !talking)) {
    sceneTurnDue = null;
    return false;
  }
  const presentation = liveCallPresentationStore.getState();
  const heldBack = sceneHeldBack(profile, talking);
  if (!callConnected || !isAutoSpeakEnabled() || heldBack) {
    sceneTurnDue = null;
    dispatchPerf('scene_reaction_suppressed', { connected: callConnected, held_back: heldBack, talking });
    return false;
  }
  // A scene turn never cuts off a reply, the person or another remark: it waits for the floor.
  if (!floorFree()) return true;
  sceneTurnDue = null;
  // Talk on: the next line. Switched off on this call: the single reaction, and the server is told so.
  const switchedOff = !talking && Boolean(profile.scene_talk_enabled) && !presentation.sceneTalkOn;
  void startProactiveTurn(sessionId, talking ? SCENE_LINE_REASON : SCENE_REACTION_REASON, profile, timing, 'scene', switchedOff);
  return true;
}

/**
 * After the level's silence, a member may start the others talking (companion 6.4). The server measures the silence
 * from its last message and enforces the setting, the backoff and the cap; the call holds back during quiet hours,
 * Quiet, Mute or a hidden tab, and asks at most once per silence.
 */
function evaluateSceneStart(
  sessionId: string,
  profile: LiveConversationProfile,
  timing: InitiativePolicyTiming,
  nowMs: number,
): void {
  if (!sceneTalkActive(profile) || !callSceneHasGuests(sessionId) || !callConnected || !isAutoSpeakEnabled()) return;
  if (profile.initiative_mode === 'off' || (profile.max_initiatives_per_hour ?? DEFAULT_MAX_INITIATIVES_PER_HOUR) <= 0) return;
  if (sceneTurnDue || sceneHeldBack(profile, true) || !floorFree()) return;
  const silenceMs = SCENE_TALK_SILENCE_MS[profile.scene_talk_level] ?? SCENE_TALK_SILENCE_MS.sometimes;
  if (nowMs - lastActivityAtMs < silenceMs || nowMs - sceneStartAskedAtMs < silenceMs) return;
  sceneStartAskedAtMs = nowMs;
  // A start counts as activity and spends none of the quiet period's prompts.
  lastActivityAtMs = nowMs;
  void startProactiveTurn(sessionId, SCENE_TALK_REASON, profile, timing, 'scene');
}

/** The account lets the members talk to each other, and this call's "Let them talk" is on. */
function sceneTalkActive(profile: LiveConversationProfile): boolean {
  return Boolean(profile.scene_talk_enabled) && liveCallPresentationStore.getState().sceneTalkOn;
}

/** Why a scene turn waits now, or null. Lines and starts also hold back for Mute and quiet hours. */
function sceneHeldBack(profile: LiveConversationProfile, talking: boolean): string | null {
  const presentation = liveCallPresentationStore.getState();
  if (document.visibilityState !== 'visible') return 'tab_hidden';
  if (presentation.companionQuiet) return 'quiet';
  if (!talking) return null;
  if (presentation.micMuted) return 'muted';
  if (profile.quiet_hours_enabled
    && insideQuietHours(profile.quiet_hours_start ?? '', profile.quiet_hours_end ?? '', new Date())) {
    return 'quiet_hours';
  }
  return null;
}

function floorFree(): boolean {
  const conversation = liveConversationStore.getState().conversation;
  return !USER_HOLDS_FLOOR.has(conversation.userTurn) && !ASSISTANT_TURN_IN_FLIGHT.has(conversation.assistantTurn)
    && !isAssistantSpeaking() && !requestController && !pending;
}

/** The one path that names a report: the server's candidate, read at most every 5 s. */
function refreshTaskReportCandidate(sessionId: string): Promise<void> {
  if (reportCandidateRequest) return reportCandidateRequest;
  if (performance.now() - reportCandidateCheckedAtMs < TASK_REPORT_CANDIDATE_REFRESH_MS) return Promise.resolve();
  reportCandidateCheckedAtMs = performance.now();
  reportCandidateRequest = (async () => {
    try {
      const data = await unwrap(api.GET('/api/chat/sessions/{session_id}/live-call/initiative-candidate', {
        params: { path: { session_id: sessionId } },
        cache: 'no-store',
      }));
      if (selectedSessionId !== sessionId) return;
      const reason = typeof data.reason === 'string' && data.reason.startsWith(TASK_REPORT_REASON_PREFIX) ? data.reason : null;
      reportCandidate = reason ? { sessionId, reason } : null;
    } catch (error) {
      dispatchPerf('task_report_candidate_failed', { error: error instanceof Error ? error.message : String(error) });
    }
  })().finally(() => {
    reportCandidateRequest = null;
  });
  return reportCandidateRequest;
}

function reportReasonFor(taskId: string): string {
  return `${TASK_REPORT_REASON_PREFIX}${taskId}`;
}

async function startProactiveTurn(
  sessionId: string,
  reason: string,
  profile: LiveConversationProfile,
  timing: InitiativePolicyTiming,
  source?: CompanionInitiativeSource,
  sceneTalkSwitchedOff = false,
): Promise<void> {
  if (requestController || pending) return;
  const initiativeSource = source ?? (reason === 'ambient_visual_presence' ? 'ambient' : 'social');
  const isReport = initiativeSource === 'task';
  const isScene = initiativeSource === 'scene';
  const initiative = companionInitiativeArbiter.begin({
    source: initiativeSource,
    priority: 'normal',
    nowMs: Date.now(),
    // A reaction follows the conversation, not the companion's last remark: no cooldown.
    cooldownMs: isScene ? 0 : isReport ? TASK_REPORT_COOLDOWN_MS : timing.cooldownMs,
  });
  if (!initiative.accepted || !initiative.token) {
    dispatchPerf('initiative_global_arbiter_suppressed', {
      initiative_reason: reason,
      reason: initiative.reason,
      eligible_in_ms: initiative.eligibleInMs,
    });
    return;
  }
  const controller = new AbortController();
  requestController = controller;
  requestInitiativeToken = initiative.token;
  let transferred = false;
  let turnReason = reason;
  try {
    // Social initiative asks the server for a grounded reason first: an open loop from the speaker's own memory.
    if (initiativeSource === 'social') turnReason = (await openLoopReason(sessionId, controller.signal)) ?? reason;
    if (controller.signal.aborted) return;
    // A report's prompt is built on the server from its record of the task; the call sends only the reason.
    const params = new URLSearchParams({ purpose: 'proactive_reengagement', initiative_reason: turnReason });
    if (isReport) reportAttempts.set(reason, (reportAttempts.get(reason) ?? 0) + 1);
    else if (isScene) {
      if (sceneTalkSwitchedOff) params.set('scene_talk_switched_off', 'true');
    } else {
      params.set('state_summary', conversationStateSummary(profile, timing, sessionId));
      if (timing.typicalTurnWords !== null) params.set('target_words', String(timing.typicalTurnWords));
    }
    dispatchPerf('initiative_generation_started', {
      session_id: sessionId,
      initiative_source: initiativeSource,
      initiative_reason: turnReason,
      fallback_reason: turnReason === reason ? null : reason,
      target_words: timing.typicalTurnWords,
    });
    if (timing.responseOnsetMs) await waitForOnset(timing.responseOnsetMs, controller.signal);
    const response = await openStream(`/api/chat/sessions/${encodeURIComponent(sessionId)}/live-call/greeting/stream?${params}`, {
      method: 'POST',
      signal: controller.signal,
    });
    const parsed = parseProactiveSse(await response.text());
    if (controller.signal.aborted) {
      // The stream finished but the call moved on: the line's lease is the call's to give back.
      if (parsed && isScene) releaseSceneLease(sessionId, parsed.turnId, 'aborted-after-stream');
      return;
    }
    // The candidate is spent: the next report, or a retry of this one, is chosen by the server again.
    if (isReport) reportCandidate = null;
    if (!parsed) {
      if (!isReport && !isScene) noteSkipped(turnReason, initiativeSource);
      return;
    }
    const turn: PendingProactive = {
      sessionId,
      turnId: parsed.turnId,
      content: parsed.content,
      reason: isReport ? reason : parsed.initiativeReason || turnReason,
      audioStarted: isAssistantSpeaking(),
      committing: false,
      initiativeToken: initiative.token,
      source: initiativeSource,
      answered: false,
    };
    pending = turn;
    if (isReport && parsed.proposalTaskId) {
      openProposalQuestion(sessionId, parsed.proposalTaskId, parsed.turnId);
      if (turn.audioStarted) markProposalQuestionAudible(turn.turnId);
    }
    requestInitiativeToken = null;
    transferred = true;
    dispatchPerf('initiative_generation_completed', { turn_id: parsed.turnId, content_chars: parsed.content.length });
    if (!turn.audioStarted) {
      audioStartTimer = setTimeout(() => {
        if (pending === turn && !turn.audioStarted) clearPending('audio-never-started');
      }, AUDIO_START_TIMEOUT_MS);
      setTimeout(handleAuthoritativeStateChange, 0);
    }
  } catch (error) {
    if (isScene && error instanceof ApiError && error.status === 409) {
      // Nobody reacts or speaks next, the thread closed first (the person spoke), or a start is not due: not a
      // failure. Nothing is asked again until another turn ends.
      dispatchPerf(reason === SCENE_REACTION_REASON ? 'scene_reaction_skipped' : 'scene_talk_skipped', {
        session_id: sessionId,
        initiative_reason: reason,
        detail: error.detail || null,
      });
    } else if (!controller.signal.aborted) {
      if (isReport) reportCandidate = null;
      dispatchPerf('initiative_generation_failed', {
        initiative_source: initiativeSource,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  } finally {
    if (!transferred) companionInitiativeArbiter.finish(initiative.token, Date.now(), false);
    if (requestInitiativeToken === initiative.token) requestInitiativeToken = null;
    if (requestController === controller) requestController = null;
  }
}

function handleAuthoritativeStateChange(): void {
  const runtime = liveConversationStore.getState();
  selectedSessionId = runtime.sessionId ?? selectedSessionId;
  callConnected = runtime.conversation.connection === 'connected';
  const speaking = isAssistantSpeaking();
  if (speaking === assistantSpeaking) return;
  const wasSpeaking = assistantSpeaking;
  assistantSpeaking = speaking;
  lastActivityAtMs = performance.now();
  // The audio controller's playback events, once seen, alone say when a line is heard and when it ends: the call's
  // speaking state also follows replies, and it can lag or stay set past a line's end.
  if (pending && speaking && !playbackReported) {
    pending.audioStarted = true;
    markProposalQuestionAudible(pending.turnId);
    clearAudioStartTimer();
  }
  if (pending?.audioStarted && wasSpeaking && !speaking) {
    if (!playbackReported) void commitPending('completed');
  } else if (wasSpeaking && !speaking && !pending && !requestController && runtime.sessionId
    && callSceneHasGuests(runtime.sessionId) && !sceneTurnDue?.afterLine) {
    // A reply ended: a member may react. A line just committed has already asked for the next line.
    sceneTurnDue = { sessionId: runtime.sessionId, sinceMs: performance.now(), afterLine: false };
  }
}

/**
 * The audio controller plays every proactive turn as a greeting-kind turn and reports its playback. Its own audio
 * marks the turn audible (a reply's audio does not), and the end of that audio settles it: the call's speaking state
 * can stay set past the line's end, which once left a finished line waiting a whole exchange to be committed.
 */
function handleProactivePlayback(event: Event): void {
  const detail = (event as CustomEvent<{ speaking?: unknown; kind?: unknown; source?: unknown }>).detail ?? {};
  if (detail.source === 'unified-live-voice') playbackReported = true;
  const turn = pending;
  if (!turn || turn.committing) return;
  const ownKind = detail.kind === 'greeting';
  if (detail.speaking) {
    if (ownKind && !turn.audioStarted) {
      turn.audioStarted = true;
      markProposalQuestionAudible(turn.turnId);
      clearAudioStartTimer();
    } else if (!ownKind && turn.audioStarted) {
      // Another turn (a reply to something typed) took over the line's playback: it was cut off there.
      void commitPending('interrupted');
    }
    return;
  }
  // Only the end of the line's own audio settles it; a reply's end says nothing about the line.
  if (!turn.audioStarted || !ownKind) return;
  // After this event's dispatch: when the person's speech stopped the line, its handler settles it as interrupted.
  setTimeout(() => {
    if (pending === turn && !turn.committing) void commitPending('completed');
  }, 0);
}

async function commitPending(status: 'completed' | 'interrupted'): Promise<void> {
  const turn = pending;
  if (!turn || turn.committing) return;
  // A scene turn cut off mid-way tells the server what the person heard; the server checks it against its own text.
  const heard = status === 'interrupted' && isSceneTurnId(turn.turnId) ? readLastProactiveTurnHeard(turn.sessionId) : null;
  if (status === 'interrupted' && isSceneTurnId(turn.turnId) && !heard?.heardText) {
    // Stopped before a word of it was heard: the line was never said. It is dropped and its lease given back.
    clearPending('interrupted-before-heard');
    return;
  }
  turn.committing = true;
  clearAudioStartTimer();
  // The person heard it whether or not the commit lands. A report answers their own request, so it does not use up
  // the quiet period's prompts, count toward the hourly cap, or wait for an answer.
  if (countsAsCompanionRemark(turn.source)) {
    const nowMs = performance.now();
    promptCount += 1;
    lastPromptAtMs = nowMs;
    deliveredSocialAtMs.push(nowMs);
    if (!turn.answered) {
      awaitingAnswer = { turnId: turn.turnId, reason: turn.reason, untilMs: nowMs + INITIATIVE_ANSWER_WINDOW_MS };
    }
  }
  try {
    await unwrap(api.POST('/api/chat/sessions/{session_id}/live-conversation/proactive/delivery', {
      params: { path: { session_id: turn.sessionId } },
      body: {
        turn_id: turn.turnId,
        content: turn.content,
        initiative_reason: turn.reason,
        delivery_status: status,
        ...(heard ? { heard_text: heard.heardText, interrupted_at_phrase: heard.interruptedAtPhrase } : {}),
      },
    }));
    lastActivityAtMs = performance.now();
    // A line or an opener that played to the end: the next line is asked only now that it is committed.
    if (status === 'completed' && isSceneTalkReason(turn.reason)) {
      sceneTurnDue = { sessionId: turn.sessionId, sinceMs: performance.now(), afterLine: true };
    }
    emitOmnixEvent(LIVE_CONVERSATION_PROACTIVE_DELIVERED_EVENT, { sessionId: turn.sessionId, turnId: turn.turnId, status });
    dispatchPerf('initiative_delivery_committed', { turn_id: turn.turnId, delivery_status: status });
  } catch (error) {
    dispatchPerf('initiative_delivery_commit_failed', {
      error: error instanceof Error ? error.message : String(error),
    });
  } finally {
    companionInitiativeArbiter.finish(turn.initiativeToken, Date.now(), true);
    if (pending === turn) pending = null;
  }
}

/** A remark the companion chose to make: it uses the quiet period's prompts and waits for an answer. */
function countsAsCompanionRemark(source: CompanionInitiativeSource): boolean {
  return source !== 'task' && source !== 'scene';
}

function resetQuietPeriod(reason: string): void {
  sceneTurnDue = null;
  requestController?.abort(reason);
  requestController = null;
  releaseRequestInitiative(false);
  clearPending(reason);
  promptCount = 0;
  lastPromptAtMs = null;
  lastActivityAtMs = performance.now();
  reportCandidate = null;
  reportCandidateCheckedAtMs = Number.NEGATIVE_INFINITY;
  loggedDecisions.clear();
  if (reason !== 'profile-changed') awaitingAnswer = null;
  if (reason === 'call-started' || reason === 'session-changed') {
    sceneStartAskedAtMs = Number.NEGATIVE_INFINITY;
    reportAttempts.clear();
    cooledReasons.clear();
  }
}

/** The person spoke: a social remark playing now, or one inside its answer window, was answered. */
function noteAnswered(): void {
  const turn = pending;
  if (turn?.audioStarted && countsAsCompanionRemark(turn.source)) {
    if (!turn.answered) {
      turn.answered = true;
      dispatchPerf('initiative_answered', { turn_id: turn.turnId, initiative_reason: turn.reason, when: 'during' });
    }
    awaitingAnswer = null;
    return;
  }
  const waiting = awaitingAnswer;
  awaitingAnswer = null;
  if (!waiting || performance.now() > waiting.untilMs) return;
  dispatchPerf('initiative_answered', {
    turn_id: waiting.turnId,
    initiative_reason: waiting.reason,
    when: 'after',
    answered_in_ms: Math.round(performance.now() - (waiting.untilMs - INITIATIVE_ANSWER_WINDOW_MS)),
  });
}

/** A remark nobody answered cools its reason for the rest of the call. */
function expireUnanswered(nowMs: number): void {
  const waiting = awaitingAnswer;
  if (!waiting || nowMs <= waiting.untilMs) return;
  awaitingAnswer = null;
  cooledReasons.add(waiting.reason);
  dispatchPerf('initiative_ignored', {
    turn_id: waiting.turnId,
    initiative_reason: waiting.reason,
    answer_window_ms: INITIATIVE_ANSWER_WINDOW_MS,
  });
}

/**
 * The model passed (SKIP). Nothing was said, so the arbiter releases undelivered, but the call waits a cooldown
 * before asking again. A social reason will not change until the person speaks, so it also spends one of the quiet
 * period's prompts; an open loop the model passed on is not raised again this call.
 */
function noteSkipped(reason: string, source: CompanionInitiativeSource): void {
  lastPromptAtMs = performance.now();
  if (source === 'social') promptCount += 1;
  if (reason.startsWith(OPEN_LOOP_REASON_PREFIX)) cooledReasons.add(reason);
  dispatchPerf('initiative_skipped', { initiative_source: source, initiative_reason: reason });
}

function socialRemarksInLastHour(nowMs: number): number {
  while (deliveredSocialAtMs.length && nowMs - deliveredSocialAtMs[0] >= HOUR_MS) deliveredSocialAtMs.shift();
  return deliveredSocialAtMs.length;
}

/**
 * The server's open loop for a quiet call, or null: none open, already raised, cooled this call, slow or failed.
 * The call asks only once its own policy and the arbiter let social initiative speak.
 */
async function openLoopReason(sessionId: string, signal: AbortSignal): Promise<string | null> {
  const request = new AbortController();
  const abort = () => request.abort('initiative-aborted');
  signal.addEventListener('abort', abort, { once: true });
  const timer = setTimeout(() => request.abort('open-loop-timeout'), OPEN_LOOP_CANDIDATE_TIMEOUT_MS);
  try {
    const data = await unwrap(api.GET('/api/chat/sessions/{session_id}/live-call/initiative-candidate', {
      params: { path: { session_id: sessionId }, query: { social: true } },
      cache: 'no-store',
      signal: request.signal,
    }));
    const reason = typeof data.reason === 'string' && data.reason.startsWith(OPEN_LOOP_REASON_PREFIX) ? data.reason : null;
    return reason && !cooledReasons.has(reason) ? reason : null;
  } catch (error) {
    if (!signal.aborted) {
      dispatchPerf('open_loop_candidate_failed', {
        error: request.signal.aborted ? 'timeout' : error instanceof Error ? error.message : String(error),
      });
    }
    return null;
  } finally {
    clearTimeout(timer);
    signal.removeEventListener('abort', abort);
  }
}

function clearPending(reason: string): void {
  if (pending) {
    dispatchPerf('initiative_pending_cleared', { turn_id: pending.turnId, reason });
    companionInitiativeArbiter.finish(pending.initiativeToken, Date.now(), false);
    // A scene turn dropped before it played gives its lease back now rather than at its TTL (companion 6.3).
    if (isSceneTurnId(pending.turnId)) releaseSceneLease(pending.sessionId, pending.turnId, reason);
  }
  pending = null;
  clearAudioStartTimer();
}

function releaseSceneLease(sessionId: string, turnId: string, reason: string): void {
  void unwrap(api.POST('/api/chat/sessions/{session_id}/live-conversation/proactive/release', {
    params: { path: { session_id: sessionId } },
    body: { turn_id: turnId },
  })).then((data) => {
    dispatchPerf('scene_lease_released', { turn_id: turnId, reason, released: data.released });
  }).catch((error: unknown) => {
    dispatchPerf('scene_lease_release_failed', {
      turn_id: turnId,
      error: error instanceof Error ? error.message : String(error),
    });
  });
}

function releaseRequestInitiative(delivered: boolean): void {
  if (!requestInitiativeToken) return;
  companionInitiativeArbiter.finish(requestInitiativeToken, Date.now(), delivered);
  requestInitiativeToken = null;
}

function clearAudioStartTimer(): void {
  if (audioStartTimer !== null) clearTimeout(audioStartTimer);
  audioStartTimer = null;
}

function currentDraftOrTranscript(): string {
  const transcript = liveConversationStore.getState().transcript;
  return transcript.partial || transcript.lastFinal;
}

function conversationStateSummary(
  profile: LiveConversationProfile,
  timing: InitiativePolicyTiming,
  sessionId: string,
): string {
  const runtime = liveConversationStore.getState();
  const messages = runtime.transcript.recentFinals
    .slice(-3)
    .map((value) => value.replace(/\s+/g, ' ').trim())
    .filter(Boolean);
  const visual = freshDesktopContext(sessionId);
  return [
    `stance=${profile.conversation_stance}`,
    `presence=${profile.presence_preset}`,
    `policy_version=${runtime.presencePolicy?.version ?? 'none'}`,
    `target_words=${timing.typicalTurnWords ?? 'profile'}`,
    `recent=${messages.join(' | ')}`,
    visual ? `desktop=${visual.activity_thread || visual.scene_summary}` : '',
  ].filter(Boolean).join('; ').slice(0, 900);
}

function freshDesktopContext(sessionId: string): DesktopContext | null {
  if (!desktopContext || desktopContextSessionId !== sessionId) return null;
  const observedAt = Date.parse(desktopContext.observed_at);
  if (!Number.isFinite(observedAt) || Date.now() - observedAt > DESKTOP_CONTEXT_MAX_AGE_MS) return null;
  return desktopContext;
}

async function refreshDesktopContext(sessionId: string, force: boolean): Promise<void> {
  const nowMs = Date.now();
  if (!force && desktopContextSessionId === sessionId && nowMs - desktopContextLoadedAtMs < DESKTOP_CONTEXT_REFRESH_MS) return;
  if (desktopContextRequest) return desktopContextRequest;
  desktopContextRequest = (async () => {
    try {
      const { data, response } = await api.GET('/api/desktop-companion/context', {
        params: { query: { session_id: sessionId } },
        cache: 'no-store',
      });
      if (!response.ok) return;
      // The context route returns an untyped object (or null).
      const payload = (data ?? null) as DesktopContext | null;
      desktopContext = payload && payload.session_id === sessionId ? payload : null;
      desktopContextSessionId = sessionId;
      desktopContextLoadedAtMs = Date.now();
    } catch {
      desktopContextLoadedAtMs = Date.now();
    }
  })().finally(() => {
    desktopContextRequest = null;
  });
  return desktopContextRequest;
}

function isAssistantSpeaking(): boolean {
  const conversation = liveConversationStore.getState().conversation;
  return conversation.assistantTurn === 'speaking' || conversation.delivery === 'audio_started';
}

function isAutoSpeakEnabled(): boolean {
  return liveCallPresentationStore.getState().autoSpeak;
}

function waitForOnset(delayMs: number, signal: AbortSignal): Promise<void> {
  const bounded = Math.max(0, Math.min(5_000, delayMs));
  if (!bounded || signal.aborted) return Promise.resolve();
  return new Promise((resolve) => {
    const timer = window.setTimeout(resolve, bounded);
    signal.addEventListener('abort', () => {
      window.clearTimeout(timer);
      resolve();
    }, { once: true });
  });
}

function dispatchPerf(stage: string, details: Record<string, unknown>): void {
  emitOmnixEvent(ASSISTANT_VOICE_PERF_EVENT, { stage, timestamp: new Date().toISOString(), ...details });
  // The call log keeps what initiative did (companion 3.1); a decision repeated every tick only when it changes.
  if (CHANGE_ONLY_STAGES.has(stage)) {
    const decision = `${String(details.action ?? '')}:${String(details.reason ?? '')}`;
    if (loggedDecisions.get(stage) === decision) return;
    loggedDecisions.set(stage, decision);
  }
  liveVoiceCall.activeSession?.reporter.record(stage, details, 'live_conversation_initiative');
}
