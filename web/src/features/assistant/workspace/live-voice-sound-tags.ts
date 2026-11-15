import type { LiveVoiceCueId } from './live-voice-cue-bank';

// A live reply may hold [hmm], [chuckle] or [sigh] (server: app/conversation/sound_tags.py). The voice's recorded
// clip plays for the tag; the tag itself is never spoken. While a reply streams, a complete tag is held as one
// private-use character so it neither counts toward a clause's length nor splits one.
export type LiveVoiceSoundTag = 'hmm' | 'chuckle' | 'sigh';

export const SOUND_TAG_CUES: Readonly<Record<LiveVoiceSoundTag, LiveVoiceCueId>> = {
  hmm: 'hmm',
  chuckle: 'amused_exhale',
  sigh: 'sigh',
};

const MARKS: Readonly<Record<LiveVoiceSoundTag, string>> = {
  hmm: '',
  chuckle: '',
  sigh: '',
};
const MARK_CUES = new Map<string, LiveVoiceCueId>(
  (Object.keys(MARKS) as LiveVoiceSoundTag[]).map((tag) => [MARKS[tag], SOUND_TAG_CUES[tag]]),
);
const MARK_PATTERN = /[-]/gu;
const BRACKET_GROUP = /\[([^[\]\n]{0,80})\]/gu;
const STRAY_BRACKET = /[[\]]/gu;
const WORD = /[\p{L}\p{N}]/u;

export function soundTagName(inner: string): LiveVoiceSoundTag | null {
  const word = inner.trim();
  if (/^h+m+$/iu.test(word)) return 'hmm';
  if (/^(?:chuckle|laugh|giggle)s?$/iu.test(word)) return 'chuckle';
  if (/^sighs?$/iu.test(word)) return 'sigh';
  return null;
}

/** Replace each complete known tag with its mark; other bracketed text stays for the sanitizer to remove. */
export function markSoundTags(text: string): string {
  if (!text.includes('[')) return text;
  return text.replace(BRACKET_GROUP, (match, inner: string) => {
    const tag = soundTagName(inner);
    return tag ? MARKS[tag] : match;
  });
}

/**
 * The clause's cue and where it plays: `leading` when no words come before the first mark (the sound opens the
 * clause), otherwise it belongs after the clause's words. The returned text has every mark removed.
 */
export function takeSoundMarks(text: string): { text: string; cue: LiveVoiceCueId | null; leading: boolean } {
  MARK_PATTERN.lastIndex = 0;
  const match = MARK_PATTERN.exec(text);
  MARK_PATTERN.lastIndex = 0;
  if (!match) return { text, cue: null, leading: false };
  return {
    text: text.replace(MARK_PATTERN, ' '),
    cue: MARK_CUES.get(match[0]) ?? null,
    leading: !WORD.test(text.slice(0, match.index)),
  };
}

/** Remove marks, bracketed text and stray brackets: none of it is ever read aloud. */
export function removeBracketedText(text: string): string {
  if (!text.includes('[') && !text.includes(']') && !/[-]/u.test(text)) return text;
  return text.replace(MARK_PATTERN, ' ').replace(BRACKET_GROUP, ' ').replace(STRAY_BRACKET, ' ');
}

/** A reply's raw text without its tags, for anything that reads what the character said. */
export function stripSoundTags(text: string): string {
  const cleaned = removeBracketedText(markSoundTags(text));
  if (cleaned === text) return text;
  return cleaned.replace(/\s+/gu, ' ').replace(/\s+([,.;:!?])/gu, '$1').trim();
}
