import { previewJournalDetail, previewJournalEntries, previewRecentEvents, previewSessionSummary } from './rpgUiPreview';
import { compactTimestamp, firstArray, firstNumber, firstRecord, firstString, getSessionRecords, recordValue, speakerLabel } from './rpgUiRecords';
import type { RpgHeroSummaryPreview, RpgJob, RpgJournalDetailPreview, RpgJournalEntryPreview, RpgSession, RpgSessionSummaryPreview, RpgStoryMessagePreview } from './rpgUiTypes';

interface TimelineEvent {
  time: string;
  title: string;
  detail: string;
  actor?: string;
  kind?: string;
}

const EMPTY_VISIBLE_RESPONSE_TEXT = new Set(['', '[]', '{}', '[ ]', '{ }', 'null', 'none', 'false', 'true']);

export function buildRecentEvents(selectedSession: RpgSessionSummaryPreview, timeline: TimelineEvent[]): string[] {
  if (selectedSession.source === 'preview') return previewRecentEvents;
  if (timeline.length) return timeline.slice(0, 4).map((event) => formatTimelineEvent(event));
  return [`Loaded ${selectedSession.title}.`, `Current location: ${selectedSession.location}.`, `${selectedSession.turnLabel} • ${selectedSession.updatedAt}.`];
}

export function buildJournalEntries(selectedSession: RpgSessionSummaryPreview, session: RpgSession | undefined): RpgJournalEntryPreview[] {
  if (selectedSession.source === 'preview') return previewJournalEntries;
  const roots = getSessionRecords(session);
  const journal = firstRecord(
    ...roots.flatMap((root) => [root.player_journal, recordValue(root.runtime_state)?.player_journal]),
  );
  const seenDays = new Set<string>();
  const entries = firstArray(journal?.entries)
    .map((value) => recordValue(value))
    .filter((value): value is Record<string, unknown> => Boolean(value))
    .map((entry, index) => {
      const time = recordValue(entry.time);
      const voice = recordValue(entry.voice);
      const day = firstNumber(entry.day, time?.absolute_day) ?? index + 1;
      const dayLabel = firstString(entry.day_label) ?? `Day ${day}`;
      const timeLabel = firstString(time?.time_label);
      const voiceLabel = firstString(voice?.label);
      return {
        time: [dayLabel, timeLabel].filter(Boolean).join(' • '),
        title: firstString(entry.title) ?? (voiceLabel ? `${voiceLabel}'s journal` : 'My journal'),
        detail: firstString(entry.text, entry.summary, entry.detail) ?? 'No account has been written for this day yet.',
      };
    })
    .reverse()
    .filter((entry) => {
      const dayKey = entry.time.split(' • ')[0];
      if (seenDays.has(dayKey)) return false;
      seenDays.add(dayKey);
      return true;
    });
  if (entries.length) return entries;
  return [
    { time: 'Day 1', title: 'My journal', detail: 'The first daily account will be written after the next turn.' },
  ];
}

export function buildJournalDetail(selectedSession: RpgSessionSummaryPreview, entries: RpgJournalEntryPreview[]): RpgJournalDetailPreview {
  if (selectedSession.source === 'preview') return previewJournalDetail;
  const latest = entries[0];
  const bullets = [`Where: ${selectedSession.location}`, selectedSession.turnLabel];
  return latest
    ? { title: latest.title, detail: latest.detail, bullets: [`When: ${latest.time}`, ...bullets], tags: [] }
    : { title: 'My journal', detail: selectedSession.summary, bullets, tags: [] };
}

export function buildTimelineEvents(session: RpgSession | undefined): TimelineEvent[] {
  const roots = getSessionRecords(session);
  if (!roots.length) return [];
  const items = firstArray(
    ...roots.flatMap((root) => [root.timeline, root.recent_events, root.events, root.event_log, root.turn_history, root.turns, root.history, root.dialogue_log, root.dialogue, root.logs, recordValue(root.journal)?.entries])
  );
  return items
    .map(toTimelineEvent)
    .filter((event): event is TimelineEvent => Boolean(event))
    .slice(0, 8);
}

function toTimelineEvent(item: unknown, index: number): TimelineEvent | undefined {
  if (typeof item === 'string' && item.trim()) return { time: `Event ${index + 1}`, title: item.trim(), detail: item.trim(), kind: 'event' };
  const record = recordValue(item);
  if (!record) return undefined;
  const actor = firstString(record.actor, record.speaker, record.character, record.npc, record.source);
  const command = firstString(record.command, record.action, record.player_action, record.playerAction, record.input);
  const narration = firstString(record.narration, record.response, record.output, record.summary, record.result, record.text, record.message, record.description);
  const detail = narration ?? command ?? firstString(record.detail, record.title, record.label, record.event) ?? 'RPG event indexed from live session.';
  const title = firstString(record.title, record.label, record.event, record.kind, record.type) ?? (command ? 'Player command' : actor ? `${actor} speaks` : `Session event ${index + 1}`);
  const time = firstString(record.time, record.timestamp, record.created_at, record.updated_at, record.turn_label) ?? turnLabelFor(record, index);
  const kind = firstString(record.kind, record.type, record.category, command ? 'command' : undefined);
  return { time: compactTimestamp(time) ?? time, title, detail, actor, kind };
}

function formatTimelineEvent(event: TimelineEvent): string {
  return event.actor && !event.detail.startsWith(`${event.actor}:`) ? `${event.actor}: ${event.detail}` : event.detail;
}

function turnLabelFor(record: Record<string, unknown>, index: number): string {
  const turn = firstNumber(record.turn, record.turn_count, record.index, record.sequence);
  return turn !== undefined ? `Turn ${turn}` : `Event ${index + 1}`;
}

export function buildRpgTurnJobTimelineEvents(jobs: RpgJob[], sessionId: string, playerName: string): TimelineEvent[] {
  if (!sessionId || sessionId === previewSessionSummary.id) return [];
  return jobs
    .filter((job) => {
      const inputRef = recordValue(job.input_ref);
      return (job.type === 'rpg.turn' || job.type === 'rpg.turn.foreground_record')
        && firstString(inputRef?.session_id) === sessionId;
    })
    .flatMap((job) => {
      const inputPayload = recordValue(job.input_payload);
      const command = firstString(inputPayload?.command)?.trim();
      const output = firstArray(job.output_refs)
        .map(recordValue)
        .find((candidate) => candidate && firstString(candidate.type, candidate.kind) === 'rpg_turn_response');
      const response = cleanRpgTurnResponse(rpgTurnOutputText(output));
      const events: TimelineEvent[] = [];
      if (command) {
        events.push({
          actor: playerName,
          detail: command,
          kind: 'player_message',
          time: compactTimestamp(firstString(job.created_at)) ?? 'Queued turn',
          title: 'Player message',
        });
      }
      if (response) {
        const speaker = inferResponseSpeaker(response);
        events.push({
          actor: speaker,
          detail: response,
          kind: speaker === 'Omnix' ? 'narrator_message' : 'npc_message',
          time: compactTimestamp(firstString(job.completed_at, job.updated_at)) ?? 'Completed turn',
          title: speaker === 'Omnix' ? 'Narrator message' : `${speaker} response`,
        });
      }
      return events;
    });
}

/**
 * The reply text of an `rpg_turn_response` job output: the gateway's foreground
 * record carries the turn response (`turn_response`); older outputs carry the text.
 */
export function rpgTurnOutputText(output: Record<string, unknown> | undefined): string | undefined {
  const turn = recordValue(output?.turn_response);
  return firstString(output?.content, output?.text, turn?.response, turn?.content, recordValue(turn?.visible_response)?.plain_text);
}

function cleanRpgTurnResponse(response: string | undefined): string | undefined {
  if (!response) return undefined;
  const paragraphs = response.split(/\n\s*\n/).map((paragraph) => paragraph.trim()).filter(Boolean);
  const narrativeParagraphs = paragraphs.filter((paragraph) => !/^(?:Action|Result):\s*/i.test(paragraph));
  const visibleParagraphs = narrativeParagraphs.length ? narrativeParagraphs : paragraphs;
  const text = visibleParagraphs
    .map((paragraph) => paragraph.replace(/,['’](?=\s)/g, ',"').replace(/(\s)['’](?=[A-Z])/g, '$1"'))
    .join('\n\n');
  return text && !EMPTY_VISIBLE_RESPONSE_TEXT.has(text.toLowerCase()) ? text : undefined;
}

export function buildStoryMessages(events: TimelineEvent[], hero: RpgHeroSummaryPreview): RpgStoryMessagePreview[] {
  const turns: TimelineEvent[][] = [];
  for (const event of events) {
    if (event.kind === 'player_message' || !turns.length) {
      turns.push([event]);
    } else {
      turns[turns.length - 1].push(event);
    }
  }

  return turns.slice(0, 3).reverse().flat().map((event) => {
    if (event.kind === 'player_message') {
      return { avatar: hero.avatar, speaker: `${hero.name} (You)`, text: event.detail, tone: 'player' };
    }
    const speaker = event.actor ?? 'Omnix';
    const isNarrator = speaker === 'Omnix';
    return {
      avatar: speaker.charAt(0).toUpperCase() || 'O',
      speaker: isNarrator ? 'Omnix (Narrator)' : speaker,
      text: event.detail,
      tone: isNarrator ? 'narrator' : 'npc',
    };
  });
}

export function buildInteractionStoryMessages(
  session: RpgSession | undefined,
  hero: RpgHeroSummaryPreview,
): RpgStoryMessagePreview[] {
  const runtime = recordValue(session?.runtime_state);
  const interactions = firstArray(runtime?.recent_interactions);
  if (!interactions.length) return [];
  return interactions.slice(-12).flatMap((item) => {
    const event = recordValue(item);
    if (!event) return [];
    const interactionId = firstString(event.interaction_id);
    const playerInput = firstString(event.player_input);
    const visible = recordValue(event.visible_response);
    const narration = firstString(visible?.narration, event.narration);
    const visibleMessages = firstArray(visible?.messages).map(recordValue).filter(Boolean) as Record<string, unknown>[];
    const result: RpgStoryMessagePreview[] = [];
    if (playerInput) {
      result.push({
        id: interactionId ? `${interactionId}:player` : undefined,
        interactionId,
        messageKind: 'player',
        messageIndex: 0,
        avatar: hero.avatar,
        speaker: `${hero.name} (You)`,
        text: playerInput,
        tone: 'player',
      });
    }
    if (narration) {
      result.push({
        id: interactionId ? `${interactionId}:narration` : undefined,
        interactionId,
        messageKind: 'narration',
        messageIndex: 0,
        avatar: 'O',
        speaker: 'Omnix (Narrator)',
        text: narration,
        tone: 'narrator',
      });
    }
    visibleMessages.forEach((message, index) => {
      const text = firstString(message.text);
      if (!text) return;
      const speaker = speakerLabel(firstString(message.speaker, event.speaker) ?? 'Omnix');
      result.push({
        id: interactionId ? `${interactionId}:message:${index}` : undefined,
        interactionId,
        messageKind: firstString(message.kind) ?? 'npc_dialogue',
        messageIndex: index,
        avatar: speaker.charAt(0).toUpperCase() || 'O',
        speaker: speaker === 'Omnix' ? 'Omnix (Narrator)' : speaker,
        text,
        tone: speaker === 'Omnix' ? 'narrator' : 'npc',
      });
    });
    return result;
  }).slice(-40);
}

function inferResponseSpeaker(response: string): string {
  const match = response.match(/^([A-Z][A-Za-z'’-]*(?:\s+[A-Z][A-Za-z'’-]*){0,2})\s+(?=[a-z])/);
  const candidate = match?.[1];
  if (!candidate || /^(?:A|An|He|Her|His|I|It|Its|She|The|Their|They|This|We|You|Your)$/i.test(candidate)) {
    return 'Omnix';
  }
  return candidate;
}
