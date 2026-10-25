import type { RpgLaunchResponse } from './api/rpgSessionClient';
import type { RpgHotbarAbilityPreview } from './rpgUiTypes';

type AbilityStatus = 'unlocked' | 'available' | 'locked';

export interface AbilityPreview {
  id: string;
  name: string;
  icon: string;
  description: string;
  kind: 'active' | 'passive' | 'narrative_trait' | string;
  capability: string;
  powerSource: string;
  purpose: string;
  dimensions: string[];
  levelRequired: number;
  rank: number;
  maxRank: number;
  cooldown: number;
  resourceCost: Record<string, number>;
  prerequisites: string[];
  influenceTags: string[];
  hooks: string[];
  categoryName: string;
  isUnlocked: boolean;
  isAvailable: boolean;
  missingPrerequisites: string[];
  status: AbilityStatus;
  statusLabel: string;
}

interface AbilityCategoryPreview {
  id: string;
  name: string;
  capability: string;
  dimensions: string[];
  abilities: AbilityPreview[];
}

interface HotbarSlotPreview {
  slot: string;
  ability?: AbilityPreview;
}

export interface SkillProgressionPreview {
  id: string;
  label: string;
  rank: number;
  xp: number;
  /** XP the skill needs for its next rank. */
  threshold: number;
  source: string;
}

export interface EffectPreview {
  id: string;
  name: string;
  detail: string;
  dimensions: string[];
  remaining?: number;
}

export interface AbilityCoveragePreview {
  ok: boolean;
  score: number;
  totalObservations: number;
  coveredDimensions: string[];
  missingDimensions: string[];
  dimensionCounts: Record<string, number>;
  sourceCounts: Record<string, number>;
  warnings: string[];
}

export interface AbilityOverview {
  className: string;
  treeId: string;
  abilityPoints: number;
  playerLevel: number;
  categories: AbilityCategoryPreview[];
  allAbilities: AbilityPreview[];
  hotbarSlots: HotbarSlotPreview[];
  hotbarAbilities: RpgHotbarAbilityPreview[];
  skills: SkillProgressionPreview[];
  traits: AbilityPreview[];
  activeEffects: EffectPreview[];
  coverage: AbilityCoveragePreview;
  source: 'live' | 'preview';
}

export const REQUIRED_DIMENSIONS = ['resources', 'information', 'relationships', 'access', 'environment', 'position', 'narrative', 'economy', 'world'];

export function formatAbilityCost(cost: Record<string, unknown> | undefined): string {
  if (!cost) return '';
  return Object.entries(cost)
    .filter(([, value]) => typeof value === 'number')
    .map(([resource, value]) => `${value} ${titleCase(resource)}`)
    .join(' • ');
}

/** XP a skill needs for its next rank (ability_runtime.grant_skill_xp): its XP counts within the current rank. */
function skillRankThreshold(rank: number): number {
  return Math.max(25, rank * 100);
}

export function buildAbilityOverview(
  payload: RpgLaunchResponse | undefined,
  fallbackHotbar: RpgHotbarAbilityPreview[],
  hasLiveSession = false,
): AbilityOverview {
  const payloadRecord = recordValue(payload);
  const session = recordValue(payloadRecord?.session);
  const game = recordValue(payloadRecord?.game);
  const state = recordValue(session?.state) ?? game ?? session;
  const tree = recordValue(state?.ability_tree);
  const abilityState = recordValue(state?.ability_state);
  const player = recordValue(state?.player);
  const rawAbilities = firstArray(tree?.abilities);
  const coverage = buildCoveragePreview(payloadRecord, state);
  if (!state || !tree || !rawAbilities.length) {
    const previewAbilities = fallbackHotbar.map((ability) => ({
      ...previewAbilityFromHotbar(ability),
      capability: hasLiveSession ? 'session' : 'preview',
      powerSource: hasLiveSession ? 'session' : 'preview',
    }));
    return {
      className: hasLiveSession ? 'Session hotbar' : 'Preview ability kit',
      treeId: hasLiveSession ? 'session-hotbar' : 'preview-hotbar',
      abilityPoints: 0,
      playerLevel: 1,
      categories: [
        {
          id: hasLiveSession ? 'session' : 'preview',
          name: hasLiveSession ? 'Session Hotbar' : 'Preview Hotbar',
          capability: hasLiveSession ? 'session' : 'preview',
          dimensions: ['resources', 'position'],
          abilities: previewAbilities,
        },
      ],
      allAbilities: previewAbilities,
      hotbarSlots: fallbackHotbar.map((ability) => ({ slot: ability.key, ability: previewAbilities.find((candidate) => candidate.name === ability.label) })),
      hotbarAbilities: fallbackHotbar,
      skills: [],
      traits: [],
      activeEffects: [],
      coverage,
      source: hasLiveSession ? 'live' : 'preview',
    };
  }

  const unlocked = new Set(firstArray(abilityState?.unlocked).map(String));
  const ranks = recordValue(abilityState?.ranks) ?? {};
  const cooldowns = recordValue(abilityState?.cooldowns) ?? {};
  const abilityPoints = firstNumber(abilityState?.ability_points) ?? 0;
  const playerLevel = firstNumber(player?.level) ?? 1;
  const categoryLookup = buildCategoryLookup(tree);
  const abilities = rawAbilities.map((rawAbility) => buildAbilityPreview(rawAbility, categoryLookup, unlocked, ranks, cooldowns, abilityPoints, playerLevel));
  const abilityById = new Map(abilities.map((ability) => [ability.id, ability]));
  const categories = firstArray(tree.categories).map((rawCategory, index) => buildCategoryPreview(rawCategory, index, abilities, abilityById));
  const fallbackCategory = categories.length ? categories : [{ id: 'abilities', name: 'Abilities', capability: String(tree.primary_capability ?? 'custom'), dimensions: unique(abilities.flatMap((ability) => ability.dimensions)), abilities }];
  const hotbar = recordValue(state.hotbar) ?? recordValue(abilityState?.hotbar) ?? {};
  const hotbarSlots = Array.from({ length: 10 }, (_, index) => {
    const slot = String(index + 1);
    const abilityId = firstString(hotbar[slot]);
    return { slot, ability: abilityId ? abilityById.get(abilityId) : undefined };
  });
  const hotbarAbilities = hotbarSlots
    .filter((slot): slot is HotbarSlotPreview & { ability: AbilityPreview } => Boolean(slot.ability))
    .slice(0, 6)
    .map((slot) => ({
      key: slot.slot,
      icon: slot.ability.icon,
      label: slot.ability.name,
      abilityId: slot.ability.id,
      description: slot.ability.description,
    }));

  return {
    className: firstString(tree.class_name) ?? 'Ability tree',
    treeId: firstString(tree.tree_id) ?? 'ability-tree',
    abilityPoints,
    playerLevel,
    categories: fallbackCategory,
    allAbilities: abilities,
    hotbarSlots,
    hotbarAbilities,
    skills: buildSkillProgression(state),
    traits: abilities.filter((ability) => ability.kind === 'narrative_trait'),
    activeEffects: buildActiveEffects(state, abilityState),
    coverage,
    source: 'live',
  };
}

function buildCoveragePreview(payload: Record<string, unknown> | undefined, state: Record<string, unknown> | undefined): AbilityCoveragePreview {
  const mechanics = recordValue(state?.mechanics);
  const snapshots = firstArray(mechanics?.ability_coverage_snapshots);
  const source =
    recordValue(payload?.ability_coverage) ??
    recordValue(mechanics?.ability_coverage_latest) ??
    recordValue(snapshots[0]);

  if (!source) {
    return {
      ok: false,
      score: 0,
      totalObservations: 0,
      coveredDimensions: [],
      missingDimensions: REQUIRED_DIMENSIONS,
      dimensionCounts: {},
      sourceCounts: {},
      warnings: [],
    };
  }

  const coveredDimensions = firstArray(source.covered_dimensions).map(String);
  const missingDimensions = firstArray(source.missing_dimensions).map(String);
  return {
    ok: typeof source.ok === 'boolean' ? source.ok : missingDimensions.length === 0,
    score: Math.max(0, Math.min(1, firstNumber(source.coverage_score) ?? 0)),
    totalObservations: firstNumber(source.total_observations) ?? 0,
    coveredDimensions,
    missingDimensions,
    dimensionCounts: numericRecord(source.dimension_counts),
    sourceCounts: numericRecord(source.source_counts),
    warnings: firstArray(source.warnings).map(String),
  };
}

function buildAbilityPreview(rawAbility: unknown, categoryLookup: Map<string, string>, unlocked: Set<string>, ranks: Record<string, unknown>, cooldowns: Record<string, unknown>, abilityPoints: number, playerLevel: number): AbilityPreview {
  const record = recordValue(rawAbility) ?? {};
  const id = firstString(record.ability_id, record.id, record.name) ?? 'ability';
  const kind = firstString(record.kind) ?? 'active';
  const prerequisites = firstArray(record.prerequisites).map(String);
  const missingPrerequisites = prerequisites.filter((prerequisite) => !unlocked.has(prerequisite));
  const levelRequired = firstNumber(record.level_required) ?? 1;
  const isUnlocked = unlocked.has(id);
  const isAvailable = !isUnlocked && playerLevel >= levelRequired && missingPrerequisites.length === 0 && abilityPoints > 0;
  const status: AbilityStatus = isUnlocked ? 'unlocked' : isAvailable ? 'available' : 'locked';
  const rank = firstNumber(ranks[id], record.rank) ?? 1;
  const maxRank = firstNumber(record.max_rank) ?? 1;
  const cooldown = firstNumber(cooldowns[id]) ?? 0;
  return {
    id,
    name: firstString(record.name, record.label, record.ability_id) ?? titleCase(id),
    icon: firstString(record.icon) ?? iconForAbility(firstString(record.purpose), firstArray(record.dimensions).map(String)),
    description: firstString(record.description, record.summary) ?? 'Ability indexed from the selected session.',
    kind,
    capability: firstString(record.capability) ?? 'custom',
    powerSource: firstString(record.power_source) ?? 'mundane',
    purpose: firstString(record.purpose) ?? 'utility',
    dimensions: firstArray(record.dimensions).map(String),
    levelRequired,
    rank,
    maxRank,
    cooldown,
    resourceCost: numericRecord(record.resource_cost),
    prerequisites,
    influenceTags: firstArray(record.influence_tags).map(String),
    hooks: firstArray(record.hooks).map(String),
    categoryName: categoryLookup.get(id) ?? 'Abilities',
    isUnlocked,
    isAvailable,
    missingPrerequisites,
    status,
    statusLabel: abilityStatusLabel(status, levelRequired, playerLevel, missingPrerequisites, rank, maxRank, cooldown, abilityPoints),
  };
}

function buildCategoryLookup(tree: Record<string, unknown>): Map<string, string> {
  const lookup = new Map<string, string>();
  firstArray(tree.categories).forEach((rawCategory) => {
    const category = recordValue(rawCategory) ?? {};
    const name = firstString(category.name, category.category_id) ?? 'Abilities';
    firstArray(category.abilities).forEach((abilityId) => lookup.set(String(abilityId), name));
  });
  return lookup;
}

function buildCategoryPreview(rawCategory: unknown, index: number, abilities: AbilityPreview[], abilityById: Map<string, AbilityPreview>): AbilityCategoryPreview {
  const category = recordValue(rawCategory) ?? {};
  const ids = firstArray(category.abilities).map(String);
  const categoryAbilities = ids.map((id) => abilityById.get(id)).filter((ability): ability is AbilityPreview => Boolean(ability));
  return {
    id: firstString(category.category_id, category.id) ?? `category-${index + 1}`,
    name: firstString(category.name, category.label) ?? `Category ${index + 1}`,
    capability: firstString(category.capability) ?? categoryAbilities[0]?.capability ?? 'custom',
    dimensions: firstArray(category.dimensions).map(String).length ? firstArray(category.dimensions).map(String) : unique(categoryAbilities.flatMap((ability) => ability.dimensions)),
    abilities: categoryAbilities.length ? categoryAbilities : abilities,
  };
}

/** The character sheet's skills (practice and use level them toward `xp_to_next`), then the capabilities abilities train. */
function buildSkillProgression(state: Record<string, unknown>): SkillProgressionPreview[] {
  const sheetSkills = Object.entries(recordValue(recordValue(state.player)?.skills) ?? {}).map(([id, rawSkill]) => {
    const skill = recordValue(rawSkill) ?? {};
    const rank = firstNumber(skill.level, skill.rank) ?? 0;
    return {
      id,
      label: titleCase(id),
      rank,
      xp: firstNumber(skill.xp) ?? 0,
      threshold: firstNumber(skill.xp_to_next) ?? skillRankThreshold(rank),
      source: firstString(skill.last_source) ?? '',
    };
  });
  const listed = new Set(sheetSkills.map((skill) => skill.id));
  const abilitySkills = Object.entries(recordValue(state.skill_progression) ?? {})
    .filter(([id]) => !listed.has(id))
    .map(([id, rawSkill]) => {
      const skill = recordValue(rawSkill) ?? {};
      const rank = firstNumber(skill.rank) ?? 1;
      return { id, label: titleCase(id), rank, xp: firstNumber(skill.xp) ?? 0, threshold: skillRankThreshold(rank), source: firstString(skill.last_source) ?? '' };
    });
  return [...sheetSkills, ...abilitySkills];
}

function buildActiveEffects(state: Record<string, unknown>, abilityState: Record<string, unknown> | undefined): EffectPreview[] {
  const abilityEffects = firstArray(abilityState?.active_effects);
  const runtimeEffects = firstArray(recordValue(state.runtime)?.effects);
  return [...abilityEffects, ...runtimeEffects].slice(0, 8).map((rawEffect, index) => {
    const effect = recordValue(rawEffect) ?? {};
    const dimensions = firstArray(effect.dimensions).map(String).length ? firstArray(effect.dimensions).map(String) : [firstString(effect.dimension) ?? 'effect'];
    const name = firstString(effect.name, effect.source, effect.ability_name, effect.ability_id) ?? `Effect ${index + 1}`;
    const detail = firstString(effect.check, effect.purpose, effect.target) ?? dimensions.map(titleCase).join(', ');
    return { id: `${name}-${index}`, name, detail, dimensions, remaining: firstNumber(effect.remaining_turns) };
  });
}

function previewAbilityFromHotbar(ability: RpgHotbarAbilityPreview): AbilityPreview {
  return {
    id: ability.label,
    name: ability.label,
    icon: ability.icon,
    description: 'Preview hotbar ability. Select or create a session to inspect the saved ability tree.',
    kind: 'active',
    capability: 'preview',
    powerSource: 'preview',
    purpose: 'utility',
    dimensions: ['resources', 'position'],
    levelRequired: 1,
    rank: 1,
    maxRank: 1,
    cooldown: 0,
    resourceCost: {},
    prerequisites: [],
    influenceTags: [],
    hooks: [],
    categoryName: 'Preview Hotbar',
    isUnlocked: true,
    isAvailable: false,
    missingPrerequisites: [],
    status: 'unlocked',
    statusLabel: 'Preview',
  };
}

function abilityStatusLabel(status: AbilityStatus, levelRequired: number, playerLevel: number, missingPrerequisites: string[], rank: number, maxRank: number, cooldown: number, abilityPoints: number): string {
  if (status === 'unlocked') {
    return cooldown > 0 ? `Cooldown ${cooldown} turn(s) • rank ${rank}/${maxRank}` : `Unlocked • rank ${rank}/${maxRank}`;
  }
  if (playerLevel < levelRequired) {
    return `Locked • level ${levelRequired}`;
  }
  if (missingPrerequisites.length) {
    return `Locked • requires ${missingPrerequisites.map(titleCase).join(', ')}`;
  }
  return abilityPoints > 0 ? 'Available • costs 1 point' : 'Locked • needs ability point';
}

export function abilityDetail(ability: AbilityPreview): string {
  const cost = Object.entries(ability.resourceCost)
    .filter(([, value]) => value > 0)
    .map(([resource, value]) => `${value} ${resource}`)
    .join(', ');
  const pieces = [
    ability.description,
    `Dimensions: ${ability.dimensions.map(titleCase).join(', ') || 'None indexed'}.`,
    `Purpose: ${titleCase(ability.purpose)}.`,
    cost ? `Cost: ${cost}.` : 'No resource cost.',
    ability.hooks.length ? `Hooks: ${ability.hooks.map(titleCase).join(', ')}.` : undefined,
    ability.influenceTags.length ? `Tags: ${ability.influenceTags.map(titleCase).join(', ')}.` : undefined,
  ];
  return pieces.filter(Boolean).join(' ');
}

export function nextAssignableHotbarSlot(slots: HotbarSlotPreview[], abilityId?: string): string {
  const existing = slots.find((slot) => slot.ability?.id === abilityId);
  if (existing) {
    return existing.slot;
  }
  return slots.find((slot) => !slot.ability)?.slot ?? '1';
}

function numericRecord(value: unknown): Record<string, number> {
  const record = recordValue(value) ?? {};
  return Object.fromEntries(Object.entries(record).map(([key, amount]) => [key, firstNumber(amount) ?? 0]));
}

export function recordValue(value: unknown): Record<string, unknown> | undefined {
  if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return undefined;
}

function firstArray(...values: unknown[]): unknown[] {
  for (const value of values) {
    if (Array.isArray(value)) {
      return value;
    }
  }
  return [];
}

export function firstString(...values: unknown[]): string | undefined {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) {
      return value;
    }
  }
  return undefined;
}

export function firstNumber(...values: unknown[]): number | undefined {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value;
    }
    if (typeof value === 'string' && value.trim()) {
      const parsed = Number(value.replace(/,/g, ''));
      if (Number.isFinite(parsed)) {
        return parsed;
      }
    }
  }
  return undefined;
}

function unique(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))];
}

function iconForAbility(purpose: string | undefined, dimensions: string[]): string {
  const text = `${purpose ?? ''} ${dimensions.join(' ')}`.toLowerCase();
  if (text.includes('healing')) return '✚';
  if (text.includes('information')) return '⌕';
  if (text.includes('access')) return '⌁';
  if (text.includes('relationship')) return '☯';
  if (text.includes('environment')) return '✹';
  if (text.includes('damage')) return '⚔';
  if (text.includes('mobility')) return '⇥';
  return '✦';
}

export function titleCase(value: string | undefined): string {
  return String(value ?? '')
    .replace(/[_-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
