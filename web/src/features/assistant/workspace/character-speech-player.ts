import { livePortrait, type LivePortraitSpeaker } from '../chat/portrait/livePortrait';
import { createLiveCallDiagnosticsReporter, createLiveCallTraceId, type LiveCallDiagnosticsReporter } from './live-call-diagnostics-client';
import { createLiveVoicePcmSession, type LiveOutputOwnership, type LiveVoicePcmSession } from './live-voice-pcm-session';

/**
 * Lines spoken as characters outside a chat (a podcast's live avatars, D4): each line in its speaker's voice through
 * the live voice socket, with that character's portrait when its avatar is one. A speaker change opens a new audio
 * session (a session speaks in one voice, with one face), the way a group call's next speaker does.
 */
export type CharacterLine = {
  text: string;
  /** The TTS speaker id (a voice profile's clone id), or null for the default voice. */
  voiceId: string | null;
  /** The character whose face speaks the line; null speaks it without one. */
  speaker: LivePortraitSpeaker | null;
};

export type CharacterSpeechRun = {
  /** Settles once every line has been heard, or the run was stopped; rejects when a session could not open. */
  done: Promise<void>;
  stop: () => void;
  /** Holds the run once the line now playing ends (the live voice socket cannot pause a phrase mid-way). */
  pause: () => void;
  resume: () => void;
};

type OpenSession = { key: string; session: LiveVoicePcmSession; reporter: LiveCallDiagnosticsReporter; phrases: number };

const MAX_PHRASE_CHARS = 220;

/** A line in phrases the live socket synthesizes one at a time (sentences; long ones cut at a comma or a space). */
export function linePhrases(text: string): string[] {
  const sentences = text.replace(/\s+/g, ' ').trim().match(/[^.!?]+[.!?]+["')\]]*|[^.!?]+$/g) ?? [];
  const phrases: string[] = [];
  for (const raw of sentences) {
    let sentence = raw.trim();
    while (sentence.length > MAX_PHRASE_CHARS) {
      const window = sentence.slice(0, MAX_PHRASE_CHARS);
      const cut = Math.max(window.lastIndexOf(', '), window.lastIndexOf(' '));
      const at = cut > 40 ? cut + 1 : MAX_PHRASE_CHARS;
      phrases.push(sentence.slice(0, at).trim());
      sentence = sentence.slice(at).trim();
    }
    if (sentence) phrases.push(sentence);
  }
  return phrases;
}

/** Speak `lines` in order; `onLine` hears which line (and whose face) is about to play. */
export function speakAsCharacters(
  runKey: string,
  lines: readonly CharacterLine[],
  onLine: (index: number, line: CharacterLine) => void = () => undefined,
): CharacterSpeechRun {
  let stopped = false;
  let open: OpenSession | null = null;
  let order = 0;
  let held: { until: Promise<void>; release: () => void } | null = null;
  const release = () => {
    const hold = held;
    held = null;
    hold?.release();
  };

  const close = async (reason: string): Promise<void> => {
    const current = open;
    open = null;
    if (!current) return;
    livePortrait.end();
    if (!current.session.isClosed()) await current.session.stop(reason).catch(() => undefined);
    await current.reporter.close('character_speech_session_closed', { reason, run_key: runKey, phrase_count: current.phrases });
  };

  const sessionFor = async (line: CharacterLine): Promise<OpenSession> => {
    const portrait = Boolean(line.speaker && livePortrait.wantedForCharacter(line.speaker));
    const key = `${line.voiceId ?? ''}\n${line.speaker?.id ?? ''}\n${portrait}`;
    if (open && open.key === key && !open.session.isClosed() && !open.session.hasFailed()) return open;
    await close('character_speech_speaker_changed');
    const traceId = createLiveCallTraceId(`${runKey}:character-speech`);
    const reporter = createLiveCallDiagnosticsReporter(traceId);
    reporter.record('character_speech_session_created', {
      run_key: runKey, voice_id: line.voiceId, speaker_id: line.speaker?.id ?? null, portrait,
    }, 'controller');
    const hooks = portrait && line.speaker ? livePortrait.beginForCharacter(runKey, line.speaker) : undefined;
    let session: LiveVoicePcmSession;
    try {
      session = await createLiveVoicePcmSession(traceId, line.voiceId, reporter, {
        sessionScoped: true, affinityKey: runKey, portrait: hooks,
      });
    } catch (error) {
      if (hooks) livePortrait.end();
      await reporter.close('character_speech_session_failed', { error: error instanceof Error ? error.message : String(error) });
      throw error;
    }
    if (stopped) {
      if (hooks) livePortrait.end();
      await session.stop('character_speech_stopped').catch(() => undefined);
      await reporter.close('character_speech_session_closed', { reason: 'character_speech_stopped', run_key: runKey, phrase_count: 0 });
      throw new Error('stopped');
    }
    if (hooks) livePortrait.attachSession(session);
    open = { key, session, reporter, phrases: 0 };
    return open;
  };

  const run = async (): Promise<void> => {
    for (const [index, line] of lines.entries()) {
      while (held && !stopped) await held.until;
      if (stopped) return;
      const phrases = linePhrases(line.text);
      if (!phrases.length) continue;
      let current: OpenSession;
      try {
        current = await sessionFor(line);
      } catch (error) {
        if (stopped) return;
        throw error;
      }
      onLine(index, line);
      // Every phrase is its own output of the line's epoch, as a call's reply is; the last one ends the line.
      const epoch = index + 1;
      const owned: LiveOutputOwnership[] = [];
      const queued = phrases.map((phrase, phraseIndex) => {
        const ownership = { outputId: `line-${index}-${phraseIndex}`, generationEpoch: epoch, outputOrder: order++ };
        owned.push(ownership);
        return current.session.enqueueOutputPhrase(phrase, current.phrases++, ownership);
      });
      await Promise.all(queued);
      if (stopped) return;
      const last = owned[owned.length - 1];
      current.session.sendOutputEnd(last.outputId, last.generationEpoch);
      await Promise.all(owned.map((ownership) => current.session.waitForOutputItem(ownership.outputId, ownership.generationEpoch)));
    }
  };

  // A stop settles the session's pending phrases and waits: whatever they throw then is the stop, not a failure.
  const done = run()
    .catch((error: unknown) => { if (!stopped) throw error; })
    .finally(() => close(stopped ? 'character_speech_stopped' : 'character_speech_finished'));
  return {
    done,
    stop: () => {
      if (stopped) return;
      stopped = true;
      release();
      void close('character_speech_stopped');
    },
    pause: () => {
      if (held || stopped) return;
      let wake = () => undefined as void;
      const until = new Promise<void>((resolve) => { wake = resolve; });
      held = { until, release: wake };
    },
    resume: release,
  };
}
