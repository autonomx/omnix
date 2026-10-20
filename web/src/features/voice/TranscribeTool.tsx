import { Button, Text } from '@mantine/core';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { omnixApiClient, type AssetListResponse } from '../../api/client';
import type { CloneSeed } from './CloneVoicePanel';
import { TRANSCRIPT_LANGUAGES } from './transcriptLanguages';
import { TranscriptEditor } from './TranscriptEditor';
import { firstOutput, jobSettled, useJobResult } from './useJobResult';

type Asset = AssetListResponse['assets'][number];

// The recordings `stt.transcribe` accepts.
const SOURCE_TYPES = new Set(['audio', 'voice_sample', 'voice_profile', 'chapter_audio', 'render', 'export']);
const SPEAKER_CHOICES = ['auto', '1', '2', '3', '4', '5', '6', '7', '8'];

function assetTitle(asset: Asset): string {
  const title = asset.metadata?.title;
  return typeof title === 'string' && title.trim() ? title : asset.file_name || asset.id;
}

/** Transcribe: timed, speaker-labelled transcripts of stored recordings, edited and exported here. */
export function TranscribeTool({ assets, onMakeVoice }: { assets: Asset[]; onMakeVoice: (seed: CloneSeed) => void }) {
  const queryClient = useQueryClient();
  const sources = useMemo(() => assets.filter((asset) => SOURCE_TYPES.has(asset.type) && asset.mime_type.startsWith('audio/')), [assets]);
  const transcripts = useMemo(() => assets.filter((asset) => asset.type === 'transcript').sort((a, b) => b.created_at.localeCompare(a.created_at)), [assets]);
  const [sourceId, setSourceId] = useState('');
  const [speakers, setSpeakers] = useState('auto');
  const [language, setLanguage] = useState('');
  const [openId, setOpenId] = useState('');
  const [jobId, setJobId] = useState('');
  const job = useJobResult(jobId);

  const queue = useMutation({
    mutationFn: () => omnixApiClient.createJob({
      module: 'stt',
      type: 'stt.transcribe',
      resource_class: 'gpu:stt',
      priority: 0,
      input_ref: { asset_id: sourceId },
      input_payload: {
        asset_id: sourceId,
        timed: true,
        diarize: speakers !== '1',
        speakers: speakers === 'auto' || speakers === '1' ? 0 : Number(speakers),
        language,
        save_transcript: true,
      },
      stages: [
        { id: 'transcribe', label: 'Transcribe with word timing', resource_class: 'gpu:stt', status: 'queued' },
        { id: 'store-transcript', label: 'Store transcript asset', resource_class: 'cpu', status: 'queued' },
      ],
    }),
    onSuccess: (created) => setJobId(created.id),
  });

  // A finished transcription opens in the editor.
  const finishedTranscript = job.data?.status === 'completed' ? String(firstOutput(job.data)?.asset_id ?? '') : '';
  useEffect(() => {
    if (!finishedTranscript) return;
    void queryClient.invalidateQueries({ queryKey: ['platform', 'assets'] });
    setOpenId(finishedTranscript);
  }, [finishedTranscript, queryClient]);

  const running = Boolean(jobId) && !jobSettled(job.data);
  const failure = job.data?.status === 'failed' ? (typeof job.data.error?.message === 'string' ? job.data.error.message : 'Transcription failed.') : '';

  return (
    <section className="voice-transcribe" aria-label="Transcribe">
      <div className="voice-section-head">
        <div><h3>Transcribe</h3><Text size="sm">Word-timed transcripts with speaker labels. Click a word to hear it; export subtitles when it reads right.</Text></div>
      </div>
      <div className="voice-transcribe-form">
        <label>Recording<select aria-label="Recording" value={sourceId} onChange={(event) => setSourceId(event.currentTarget.value)}>
          <option value="">Choose a stored recording</option>
          {sources.map((asset) => <option key={asset.id} value={asset.id}>{assetTitle(asset)}</option>)}
        </select></label>
        <label title="How many people speak. Automatic lets the engine decide; 1 skips speaker labelling.">Speakers<select aria-label="Speakers" value={speakers} onChange={(event) => setSpeakers(event.currentTarget.value)}>
          {SPEAKER_CHOICES.map((choice) => <option key={choice} value={choice}>{choice === 'auto' ? 'Automatic' : choice}</option>)}
        </select></label>
        <label title="The engine detects the language itself; the choice is recorded on the transcript.">Language<select aria-label="Transcript language" value={language} onChange={(event) => setLanguage(event.currentTarget.value)}>
          {TRANSCRIPT_LANGUAGES.map((entry) => <option key={entry.code} value={entry.code}>{entry.label}</option>)}
        </select></label>
        <Button disabled={!sourceId || running} loading={queue.isPending || running} onClick={() => queue.mutate()}>Transcribe</Button>
      </div>
      {running ? <Text size="sm" role="status">Transcribing… ({job.data?.status ?? 'queued'})</Text> : null}
      {failure || queue.isError ? <Text size="sm" role="alert">{failure || 'The transcription could not be queued.'}</Text> : null}

      <label className="voice-transcript-picker">Transcripts<select aria-label="Transcripts" value={openId} onChange={(event) => setOpenId(event.currentTarget.value)}>
        <option value="">{transcripts.length ? 'Open a transcript' : 'No transcripts yet'}</option>
        {transcripts.map((asset) => <option key={asset.id} value={asset.id}>{assetTitle(asset)}</option>)}
      </select></label>
      {openId ? <TranscriptEditor key={openId} assetId={openId} onMakeVoice={onMakeVoice} /> : null}
    </section>
  );
}
