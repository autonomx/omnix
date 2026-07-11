import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { migrateLegacyConversationSettingsOnce } from './liveConversationProfileClient';

const profile = {
  presence_preset: 'natural', talkativeness: 50, conversation_stance: 'automatic',
  conversation_pace: 'reflective', interruption_preference: 'easy', assistant_backchannel_mode: 'natural',
  initiative_mode: 'gentle', idle_threshold_ms: 15000, long_pause_behavior: 'wait',
  response_length: 'conversational', response_onset_style: 'adaptive', emotional_attunement: 'subtle',
  topic_continuity: 'natural', max_idle_prompts: 1, duplex_mode: 'automatic',
  pronunciation_save_policy: 'ask', profile_version: 2,
};

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('liveConversationProfileClient migration', () => {
  it('migrates legacy timing settings to server defaults exactly once', async () => {
    window.localStorage.setItem('omnix.liveConversation.settings', JSON.stringify({
      conversationPace: 'reflective',
      interruptionPreference: 'easy',
      backchannelMode: 'natural',
    }));
    const fetchMock = vi.fn(async () => Response.json(profile));
    vi.stubGlobal('fetch', fetchMock);

    await expect(migrateLegacyConversationSettingsOnce()).resolves.toBe(true);
    await expect(migrateLegacyConversationSettingsOnce()).resolves.toBe(false);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/live-chat/profile/defaults');
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      conversation_pace: 'reflective',
      interruption_preference: 'easy',
      assistant_backchannel_mode: 'natural',
    });
    expect(window.localStorage.getItem('omnix.liveConversation.serverProfileMigrated.v1')).toBe('done');
  });

  it('does not overwrite server defaults when no legacy settings exist', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    await expect(migrateLegacyConversationSettingsOnce()).resolves.toBe(false);

    expect(fetchMock).not.toHaveBeenCalled();
    expect(window.localStorage.getItem('omnix.liveConversation.serverProfileMigrated.v1')).toBe('done');
  });
});
