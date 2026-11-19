 
import type { InitiativeMode } from '../chat/liveConversationProfileClient';

export type InitiativePolicyInput = {
  mode: InitiativeMode;
  callConnected: boolean;
  assistantActive: boolean;
  userSpeaking: boolean;
  partialTranscript: string;
  userRequestedTime: boolean;
  sensitiveDictation: boolean;
  tabVisible: boolean;
  muted: boolean;
  requestInFlight: boolean;
  hasMeaningfulReason: boolean;
  /** The person asked the companion to keep quiet for this call. */
  callQuiet: boolean;
  /** The local clock is inside the profile's quiet hours. */
  quietHours: boolean;
  /** The reason was raised before and went unanswered, or the model passed on it, this call. */
  reasonCooled: boolean;
  /** Social remarks delivered in the last hour, and the profile's cap on them. */
  initiativesThisHour: number;
  maxInitiativesPerHour: number;
  nowMs: number;
  lastActivityAtMs: number;
  lastPromptAtMs: number | null;
  idleThresholdMs: number;
  cooldownMs: number;
  promptCount: number;
  maxPrompts: number;
};

export type InitiativePolicyDecision = {
  action: 'speak' | 'wait' | 'suppress';
  reason: string;
  eligibleInMs: number | null;
};

export function decideInitiative(input: InitiativePolicyInput): InitiativePolicyDecision {
  if (input.mode === 'off') return suppress('initiative_disabled');
  if (!input.callConnected) return suppress('call_not_connected');
  if (!input.tabVisible) return suppress('tab_hidden');
  if (input.muted) return suppress('microphone_muted');
  if (input.callQuiet) return suppress('call_quiet');
  if (input.quietHours) return suppress('quiet_hours');
  if (input.userRequestedTime) return suppress('user_requested_time');
  if (input.sensitiveDictation) return suppress('sensitive_dictation');
  if (input.reasonCooled) return suppress('reason_cooled');
  if (!input.hasMeaningfulReason) return suppress('no_meaningful_contribution');
  if (input.promptCount >= input.maxPrompts) return suppress('quiet_period_prompt_limit');
  if (input.initiativesThisHour >= input.maxInitiativesPerHour) return suppress('hourly_cap');
  if (input.assistantActive || input.requestInFlight) return wait('assistant_busy');
  if (input.userSpeaking || input.partialTranscript.trim()) return wait('user_floor_active');

  const idleRemaining = Math.max(0, input.idleThresholdMs - (input.nowMs - input.lastActivityAtMs));
  if (idleRemaining > 0) return wait('idle_threshold', idleRemaining);
  if (input.lastPromptAtMs !== null) {
    const cooldownRemaining = Math.max(0, input.cooldownMs - (input.nowMs - input.lastPromptAtMs));
    if (cooldownRemaining > 0) return wait('initiative_cooldown', cooldownRemaining);
  }
  return { action: 'speak', reason: 'social_obligation_available', eligibleInMs: 0 };
}

/**
 * Whether ``now`` (local clock) falls inside quiet hours given as ``HH:MM``. ``start < end`` is a same-day window
 * [start, end); otherwise the window wraps midnight. Equal times, or a time that cannot be read, mean no quiet hours.
 */
export function insideQuietHours(start: string, end: string, now: Date): boolean {
  const from = clockMinutes(start);
  const to = clockMinutes(end);
  if (from === null || to === null || from === to) return false;
  const minute = now.getHours() * 60 + now.getMinutes();
  return from < to ? minute >= from && minute < to : minute >= from || minute < to;
}

function clockMinutes(value: string): number | null {
  const match = /^([01]\d|2[0-3]):([0-5]\d)$/.exec(value);
  return match ? Number(match[1]) * 60 + Number(match[2]) : null;
}

export type TaskReportPolicyInput = {
  callConnected: boolean;
  autoSpeak: boolean;
  assistantActive: boolean;
  userSpeaking: boolean;
  partialTranscript: string;
  requestInFlight: boolean;
};

/**
 * A finished task's report. The person asked for this work, so only the floor holds it back: the idle threshold,
 * prompt and hourly caps, cooled reasons, quiet hours, the call's quiet toggle, initiative mode and hidden tab that
 * hold social initiative back do not apply.
 */
export function decideTaskReport(input: TaskReportPolicyInput): InitiativePolicyDecision {
  if (!input.callConnected) return suppress('call_not_connected');
  if (!input.autoSpeak) return wait('auto_speak_off');
  if (input.assistantActive || input.requestInFlight) return wait('assistant_busy');
  if (input.userSpeaking || input.partialTranscript.trim()) return wait('user_floor_active');
  return { action: 'speak', reason: 'task_report_due', eligibleInMs: 0 };
}

function wait(reason: string, eligibleInMs: number | null = null): InitiativePolicyDecision {
  return { action: 'wait', reason, eligibleInMs };
}

function suppress(reason: string): InitiativePolicyDecision {
  return { action: 'suppress', reason, eligibleInMs: null };
}
