import { Button, Group, Text, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { omnixApiClient, type AssetListResponse, type JobRecord, type ProviderFacadePayload } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { OmnixStatusPill, WorkspacePanel } from '../../design/primitives';
import { FeatureSubmitFeedback, FeatureValidationMessage } from '../shared/FeatureSubmitFeedback';
import { DEFAULT_OUTPUT_SETTINGS } from './outputDefaults';
import { firstResultAsset } from './resultList';
import { parseScriptSegments, parseScriptSpeakers, type ScriptSegmentRow, type ScriptSpeakerRow } from './scriptLines';
import './VoiceStudioWorkspace.css';

interface VoiceFormValues {
  text: string;
  providerId: string;
  speaker: string;
  voiceId: string;
}

interface VoiceCloneFormValues {
  providerId: string;
  profileName: string;
  language: string;
  quality: string;
  notes: string;
}

interface VoiceOutputRef {
  asset_id?: string;
  data_url?: string;
  duration?: number;
  mime_type?: string;
  segments?: unknown[];
  storage_path?: string;
  title?: string;
  type?: string;
}

interface PlayableVoiceOutput {
  dataUrl: string;
  duration: number;
  jobId: string;
  key: string;
  title: string;
}

type VoiceAsset = AssetListResponse['assets'][number];
type CloneSourceKind = 'upload' | 'record';
type OutputSettingName = keyof typeof DEFAULT_OUTPUT_SETTINGS;

const DEFAULT_SCRIPT = 'dave: hello there\nbob: how do you do\nmarry: i am doing fine\ndave: now lets get to the topic\nmarry: agreed.';
const STYLE_OPTIONS = ['Confident, Conversational', 'Calm', 'Enthusiastic', 'Warm', 'Deep, Authoritative', 'Narrator, Clear'];
const AUDIO_EFFECTS = ['Equalizer', 'Reverb', 'Compression', 'De-esser', 'Noise Reduction'];

export function VoiceWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const queryClient = useQueryClient();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [cloneSource, setCloneSource] = useState<CloneSourceKind>('upload');
  const [sampleFile, setSampleFile] = useState<File | null>(null);
  const [recordedSample, setRecordedSample] = useState<Blob | null>(null);
  const [mediaRecorder, setMediaRecorder] = useState<MediaRecorder | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [recordingStatus, setRecordingStatus] = useState('');
  const [voiceSearch, setVoiceSearch] = useState('');
  const [saveMessage, setSaveMessage] = useState('');
  const [showAllVoices, setShowAllVoices] = useState(false);
  const [selectedOutputKey, setSelectedOutputKey] = useState('');
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackTime, setPlaybackTime] = useState(0);
  const [playbackDuration, setPlaybackDuration] = useState(0);
  const [speakerVoiceAssignments, setSpeakerVoiceAssignments] = useState<Record<string, string>>({});
  const [speakerStyleAssignments, setSpeakerStyleAssignments] = useState<Record<string, string>>({});
  const [outputSettings, setOutputSettings] = useState(DEFAULT_OUTPUT_SETTINGS);
  const [enabledEffects, setEnabledEffects] = useState<string[]>(AUDIO_EFFECTS);

  const providersQuery = useQuery({ queryKey: ['platform', 'providers'], queryFn: () => omnixApiClient.listProviders() });
  const jobsQuery = useQuery({ queryKey: ['platform', 'jobs'], queryFn: () => omnixApiClient.listJobs() });
  const assetsQuery = useQuery({ queryKey: ['platform', 'assets'], queryFn: () => omnixApiClient.listAssets() });

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm<VoiceFormValues>({
    defaultValues: { text: DEFAULT_SCRIPT, providerId: '', speaker: '', voiceId: '' },
  });
  const {
    register: registerClone,
    handleSubmit: handleCloneSubmit,
    reset: resetClone,
    formState: { errors: cloneErrors },
  } = useForm<VoiceCloneFormValues>({
    defaultValues: { providerId: '', profileName: '', language: 'English (US)', quality: 'High (Recommended)', notes: '' },
  });

  const scriptText = watch('text') ?? '';
  const scriptSegments = useMemo(() => parseScriptSegments(scriptText), [scriptText]);
  const parsedSpeakers = useMemo(() => parseScriptSpeakers(scriptText), [scriptText]);
  const ttsProviders = useMemo(() => ttsCapableProviders(providersQuery.data), [providersQuery.data]);
  const cloneProviders = useMemo(() => cloneCapableProviders(providersQuery.data), [providersQuery.data]);
  const queriedVoiceJobs = useMemo(() => jobsQuery.data?.jobs.filter((job) => job.module === 'voice' || job.module === 'voice-cloning') ?? [], [jobsQuery.data?.jobs]);
  const audioAssets = assetsQuery.data?.assets.filter((asset) => asset.type === 'audio' || asset.type === 'voice_profile') ?? [];
  const profileAssets = audioAssets.filter((asset) => asset.type === 'voice_profile');
  const generatedAudioAssets = audioAssets.filter((asset) => asset.type === 'audio');
  const latestResultAsset = firstResultAsset(generatedAudioAssets);
  const filteredProfileAssets = useMemo(
    () => profileAssets.filter((asset) => voiceAssetName(asset).toLowerCase().includes(voiceSearch.trim().toLowerCase()) || voiceProfileName(asset).toLowerCase().includes(voiceSearch.trim().toLowerCase())),
    [profileAssets, voiceSearch],
  );
  const visibleProfileAssets = showAllVoices ? filteredProfileAssets : filteredProfileAssets.slice(0, 6);
  const selectedCloneSample = cloneSource === 'record' ? recordedSample : sampleFile;
  const selectedCloneSampleName = cloneSource === 'record' ? 'recorded-voice.webm' : sampleFile?.name ?? null;

  const createJobMutation = useMutation({
    mutationFn: (values: VoiceFormValues) =>
      omnixApiClient.createJob({
        module: 'voice',
        type: parsedSpeakers.length > 1 ? 'tts.multi_speaker_synthesize' : 'tts.synthesize',
        resource_class: 'gpu:tts',
        priority: 0,
        input_payload: {
          text: values.text,
          provider_id: values.providerId || ttsProviders[0]?.id || null,
          speaker: values.speaker || parsedSpeakers[0]?.name || null,
          voice_id: values.voiceId || assignedVoiceFor(parsedSpeakers[0] ?? { name: '', count: 0 }, profileAssets, speakerVoiceAssignments) || null,
          script_mode: parsedSpeakers.length > 1 ? 'multi_speaker' : 'single_speaker',
          script_speakers: parsedSpeakers,
          script_segments: scriptSegments,
          character_voice_assignments: buildSpeakerAssignments(parsedSpeakers, profileAssets, speakerVoiceAssignments, speakerStyleAssignments),
          output_settings: outputSettings,
          audio_effects: enabledEffects,
          save_output: true,
        },
        stages: voiceSynthesisStages(scriptSegments),
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] }),
        queryClient.invalidateQueries({ queryKey: ['platform', 'assets'] }),
      ]);
    },
  });

  const previewVoiceMutation = useMutation({
    mutationFn: (asset: VoiceAsset) => omnixApiClient.createJob({
      module: 'voice',
      type: 'tts.synthesize',
      resource_class: 'gpu:tts',
      priority: 1,
      input_payload: {
        text: `This is a preview of ${voiceAssetName(asset)} speaking in Voice Studio.`,
        provider_id: ttsProviders[0]?.id || null,
        speaker: voiceAssetName(asset),
        voice_id: asset.storage_path,
        script_mode: 'single_speaker',
        script_speakers: [{ name: 'Preview', count: 1 }],
        script_segments: [{ index: 0, speaker: 'Preview', text: `This is a preview of ${voiceAssetName(asset)} speaking in Voice Studio.` }],
        character_voice_assignments: [{ speaker: 'Preview', voice_id: asset.storage_path, style: 'Neutral', line_count: 1 }],
        output_settings: outputSettings,
        audio_effects: enabledEffects,
        save_output: true,
      },
      stages: voiceSynthesisStages([{ index: 0, speaker: 'Preview', text: 'Preview voice.' }]),
    }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] }),
        queryClient.invalidateQueries({ queryKey: ['platform', 'assets'] }),
      ]);
    },
  });

  const cloneJobMutation = useMutation({
    mutationFn: async (values: VoiceCloneFormValues) => {
      const sample = cloneSource === 'record' ? recordedSample : sampleFile;
      if (!sample) {
        throw new Error('Upload or record an audio sample before creating a clone.');
      }
      return omnixApiClient.createJob({
        module: 'voice-cloning',
        type: 'voice-cloning.create-profile',
        resource_class: 'gpu:tts',
        priority: 0,
        input_payload: {
          profile_name: values.profileName,
          provider_id: values.providerId || cloneProviders[0]?.id || null,
          language: values.language,
          quality: values.quality,
          notes: values.notes,
          source_kind: cloneSource,
          source_file_name: selectedCloneSampleName,
          source_file_size: sample.size,
          source_mime_type: sample.type || null,
          sample_audio_base64: await blobToDataUrl(sample),
          storage_hint: 'resources/voice_clones',
        },
        stages: [
          { id: 'capture-sample', label: cloneSource === 'record' ? 'Record voice sample' : 'Ingest uploaded audio', resource_class: 'cpu', status: 'queued' },
          { id: 'build-profile', label: 'Create voice profile', resource_class: 'gpu:tts', status: 'queued' },
          { id: 'preview', label: 'Generate preview clip', resource_class: 'gpu:tts', status: 'queued' },
          { id: 'store-profile', label: 'Store local voice clone', resource_class: 'cpu', status: 'queued' },
        ],
      });
    },
    onSuccess: async (_job, values) => {
      resetClone({ providerId: values.providerId, profileName: '', language: values.language, quality: values.quality, notes: '' });
      setSampleFile(null);
      setRecordedSample(null);
      setRecordingStatus('Voice clone queued and stored locally.');
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] }),
        queryClient.invalidateQueries({ queryKey: ['platform', 'assets'] }),
      ]);
    },
  });

  const voiceJobs = useMemo(
    () => mergeVoiceJobs([createJobMutation.data, previewVoiceMutation.data, cloneJobMutation.data, ...queriedVoiceJobs]),
    [cloneJobMutation.data, createJobMutation.data, previewVoiceMutation.data, queriedVoiceJobs],
  );
  const playableOutputs = useMemo(() => extractPlayableOutputs(voiceJobs), [voiceJobs]);
  const currentOutput = playableOutputs.find((output) => output.key === selectedOutputKey) ?? playableOutputs[0] ?? null;
  const effectiveDuration = playbackDuration || currentOutput?.duration || estimateDurationFromText(scriptText);
  const submitStatus = createJobMutation.isPending ? 'queued' : createJobMutation.isError ? 'error' : createJobMutation.data?.status ?? 'ready';

  useEffect(() => {
    if (playableOutputs.length > 0 && !playableOutputs.some((output) => output.key === selectedOutputKey)) {
      setSelectedOutputKey(playableOutputs[0].key);
    }
  }, [playableOutputs, selectedOutputKey]);

  useEffect(() => {
    setPlaybackTime(0);
    setPlaybackDuration(currentOutput?.duration ?? 0);
    setIsPlaying(false);
    audioRef.current?.pause();
  }, [currentOutput?.key]);

  async function togglePlayback() {
    const audio = audioRef.current;
    if (!audio || !currentOutput) {
      setSaveMessage('Generate speech before playing audio.');
      return;
    }
    if (isPlaying) {
      audio.pause();
      setIsPlaying(false);
      return;
    }
    try {
      await audio.play();
      setIsPlaying(true);
    } catch (error) {
      setSaveMessage(error instanceof Error ? error.message : 'Audio playback could not start.');
    }
  }

  function selectOutputOffset(offset: number) {
    if (!playableOutputs.length) {
      return;
    }
    const index = Math.max(0, playableOutputs.findIndex((output) => output.key === currentOutput?.key));
    const nextIndex = (index + offset + playableOutputs.length) % playableOutputs.length;
    setSelectedOutputKey(playableOutputs[nextIndex].key);
  }

  function seekPlayback(value: number) {
    const audio = audioRef.current;
    setPlaybackTime(value);
    if (audio) {
      audio.currentTime = value;
    }
  }

  function downloadCurrentOutput() {
    if (!currentOutput || typeof document === 'undefined') {
      setSaveMessage('Generate speech before saving output.');
      return;
    }
    const link = document.createElement('a');
    link.href = currentOutput.dataUrl;
    link.download = `${safeDownloadName(currentOutput.title)}.wav`;
    link.click();
  }

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
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunks.push(event.data);
        }
      };
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

  return (
    <WorkspacePanel>
      <div className="voice-studio-app">
        <aside className="voice-side-nav" aria-label="Voice Studio sections">
          <div className="voice-brand"><span className="voice-brand-mark" /> <strong>OMNIX</strong></div>
          <p>Voice Studio</p>
          {['Overview', 'Voice Library', 'Clone Voice', 'Text to Speech', 'Settings'].map((item, index) => (
            <button className={index === 0 ? 'active' : ''} key={item} type="button"><span>{['⌂', '▤', '▣', '♪', '⚙'][index]}</span>{item}</button>
          ))}
          <div className="voice-credit-card"><small>Credits</small><b>12,450</b><Button size="xs">Top up</Button></div>
          <div className="voice-user-card"><span>OM</span><div><b>Omnix Team</b><small>team@omnix.ai</small></div></div>
        </aside>

        <main className="voice-workspace-final">
          <header className="voice-final-header">
            <div><Title order={2}>Voice Studio</Title><Text size="sm">Clone voices, manage your voice library, and generate natural speech with advanced controls.</Text></div>
            <Button variant="subtle">Documentation ↗</Button>
          </header>

          <div className="voice-top-grid">
            <section className="voice-panel-final clone-panel">
              <Title order={4}>Clone a Voice</Title>
              <Text size="sm">Create a high-quality clone from your audio.</Text>
              <form className="voice-clone-form" onSubmit={handleCloneSubmit((values) => cloneJobMutation.mutate(values))}>
                <div className="clone-source-grid">
                  <button className={cloneSource === 'upload' ? 'active' : ''} type="button" onClick={() => setCloneSource('upload')}><strong>Upload Audio</strong><small>WAV, MP3, MP4</small><small>Min. 1 min recommended</small></button>
                  <button className={cloneSource === 'record' ? 'active' : ''} type="button" onClick={() => { setCloneSource('record'); void toggleRecording(); }}><strong>{isRecording ? 'Stop Recording' : 'Record Voice'}</strong><small>Record directly</small><small>in your browser</small></button>
                </div>
                <label>Voice Name<input aria-invalid={Boolean(cloneErrors.profileName)} placeholder="e.g. My New Voice" {...registerClone('profileName', { required: true })} /></label>
                <label className="voice-file-field">Audio sample<input type="file" accept="audio/*" onChange={(event) => { setSampleFile(event.currentTarget.files?.[0] ?? null); setRecordedSample(null); setCloneSource('upload'); }} /><small>{cloneSource === 'record' ? recordingStatus || 'No recording yet.' : sampleFile ? `${sampleFile.name} · ${formatBytes(sampleFile.size)}` : 'No sample selected yet.'}</small></label>
                <div className="voice-two-col"><label>Language / Accent<input {...registerClone('language')} /></label><label>Quality<select {...registerClone('quality')}><option>High (Recommended)</option><option>Balanced</option><option>Fast Preview</option></select></label></div>
                <label>Notes / Tags (optional)<textarea rows={2} placeholder="Add notes or tags to help identify this voice..." {...registerClone('notes')} /></label>
                <input type="hidden" {...registerClone('providerId')} value={cloneProviders[0]?.id ?? ''} readOnly />
                <Group justify="space-between"><Text size="xs">Clones are stored to Omnix: /resources/voice_clones</Text><Button type="submit" loading={cloneJobMutation.isPending} disabled={!selectedCloneSample || cloneJobMutation.isPending}>Create Clone</Button></Group>
              </form>
              <FeatureValidationMessage show={Boolean(cloneErrors.profileName)} message="Enter a voice name before creating a clone." />
              <FeatureSubmitFeedback error={cloneJobMutation.error} errorPrefix="Voice clone request" isError={cloneJobMutation.isError} isPending={cloneJobMutation.isPending} jobId={cloneJobMutation.data?.id} pendingMessage="Queueing voice clone job…" successPrefix="Voice clone job queued" />
            </section>

            <section className="voice-panel-final library-panel-final">
              <Group justify="space-between"><div><Title order={4}>Voice Library</Title><Text size="sm">Your cloned voices stored in Omnix resources.</Text></div><Button size="xs" variant="subtle">Filter ⟳</Button></Group>
              <label className="voice-search"><span>Search voices</span><input aria-label="Search voices" value={voiceSearch} onChange={(event) => setVoiceSearch(event.currentTarget.value)} placeholder="Search voices..." /></label>
              <div className="voice-library-table" aria-label="Voice library">
                <div className="voice-library-row table-head"><span>Name</span><span>ID / Prefix</span><span>Source</span><span>Status</span><span></span></div>
                {visibleProfileAssets.map((asset) => <VoiceLibraryRow asset={asset} key={asset.id} onPreview={() => previewVoiceMutation.mutate(asset)} onUse={() => useVoice(asset, setValue, setSaveMessage)} />)}
              </div>
              <Group justify="space-between"><Text size="xs">{filteredProfileAssets.length} voices</Text><Button size="xs" variant="subtle" onClick={() => setShowAllVoices((value) => !value)}>{showAllVoices ? 'Show first 6' : 'View all voices →'}</Button></Group>
            </section>

            <section className="voice-panel-final queue-panel-final">
              <Title order={4}>Jobs & Playback Queue</Title>
              <Text size="sm">Monitor synthesis jobs and replay results.</Text>
              <div className="queue-tabs"><button type="button">Active ({activeJobs(voiceJobs).length})</button><button type="button">Recent</button><button type="button">Failed ({voiceJobs.filter((job) => job.status === 'failed').length})</button></div>
              <div className="queue-list-final">{(voiceJobs.length ? voiceJobs : demoJobs()).slice(0, 4).map((job) => <QueueRow job={job} key={job.id} />)}</div>
              <div className="latest-preview-row"><Button size="xs" variant="subtle" onClick={() => void togglePlayback()}>{isPlaying ? 'Ⅱ' : '▶'}</Button><Waveform /><Text size="xs">{currentOutput?.title ?? latestResultAsset ? voiceAssetName(latestResultAsset as VoiceAsset) : 'No generated audio yet'}</Text></div>
            </section>
          </div>

          <section className="voice-panel-final tts-panel-final">
            <Group justify="space-between"><div><Title order={4}>Text-to-Speech (Multi-Voice)</Title><Text size="sm">Write your script with character tags, AI will detect speakers and you can assign voices and styles before generating speech.</Text></div><div className="script-actions"><Button variant="subtle" onClick={() => setValue('text', '')}>Clear</Button><Button variant="subtle" onClick={() => loadScript(setValue, setSaveMessage)}>Load Script</Button><Button onClick={() => saveScript(scriptText, setSaveMessage)}>Save Script</Button></div></Group>
            <form className="tts-workflow-grid" onSubmit={handleSubmit((values) => createJobMutation.mutate(values))}>
              <section className="script-card"><Group justify="space-between"><b>1. Script <small>(use character tags)</small></b><small>ⓘ How it works</small></Group><textarea aria-label="Script" rows={8} {...register('text', { required: true })} /><Group justify="space-between"><Text size="xs">{scriptSegments.length} stages · {parsedSpeakers.length} speakers detected</Text><Button size="xs" type="button" variant="subtle" onClick={() => setSaveMessage(`${parsedSpeakers.length} speaker${parsedSpeakers.length === 1 ? '' : 's'} detected: ${parsedSpeakers.map((speaker) => speaker.name).join(', ')}`)}>Detect Characters</Button></Group>{parsedSpeakers.length ? <div className="voice-success-note">AI automatically detected {parsedSpeakers.length} character{parsedSpeakers.length === 1 ? '' : 's'} from your script.</div> : null}{saveMessage ? <div className="voice-success-note">{saveMessage}</div> : null}</section>
              <section className="assignment-card"><Group justify="space-between"><b>2. Detected Characters & Voice Assignment</b><OmnixStatusPill>{parsedSpeakers.length} detected</OmnixStatusPill></Group><div className="assignment-table"><div className="assignment-row assignment-head"><span>Character</span><span>Assign Voice</span><span>Style / Emotion</span><span>Preview</span></div>{parsedSpeakers.map((speaker, index) => <AssignmentRow assets={profileAssets} index={index} key={speaker.name} speaker={speaker} voiceValue={assignedVoiceFor(speaker, profileAssets, speakerVoiceAssignments)} styleValue={speakerStyleAssignments[speaker.name] ?? STYLE_OPTIONS[Math.min(index, STYLE_OPTIONS.length - 1)]} onPreview={(voiceId) => previewVoiceById(voiceId, profileAssets, previewVoiceMutation.mutate)} onVoiceChange={(voiceId) => setSpeakerVoiceAssignments((current) => ({ ...current, [speaker.name]: voiceId }))} onStyleChange={(style) => setSpeakerStyleAssignments((current) => ({ ...current, [speaker.name]: style }))} />)}</div><Text size="xs">Unlabeled scripts use a single Narrator speaker. Tagged scripts are generated one stage per line.</Text></section>
              <section className="generate-card"><b>3. Generate Speech</b><Text size="sm">Generate multi-stage audio from your script.</Text><input type="hidden" {...register('providerId')} value={ttsProviders[0]?.id ?? ''} readOnly /><input type="hidden" {...register('voiceId')} value={profileAssets[0]?.storage_path ?? ''} readOnly /><input type="hidden" {...register('speaker')} value={parsedSpeakers[0]?.name ?? 'Narrator'} readOnly /><Button className="generate-speech-button" type="submit" loading={createJobMutation.isPending}>▥ Generate Speech</Button><Button type="button" variant="subtle" onClick={downloadCurrentOutput}>⇩ Save Output</Button><Text size="xs">Estimated duration: ~ {formatPlaybackTime(estimateDurationFromText(scriptText))}</Text><FeatureSubmitFeedback error={createJobMutation.error} errorPrefix="TTS request" isError={createJobMutation.isError} isPending={createJobMutation.isPending} jobId={createJobMutation.data?.id} pendingMessage="Queueing TTS job…" successPrefix="TTS job queued" /></section>
            </form>
            <FeatureValidationMessage show={Boolean(errors.text)} message="Enter script text before generating speech." />
          </section>

          <div className="voice-bottom-grid">
            <section className="voice-panel-final enhancement-panel"><Title order={5}>Voice Enhancement</Title><Text size="xs">Fine-tune and enhance the output with advanced controls.</Text><div className="enhancement-controls">{(Object.entries(outputSettings) as [OutputSettingName, number][]).map(([name, value]) => <label key={name}><span>{settingLabel(name)}</span><b>{settingValueLabel(name, value)}</b><input aria-label={`Output ${name}`} type="range" min={rangeMin(name)} max={rangeMax(name)} step="0.01" value={value} onChange={(event) => setOutputSettings((current) => ({ ...current, [name]: Number(event.currentTarget.value) }))} /></label>)}</div></section>
            <section className="voice-panel-final effects-panel"><Title order={5}>Audio Effects</Title><Text size="xs">Apply effects to polish and enhance the final audio.</Text><div className="effect-buttons">{AUDIO_EFFECTS.map((effect) => <button className={enabledEffects.includes(effect) ? 'active' : ''} key={effect} type="button" onClick={() => toggleEffect(effect, setEnabledEffects)}>{effect}</button>)}<button type="button">More</button></div></section>
          </div>

          <footer className="now-playing-bar">
            <audio ref={audioRef} src={currentOutput?.dataUrl ?? undefined} preload="metadata" onLoadedMetadata={(event) => setPlaybackDuration(event.currentTarget.duration || currentOutput?.duration || 0)} onTimeUpdate={(event) => setPlaybackTime(event.currentTarget.currentTime)} onEnded={() => setIsPlaying(false)} />
            <button type="button">⌃</button><div><b>Now Playing</b><span>{currentOutput?.title ?? latestResultAsset ? voiceAssetName(latestResultAsset as VoiceAsset) : `${module.label} output`} · {parsedSpeakers.length} speaker{parsedSpeakers.length === 1 ? '' : 's'}</span></div><button type="button" onClick={() => selectOutputOffset(-1)}>↢</button><button className="main-play" type="button" onClick={() => void togglePlayback()}>{isPlaying ? 'Ⅱ' : '▶'}</button><button type="button" onClick={() => selectOutputOffset(1)}>↣</button><span>{formatPlaybackTime(playbackTime)}</span><input aria-label="Voice playback position" className="now-playing-seek" type="range" min={0} max={Math.max(effectiveDuration, 0.1)} step="0.01" value={Math.min(playbackTime, effectiveDuration)} onChange={(event) => seekPlayback(Number(event.currentTarget.value))} /><span>{formatPlaybackTime(effectiveDuration)}</span><button type="button" onClick={downloadCurrentOutput}>⇩</button><button type="button">⋯</button></footer>
        </main>
      </div>
    </WorkspacePanel>
  );
}

function VoiceLibraryRow({ asset, onPreview, onUse }: { asset: VoiceAsset; onPreview: () => void; onUse: () => void }) {
  return <div className="voice-library-row"><span><i>{voiceInitial(asset)}</i><b>{voiceAssetName(asset)}</b><small>{voiceProfileDescription(asset)}</small></span><span>{voiceProfileName(asset)}</span><span>Local Clone</span><span className="ready-chip">Ready</span><span><Button size="xs" variant="subtle" onClick={onPreview}>▶</Button><Button size="xs" variant="subtle" onClick={onUse}>Use</Button><Button size="xs" variant="subtle">⋯</Button></span></div>;
}

function QueueRow({ job }: { job: { id: string; type: string; status: string; module: string; progress?: { current: number; total: number }; stages?: Array<{ label?: string; status?: string }> } }) {
  const progress = progressPercent(job.progress);
  const stageSummary = job.stages?.length ? `${job.stages.length} stages · ${job.stages.slice(0, 2).map((stage) => stage.label || stage.status || 'stage').join(', ')}` : job.module;
  return <article className="queue-row-final"><span className="job-icon">▥</span><div><b>{job.type}</b><small>{stageSummary}</small></div><div><OmnixStatusPill>{job.status}</OmnixStatusPill>{progress ? <div className="queue-progress"><span style={{ width: `${progress}%` }} /></div> : null}</div><small>{progress || job.status === 'completed' ? `${progress}%` : '—'}</small><button type="button">⋯</button></article>;
}

function AssignmentRow({ assets, index, speaker, voiceValue, styleValue, onPreview, onVoiceChange, onStyleChange }: { assets: VoiceAsset[]; index: number; speaker: ScriptSpeakerRow; voiceValue: string; styleValue: string; onPreview: (voiceId: string) => void; onVoiceChange: (voiceId: string) => void; onStyleChange: (style: string) => void }) {
  return <div className="assignment-row"><span><i>{speaker.name.slice(0, 2).toUpperCase()}</i>{speaker.name}</span><select aria-label={`${speaker.name} voice`} value={voiceValue} onChange={(event) => onVoiceChange(event.currentTarget.value)}>{assets.map((asset) => <option key={asset.id} value={asset.storage_path}>{voiceAssetName(asset)} ({voiceProfileName(asset)})</option>)}{!assets.length ? <option value="">No cloned voices</option> : null}</select><select aria-label={`${speaker.name} style`} value={styleValue} onChange={(event) => onStyleChange(event.currentTarget.value)}>{STYLE_OPTIONS.map((style) => <option key={style} value={style}>{style}</option>)}</select><Button size="xs" variant="subtle" type="button" onClick={() => onPreview(voiceValue)}>▶</Button></div>;
}

function Waveform() {
  return <div className="voice-waveform-final" aria-hidden="true">{Array.from({ length: 64 }, (_, index) => <span key={index} style={{ height: `${18 + ((index * 19) % 62)}%` }} />)}</div>;
}

function ttsCapableProviders(payload: ProviderFacadePayload | undefined) {
  return payload?.providers.filter((provider) => provider.capabilities.includes('tts')) ?? [];
}

function cloneCapableProviders(payload: ProviderFacadePayload | undefined) {
  return payload?.providers.filter((provider) => provider.capabilities.includes('voice_cloning') || provider.capabilities.includes('tts')) ?? [];
}

function buildSpeakerAssignments(speakers: ScriptSpeakerRow[], assets: VoiceAsset[], voiceAssignments: Record<string, string>, styleAssignments: Record<string, string>) {
  return speakers.map((speaker, index) => ({
    speaker: speaker.name,
    voice_id: assignedVoiceFor(speaker, assets, voiceAssignments) || null,
    style: styleAssignments[speaker.name] ?? STYLE_OPTIONS[Math.min(index, STYLE_OPTIONS.length - 1)],
    line_count: speaker.count,
  }));
}

function assignedVoiceFor(speaker: ScriptSpeakerRow, assets: VoiceAsset[], voiceAssignments: Record<string, string>): string {
  return voiceAssignments[speaker.name] ?? findMatchingVoice(speaker.name, assets)?.storage_path ?? assets[0]?.storage_path ?? '';
}

function findMatchingVoice(name: string, assets: VoiceAsset[]): VoiceAsset | undefined {
  const normalizedName = name.toLowerCase();
  return assets.find((asset) => voiceAssetName(asset).toLowerCase().includes(normalizedName) || voiceProfileName(asset).toLowerCase().includes(normalizedName));
}

function previewVoiceById(voiceId: string, assets: VoiceAsset[], preview: (asset: VoiceAsset) => void) {
  const asset = assets.find((entry) => entry.storage_path === voiceId || entry.id === voiceId);
  if (asset) {
    preview(asset);
  }
}

function useVoice(asset: VoiceAsset, setValue: ReturnType<typeof useForm<VoiceFormValues>>['setValue'], setSaveMessage: (message: string) => void) {
  setValue('voiceId', asset.storage_path);
  setValue('speaker', voiceAssetName(asset));
  setSaveMessage(`Selected ${voiceAssetName(asset)} for synthesis.`);
}

function activeJobs(jobs: Array<{ status: string }>) {
  return jobs.filter((job) => job.status === 'queued' || job.status === 'running' || job.status === 'leased');
}

function mergeVoiceJobs(jobs: Array<JobRecord | undefined>): JobRecord[] {
  const merged = new Map<string, JobRecord>();
  for (const job of jobs) {
    if (job?.id) {
      merged.set(job.id, job);
    }
  }
  return Array.from(merged.values());
}

function extractPlayableOutputs(jobs: JobRecord[]): PlayableVoiceOutput[] {
  const outputs: PlayableVoiceOutput[] = [];
  for (const job of jobs) {
    const refs = (job.output_refs ?? []) as VoiceOutputRef[];
    for (const ref of refs) {
      if (ref.data_url) {
        const title = ref.title || job.type || 'voice_output';
        outputs.push({ dataUrl: ref.data_url, duration: Number(ref.duration || 0), jobId: job.id, key: `${job.id}:${ref.asset_id || ref.title || outputs.length}`, title });
      }
    }
  }
  return outputs;
}

function demoJobs() {
  return [
    { id: 'demo-active', type: 'meeting_script_v2', status: 'running', module: 'Multi-voice synthesis', progress: { current: 65, total: 100 } },
    { id: 'demo-queued', type: 'character_demo', status: 'queued', module: 'Multi-voice synthesis', progress: { current: 0, total: 100 } },
    { id: 'demo-done', type: 'product_intro_v1', status: 'completed', module: 'Single voice', progress: { current: 100, total: 100 } },
  ];
}

function saveScript(text: string, setSaveMessage: (message: string) => void) {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem('omnix.voice.lastScript', text);
  }
  setSaveMessage('Script saved locally.');
}

function loadScript(setValue: ReturnType<typeof useForm<VoiceFormValues>>['setValue'], setSaveMessage: (message: string) => void) {
  const saved = typeof window !== 'undefined' ? window.localStorage.getItem('omnix.voice.lastScript') : null;
  setValue('text', saved || DEFAULT_SCRIPT);
  setSaveMessage(saved ? 'Loaded saved script.' : 'Loaded example script.');
}

function toggleEffect(effect: string, setEnabledEffects: (value: (current: string[]) => string[]) => void) {
  setEnabledEffects((current) => current.includes(effect) ? current.filter((entry) => entry !== effect) : [...current, effect]);
}

function voiceSynthesisStages(segments: ScriptSegmentRow[]) {
  return [
    { id: 'parse-script', label: 'Detect script characters', resource_class: 'cpu' as const, status: 'queued' as const },
    { id: 'assign-voices', label: 'Apply voice assignments', resource_class: 'cpu' as const, status: 'queued' as const },
    ...segments.map((segment, index) => ({ id: `synthesize-${index.toString().padStart(4, '0')}`, label: `Generate ${segment.speaker} stage ${index + 1}`, resource_class: 'gpu:tts' as const, status: 'queued' as const })),
    { id: 'stitch-audio', label: 'Stitch generated stages', resource_class: 'cpu' as const, status: 'queued' as const },
    { id: 'store-audio', label: 'Save audio output', resource_class: 'cpu' as const, status: 'queued' as const },
  ];
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(reader.error ?? new Error('Audio sample could not be read.'));
    reader.readAsDataURL(blob);
  });
}

function progressPercent(progress: { current: number; total: number } | undefined): number {
  if (!progress || progress.total <= 0) return 0;
  return Math.min(100, Math.round((progress.current / progress.total) * 100));
}

function voiceAssetName(asset: VoiceAsset): string {
  return asset.storage_path.split(/[\\/]/).pop()?.replace(/\.[^.]+$/, '') || asset.id;
}

function voiceProfileName(asset: VoiceAsset): string {
  return asset.id.replace(/^voice-cloning:/, '').replace(/^asset:/, '');
}

function voiceInitial(asset: VoiceAsset): string {
  return voiceAssetName(asset).slice(0, 2).toUpperCase() || 'VC';
}

function voiceProfileDescription(asset: VoiceAsset): string {
  return asset.module === 'voice-cloning' ? 'Cloned voice' : 'Local voice';
}

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function formatPlaybackTime(value: number): string {
  const safe = Number.isFinite(value) ? Math.max(0, value) : 0;
  const minutes = Math.floor(safe / 60).toString().padStart(2, '0');
  const seconds = Math.floor(safe % 60).toString().padStart(2, '0');
  return `${minutes}:${seconds}`;
}

function estimateDurationFromText(text: string): number {
  return Math.max(1, Math.min(600, text.trim().length / 14));
}

function safeDownloadName(value: string): string {
  return value.replace(/[^A-Za-z0-9_.-]+/g, '-').replace(/^-+|-+$/g, '') || 'voice-output';
}

function settingLabel(name: OutputSettingName): string {
  if (name === 'style') return 'Style Exaggeration';
  return name.replace(/^./, (first) => first.toUpperCase());
}

function settingValueLabel(name: OutputSettingName, value: number): string {
  if (name === 'speed') return `${value.toFixed(2)}x`;
  if (name === 'pitch') return `${value.toFixed(0)} st`;
  if (name === 'volume') return `${value.toFixed(1)} dB`;
  return value.toFixed(2);
}

function rangeMin(name: OutputSettingName): number {
  if (name === 'pitch') return -12;
  if (name === 'volume') return -12;
  return 0;
}

function rangeMax(name: OutputSettingName): number {
  if (name === 'speed') return 2;
  if (name === 'pitch') return 12;
  if (name === 'volume') return 12;
  return 1;
}
