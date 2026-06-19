import type { RpgInventoryItemPreview } from './rpgUiState';

export type RpgItemUiActionKind =
  | 'inspect'
  | 'use'
  | 'equip'
  | 'drop'
  | 'salvage'
  | 'craft'
  | 'modify'
  | 'sell'
  | 'buy'
  | 'diagnostics'
  | 'maintenance'
  | 'objectives'
  | 'scenario';

export type RpgItemUiActionMode = 'loadout' | 'item_resolve' | 'merchant' | 'status';

export interface RpgItemUiAction {
  id: string;
  kind: RpgItemUiActionKind;
  label: string;
  detail: string;
  mode: RpgItemUiActionMode;
  command: string;
  payload: Record<string, unknown>;
  disabled?: boolean;
}

export interface RpgItemObjectivePreview {
  id: string;
  label: string;
  detail: string;
  action: string;
  payload: Record<string, unknown>;
  disabled?: boolean;
}

export interface RpgItemStatusCard {
  id: string;
  label: string;
  value: string;
  detail: string;
  tone: 'ready' | 'warning' | 'danger' | 'muted';
}

export interface RpgMerchantEntryPreview {
  id: string;
  label: string;
  detail: string;
  priceLabel: string;
  action: 'buy' | 'sell';
  payload: Record<string, unknown>;
  disabled?: boolean;
}

interface BuildSelectedItemActionsInput {
  item?: RpgInventoryItemPreview;
  selectedSessionId?: string | null;
}

interface BuildStatusCardsInput {
  diagnostics?: Record<string, unknown> | null;
  maintenance?: Record<string, unknown> | null;
  report?: Record<string, unknown> | null;
}

const DEFAULT_ITEM_COUNT = '1';

export function buildSelectedItemActions({ item, selectedSessionId }: BuildSelectedItemActionsInput): RpgItemUiAction[] {
  if (!item) {
    return [];
  }

  const itemName = item.label;
  const disabled = !selectedSessionId;
  const baseDetail = disabled ? 'Select a live session before applying item actions.' : `${item.count || DEFAULT_ITEM_COUNT} carried.`;
  const loadout = (kind: RpgItemUiActionKind, label: string, detail: string, action: string): RpgItemUiAction => ({
    id: `${kind}:${itemName}`,
    kind,
    label,
    detail: `${detail} ${baseDetail}`.trim(),
    mode: 'loadout',
    command: `${label} ${itemName}`,
    payload: { action, item_name: itemName },
    disabled,
  });
  const resolve = (kind: RpgItemUiActionKind, label: string, detail: string, command: string): RpgItemUiAction => ({
    id: `${kind}:${itemName}`,
    kind,
    label,
    detail: `${detail} ${baseDetail}`.trim(),
    mode: kind === 'sell' ? 'merchant' : 'item_resolve',
    command,
    payload: kind === 'sell' ? { command, item_name: itemName } : { command },
    disabled,
  });

  return [
    loadout('inspect', 'Inspect', 'Review deterministic item details.', 'inspect'),
    loadout('use', 'Use', 'Apply item effects through deterministic item handling.', 'use'),
    loadout('equip', 'Equip', 'Equip the item if it belongs in a gear slot.', 'equip'),
    loadout('drop', 'Drop', 'Remove one carried instance when safe.', 'drop'),
    resolve('salvage', 'Salvage', 'Recover deterministic materials from the item.', `salvage ${itemName}`),
    resolve('sell', 'Sell', 'Offer the item to the active merchant service.', `sell ${itemName}`),
  ];
}

export function buildItemObjectivePreviews(payload: Record<string, unknown> | null | undefined): RpgItemObjectivePreview[] {
  const objectives = Array.isArray(payload?.objectives) ? payload.objectives : [];
  return objectives.map((entry, index) => {
    const objective = asRecord(entry);
    const action = readString(objective.action) || readString(objective.kind) || 'item_action';
    const label = readString(objective.label) || titleCase(action);
    const detail = readString(objective.detail) || readString(objective.reason) || 'Deterministic item-system suggestion.';
    const payloadValue = readRecord(objective.payload) ?? readRecord(objective.request) ?? {};
    return {
      id: readString(objective.id) || `${action}:${index}`,
      label,
      detail,
      action,
      payload: payloadValue,
      disabled: Boolean(objective.disabled),
    };
  });
}

export function buildItemStatusCards({ diagnostics, maintenance, report }: BuildStatusCardsInput): RpgItemStatusCard[] {
  const diagnosticSummary = asRecord(diagnostics?.summary) ?? diagnostics ?? {};
  const maintenanceSummary = asRecord(maintenance?.summary) ?? maintenance ?? {};
  const reportSummary = asRecord(report?.summary) ?? report ?? {};
  const severity = readString(diagnostics?.severity) || readString(diagnosticSummary.severity) || 'unknown';
  const issueCount = readNumber(diagnosticSummary.issue_count) ?? readNumber(diagnostics?.issue_count) ?? 0;
  const warningCount = readNumber(diagnosticSummary.warning_count) ?? readNumber(diagnostics?.warning_count) ?? 0;
  const droppedCount = readNumber(maintenanceSummary.dropped_count) ?? readNumber(maintenance?.dropped_count) ?? 0;
  const coverageScore = readNumber(reportSummary.coverage_score) ?? readNumber(report?.coverage_score) ?? 0;

  return [
    {
      id: 'diagnostics',
      label: 'Item diagnostics',
      value: severity,
      detail: `${issueCount} issue${issueCount === 1 ? '' : 's'} • ${warningCount} warning${warningCount === 1 ? '' : 's'}`,
      tone: issueCount > 0 ? 'danger' : warningCount > 0 ? 'warning' : severity === 'unknown' ? 'muted' : 'ready',
    },
    {
      id: 'maintenance',
      label: 'Item maintenance',
      value: droppedCount > 0 ? `${droppedCount} compacted` : 'Stable',
      detail: droppedCount > 0 ? 'Oversized item traces were compacted.' : 'No item-state compaction required.',
      tone: droppedCount > 0 ? 'warning' : 'ready',
    },
    {
      id: 'coverage',
      label: 'Item coverage',
      value: `${Math.round(Math.max(0, Math.min(1, coverageScore)) * 100)}%`,
      detail: readString(reportSummary.detail) || 'Autoplay/report item coverage summary.',
      tone: coverageScore >= 0.8 ? 'ready' : coverageScore > 0 ? 'warning' : 'muted',
    },
  ];
}

export function buildMerchantEntryPreviews(payload: Record<string, unknown> | null | undefined): RpgMerchantEntryPreview[] {
  const entries = Array.isArray(payload?.entries)
    ? payload.entries
    : Array.isArray(payload?.menu)
      ? payload.menu
      : Array.isArray(payload?.items)
        ? payload.items
        : [];

  return entries.map((entry, index) => {
    const record = asRecord(entry);
    const action = readString(record.action) === 'sell' ? 'sell' : 'buy';
    const itemName = readString(record.item_name) || readString(record.name) || readString(record.label) || `Item ${index + 1}`;
    const priceLabel = readString(record.price_label) || formatPrice(record.price ?? record.quote ?? record.currency);
    return {
      id: readString(record.id) || `${action}:${itemName}:${index}`,
      label: itemName,
      detail: readString(record.detail) || readString(record.description) || `${titleCase(action)} ${itemName}`,
      priceLabel,
      action,
      payload: { action, item_name: itemName },
      disabled: Boolean(record.disabled),
    };
  });
}

function asRecord(value: unknown): Record<string, unknown> {
  return readRecord(value) ?? {};
}

function readRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : undefined;
}

function readString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value : undefined;
}

function readNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function titleCase(value: string): string {
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function formatPrice(value: unknown): string {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return `${value} coin${value === 1 ? '' : 's'}`;
  }
  const record = asRecord(value);
  const gold = readNumber(record.gold) ?? 0;
  const silver = readNumber(record.silver) ?? 0;
  const copper = readNumber(record.copper) ?? 0;
  const parts = [gold ? `${gold}g` : '', silver ? `${silver}s` : '', copper ? `${copper}c` : ''].filter(Boolean);
  return parts.length ? parts.join(' ') : 'Quote pending';
}
