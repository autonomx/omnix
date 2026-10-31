import { recordValue } from './rpgUiRecords';
import type { RpgSession } from './rpgUiTypes';

/** A group's standing with the hero, in words (evolution roadmap EV-1): its name and band. */
export interface RpgStandingPreview {
  groupId: string;
  name: string;
  band: string;
}

/** What the hero's decisions changed in the world (EV-1): the author's line for each fact the hero knows, and each
 * group's standing. The engine writes both onto the sheet (`state.what_has_changed`, `state.group_standing`). */
export interface RpgWorldChangesPreview {
  lines: string[];
  standing: RpgStandingPreview[];
  /** The word the hero has heard going about (EV-4, `state.word_heard`): what people are doing toward their goals. */
  word: string[];
}

export const emptyWorldChanges: RpgWorldChangesPreview = { lines: [], standing: [], word: [] };

function textLines(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((line): line is string => typeof line === 'string' && line.trim().length > 0)
    : [];
}

export function buildWorldChanges(session: RpgSession | undefined): RpgWorldChangesPreview {
  const sheet = recordValue(session?.state);
  if (!sheet) return emptyWorldChanges;
  const lines = textLines(sheet.what_has_changed);
  const standing = Array.isArray(sheet.group_standing)
    ? sheet.group_standing.flatMap((row) => {
      const group = recordValue(row);
      if (!group || typeof group.group_id !== 'string' || typeof group.band !== 'string') return [];
      return [{ groupId: group.group_id, name: typeof group.name === 'string' ? group.name : group.group_id, band: group.band }];
    })
    : [];
  return { lines, standing, word: textLines(sheet.word_heard) };
}
