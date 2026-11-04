import type { AssetListResponse, JobListResponse, ReportListResponse } from '../../api/client';

export interface RpgHeroSummaryPreview {
  avatar: string;
  name: string;
  subtitle: string;
  origin: string;
  xpLabel: string;
  xpPercent: number;
  gold: string;
  source: 'live' | 'preview';
}

export interface RpgStatPreview {
  label: string;
  value: string;
  percent: number;
  tone: 'danger' | 'success' | 'mana';
}

export interface RpgSurvivalNeedPreview {
  id: 'hunger' | 'thirst' | 'fatigue';
  label: string;
  percent: number;
  severity: 'stable' | 'warning' | 'critical';
  value: string;
}

export interface RpgSurvivalPreview {
  actions: RpgQuickActionPreview[];
  detail: string;
  needs: RpgSurvivalNeedPreview[];
  source: 'live' | 'preview';
  status: 'Stable' | 'Warning' | 'Critical';
  warnings: string[];
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
  status?: string;
}

/** Who is here and where the paths lead, by name (the player view's). */
export interface RpgHerePreview {
  people: string[];
  exits: string[];
}

export interface RpgQuickActionPreview {
  label: string;
  icon: string;
  command: string;
  /** A card the game offered (evolution roadmap EV-9): the reading it plays, with no model call. */
  card?: Record<string, unknown>;
}

export interface RpgJournalEntryPreview {
  time: string;
  title: string;
  detail: string;
}

export interface RpgJournalDetailPreview {
  title: string;
  detail: string;
  bullets: string[];
  tags: string[];
}

export interface RpgInventoryItemPreview {
  icon: string;
  count: string;
  label: string;
  /** What the item rules let the hero do with it (use, equip, unequip, drop, sell), as the game says. */
  actions?: string[];
  category?: string;
  description?: string;
  worn?: boolean;
}

export interface RpgHotbarAbilityPreview {
  key: string;
  icon: string;
  label: string;
  abilityId?: string;
  description?: string;
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
  errorDetail?: string;
  source: 'live' | 'preview';
}

export interface RpgSessionSummaryPreview {
  id: string;
  worldId?: string;
  title: string;
  location: string;
  summary: string;
  updatedAt: string;
  turnLabel: string;
  checkpointLabel: string;
  sortRank: number;
  /** When the campaign was last played (epoch ms), when the list says. */
  lastPlayedMs?: number;
  source: 'live' | 'preview';
}

export interface RpgCheckpointSummaryPreview {
  label: string;
  detail: string;
  source: 'live' | 'preview';
}

export interface RpgOutcomeFactPreview {
  kind: string;
  text: string;
  tone?: 'gain' | 'loss' | 'neutral';
}

export interface RpgStoryMessagePreview {
  id?: string;
  interactionId?: string;
  submissionId?: string;
  messageKind?: string;
  messageIndex?: number;
  avatar: string;
  speaker: string;
  text: string;
  tone: 'player' | 'npc' | 'narrator';
  /** The outcome card's facts (RQ-7.2): what the turn changed. */
  facts?: RpgOutcomeFactPreview[];
  /** Who speaks it (EV-13): a person's id, or "narrator". */
  speakerId?: string;
  /** The quotes inside a narration and who speaks each (EV-13). */
  voices?: { speaker_id: string; start: number; end: number }[];
  /** The names in the text that open their lore (EV-12), as the turn's final text gave them. */
  links?: { entry_id: string; start: number; end: number }[];
}

export type RpgSession = Record<string, unknown>;

export type RpgJob = JobListResponse['jobs'][number];

export type RpgAsset = AssetListResponse['assets'][number];

export type RpgReport = NonNullable<ReportListResponse['reports']>[number];
