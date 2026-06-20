import type { RpgCapability, RpgNewGameRequest, RpgPowerSource } from '../../api/client';

export type Capability = 'combat' | 'influence' | 'technical' | 'survival' | 'knowledge' | 'support';
export type BuildKey = 'balanced' | 'scout' | 'negotiator' | 'survivor' | 'scholar';
export type CreationStageState = 'done' | 'active' | 'pending';

export interface StatDefinition {
  key: string;
  label: string;
  detail: string;
}

export interface SelectOption {
  value: string;
  label: string;
  detail: string;
}

export interface BuildTemplate {
  key: BuildKey;
  label: string;
  detail: string;
  boosts: Record<string, number>;
  starterGear: string[];
}

export interface CreationStage {
  label: string;
  detail: string;
}

export interface CampaignCreationSelections {
  background: string;
  buildKey: BuildKey;
  capabilities: Record<Capability, boolean>;
  characterName: string;
  combatLethality: string;
  difficulty: string;
  economyPressure: string;
  powerSource: string;
  primaryCapability: string;
  pronouns: string;
  seed: string;
  startingLocation: string;
  stats: Record<string, number>;
  systems: {
    autosave: boolean;
    companions: boolean;
    grounding: boolean;
    images: boolean;
    narration: boolean;
    permadeath: boolean;
    softAudit: boolean;
    stt: boolean;
    tts: boolean;
  };
  worldActivity: string;
}

export const BASE_STAT = 8;
export const MAX_STAT = 16;
export const STAT_POOL = 20;

export const statDefinitions: StatDefinition[] = [
  { key: 'strength', label: 'Strength', detail: 'Melee force, carry weight, hard physical checks.' },
  { key: 'agility', label: 'Agility', detail: 'Initiative, stealth, dodge, delicate movement.' },
  { key: 'endurance', label: 'Endurance', detail: 'HP, exhaustion tolerance, long travel safety.' },
  { key: 'intellect', label: 'Intellect', detail: 'Knowledge checks, puzzle handling, crafting logic.' },
  { key: 'charisma', label: 'Charisma', detail: 'Dialogue leverage, prices, morale, recruitment.' },
  { key: 'perception', label: 'Perception', detail: 'Recon, clues, ambush detection, hidden details.' },
  { key: 'archery', label: 'Archery', detail: 'Ranged accuracy, combat opening, hunting shots.' },
  { key: 'survival', label: 'Survival', detail: 'Foraging, weather, resting, wilderness travel.' },
];

export const buildTemplates: BuildTemplate[] = [
  {
    key: 'balanced',
    label: 'Balanced Adventurer',
    detail: 'Even stats and flexible starter gear.',
    boosts: { strength: 1, agility: 1, endurance: 1, intellect: 1, charisma: 1, perception: 1, archery: 1, survival: 1 },
    starterGear: ['Travel cloak', 'Iron dagger', 'Trail rations x3', 'Torch x2', '10 silver'],
  },
  {
    key: 'scout',
    label: 'Road Scout',
    detail: 'Recon, archery, ambush detection, and travel safety.',
    boosts: { agility: 2, perception: 3, archery: 3, survival: 2 },
    starterGear: ['Shortbow', 'Arrow bundle', 'Bedroll', 'Trail rations x4', '6 silver'],
  },
  {
    key: 'negotiator',
    label: 'Silver-Tongued Agent',
    detail: 'Dialogue, merchant pressure, recruitment, and rumor work.',
    boosts: { charisma: 4, intellect: 2, perception: 2, agility: 1 },
    starterGear: ['Fine cloak', 'Ledger note', 'Rations x2', '15 silver'],
  },
  {
    key: 'survivor',
    label: 'Hardy Survivor',
    detail: 'HP, wilderness resilience, rests, and dangerous roads.',
    boosts: { endurance: 4, survival: 4, strength: 2 },
    starterGear: ['Hand axe', 'Field kit', 'Rope coil', 'Rations x5', '5 silver'],
  },
  {
    key: 'scholar',
    label: 'Practical Scholar',
    detail: 'Knowledge, crafting recipes, clues, and ancient records.',
    boosts: { intellect: 4, perception: 3, charisma: 1, survival: 1 },
    starterGear: ['Field journal', 'Ink kit', 'Old map', 'Torch x2', '8 silver'],
  },
];

export const backgrounds: SelectOption[] = [
  { value: 'wanderer', label: 'Wanderer', detail: 'Road-wise, socially flexible, and easy to seed into tavern hooks.' },
  { value: 'local', label: 'Local Regular', detail: 'Starts with stronger local rumors and familiar NPC names.' },
  { value: 'guild', label: 'Guild Apprentice', detail: 'Better crafting, trade, and service affordances.' },
  { value: 'ex-guard', label: 'Former Guard', detail: 'More combat discipline and watch authority context.' },
];

export const locations: SelectOption[] = [
  { value: 'rusty-flagons', label: 'Rusty Flagon Tavern', detail: 'Best for inn, merchant, rumor, companion, and opening-hook coverage.' },
  { value: 'market-road', label: 'Market Road', detail: 'Starts near travel, trading, guards, and roadside encounters.' },
  { value: 'old-quarry', label: 'Old Quarry Edge', detail: 'Investigation-forward start with riskier exploration.' },
  { value: 'watch-post', label: 'Northern Watch Post', detail: 'Combat, guard intervention, patrols, and faction pressure.' },
];

export const powerSources: SelectOption[] = [
  { value: 'mundane', label: 'Mundane', detail: 'Low-magic physical/social fantasy; strongest deterministic baseline.' },
  { value: 'divine', label: 'Divine Oath', detail: 'Support, healing hooks, vow pressure, and social expectations.' },
  { value: 'arcane', label: 'Arcane Talent', detail: 'Knowledge and utility-magic flavor while mechanics stay simulation-owned.' },
  { value: 'technique', label: 'Martial Technique', detail: 'Combat stance and skill flavor without supernatural assumptions.' },
];

export const primaryCapabilities: SelectOption[] = [
  { value: 'recon', label: 'Recon', detail: 'Clues, scouting, perception, travel safety.' },
  { value: 'combat', label: 'Combat', detail: 'Initiative, damage, target choice, survival under threat.' },
  { value: 'influence', label: 'Influence', detail: 'Negotiation, recruitment, rumors, prices.' },
  { value: 'support', label: 'Support', detail: 'Party care, rest safety, service interactions.' },
  { value: 'craft', label: 'Craft / Technical', detail: 'Item use, crafting, salvage, repair, and knowledge items.' },
];

export const creationStages: CreationStage[] = [
  { label: 'Validated setup', detail: 'Required fields, toggles, and point-buy totals checked.' },
  { label: 'Resolved seed', detail: 'Visible or random seed converted into deterministic campaign entropy.' },
  { label: 'Created player profile', detail: 'Identity, pronouns, background, power source, and capability tags prepared.' },
  { label: 'Applied stat allocation', detail: 'Point-buy stats and build boosts converted into initial profile metadata.' },
  { label: 'Assigned starter gear', detail: 'Starter kit, currency, and capability gear staged for session creation.' },
  { label: 'Prepared starting location', detail: 'Location, available services, and initial NPC roster resolved.' },
  { label: 'Seeding NPCs and services', detail: 'Innkeeper, merchants, rumors, party eligibility, and local events staged.' },
  { label: 'Creating opening hook', detail: 'First objective, suggested actions, and opening scene context generated.' },
  { label: 'Saving campaign session', detail: 'Autosave/checkpoint payload prepared for replay-preserving launch.' },
  { label: 'Preparing first turn context', detail: 'Turn composer, narration, TTS/STT, and optional image hooks made ready.' },
];

export const capabilityLabels: Record<Capability, string> = {
  combat: 'Combat',
  influence: 'Influence',
  technical: 'Technical',
  survival: 'Survival',
  knowledge: 'Knowledge',
  support: 'Support',
};

export const initialStats = Object.fromEntries(statDefinitions.map((stat) => [stat.key, BASE_STAT])) as Record<string, number>;

export function buildRpgNewGameRequest(selections: CampaignCreationSelections): RpgNewGameRequest {
  const selectedBuild = buildTemplates.find((template) => template.key === selections.buildKey) ?? buildTemplates[0];
  const primary = mapPrimaryCapability(selections.primaryCapability);
  const secondary = (Object.entries(selections.capabilities) as Array<[Capability, boolean]>)
    .filter(([, enabled]) => enabled)
    .map(([capability]) => mapSecondaryCapability(capability))
    .filter((capability, index, all) => capability !== primary && all.indexOf(capability) === index);
  const seed = parseSeed(selections.seed);

  return {
    campaign_template: 'deterministic_rpg_campaign',
    tone: selectedBuild.detail,
    background: selections.background,
    starting_location: mapStartingLocation(selections.startingLocation),
    player: {
      name: selections.characterName.trim(),
      pronouns: selections.pronouns.trim(),
      background: selections.background,
      build: mapBuildKey(selections.buildKey),
      portrait_seed: seed,
    },
    primary_capability: primary,
    secondary_capabilities: secondary,
    power_source: mapPowerSource(selections.powerSource),
    generated_class_name: selectedBuild.label,
    generated_class_summary: `${selectedBuild.detail} Starter gear: ${selectedBuild.starterGear.join(', ')}.`,
    difficulty: mapDifficulty(selections.difficulty),
    world_activity: mapWorldActivity(selections.worldActivity),
    economy_pressure: mapEconomyPressure(selections.economyPressure),
    combat_lethality: mapCombatLethality(selections.combatLethality),
    companions_enabled: selections.systems.companions,
    permadeath: selections.systems.permadeath,
    seed,
    initial_stats: { ...selections.stats },
    starter_gear: [...selectedBuild.starterGear],
    starting_build: selectedBuild.label,
    system_options: { ...selections.systems },
    features: {
      autosave: selections.systems.autosave,
      validator: selections.systems.grounding,
      background_soft_audit: selections.systems.softAudit,
      llm_narration: selections.systems.narration,
      image_generation: selections.systems.images,
      tts: selections.systems.tts,
      stt: selections.systems.stt,
    },
  };
}

function parseSeed(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

function mapBuildKey(value: BuildKey): NonNullable<RpgNewGameRequest['player']>['build'] {
  const mapping: Record<BuildKey, NonNullable<RpgNewGameRequest['player']>['build']> = {
    balanced: 'balanced_adventurer',
    scout: 'ranger',
    negotiator: 'silver_tongue',
    survivor: 'warrior',
    scholar: 'balanced_adventurer',
  };
  return mapping[value];
}

function mapPrimaryCapability(value: string): RpgCapability {
  return value === 'craft' ? 'technical' : (value as RpgCapability);
}

function mapSecondaryCapability(value: Capability): RpgCapability {
  return value;
}

function mapPowerSource(value: string): RpgPowerSource {
  const mapping: Record<string, RpgPowerSource> = {
    arcane: 'magic',
    divine: 'divine',
    mundane: 'mundane',
    technique: 'martial',
  };
  return mapping[value] ?? 'custom';
}

function mapStartingLocation(value: string): string {
  const mapping: Record<string, string> = {
    'market-road': 'market_road',
    'old-quarry': 'old_quarry_edge',
    'rusty-flagons': 'rusty_flagon_tavern',
    'watch-post': 'northern_watch_post',
  };
  return mapping[value] ?? value;
}

function mapDifficulty(value: string): NonNullable<RpgNewGameRequest['difficulty']> {
  if (value === 'hard') {
    return 'harsh';
  }
  return value === 'story' ? 'story' : 'normal';
}

function mapWorldActivity(value: string): NonNullable<RpgNewGameRequest['world_activity']> {
  if (value === 'busy') {
    return 'living_world';
  }
  return value === 'quiet' ? 'quiet' : 'standard';
}

function mapEconomyPressure(value: string): NonNullable<RpgNewGameRequest['economy_pressure']> {
  if (value === 'low') {
    return 'relaxed';
  }
  if (value === 'tight') {
    return 'strict';
  }
  return 'normal';
}

function mapCombatLethality(value: string): NonNullable<RpgNewGameRequest['combat_lethality']> {
  if (value === 'forgiving') {
    return 'safe';
  }
  return value === 'deadly' ? 'deadly' : 'normal';
}
