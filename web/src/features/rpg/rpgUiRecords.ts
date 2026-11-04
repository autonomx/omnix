import { NOT_TRACKED } from './rpgUiPreview';
import type { RpgSession, RpgStatPreview } from './rpgUiTypes';

export function getEnvironmentSnapshot(session: RpgSession | undefined): Record<string, unknown> | undefined {
  const state = recordValue(session?.state);
  const payload = recordValue(session?.payload);
  return firstRecord(session?.environment_snapshot, state?.environment_snapshot, payload?.environment_snapshot);
}

export function toStat(label: string, metric: { current: number; max: number }, tone: RpgStatPreview['tone']): RpgStatPreview {
  return { label, value: metricLabel(metric.current, metric.max), percent: metricPercent(metric.current, metric.max), tone };
}

export function emptyStat(label: string, tone: RpgStatPreview['tone']): RpgStatPreview {
  return { label, value: NOT_TRACKED, percent: 0, tone };
}

export function emptyHeroStats(): RpgStatPreview[] {
  return [emptyStat('HP', 'danger'), emptyStat('Stamina', 'success'), emptyStat('Mana', 'mana')];
}

export function getPlayerRecord(session: RpgSession | undefined): Record<string, unknown> | undefined {
  const canonicalPlayer = recordValue(recordValue(session?.simulation_state)?.player_state);
  const roots = getSessionRecords(session);
  const projectedPlayer = firstRecord(...roots.flatMap((root) => [root.player, root.hero, root.character, root.player_state, root.character_state, recordValue(root.state)?.player]));
  if (canonicalPlayer && projectedPlayer) {
    return {
      ...projectedPlayer,
      ...canonicalPlayer,
      resources: {
        ...recordValue(projectedPlayer.resources),
        ...recordValue(canonicalPlayer.resources),
      },
    };
  }
  return canonicalPlayer ?? projectedPlayer;
}

export function getSessionRecords(session: RpgSession | undefined): Record<string, unknown>[] {
  if (!session) return [];
  return [
    session,
    recordValue(session.simulation_state),
    recordValue(session.metadata),
    recordValue(session.state),
    recordValue(session.payload),
    recordValue(session.runtime_state),
  ].filter((record): record is Record<string, unknown> => Boolean(record));
}

export function readMetric(records: Array<Record<string, unknown> | undefined>, currentKeys: string[], maxKeys: string[]): { current: number; max: number } | undefined {
  for (const record of records) {
    if (!record) continue;
    const nestedMetric = firstRecord(...currentKeys.map((key) => recordValue(record[key])));
    const nestedCurrent = firstNumber(nestedMetric?.current, nestedMetric?.value, nestedMetric?.amount);
    const nestedMax = firstNumber(nestedMetric?.max, nestedMetric?.total, nestedMetric?.maximum);
    if (nestedCurrent !== undefined && nestedMax !== undefined) return { current: nestedCurrent, max: nestedMax };
    const current = firstNumber(...currentKeys.flatMap((key) => [record[key], record[`current_${key}`], record[`current${titleCase(key)}`]]));
    const max = firstNumber(...maxKeys.flatMap((key) => [record[key], record[`maximum_${key}`]]));
    if (current !== undefined && max !== undefined) return { current, max };
  }
  return undefined;
}

export function formatCurrency(...values: unknown[]): string {
  const currencyRecord = firstRecord(...values.map((value) => recordValue(value)));
  if (currencyRecord) {
    const gold = firstNumber(currencyRecord.gold, currencyRecord.gp, currencyRecord.coins);
    const silver = firstNumber(currencyRecord.silver, currencyRecord.sp);
    const copper = firstNumber(currencyRecord.copper, currencyRecord.cp);
    if (gold !== undefined || silver !== undefined || copper !== undefined) {
      return [gold !== undefined ? `${formatNumber(gold)}g` : undefined, silver !== undefined ? `${formatNumber(silver)}s` : undefined, copper !== undefined ? `${formatNumber(copper)}c` : undefined]
        .filter(Boolean)
        .join(' ');
    }
  }
  const numeric = firstNumber(...values);
  if (numeric !== undefined) return formatNumber(numeric);
  return firstString(...values) ?? NOT_TRACKED;
}

export function quickActionLabel(command: string): string {
  const [verb = 'Action'] = command.trim().split(/\s+/);
  return titleCase(verb);
}

export function quickActionIcon(command: string): string {
  const normalized = command.toLowerCase();
  if (normalized.startsWith('talk') || normalized.startsWith('ask')) return '☯';
  if (normalized.startsWith('travel') || normalized.startsWith('go')) return '🧭';
  if (/(look|listen|check|search|investigate|inspect)/.test(normalized)) return '⌕';
  if (/(rest|camp)/.test(normalized)) return '♨';
  if (/(attack|fight|ambush)/.test(normalized)) return '⚔';
  return '◇';
}

export function metricLabel(current: number, max: number): string {
  return `${formatNumber(current)} / ${formatNumber(max)}`;
}

export function metricPercent(current: number, max: number): number {
  if (max <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((current / max) * 100)));
}

export function relationshipScore(value: number | undefined): number {
  if (value === undefined) return 50;
  if (value > 0 && value <= 1) return Math.round(value * 100);
  return Math.max(0, Math.min(100, Math.round(value)));
}

export function stanceForScore(score: number): string {
  if (score >= 75) return 'Ally';
  if (score >= 55) return 'Friendly';
  if (score >= 35) return 'Neutral';
  if (score >= 15) return 'Wary';
  return 'Hostile';
}

export function firstString(...values: unknown[]): string | undefined {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value;
    if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  }
  return undefined;
}

export function firstNumber(...values: unknown[]): number | undefined {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string' && value.trim()) {
      const parsed = Number(value.replace(/,/g, ''));
      if (Number.isFinite(parsed)) return parsed;
    }
  }
  return undefined;
}

export function firstRecord(...values: unknown[]): Record<string, unknown> | undefined {
  return values.map(recordValue).find(Boolean);
}

export function firstArray(...values: unknown[]): unknown[] {
  for (const value of values) {
    if (Array.isArray(value)) return value;
  }
  return [];
}

export function recordValue(value: unknown): Record<string, unknown> | undefined {
  if (typeof value === 'object' && value !== null && !Array.isArray(value)) return value as Record<string, unknown>;
  return undefined;
}

export function compactTimestamp(value: string | undefined): string | undefined {
  if (!value) return undefined;
  if (!value.includes('T')) return value;
  const [date, time = ''] = value.split('T');
  const [hour = '00', minute = '00'] = time.split(':');
  return `${date} ${hour}:${minute} UTC`;
}

export function timestampRank(value: string | undefined): number {
  if (!value) return 0;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat('en-US').format(value);
}

export function initialFor(name: string): string {
  return name.trim().charAt(0).toUpperCase() || 'A';
}

export function titleCase(value: string): string {
  return value
    .replace(/[_-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function iconForInventory(label: string): string {
  const text = label.toLowerCase();
  if (text.includes('potion') || text.includes('heal')) return '🧪';
  if (text.includes('mana')) return '💧';
  if (text.includes('ration') || text.includes('food')) return '🥩';
  if (text.includes('rope')) return '🪢';
  if (text.includes('torch') || text.includes('fire')) return '🔥';
  if (text.includes('scroll') || text.includes('letter')) return '📜';
  return '▣';
}

export function questIcon(status: unknown): string {
  const text = String(status ?? '').toLowerCase();
  if (text.includes('complete')) return '✓';
  if (text.includes('failed')) return '×';
  if (text.includes('urgent')) return '▲';
  return '◆';
}

/** The name a speaker goes by. A person the world does not name reaches the story as a raw id ("npc:helix"): the
 * player reads a name, not an id. */
export function speakerLabel(speaker: string): string {
  if (!/^npc:/i.test(speaker)) return speaker;
  const words = speaker.slice(4).replace(/[_-]+/g, ' ').trim();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : 'Someone';
}
