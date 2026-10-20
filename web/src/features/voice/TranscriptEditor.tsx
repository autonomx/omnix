import { Button, Text } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState, type KeyboardEvent, type MouseEvent } from 'react';
import { downloadBlob } from '../../shared/download';
import { voiceApiClient, type TranscriptExportFormat } from './api/voiceClient';
import type { CloneSeed } from './CloneVoicePanel';
import {
  activeWord,
  asTranscriptDocument,
  editSegmentText,
  formatClock,
  isLowConfidence,
  mergeWithNext,
  renameSpeaker,
  setSegmentSpeaker,
  splitSegment,
  type TranscriptDocument,
} from './transcriptDocument';
import { PeaksCanvas } from './TransportBar';

const EXPORT_FORMATS: TranscriptExportFormat[] = ['srt', 'vtt', 'txt', 'json'];

function base64File(base64: string, name: string, type: string): File {
  const bytes = Uint8Array.from(atob(base64), (char) => char.charCodeAt(0));
  return new File([bytes], name, { type });
}

/** Speakers: rename in place, or cut one's cleanest speech into a clone sample. */
function SpeakerBar({ speakers, busySpeaker, dirty, onRename, onMakeVoice }: {
  speakers: string[];
  busySpeaker: string;
  dirty: boolean;
  onRename: (from: string, to: string) => void;
  onMakeVoice: (speaker: string) => void;
}) {
  const [renaming, setRenaming] = useState<Record<string, string>>({});
  return (
    <div className="voice-transcript-speakers" aria-label="Speakers">
      {speakers.map((speaker) => (
        <div key={speaker} className="voice-transcript-speaker">
          <input
            aria-label={`Rename ${speaker}`}
            value={renaming[speaker] ?? speaker}
            onChange={(event) => { const value = event.currentTarget.value; setRenaming((current) => ({ ...current, [speaker]: value })); }}
            onBlur={() => {
              const next = renaming[speaker];
              setRenaming((current) => { const copy = { ...current }; delete copy[speaker]; return copy; });
              if (next !== undefined) onRename(speaker, next);
            }}
            onKeyDown={(event) => { if (event.key === 'Enter') event.currentTarget.blur(); }}
          />
          <Button size="xs" variant="subtle" aria-label={`Make a voice from ${speaker}`} loading={busySpeaker === speaker} disabled={dirty} title={dirty ? 'Save first: the sample is cut from the saved transcript.' : `Cut ${speaker}'s cleanest 10–30 seconds into a clone sample.`} onClick={() => onMakeVoice(speaker)}>Make a voice</Button>
        </div>
      ))}
    </div>
  );
}

/**
 * The editable transcript: the source recording's waveform, segments whose words
 * seek playback, speaker renames, split and merge, and exports.
 */
export function TranscriptEditor({ assetId, onMakeVoice }: { assetId: string; onMakeVoice: (seed: CloneSeed) => void }) {
  const queryClient = useQueryClient();
  const audio = useRef<HTMLAudioElement | null>(null);
  const [draft, setDraft] = useState<TranscriptDocument | null>(null);
  const [revision, setRevision] = useState(0);
  const [time, setTime] = useState(0);
  const [splitting, setSplitting] = useState<number | null>(null);
  const [editing, setEditing] = useState<{ index: number; text: string } | null>(null);
  const [notice, setNotice] = useState('');

  const transcript = useQuery({ queryKey: ['voice', 'transcript', assetId], queryFn: () => voiceApiClient.getTranscript(assetId) });
  useEffect(() => {
    if (!transcript.data) return;
    setDraft(asTranscriptDocument(transcript.data.document));
    setRevision(transcript.data.revision);
    setSplitting(null);
    setEditing(null);
  }, [transcript.data]);
  const saved = transcript.data ? asTranscriptDocument(transcript.data.document) : null;
  const dirty = Boolean(draft && saved && JSON.stringify(draft) !== JSON.stringify(saved));
  const sourceId = draft?.source_asset_id ?? '';
  const peaks = useQuery({
    queryKey: ['voice', 'take-peaks', sourceId],
    queryFn: () => voiceApiClient.getTakePeaks(sourceId, 720),
    enabled: Boolean(sourceId),
    staleTime: Infinity,
    retry: false,
  });

  const save = useMutation({
    mutationFn: () => voiceApiClient.saveTranscript(assetId, draft as unknown as Record<string, unknown>, revision),
    onSuccess: async (result) => {
      queryClient.setQueryData(['voice', 'transcript', assetId], result);
      await queryClient.invalidateQueries({ queryKey: ['platform', 'assets'] });
      setNotice('Transcript saved.');
    },
  });
  const exportFile = useMutation({
    mutationFn: (format: TranscriptExportFormat) => voiceApiClient.exportTranscript(assetId, format),
    onSuccess: ({ blob, filename }) => downloadBlob(blob, filename),
  });
  const makeVoice = useMutation({
    mutationFn: (speaker: string) => voiceApiClient.speakerSample(assetId, speaker),
    onSuccess: (sample) => onMakeVoice({
      key: `${assetId}:${sample.speaker}:${Date.now()}`,
      file: base64File(sample.audio_base64, `${sample.speaker}-sample.wav`, sample.mime_type),
      text: sample.text,
      name: sample.speaker,
    }),
  });

  if (transcript.isLoading) return <Text size="sm">Loading transcript…</Text>;
  if (transcript.isError || !draft) return <Text size="sm" role="alert">The transcript could not be opened.</Text>;
  const duration = draft.duration || peaks.data?.duration || 0;
  const active = activeWord(draft, time);

  function seek(seconds: number) {
    if (!audio.current) return;
    audio.current.currentTime = seconds;
    setTime(seconds);
    void audio.current.play().catch(() => undefined);
  }
  function waveformTime(event: MouseEvent<HTMLCanvasElement>): number {
    const bounds = event.currentTarget.getBoundingClientRect();
    return bounds.width ? Math.min(1, Math.max(0, (event.clientX - bounds.left) / bounds.width)) * duration : 0;
  }
  function waveformKey(event: KeyboardEvent<HTMLCanvasElement>) {
    if (event.key === 'ArrowLeft') seek(Math.max(0, time - 2));
    if (event.key === 'ArrowRight') seek(Math.min(duration, time + 2));
  }
  function update(next: TranscriptDocument) {
    setDraft(next);
    setNotice('');
  }
  const saveError = save.error instanceof Error && /409|conflict/i.test(save.error.message)
    ? 'Someone saved this transcript meanwhile; reload it before saving.'
    : save.isError ? 'The transcript could not be saved.' : '';

  return (
    <section className="voice-transcript" aria-label="Transcript editor">
      <div className="voice-section-head">
        <div>
          <h3>{transcript.data?.title}</h3>
          <Text size="sm">{formatClock(duration)} · {draft.language === 'auto' ? 'language not set' : draft.language} · {draft.engine || 'engine unknown'} · revision {revision}</Text>
        </div>
        <div className="script-actions">
          <Button size="xs" loading={save.isPending} disabled={!dirty} onClick={() => save.mutate()}>{dirty ? 'Save changes' : 'Saved'}</Button>
          <Button size="xs" variant="subtle" disabled={!dirty} onClick={() => saved && setDraft(saved)}>Discard</Button>
          {EXPORT_FORMATS.map((format) => (
            <Button key={format} size="xs" variant="subtle" disabled={dirty} title={dirty ? 'Save first: exports are built from the saved transcript.' : `Download as ${format.toUpperCase()}`} loading={exportFile.isPending && exportFile.variables === format} onClick={() => exportFile.mutate(format)}>{format.toUpperCase()}</Button>
          ))}
        </div>
      </div>
      {saveError ? <Text size="sm" role="alert">{saveError}</Text> : null}
      {exportFile.isError ? <Text size="sm" role="alert">{exportFile.error instanceof Error ? exportFile.error.message : 'The export failed.'}</Text> : null}
      {notice ? <div className="voice-success-note" role="status">{notice}</div> : null}

      <div className="voice-transcript-player">
        <audio ref={audio} controls preload="metadata" src={sourceId ? `/api/assets/${encodeURIComponent(sourceId)}/audio` : undefined} aria-label="Source recording" onTimeUpdate={(event) => setTime(event.currentTarget.currentTime)} />
        <PeaksCanvas peaks={peaks.data?.peaks ?? null} progress={duration ? time / duration : 0} loop={null} onClick={(event) => seek(waveformTime(event))} onShiftDrag={() => undefined} toTime={waveformTime} onKeyDown={waveformKey} />
      </div>

      <SpeakerBar
        speakers={draft.speakers}
        busySpeaker={makeVoice.isPending ? makeVoice.variables ?? '' : ''}
        dirty={dirty}
        onRename={(from, to) => update(renameSpeaker(draft, from, to))}
        onMakeVoice={(speaker) => makeVoice.mutate(speaker)}
      />
      {makeVoice.isError ? <Text size="sm" role="alert">{makeVoice.error instanceof Error && /too_short|422/.test(makeVoice.error.message) ? 'That speaker has less than 10 seconds of clean speech.' : 'The sample could not be cut.'}</Text> : null}

      <ol className="voice-transcript-segments">
        {draft.segments.map((segment, index) => (
          <li key={`${index}-${segment.start}`} className={active.segment === index ? 'voice-transcript-segment active' : 'voice-transcript-segment'}>
            <div className="voice-transcript-meta">
              <button type="button" className="voice-transcript-time" aria-label={`Play from ${formatClock(segment.start)}`} onClick={() => seek(segment.start)}>{formatClock(segment.start)}</button>
              <select aria-label={`Segment ${index + 1} speaker`} value={segment.speaker} onChange={(event) => update(setSegmentSpeaker(draft, index, event.currentTarget.value))}>
                {draft.speakers.map((speaker) => <option key={speaker} value={speaker}>{speaker}</option>)}
              </select>
            </div>
            {editing?.index === index ? (
              <div className="voice-transcript-edit">
                <textarea aria-label={`Segment ${index + 1} text`} rows={2} value={editing.text} onChange={(event) => setEditing({ index, text: event.currentTarget.value })} />
                <Button size="xs" onClick={() => { update(editSegmentText(draft, index, editing.text)); setEditing(null); }}>Apply</Button>
                <Button size="xs" variant="subtle" onClick={() => setEditing(null)}>Cancel</Button>
              </div>
            ) : (
              <p className="voice-transcript-words">
                {segment.words.length ? segment.words.map((word, wordIndex) => {
                  const classes = ['voice-transcript-word', isLowConfidence(word) ? 'low' : '', active.segment === index && active.word === wordIndex ? 'active' : ''].filter(Boolean).join(' ');
                  const splitHere = splitting === index && wordIndex > 0;
                  return (
                    <button
                      key={wordIndex}
                      type="button"
                      className={classes}
                      title={splitHere ? 'Start a new segment here' : isLowConfidence(word) ? `Low confidence (${Math.round((word.confidence ?? 0) * 100)}%)` : formatClock(word.start)}
                      onClick={() => {
                        if (splitHere) { update(splitSegment(draft, index, wordIndex)); setSplitting(null); } else seek(word.start);
                      }}
                    >{word.word}</button>
                  );
                }) : <span>{segment.text}</span>}
              </p>
            )}
            <div className="voice-transcript-actions">
              <Button size="xs" variant="subtle" aria-label={`Edit segment ${index + 1} text`} onClick={() => setEditing({ index, text: segment.text })}>Edit text</Button>
              <Button size="xs" variant="subtle" aria-label={`Split segment ${index + 1}`} aria-pressed={splitting === index} disabled={segment.words.length < 2} onClick={() => setSplitting(splitting === index ? null : index)}>{splitting === index ? 'Pick a word…' : 'Split'}</Button>
              <Button size="xs" variant="subtle" aria-label={`Merge segment ${index + 1} with the next`} disabled={index + 1 >= draft.segments.length} onClick={() => update(mergeWithNext(draft, index))}>Merge with next</Button>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
