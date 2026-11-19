import { beforeEach, describe, expect, it, vi } from 'vitest';
import { liveVoiceTranscriptStore } from './live-voice-transcript-store';

describe('live voice transcript store', () => {
  beforeEach(() => liveVoiceTranscriptStore.resetForTests());

  it('grows the speaker draft and settles it on the final', () => {
    liveVoiceTranscriptStore.write('You', 'where are', 'draft');
    liveVoiceTranscriptStore.write('You', 'where are we going', 'draft');
    expect(liveVoiceTranscriptStore.draftText()).toBe('where are we going');

    liveVoiceTranscriptStore.write('You', 'Where are we going?', 'final');

    expect(liveVoiceTranscriptStore.getState().rows).toEqual([
      expect.objectContaining({ speaker: 'You', text: 'Where are we going?', draft: false }),
    ]);
    expect(liveVoiceTranscriptStore.draftText()).toBe('');
  });

  it('settles the speaker draft as a held row for words in another voice, which a sent message leaves in place', () => {
    liveVoiceTranscriptStore.write('You', 'and the score', 'draft');
    const heldId = liveVoiceTranscriptStore.writeHeld('And the score is two nil.');
    liveVoiceTranscriptStore.write('You', 'What did I miss?', 'final');

    expect(liveVoiceTranscriptStore.removeFinalUserRows()).toBe(1);
    expect(liveVoiceTranscriptStore.getState().rows).toEqual([
      expect.objectContaining({ id: heldId, text: 'And the score is two nil.', draft: false, held: 'pending' }),
    ]);

    liveVoiceTranscriptStore.expireHeld();
    expect(liveVoiceTranscriptStore.getState().rows[0]?.held).toBe('expired');
    expect(liveVoiceTranscriptStore.writeHeld('   ')).toBeNull();
  });

  it('turns a held row sent anyway into an ordinary one, which the sent message replaces', () => {
    const heldId = liveVoiceTranscriptStore.writeHeld('Remind me to call Sam.')!;

    liveVoiceTranscriptStore.releaseHeld(heldId);

    expect(liveVoiceTranscriptStore.getState().rows[0]).not.toHaveProperty('held');
    expect(liveVoiceTranscriptStore.removeFinalUserRows()).toBe(1);
  });

  it('gives another speaker its own row instead of writing into the draft', () => {
    liveVoiceTranscriptStore.write('You', 'hold on', 'draft');
    liveVoiceTranscriptStore.write('Omnix', 'Live voice paused.', 'final');

    expect(liveVoiceTranscriptStore.getState().rows.map((row) => [row.speaker, row.text, row.draft])).toEqual([
      ['You', 'hold on', false],
      ['Omnix', 'Live voice paused.', false],
    ]);
  });

  it('ignores empty words and keeps delivery when rows are cleared', () => {
    const listener = vi.fn();
    const unsubscribe = liveVoiceTranscriptStore.subscribe(listener);
    liveVoiceTranscriptStore.write('You', '   ', 'draft');
    expect(listener).not.toHaveBeenCalled();

    liveVoiceTranscriptStore.write('You', 'hello', 'final');
    liveVoiceTranscriptStore.setDelivery({ text: 'Hi there', partial: true });
    liveVoiceTranscriptStore.setDelivery({ text: 'Hi there', partial: true });
    liveVoiceTranscriptStore.clear();

    expect(liveVoiceTranscriptStore.getState()).toEqual({ rows: [], delivery: { text: 'Hi there', partial: true } });
    expect(listener).toHaveBeenCalledTimes(3);
    unsubscribe();
  });
});
