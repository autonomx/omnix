import { describe, expect, it } from 'vitest';
import { buildRpgNewGameRequest, initialStats, type CampaignCreationSelections } from './rpgCreateCampaignState';

const baseSelections: CampaignCreationSelections = {
  background: 'wanderer',
  buildKey: 'scout',
  capabilities: {
    combat: true,
    influence: false,
    knowledge: false,
    support: false,
    survival: true,
    technical: true,
  },
  characterName: 'Mira',
  combatLethality: 'deadly',
  difficulty: 'hard',
  economyPressure: 'tight',
  powerSource: 'arcane',
  primaryCapability: 'craft',
  pronouns: 'she/her',
  seed: '9137',
  startingLocation: 'watch-post',
  stats: { ...initialStats, perception: 11 },
  systems: {
    autosave: true,
    companions: true,
    grounding: true,
    images: false,
    narration: true,
    permadeath: false,
    softAudit: true,
    stt: true,
    tts: true,
  },
  worldActivity: 'busy',
};

describe('RPG campaign creation state', () => {
  it('maps wizard selections to the supported RPG new-game request contract', () => {
    const request = buildRpgNewGameRequest(baseSelections) as Record<string, unknown>;

    expect(request).toMatchObject({
      campaign_template: 'deterministic_rpg_campaign',
      combat_lethality: 'deadly',
      difficulty: 'harsh',
      economy_pressure: 'strict',
      power_source: 'magic',
      primary_capability: 'technical',
      seed: 9137,
      starting_location: 'northern_watch_post',
      world_activity: 'living_world',
    });
    expect(request.player).toMatchObject({ build: 'ranger', name: 'Mira', portrait_seed: 9137, pronouns: 'she/her' });
    expect(request.secondary_capabilities).toEqual(['combat', 'survival']);
    expect(request.initial_stats).toMatchObject({ perception: 11 });
    expect(request.starter_gear).toContain('Shortbow');
    expect(request.features).toMatchObject({ autosave: true, background_soft_audit: true, image_generation: false, validator: true });
  });

  it('falls back to nullable seed and normalized safe defaults', () => {
    const request = buildRpgNewGameRequest({
      ...baseSelections,
      buildKey: 'negotiator',
      combatLethality: 'forgiving',
      difficulty: 'story',
      economyPressure: 'low',
      powerSource: 'technique',
      primaryCapability: 'recon',
      seed: '',
      startingLocation: 'rusty-flagons',
      worldActivity: 'quiet',
    });

    expect(request).toMatchObject({
      combat_lethality: 'safe',
      difficulty: 'story',
      economy_pressure: 'relaxed',
      power_source: 'martial',
      primary_capability: 'recon',
      seed: null,
      starting_location: 'rusty_flagon_tavern',
      world_activity: 'quiet',
    });
    expect(request.player).toMatchObject({ build: 'silver_tongue', portrait_seed: null });
  });
});
