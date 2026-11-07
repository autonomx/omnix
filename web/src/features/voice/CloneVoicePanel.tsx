import { Button, Group, Text } from '@mantine/core';
import { useMutation } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { omnixApiClient, type JobRecord } from '../../api/client';
import { FeatureSubmitFeedback, FeatureValidationMessage } from '../../shared/FeatureSubmitFeedback';
import { useAudioToolsStatus } from './AudioToolsTool';
import { jobSettled, useJobResult } from './useJobResult';
import { blobToDataUrl, formatBytes } from './voiceAssets';
import { sampleCheckWarnings, transcriptFromJob, voiceJobErrorMessage } from './voiceOutputs';
import './VoiceStudioWorkspace.css';

interface VoiceCloneFormValues {
  providerId: string;
  profileName: string;
  language: string;
  quality: string;
  notes: string;
  referenceText: string;
  generateTranscript: boolean;
  isolateVocals: boolean;
  enhanceSample: boolean;
  pickBestSection: boolean;
}

type CloneSourceKind = 'upload' | 'record';

export interface CloneDefaults {
  revision: string;
  providerId: string;
  language: string;
  quality: string;
  sttProviderId: string;
}

/** Quality sets how strictly the sample is checked for noise and clipping before cloning. */
const QUALITY_OPTIONS = [
  { value: 'High', label: 'High (strict check)' },
  { value: 'Standard', label: 'Standard' },
  { value: 'Draft', label: 'Draft (lenient check)' },
];

/** A sample handed over by another tool (Transcribe's "Make a voice"), with the words it holds. */
export interface CloneSeed {
  key: string;
  file: File;
  text: string;
  name: string;
}

/** Upload or record a sample, review its transcript, and clone it into the library. */
export function CloneVoicePanel({ defaults, onFinished, seed }: { defaults: CloneDefaults; onFinished: () => Promise<unknown>; seed?: CloneSeed | null }) {
  const [cloneSource, setCloneSource] = useState<CloneSourceKind>('upload');
  // Isolating and cleaning up a sample needs the audio service.
  const audioTools = useAudioToolsStatus();
  const [sampleFile, setSampleFile] = useState<File | null>(null);
  const [recordedSample, setRecordedSample] = useState<Blob | null>(null);
  const [mediaRecorder, setMediaRecorder] = useState<MediaRecorder | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [recordingStatus, setRecordingStatus] = useState('');
  const [transcription, setTranscription] = useState<{ jobId: string; sample: Blob } | null>(null);
  const [cloneRun, setCloneRun] = useState<{ jobId: string; sample: Blob } | null>(null);
  const appliedRevision = useRef('');
  const formDefaults = (): VoiceCloneFormValues => ({
    providerId: defaults.providerId, profileName: '', language: defaults.language,
    quality: normalizeQuality(defaults.quality), notes: '', referenceText: '', generateTranscript: true,
    isolateVocals: false, enhanceSample: false, pickBestSection: true,
  });
  const { register, handleSubmit, reset, getValues, setValue, formState: { errors, isDirty } } = useForm<VoiceCloneFormValues>({ defaultValues: formDefaults() });

  useEffect(() => {
    if (!defaults.revision || appliedRevision.current === defaults.revision) return;
    if (!isDirty) reset(formDefaults());
    appliedRevision.current = defaults.revision;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-apply only when the settings revision changes
  }, [defaults.revision, isDirty, reset]);

  // A handed-over sample arrives as an upload with its transcript filled in.
  useEffect(() => {
    if (!seed) return;
    setCloneSource('upload');
    setRecordedSample(null);
    setSampleFile(seed.file);
    setValue('referenceText', seed.text, { shouldDirty: true });
    setValue('generateTranscript', false, { shouldDirty: true });
    if (seed.name) setValue('profileName', seed.name, { shouldDirty: true });
  }, [seed, setValue]);

  const selectedSample = cloneSource === 'record' ? recordedSample : sampleFile;
  const selectedSampleName = cloneSource === 'record' ? 'recorded-voice.webm' : sampleFile?.name ?? null;

  const cloneMutation = useMutation({
    mutationFn: async (values: VoiceCloneFormValues) => {
      if (!selectedSample) throw new Error('Upload or record an audio sample before creating a clone.');
      const job = await omnixApiClient.createJob({
        module: 'voice-cloning',
        type: 'voice-cloning.create-profile',
        resource_class: 'gpu:tts',
        priority: 0,
        input_payload: {
          profile_name: values.profileName,
          provider_id: values.providerId || defaults.providerId || null,
          language: values.language || defaults.language,
          quality: values.quality || defaults.quality,
          notes: values.notes,
          reference_text: values.referenceText.trim(),
          generate_transcript: values.generateTranscript,
          isolate_vocals: values.isolateVocals,
          enhance_sample: values.enhanceSample,
          pick_best_section: values.pickBestSection,
          stt_provider_id: defaults.sttProviderId || null,
          source_kind: cloneSource,
          source_file_name: selectedSampleName,
          source_file_size: selectedSample.size,
          source_mime_type: selectedSample.type || null,
          sample_audio_base64: await blobToDataUrl(selectedSample),
          storage_hint: 'resources/voice_clones',
        },
        stages: [
          { id: 'capture-sample', label: cloneSource === 'record' ? 'Record voice sample' : 'Ingest uploaded audio', resource_class: 'cpu', status: 'queued' },
          { id: 'check-sample', label: 'Clean and check the sample', resource_class: 'cpu', status: 'queued' },
          ...(values.generateTranscript && !values.referenceText.trim()
            ? [{ id: 'transcribe-sample', label: 'Generate reference transcript', resource_class: 'gpu:stt' as const, status: 'queued' as const }]
            : []),
          { id: 'store-profile', label: 'Store local voice clone', resource_class: 'cpu', status: 'queued' },
        ],
      });
      return { jobId: job.id, sample: selectedSample };
    },
    onMutate: () => setCloneRun(null),
    onSuccess: setCloneRun,
  });

  const cloneJob = useJobResult(cloneRun?.jobId ?? '');
  const settledClone = jobSettled(cloneJob.data) ? cloneJob.data : undefined;
  const cloning = cloneMutation.isPending || (Boolean(cloneRun) && !settledClone);
  const cloneFailure = settledClone && settledClone.status !== 'completed' ? cloneFailureMessage(settledClone) : '';

  // A voice joins the library when its job finishes, not when it is queued. A failed job keeps the form to try again.
  useEffect(() => {
    if (!settledClone || !cloneRun) return;
    void onFinished();
    if (settledClone.status !== 'completed') return;
    const warnings = sampleCheckWarnings(settledClone);
    setRecordingStatus(`Voice clone created and added to the Voice Library.${warnings.length ? ` ${warnings.join(' ')}` : ''}`);
    if (cloneRun.sample === selectedSample) {
      const values = getValues();
      reset({ ...formDefaults(), providerId: values.providerId, language: values.language, quality: values.quality, generateTranscript: values.generateTranscript });
      setSampleFile(null);
      setRecordedSample(null);
    }
    setCloneRun(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once, when the job settles
  }, [settledClone]);

  const transcribeMutation = useMutation({
    mutationFn: async () => {
      if (!selectedSample) throw new Error('Upload or record an audio sample before transcribing it.');
      const values = getValues();
      const job = await omnixApiClient.createJob({
        module: 'voice-cloning',
        type: 'voice-cloning.transcribe-sample',
        resource_class: 'gpu:stt',
        priority: 0,
        input_payload: {
          provider_id: values.providerId || defaults.providerId || null,
          stt_provider_id: defaults.sttProviderId || null,
          language: values.language || defaults.language,
          source_file_name: selectedSampleName,
          source_mime_type: selectedSample.type || null,
          sample_audio_base64: await blobToDataUrl(selectedSample),
        },
        stages: [{ id: 'transcribe-sample', label: 'Transcribe reference sample', resource_class: 'gpu:stt', status: 'queued' }],
      });
      return { jobId: job.id, sample: selectedSample };
    },
    onMutate: () => setTranscription(null),
    onSuccess: setTranscription,
  });

  // The job answers for the sample it was queued with; a different sample drops it.
  const transcribeJob = useJobResult(transcription?.sample === selectedSample ? transcription.jobId : '');
  const settledJob = jobSettled(transcribeJob.data) ? transcribeJob.data : undefined;
  const transcript = settledJob?.status === 'completed' ? transcriptFromJob(settledJob) : '';
  const transcribing = transcribeMutation.isPending || (transcription?.sample === selectedSample && !settledJob);
  const transcribeFailure = !settledJob || transcript ? '' : transcribeFailureMessage(settledJob);

  // A finished transcript fills the form once, so it never overwrites later corrections.
  useEffect(() => {
    if (!transcript) return;
    setValue('referenceText', transcript, { shouldDirty: true, shouldValidate: true });
    setValue('generateTranscript', false, { shouldDirty: true });
    setRecordingStatus('Transcript generated. Review or correct it before creating the clone.');
    setTranscription(null);
  }, [transcript, setValue]);

  async function toggleRecording() {
    if (mediaRecorder && isRecording) {
      mediaRecorder.stop();
      setIsRecording(false);
      return;
    }
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setRecordingStatus('Browser recording is not available. Upload an audio file instead.');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      const chunks: BlobPart[] = [];
      recorder.ondataavailable = (event) => { if (event.data.size > 0) chunks.push(event.data); };
      recorder.onstop = () => {
        const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' });
        setRecordedSample(blob);
        setRecordingStatus(`Recorded sample · ${formatBytes(blob.size)}`);
        setMediaRecorder(null);
        setIsRecording(false);
        stream.getTracks().forEach((track) => track.stop());
      };
      setRecordedSample(null);
      setMediaRecorder(recorder);
      setIsRecording(true);
      setRecordingStatus('Recording… click Record Voice again to stop.');
      recorder.start();
    } catch (error) {
      setRecordingStatus(error instanceof Error ? error.message : 'Could not start recording.');
      setIsRecording(false);
    }
  }

  function resetDefaults() {
    reset(formDefaults());
    setSampleFile(null);
    setRecordedSample(null);
    setRecordingStatus('');
    setCloneSource('upload');
  }

  return (
    <section className="voice-clone" aria-label="Clone a Voice">
      <div className="voice-section-head"><div><h3>Clone a Voice</h3><Text size="sm">The sample is trimmed, its long pauses shortened, then levelled and checked for noise and clipping before cloning.</Text></div></div>
      <form className="voice-clone-form" onSubmit={handleSubmit((values) => cloneMutation.mutate(values))}>
        <div className="clone-source-grid">
          <button className={cloneSource === 'upload' ? 'active' : ''} type="button" onClick={() => setCloneSource('upload')}><strong>Upload Audio</strong><small>WAV, FLAC, MP3, Ogg</small><small>10–30 seconds clones best</small></button>
          <button className={cloneSource === 'record' ? 'active' : ''} type="button" onClick={() => { setCloneSource('record'); void toggleRecording(); }}><strong>{isRecording ? 'Stop Recording' : 'Record Voice'}</strong><small>Record directly</small><small>in your browser</small></button>
        </div>
        <label>Voice Name<input aria-invalid={Boolean(errors.profileName)} placeholder="e.g. My New Voice" {...register('profileName', { required: true })} /></label>
        <label className="voice-file-field">Audio sample<input type="file" accept="audio/*" onChange={(event) => { setSampleFile(event.currentTarget.files?.[0] ?? null); setRecordedSample(null); setCloneSource('upload'); }} /><small>{cloneSource === 'record' ? recordingStatus || 'No recording yet.' : sampleFile ? `${sampleFile.name} · ${formatBytes(sampleFile.size)}` : 'No sample selected yet.'}</small></label>
        <div className="voice-two-col">
          <label>Language / Accent<input {...register('language')} /></label>
          <label title="How strictly the sample is checked for background noise and clipping.">Quality<select {...register('quality')}>{QUALITY_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
        </div>
        <div className="voice-clone-prep">
          <label><input type="checkbox" disabled={!audioTools.data?.available} {...register('isolateVocals')} /> Isolate vocals first</label>
          <label><input type="checkbox" disabled={!audioTools.data?.available} {...register('enhanceSample')} /> Clean up noise</label>
          {audioTools.isPending || audioTools.data?.available ? null : <small>{audioTools.data?.detail || 'The audio service did not answer.'} Checking again…</small>}
          <label title="Tries a few 5 to 9 second sections of the sample on the voice engine and keeps the one whose test lines go silent least. Adds a minute or two; the whole sample is kept too."><input type="checkbox" {...register('pickBestSection')} /> Pick the best section</label>
        </div>
        <label>Reference transcript (optional)<textarea rows={3} placeholder="Paste the exact spoken words, or transcribe the selected sample with STT." {...register('referenceText')} /></label>
        <Group className="voice-transcribe-action" justify="space-between" align="center"><Text size="xs">Use STT now so you can verify the exact words before cloning.</Text><Button type="button" size="sm" variant="outline" loading={transcribing} disabled={!selectedSample || transcribing} onClick={() => transcribeMutation.mutate()}>Generate Transcript</Button></Group>
        {transcribeMutation.isError ? <div className="platform-empty" role="alert">{transcribeMutation.error instanceof Error ? transcribeMutation.error.message : 'STT could not transcribe the sample.'}</div> : null}
        {transcribeFailure ? <div className="platform-empty" role="alert">{transcribeFailure}</div> : null}
        <label className="voice-transcript-option"><input type="checkbox" {...register('generateTranscript')} /><span>Generate transcript with STT<small>Uses the configured STT provider when the reference transcript is empty.</small></span></label>
        <label>Notes / Tags (optional)<textarea rows={2} placeholder="Add notes or tags to help identify this voice..." {...register('notes')} /></label>
        <Group justify="space-between"><Text size="xs">{recordingStatus && cloneSource === 'upload' ? recordingStatus : 'Clones are stored in Omnix resources.'}</Text><Group gap="xs"><Button type="button" variant="subtle" onClick={resetDefaults}>Reset defaults</Button><Button type="submit" loading={cloning} disabled={!selectedSample || cloning}>Create Clone</Button></Group></Group>
      </form>
      <FeatureValidationMessage show={Boolean(errors.profileName)} message="Enter a voice name before creating a clone." />
      <FeatureSubmitFeedback error={cloneMutation.error} errorPrefix="Voice clone request" isError={cloneMutation.isError} isPending={cloning} pendingMessage="Cloning the voice…" successPrefix="Voice clone job queued" />
      {cloneFailure ? <div className="platform-empty" role="alert">{cloneFailure}</div> : null}
    </section>
  );
}

/** Why a settled clone job made no voice. */
function cloneFailureMessage(job: JobRecord): string {
  return voiceJobErrorMessage(job) || 'The voice clone stopped before it finished.';
}

/** Why a settled transcription job left no transcript. */
function transcribeFailureMessage(job: JobRecord): string {
  if (job.status === 'completed') return 'STT completed without returning a transcript.';
  if (job.status === 'failed') return job.error?.message || 'STT could not transcribe the audio sample.';
  return 'The transcription stopped before it finished.';
}

/** Older settings and forms used other labels for the same three strictness levels. */
function normalizeQuality(value: string): string {
  const label = (value || '').toLowerCase();
  if (/high|studio|recommended/.test(label)) return 'High';
  if (/draft|fast|preview/.test(label)) return 'Draft';
  return 'Standard';
}
