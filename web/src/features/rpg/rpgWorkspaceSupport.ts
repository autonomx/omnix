import type { JobRecord } from '../../api/client';
import type { HermesRpgSuggestion } from './api/hermesClient';
import { rpgTurnOutputText } from './rpgStoryState';
import type { RpgQuickActionPreview, RpgStoryMessagePreview } from './rpgUiTypes';

export interface RpgFormValues {
  sessionId: string;
  command: string;
  /** A card clicked (EV-9): played as it is, not read from the command. */
  card?: Record<string, unknown>;
}

export interface PendingRpgTurnSubmission {
  command: string;
  sessionId: string;
  submittedAt: number;
}

export const ACTIVE_JOB_STATUSES = new Set(['queued', 'leased', 'running', 'waiting', 'retrying', 'cancel_requested']);

const RPG_SELECTED_SESSION_STORAGE_KEY = 'omnix:rpg:selected-session-id';

const RPG_DEVELOPER_TOOLS_STORAGE_KEY = 'omnix:rpg:developer-tools';

export const RPG_TURN_QUEUE_TIMEOUT_MS = 45_000;

export const RPG_TURN_RECOVERY_WINDOW_MS = 60_000;

export function formatQueryError(error: unknown) {
  if (error instanceof Error) {
    return error.message;
  }

  return 'Request failed before the RPG workspace could read this source.';
}

export function readStoredRpgSessionId(): string {
  if (typeof window === 'undefined') {
    return '';
  }

  try {
    return window.localStorage.getItem(RPG_SELECTED_SESSION_STORAGE_KEY)?.trim() ?? '';
  } catch {
    return '';
  }
}

export function readStoredDeveloperTools(): boolean {
  if (typeof window === 'undefined') {
    return false;
  }

  try {
    return window.localStorage.getItem(RPG_DEVELOPER_TOOLS_STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

export function writeStoredDeveloperTools(enabled: boolean): void {
  try {
    if (enabled) {
      window.localStorage.setItem(RPG_DEVELOPER_TOOLS_STORAGE_KEY, '1');
    } else {
      window.localStorage.removeItem(RPG_DEVELOPER_TOOLS_STORAGE_KEY);
    }
  } catch {
    // Storage can be unavailable; the choice still holds for this visit.
  }
}

export function writeStoredRpgSessionId(sessionId: string | null): void {
  if (typeof window === 'undefined') {
    return;
  }

  try {
    if (sessionId?.trim()) {
      window.localStorage.setItem(RPG_SELECTED_SESSION_STORAGE_KEY, sessionId.trim());
    } else {
      window.localStorage.removeItem(RPG_SELECTED_SESSION_STORAGE_KEY);
    }
  } catch {
    // Storage can be unavailable in private or embedded contexts; the live selection still works in memory.
  }
}

export function timestampMs(value?: string | null): number {
  const parsed = Date.parse(value ?? '');
  return Number.isFinite(parsed) ? parsed : 0;
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function arrayValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function firstString(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
  }
  return null;
}

const EMPTY_VISIBLE_RESPONSE_TEXT = new Set(['', '[]', '{}', '[ ]', '{ }', 'null', 'none', 'false', 'true']);

function isEmptyVisibleResponseText(text: string): boolean {
  return EMPTY_VISIBLE_RESPONSE_TEXT.has(text.trim().toLowerCase());
}

function cleanSubmittedTurnResponse(response: string | null): string | null {
  if (!response) return null;
  const paragraphs = response.split(/\n\s*\n/).map((paragraph) => paragraph.trim()).filter(Boolean);
  const visibleParagraphs = paragraphs.filter((paragraph) => !/^(?:Action|Result):\s*/i.test(paragraph));
  const text = (visibleParagraphs.length ? visibleParagraphs : paragraphs).join('\n\n');
  return text && !isEmptyVisibleResponseText(text) ? text : null;
}

function submittedTurnResponseContent(job: JobRecord | undefined): string | null {
  const output = arrayValue(job?.output_refs)
    .map(recordValue)
    .find((candidate) => firstString(candidate.type, candidate.kind) === 'rpg_turn_response');
  return cleanSubmittedTurnResponse(rpgTurnOutputText(output) ?? null);
}

function submittedTurnCommand(job: JobRecord | undefined): string | null {
  return firstString(recordValue(job?.input_payload).command);
}

function submittedTurnSessionId(job: JobRecord | undefined): string | null {
  return firstString(recordValue(job?.input_ref).session_id);
}

function inferSubmittedResponseSpeaker(response: string): string {
  const match = response.match(/^\s*([A-Z][A-Za-z0-9 _'-]{0,40}):/);
  return match?.[1]?.trim() || 'Omnix';
}

export function quickActionsFromHermesSuggestions(
  suggestions: HermesRpgSuggestion[],
): RpgQuickActionPreview[] {
  const icons: Record<string, string> = {
    combat: '⚔',
    dialogue: '☯',
    inventory: '▣',
    journal: '◇',
    objective: '◆',
    progression: '✦',
    travel: '⌖',
  };
  return suggestions.flatMap((suggestion) => {
    const command = suggestion.command?.trim();
    if (!command) return [];
    return [{
      command,
      icon: icons[suggestion.kind ?? ''] ?? '◇',
      label: suggestion.label?.trim() || command,
    }];
  }).slice(0, 6);
}

export function isRpgTurnJobType(type: string): boolean {
  return type === 'rpg.turn' || type === 'rpg.turn.foreground_record';
}

function submittedTurnInteractionId(job: JobRecord): string | undefined {
  for (const output of job.output_refs ?? []) {
    const record = recordValue(output);
    const turnResponse = recordValue(record.turn_response);
    const interactionId = firstString(turnResponse.interaction_id, record.interaction_id);
    if (interactionId) return interactionId;
  }
  return undefined;
}

export function buildSubmittedTurnStoryMessages(
  job: JobRecord | undefined,
  heroName: string,
  heroAvatar: string,
  selectedSessionId: string | null,
): RpgStoryMessagePreview[] {
  if (!job || !isRpgTurnJobType(job.type)) return [];
  // Foreground-record jobs mirror the same structured response already owned
  // by the turn UI store and durable session. Rendering their combined content
  // creates a transient second response and can surface stale fallback prose.
  if (job.type === 'rpg.turn.foreground_record') return [];
  const jobSessionId = submittedTurnSessionId(job);
  if (selectedSessionId && jobSessionId && jobSessionId !== selectedSessionId) return [];

  const messages: RpgStoryMessagePreview[] = [];
  const interactionId = submittedTurnInteractionId(job);
  const command = submittedTurnCommand(job);
  if (command) {
    messages.push({
      id: interactionId ? `${interactionId}:player` : undefined,
      interactionId,
      avatar: heroAvatar,
      speaker: `${heroName} (You)`,
      text: command,
      tone: 'player',
    });
  }

  const response = submittedTurnResponseContent(job);
  if (response) {
    const speaker = inferSubmittedResponseSpeaker(response);
    messages.push({
      id: interactionId ? `${interactionId}:submitted-response` : undefined,
      interactionId,
      avatar: speaker === 'Omnix' ? 'O' : speaker.charAt(0).toUpperCase(),
      speaker: speaker === 'Omnix' ? 'Omnix (Narrator)' : speaker,
      text: response,
      tone: speaker === 'Omnix' ? 'narrator' : 'npc',
    });
  }
  return messages;
}
