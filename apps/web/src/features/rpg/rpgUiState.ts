import type { AssetListResponse, JobListResponse, PersistenceInventory, ReportListResponse } from '../../api/client';

export interface RpgStatPreview {
  label: string;
  value: string;
  percent: number;
  tone: 'danger' | 'success' | 'mana';
}

export interface RpgGearPreview {
  icon: string;
  name: string;
  slot: string;
}

export interface RpgPartyMemberPreview {
  avatar: string;
  name: string;
  role: string;
  hp: string;
  percent: number;
}

export interface RpgQuestPreview {
  icon: string;
  title: string;
  detail: string;
}

export interface RpgQuickActionPreview {
  label: string;
  icon: string;
  command: string;
}

export interface RpgJournalEntryPreview {
  time: string;
  title: string;
  detail: string;
}

export interface RpgInventoryItemPreview {
  icon: string;
  count: string;
  label: string;
}

export interface RpgHotbarAbilityPreview {
  key: string;
  icon: string;
  label: string;
}

export interface RpgWorldStateRowPreview {
  icon: string;
  label: string;
  value: string;
}

export interface RpgNpcRelationshipPreview {
  name: string;
  stance: string;
  score: number;
}

export interface RpgJobCardPreview {
  id: string;
  title: string;
  status: string;
  progress: number;
  detail: string;
  source: 'live' | 'preview';
}

type RpgSession = PersistenceInventory['sessions'][number];
type RpgJob = JobListResponse['jobs'][number];
type RpgAsset = AssetListResponse['assets'][number];
type RpgReport = ReportListResponse['reports'][number];

export interface RpgWorkspaceState {
  heroStats: RpgStatPreview[];
  equippedGear: RpgGearPreview[];
  partyMembers: RpgPartyMemberPreview[];
  activeQuests: RpgQuestPreview[];
  quickActions: RpgQuickActionPreview[];
  recentEvents: string[];
  journalEntries: RpgJournalEntryPreview[];
  inventoryItems: RpgInventoryItemPreview[];
  hotbarAbilities: RpgHotbarAbilityPreview[];
  worldStateRows: RpgWorldStateRowPreview[];
  npcRelationships: RpgNpcRelationshipPreview[];
  sessions: RpgSession[];
  rpgJobs: RpgJob[];
  rpgAssets: RpgAsset[];
  rpgReports: RpgReport[];
  jobCards: RpgJobCardPreview[];
}

export interface RpgWorkspaceStateSources {
  inventory?: PersistenceInventory;
  jobs?: JobListResponse;
  assets?: AssetListResponse;
  reports?: ReportListResponse;
}

export const heroStats: RpgStatPreview[] = [
  { label: 'HP', value: '86 / 110', percent: 78, tone: 'danger' },
  { label: 'Stamina', value: '72 / 100', percent: 72, tone: 'success' },
  { label: 'Mana', value: '64 / 120', percent: 53, tone: 'mana' },
];

export const equippedGear: RpgGearPreview[] = [
  { icon: '🏹', name: 'Longbow of the Boreal Wind', slot: 'Weapon' },
  { icon: '🛡️', name: 'Shadow Leather Armor +2', slot: 'Armor' },
  { icon: '🦉', name: 'Cloak of the Owl', slot: 'Cloak' },
  { icon: '💍', name: 'Band of Keen Senses', slot: 'Ring' },
];

export const partyMembers: RpgPartyMemberPreview[] = [
  { avatar: 'T', name: 'Thorin Ironfist', role: 'Lv. 14 Warrior', hp: '112 / 140', percent: 80 },
  { avatar: 'E', name: 'Elandra', role: 'Lv. 13 Mage', hp: '78 / 90', percent: 87 },
  { avatar: 'K', name: 'Kael', role: 'Lv. 12 Rogue', hp: '68 / 85', percent: 80 },
];

export const activeQuests: RpgQuestPreview[] = [
  { icon: '◆', title: 'The Frostbound Relic', detail: 'Find the relic in Glimmerdeep.' },
  { icon: '▲', title: 'Secrets in the Snow', detail: 'Investigate the old watchtower.' },
  { icon: '⬟', title: 'Bounty: Icefang Alpha', detail: 'Track down the alpha beast.' },
];

export const quickActions: RpgQuickActionPreview[] = [
  { label: 'Talk', icon: '☯', command: 'Talk to Thorin about the tracks near the archway.' },
  { label: 'Travel', icon: '🧭', command: 'Travel deeper into Glimmerdeep Pass toward the watchtower.' },
  { label: 'Investigate', icon: '⌕', command: 'Investigate the clawed tracks and torn Northern Watch banner.' },
  { label: 'Rest', icon: '♨', command: 'Make a short camp and let the party recover.' },
  { label: 'Inventory', icon: '▣', command: 'Open inventory and check supplies before moving on.' },
  { label: 'Attack', icon: '⚔', command: 'Prepare an ambush in case Icefang scouts are nearby.' },
];

export const recentEvents = [
  'You arrived at Glimmerdeep Pass.',
  'Thorin Ironfist: “Best keep our eyes open. This place gives me the chills.”',
  'You gained 120 XP.',
];

export const journalEntries: RpgJournalEntryPreview[] = [
  { time: 'Day 18 • 09:42', title: 'Arrived at Glimmerdeep Pass', detail: 'Reached the ancient archway.' },
  { time: 'Day 18 • 08:15', title: 'Left Frostpine Hollow', detail: 'Followed the northern trail.' },
  { time: 'Day 17 • 21:30', title: 'Long Rest at Frostpine', detail: 'Recovered after the Icefang fight.' },
];

export const inventoryItems: RpgInventoryItemPreview[] = [
  { icon: '🧪', count: '12', label: 'Healing potion' },
  { icon: '💧', count: '7', label: 'Mana tonic' },
  { icon: '🥩', count: '5', label: 'Trail rations' },
  { icon: '🔮', count: '3', label: 'Focus crystal' },
  { icon: '🪢', count: '2', label: 'Rope coil' },
  { icon: '🔥', count: '9', label: 'Torch' },
  { icon: '🍃', count: '4', label: 'Keenleaf' },
  { icon: '📜', count: '6', label: 'Scroll' },
];

export const hotbarAbilities: RpgHotbarAbilityPreview[] = [
  { key: '1', icon: '✦', label: 'Aimed Shot' },
  { key: '2', icon: '↯', label: 'Frost Arrow' },
  { key: '3', icon: '☘', label: 'Camouflage' },
  { key: '4', icon: '✹', label: 'Radiant Flare' },
  { key: '5', icon: '⟡', label: 'Volley' },
  { key: '6', icon: '⇥', label: 'Dash' },
];

export const worldStateRows: RpgWorldStateRowPreview[] = [
  { icon: '☀', label: 'Time', value: 'Day 18 • 09:42' },
  { icon: '≋', label: 'Weather', value: 'Cold, Windy' },
  { icon: '❄', label: 'Temperature', value: '-12°C' },
  { icon: '✦', label: 'Reputation', value: 'Honored (35)' },
];

export const npcRelationships: RpgNpcRelationshipPreview[] = [
  { name: 'Thorin Ironfist', stance: 'Ally', score: 78 },
  { name: 'Elandra', stance: 'Ally', score: 64 },
  { name: 'Kael', stance: 'Ally', score: 52 },
  { name: 'Captain Bryn', stance: 'Neutral', score: 10 },
];

export const previewJobs: RpgJobCardPreview[] = [
  { id: 'preview-turn', title: 'rpg.turn', status: 'Running', progress: 68, detail: 'Load / Apply turn / Narrate / Checkpoint', source: 'preview' },
  { id: 'preview-narration', title: 'narration.generate', status: 'Running', progress: 42, detail: 'Generating presentation text', source: 'preview' },
  { id: 'preview-world', title: 'world.state.update', status: 'Queued', progress: 0, detail: 'Waiting for turn output', source: 'preview' },
];

export function createRpgWorkspaceState(sources: RpgWorkspaceStateSources): RpgWorkspaceState {
  const sessions = sources.inventory?.sessions ?? [];
  const rpgJobs = sources.jobs?.jobs.filter((job) => job.module === 'rpg') ?? [];
  const rpgAssets = sources.assets?.assets.filter((asset) => asset.type === 'rpg_checkpoint' || asset.module === 'rpg') ?? [];
  const rpgReports = sources.reports?.reports?.filter((report) => report.kind.includes('rpg') || report.id.includes('rpg')) ?? [];
  const jobCards = rpgJobs.length ? rpgJobs.map(toJobCard) : previewJobs;

  return {
    heroStats,
    equippedGear,
    partyMembers,
    activeQuests,
    quickActions,
    recentEvents,
    journalEntries,
    inventoryItems,
    hotbarAbilities,
    worldStateRows,
    npcRelationships,
    sessions,
    rpgJobs,
    rpgAssets,
    rpgReports,
    jobCards,
  };
}

export function safeSessionId(session: Record<string, unknown>, index: number): string {
  const candidate = session.session_id ?? session.id ?? session.name ?? `session:${index + 1}`;
  return String(candidate);
}

export function progressPercent(progress: { current: number; total: number } | undefined): number {
  if (!progress || progress.total <= 0) {
    return 0;
  }

  return Math.min(100, Math.round((progress.current / progress.total) * 100));
}

function toJobCard(job: RpgJob): RpgJobCardPreview {
  return {
    id: String(job.id),
    title: String(job.type),
    status: String(job.status),
    progress: progressPercent(job.progress),
    detail: job.stages?.map((stage) => stage.label).join(' / ') || String(job.resource_class),
    source: 'live',
  };
}
