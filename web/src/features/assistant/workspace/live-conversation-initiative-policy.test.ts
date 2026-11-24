import { describe, expect, it } from 'vitest';

import { decideInitiative, insideQuietHours, type InitiativePolicyInput } from './live-conversation-initiative-policy';

const base: InitiativePolicyInput = {
  mode: 'gentle',
  callConnected: true,
  assistantActive: false,
  userSpeaking: false,
  partialTranscript: '',
  userRequestedTime: false,
  sensitiveDictation: false,
  tabVisible: true,
  muted: false,
  requestInFlight: false,
  hasMeaningfulReason: true,
  callQuiet: false,
  quietHours: false,
  reasonCooled: false,
  initiativesThisHour: 0,
  maxInitiativesPerHour: 4,
  nowMs: 20_000,
  lastActivityAtMs: 0,
  lastPromptAtMs: null,
  idleThresholdMs: 15_000,
  cooldownMs: 30_000,
  promptCount: 0,
  maxPrompts: 1,
};

describe('decideInitiative', () => {
  it('authorizes one meaningful move after genuine idle', () => {
    expect(decideInitiative(base)).toEqual({
      action: 'speak',
      reason: 'social_obligation_available',
      eligibleInMs: 0,
    });
  });

  it('waits while the user or assistant owns the floor', () => {
    expect(decideInitiative({ ...base, userSpeaking: true }).reason).toBe('user_floor_active');
    expect(decideInitiative({ ...base, partialTranscript: 'So I was thinking' }).reason).toBe('user_floor_active');
    expect(decideInitiative({ ...base, assistantActive: true }).reason).toBe('assistant_busy');
  });

  it('suppresses socially inappropriate prompts', () => {
    expect(decideInitiative({ ...base, userRequestedTime: true }).reason).toBe('user_requested_time');
    expect(decideInitiative({ ...base, sensitiveDictation: true }).reason).toBe('sensitive_dictation');
    expect(decideInitiative({ ...base, tabVisible: false }).reason).toBe('tab_hidden');
    expect(decideInitiative({ ...base, reasonCooled: true }).reason).toBe('reason_cooled');
    expect(decideInitiative({ ...base, hasMeaningfulReason: false }).reason).toBe('no_meaningful_contribution');
  });

  it('keeps quiet when the person asked for it or inside quiet hours', () => {
    expect(decideInitiative({ ...base, callQuiet: true })).toEqual({
      action: 'suppress', reason: 'call_quiet', eligibleInMs: null,
    });
    expect(decideInitiative({ ...base, quietHours: true }).reason).toBe('quiet_hours');
    // Quiet outranks a cooled reason, so the log names what the person chose.
    expect(decideInitiative({ ...base, callQuiet: true, reasonCooled: true }).reason).toBe('call_quiet');
  });

  it('enforces idle threshold, cooldown, prompt limit and hourly cap', () => {
    expect(decideInitiative({ ...base, nowMs: 10_000 }).eligibleInMs).toBe(5_000);
    expect(decideInitiative({ ...base, lastPromptAtMs: 10_000 }).reason).toBe('initiative_cooldown');
    expect(decideInitiative({ ...base, promptCount: 1 }).reason).toBe('quiet_period_prompt_limit');
    expect(decideInitiative({ ...base, initiativesThisHour: 4 }).reason).toBe('hourly_cap');
    expect(decideInitiative({ ...base, maxInitiativesPerHour: 0 }).reason).toBe('hourly_cap');
    expect(decideInitiative({ ...base, initiativesThisHour: 3 }).action).toBe('speak');
  });

  it("waits out the server's spacing when it turned a remark down", () => {
    expect(decideInitiative({ ...base, serverHoldUntilMs: base.nowMs + 4_000 })).toEqual({
      action: 'wait', reason: 'server_spacing', eligibleInMs: 4_000,
    });
    expect(decideInitiative({ ...base, serverHoldUntilMs: base.nowMs }).action).toBe('speak');
    expect(decideInitiative({ ...base, serverHoldUntilMs: null }).action).toBe('speak');
  });
});

describe('insideQuietHours', () => {
  const at = (hours: number, minutes = 0) => new Date(2026, 10, 15, hours, minutes);

  it('reads a same-day window as [start, end)', () => {
    expect(insideQuietHours('13:00', '15:00', at(12, 59))).toBe(false);
    expect(insideQuietHours('13:00', '15:00', at(13, 0))).toBe(true);
    expect(insideQuietHours('13:00', '15:00', at(14, 59))).toBe(true);
    expect(insideQuietHours('13:00', '15:00', at(15, 0))).toBe(false);
  });

  it('wraps a window across midnight', () => {
    expect(insideQuietHours('22:00', '08:00', at(21, 59))).toBe(false);
    expect(insideQuietHours('22:00', '08:00', at(22, 0))).toBe(true);
    expect(insideQuietHours('22:00', '08:00', at(0, 30))).toBe(true);
    expect(insideQuietHours('22:00', '08:00', at(7, 59))).toBe(true);
    expect(insideQuietHours('22:00', '08:00', at(8, 0))).toBe(false);
  });

  it('has no quiet hours for equal or unreadable times', () => {
    expect(insideQuietHours('09:00', '09:00', at(9, 0))).toBe(false);
    expect(insideQuietHours('25:00', '08:00', at(3, 0))).toBe(false);
    expect(insideQuietHours('', '08:00', at(3, 0))).toBe(false);
  });
});
