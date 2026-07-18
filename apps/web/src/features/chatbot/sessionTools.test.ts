import { describe, expect, it } from 'vitest';

import type { ChatSession } from '../../api/client';
import type { SessionInteraction } from './characterClient';
import { preservedNewChatRequest } from './sessionTools';

describe('preservedNewChatRequest', () => {
  it('carries the active character setup into a blank chat', () => {
    const session = {
      id: 'chat:old',
      title: 'Existing conversation',
      provider_id: 'lm-studio',
      model_id: 'local-model',
    } as ChatSession;
    const interaction = {
      interaction_mode: 'character',
      character_id: 'maya',
      voice_asset_id: 'voice-cloning:Maya',
      read_memory: true,
      write_memory: false,
      shared_memory_access: 'read_only',
      transcript_policy: 'temporary',
    } as SessionInteraction;

    expect(preservedNewChatRequest(session, interaction)).toEqual({
      title: 'New chat',
      provider_id: 'lm-studio',
      model_id: 'local-model',
      interaction_mode: 'character',
      character_id: 'maya',
      voice_asset_id: 'voice-cloning:Maya',
      read_memory: true,
      write_memory: false,
      shared_memory_access: 'read_only',
      transcript_policy: 'temporary',
    });
  });
});
