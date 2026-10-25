/** A turn's response as the play screen reads it, and the story entries it becomes. */
import type { components } from './api/generated';
import type { RpgStoryMessagePreview } from './rpgUiTypes';

export type RpgTurnUiStatus = 'optimistic' | 'pending' | 'complete' | 'failed';

export interface RpgTurnUiEntry extends RpgStoryMessagePreview {
  id: string;
  sessionId: string;
  submissionId: string;
  interactionId?: string;
  status: RpgTurnUiStatus;
  messageKind?: string;
  messageIndex?: number;
}

export interface RpgVisibleMessageV2 {
  kind?: string;
  speaker_id?: string;
  speaker?: string;
  text?: string;
}

export interface RpgVisibleResponseV2 {
  narration?: string;
  messages?: RpgVisibleMessageV2[];
  plain_text?: string;
}

export interface RpgTurnResponseV2 {
  ok?: boolean;
  contract_version?: string;
  session_id?: string;
  submission_id?: string;
  interaction_id?: string;
  turn_id?: string;
  trace_id?: string;
  visible_response?: RpgVisibleResponseV2;
  response?: string;
  content?: string;
  state?: {
    changed?: boolean;
    changed_domains?: string[];
  };
  timing?: Record<string, number>;
  performance?: Record<string, unknown>;
  /** The turn's one result (RQ-1.3): its changes, narration, timings and model calls. */
  outcome?: RpgTurnOutcome | null;
  /** What the player is told beside the turn: the storyteller unavailable (RQ-8.8). */
  notices?: { kind?: string; message?: string }[];
  /** A turn followed on its stream returns at its commit: its narration comes on `stream_path` (RQ-6.2). */
  narration?: { status?: string; stream_path?: string };
}

/** What the turn's narration says, as the stream's `narration.final` or the turn's response gives it. */
export function rpgNarrationEntries(
  sessionId: string,
  submissionId: string,
  interactionId: string,
  visible: RpgVisibleResponseV2,
): RpgTurnUiEntry[] {
  return rpgTurnEntriesFromPayload(sessionId, submissionId, interactionId, { visible_response: visible });
}

export type RpgTurnOutcome = components['schemas']['TurnOutcome'];

/** What a turn changed: the sections its outcome names, with the transitional changed domains. */
export function rpgTurnChangedDomains(payload: Pick<RpgTurnResponseV2, 'state' | 'outcome'>): string[] {
  const sections = payload.outcome?.presentation?.changed_sections ?? [];
  return [...new Set([...(payload.state?.changed_domains ?? []), ...sections])];
}

/** What the play screen shows of a turn: its narration, its people's lines (else the plain response), the
 * outcome card (RQ-7.2) and any notice (RQ-8.8). */
export function rpgTurnEntriesFromPayload(
  sessionId: string,
  submissionId: string,
  interactionId: string,
  payload: RpgTurnResponseV2,
): RpgTurnUiEntry[] {
  const visible = payload.visible_response || {};
  const entries: RpgTurnUiEntry[] = [];
  const narration = visible.narration?.trim();
  if (narration) {
    entries.push({
      id: `${interactionId}:narration`,
      sessionId,
      submissionId,
      interactionId,
      status: 'complete',
      avatar: 'O',
      speaker: 'Omnix (Narrator)',
      text: narration,
      tone: 'narrator',
      messageKind: 'narration',
      messageIndex: 0,
    });
  }
  for (const [index, message] of (visible.messages || []).entries()) {
    const text = message.text?.trim();
    if (!text) continue;
    const speaker = message.speaker?.trim() || 'NPC';
    entries.push({
      id: `${interactionId}:message:${index}`,
      sessionId,
      submissionId,
      interactionId,
      status: 'complete',
      avatar: speaker.charAt(0).toUpperCase() || 'N',
      speaker,
      text,
      tone: message.kind === 'narration' ? 'narrator' : 'npc',
      messageKind: message.kind || 'npc_dialogue',
      messageIndex: index,
    });
  }
  if (!entries.length) {
    const fallback = visible.plain_text?.trim() || payload.response?.trim() || payload.content?.trim();
    if (fallback) {
      entries.push({
        id: `${interactionId}:response`,
        sessionId,
        submissionId,
        interactionId,
        status: 'complete',
        avatar: 'O',
        speaker: 'Omnix',
        text: fallback,
        tone: 'narrator',
        messageKind: 'response',
        messageIndex: 0,
      });
    }
  }
  if (payload.narration?.status === 'pending' && !entries.length) {
    // The storyteller is still writing: the stream fills this in (RQ-6.2).
    entries.push({
      id: `${interactionId}:narration`, sessionId, submissionId, interactionId, status: 'pending', avatar: 'O',
      speaker: 'Omnix (Narrator)', text: 'The storyteller is writing…', tone: 'narrator', messageKind: 'narration',
      messageIndex: 0,
    });
  }
  const facts = payload.outcome?.presentation?.facts ?? [];
  if (facts.length) {
    // The outcome card (RQ-7.2): what the turn changed, as the game states it.
    entries.push({
      id: `${interactionId}:outcome`, sessionId, submissionId, interactionId, status: 'complete',
      avatar: '✦', speaker: 'What changed', text: facts.map((fact) => fact.text).join(' · '), tone: 'narrator',
      messageKind: 'outcome', facts: facts.map((fact) => ({ kind: fact.kind, text: fact.text, tone: fact.tone })),
    });
  }
  for (const [index, notice] of (payload.notices || []).entries()) {
    const text = notice.message?.trim();
    if (!text) continue;
    entries.push({
      id: `${interactionId}:notice:${index}`,
      sessionId,
      submissionId,
      interactionId,
      status: 'complete',
      avatar: 'O',
      speaker: 'Omnix',
      text,
      tone: 'narrator',
      messageKind: notice.kind || 'notice',
      messageIndex: index,
    });
  }
  return entries;
}
