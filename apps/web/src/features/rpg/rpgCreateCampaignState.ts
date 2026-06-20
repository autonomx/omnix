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
