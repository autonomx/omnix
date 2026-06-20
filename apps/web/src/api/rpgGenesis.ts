import type { RpgCapability, RpgNewGameRequest } from './client';

const GENESIS_VERSION = 'rpg_genesis_v2';

const CAPABILITY_TALENT_IDS: Partial<Record<RpgCapability, string>> = {
  combat: 'combat_readiness',
  influence: 'social_leverage',
  knowledge: 'field_knowledge',
  recon: 'reconnaissance',
  support: 'party_support',
  survival: 'survival_sense',
  technical: 'technical_handling',
};

interface LooseRequest extends RpgNewGameRequest {
  genesis?: Record<string, unknown>;
  opening_hook?: string;
  opening_pace?: string;
  relationship_preset?: string;
  starter_gear_tags?: string[];
  story_options?: Record<string, unknown>;
  system_options?: Record<string, unknown>;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function asString(value: unknown, fallback: string): string {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback;
}

function asBoolean(value: unknown, fallback: boolean): boolean {
  return typeof value === 'boolean' ? value : fallback;
}

function normalizeStats(value: unknown): Record<string, number> {
  const source = asRecord(value);
  return {
    strength: Number(source.strength ?? 10),
    agility: Number(source.agility ?? 10),
    endurance: Number(source.endurance ?? 10),
    intellect: Number(source.intellect ?? 10),
    charisma: Number(source.charisma ?? 10),
    perception: Number(source.perception ?? 10),
    archery: Number(source.archery ?? 8),
    survival: Number(source.survival ?? 8),
  };
}

function buildTalents(request: LooseRequest): Array<{ id: string; rank: number }> {
  const talents: Array<{ id: string; rank: number }> = [];
  const seen = new Set<string>();
  const addTalent = (capability: unknown, rank: number): void => {
    const key = asString(capability, '').replace('-', '_');
    const id = CAPABILITY_TALENT_IDS[key as RpgCapability] ?? key;
    if (!id || seen.has(id)) {
      return;
    }
    seen.add(id);
    talents.push({ id, rank });
  };
  addTalent(request.primary_capability, 2);
  for (const capability of request.secondary_capabilities ?? []) {
    addTalent(capability, 1);
  }
  return talents;
}

function fallbackGearTags(request: LooseRequest): string[] {
  const provided = Array.isArray(request.starter_gear_tags) ? request.starter_gear_tags.filter((tag) => typeof tag === 'string') : [];
  if (provided.length > 0) {
    return provided;
  }
  const tags = new Set<string>(['travel_supplies']);
  const capabilities = [request.primary_capability, ...(request.secondary_capabilities ?? [])];
  if (capabilities.includes('survival')) {
    tags.add('survival_tool');
  }
  if (capabilities.includes('knowledge') || capabilities.includes('technical')) {
    tags.add('field_notes');
  }
  if (capabilities.includes('recon')) {
    tags.add('ranged_weapon');
  }
  return Array.from(tags);
}

export function withRpgGenesisContract(request: RpgNewGameRequest = {}): RpgNewGameRequest {
  const loose = request as LooseRequest;
  if (loose.genesis) {
    return request;
  }
  const player = asRecord(request.player);
  const storyOptions = asRecord(loose.story_options);
  const systemOptions = asRecord(loose.system_options);
  const features = asRecord(request.features);
  const seed = typeof request.seed === 'number' ? request.seed : null;
  const genesis = {
    contract_version: GENESIS_VERSION,
    campaign_template: asString(request.campaign_template, 'deterministic_rpg_campaign'),
    genre: request.genre ?? null,
    tone: asString(request.tone, 'heroic adventure'),
    identity: {
      name: asString(player.name, 'Alyndra'),
      pronouns: asString(player.pronouns, 'she/her'),
      background: asString(player.background ?? request.background, 'wanderer'),
      origin: asString(player.background ?? request.background, 'wanderer'),
      power_source: request.power_source ?? null,
    },
    drivers: {
      archetype: asString(player.build, asString(request.generated_class_name, 'balanced_adventurer')),
      motivation: {
        primary: asString(storyOptions.opening_hook ?? loose.opening_hook, 'survival'),
        target: asString(storyOptions.relationship_preset ?? loose.relationship_preset, '' ) || null,
        intensity: 100,
        fulfilled: false,
      },
      flaw: null,
      talents: buildTalents(loose),
      values: ['agency'],
    },
    initial_stats: normalizeStats(loose.initial_stats),
    starter_gear_tags: fallbackGearTags(loose),
    story_options: {
      opening_hook: asString(storyOptions.opening_hook ?? loose.opening_hook, 'tavern_rumor'),
      opening_pace: asString(storyOptions.opening_pace ?? loose.opening_pace, 'balanced'),
      relationship_preset: asString(storyOptions.relationship_preset ?? loose.relationship_preset, 'unknown_outsider'),
    },
    world_options: {
      world_profile: null,
      starting_location: asString(request.starting_location, 'rusty_flagon_tavern'),
      difficulty: request.difficulty ?? 'normal',
      world_activity: request.world_activity ?? 'standard',
      economy_pressure: request.economy_pressure ?? 'normal',
      combat_lethality: request.combat_lethality ?? 'normal',
      seed,
    },
    system_options: {
      autosave: asBoolean(systemOptions.autosave ?? features.autosave, true),
      companions: asBoolean(systemOptions.companions ?? request.companions_enabled, true),
      permadeath: asBoolean(systemOptions.permadeath ?? request.permadeath, false),
      validator: asBoolean(systemOptions.grounding ?? features.validator, true),
      background_soft_audit: asBoolean(systemOptions.softAudit ?? features.background_soft_audit, true),
      llm_narration: asBoolean(systemOptions.narration ?? features.llm_narration, true),
      image_generation: asBoolean(systemOptions.images ?? features.image_generation, false),
      tts: asBoolean(systemOptions.tts ?? features.tts, false),
      stt: asBoolean(systemOptions.stt ?? features.stt, false),
    },
  };
  return { ...request, genesis } as RpgNewGameRequest;
}
