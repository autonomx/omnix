import { Button, Text, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { omnixApiClient, type JobRecord } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { WorkspacePanel } from '../../design/primitives';
import { DubbingTool } from '../dubbing';
import { loadSettingsProfile, voiceStudioDefaults } from '../settings';
import { FeatureSubmitFeedback, FeatureValidationMessage } from '../../shared/FeatureSubmitFeedback';
import { effectIds, type AudioEffectId } from './audioEffects';
import { voiceApiClient } from './api/voiceClient';
import { AudioToolsTool } from './AudioToolsTool';
import { BatchTool } from './BatchTool';
import { PushToTalkButton } from './PushToTalkButton';
import { CloneVoicePanel, type CloneSeed } from './CloneVoicePanel';
import { DesignTool } from './DesignTool';
import { JobsTray } from './JobsTray';
import { firstResultAsset } from './resultList';
import { RenderCheckPanel } from './RenderCheckPanel';
import { ScriptCast } from './ScriptCast';
import { parseScriptSegments, parseScriptSpeakers, type ScriptSegmentRow, type ScriptSpeakerRow } from './scriptLines';
import { rememberTool, rememberedTool, shippedTools, type StudioToolId } from './studioTools';
import { TranscribeTool } from './TranscribeTool';
import { TransportBar } from './TransportBar';
import { ENGINES_QUERY_KEY, TtsEnginePicker } from './TtsEnginePicker';
import {
  findMatchingVoice,
  findVoiceByReference,
  voiceAssetId,
  voiceAssetName,
  voiceReference,
  type VoiceAsset,
} from './voiceAssets';
import { VoiceInspector, type ExportRequest, type OutputSettingName } from './VoiceInspector';
import { VoiceLibraryGrid } from './VoiceLibraryGrid';
import { extractPlayableOutputs, mergeVoiceJobs, voiceJobErrorMessage, type PlayableVoiceOutput } from './voiceOutputs';
import { VoiceScriptEditor } from './VoiceScriptEditor';
import { SpeechModelsPanel } from './SpeechModelsPanel';
import { useSavedScript } from './useSavedScript';
import { useTakePlayback } from './useTakePlayback';
import './VoiceStudioWorkspace.css';

const DEFAULT_SCRIPT = 'dave: hello there\nbob: how do you do\nmarry: i am doing fine\ndave: now lets get to the topic\nmarry: agreed.';
const SCRIPT_STORAGE_KEY = 'omnix.voice.lastScript';
const ACTIVE_STATUSES = new Set(['queued', 'running', 'leased']);

/**
 * Voice Studio: a tool rail on the left, the active tool's canvas in the centre, the
 * voice-and-output inspector on the right, and the transport and jobs tray along the bottom.
 */
export function VoiceWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const queryClient = useQueryClient();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const appliedSettingsRevision = useRef('');
  const jobsQuery = useQuery({ queryKey: ['platform', 'jobs', 'voice-summaries'], queryFn: () => voiceApiClient.listVoiceJobSummaries() });
  const assetsQuery = useQuery({ queryKey: ['platform', 'assets'], queryFn: () => omnixApiClient.listAssets() });
  const settingsQuery = useQuery({ queryKey: ['settings', 'profile'], queryFn: () => loadSettingsProfile() });
  const enginesQuery = useQuery({ queryKey: ENGINES_QUERY_KEY, queryFn: () => voiceApiClient.listTtsEngines() });
  const selectedEngine = enginesQuery.data?.engines.find((engine) => engine.selected);
  const moduleDefaults = useMemo(() => voiceStudioDefaults(settingsQuery.data?.profile), [settingsQuery.data?.profile]);
  const centralOutputSettings = useMemo(() => ({
    stability: moduleDefaults.stability,
    similarity: moduleDefaults.similarity,
    style: moduleDefaults.style,
    speed: moduleDefaults.speed,
    pitch: moduleDefaults.pitch,
    volume: moduleDefaults.volume,
  }), [moduleDefaults.pitch, moduleDefaults.similarity, moduleDefaults.speed, moduleDefaults.stability, moduleDefaults.style, moduleDefaults.volume]);
  const centralEffects = useMemo(() => effectIds(moduleDefaults.effects), [moduleDefaults.effects]);

  const [tool, setTool] = useState<StudioToolId>(rememberedTool);
  const [scriptText, setScriptText] = useState(DEFAULT_SCRIPT);
  const [scriptTitle, setScriptTitle] = useState('');
  const [message, setMessage] = useState('');
  // A clone sample handed over by Transcribe's "Make a voice".
  const [cloneSeed, setCloneSeed] = useState<CloneSeed | null>(null);
  const [speakerVoiceAssignments, setSpeakerVoiceAssignments] = useState<Record<string, string>>({});
  const [speakerDelivery, setSpeakerDelivery] = useState<Record<string, string>>({});
  const [outputSettings, setOutputSettings] = useState<Record<OutputSettingName, number>>(centralOutputSettings);
  const [effects, setEffects] = useState<AudioEffectId[]>(centralEffects);
  const [tuningDirty, setTuningDirty] = useState(false);
  const [effectsDirty, setEffectsDirty] = useState(false);
  const [selectedOutputKey, setSelectedOutputKey] = useState('');
  const [pendingPlaybackJobId, setPendingPlaybackJobId] = useState('');
  const [completedPlaybackJob, setCompletedPlaybackJob] = useState<JobRecord | null>(null);
  const pendingPlaybackJobQuery = useQuery({
    queryKey: ['platform', 'jobs', pendingPlaybackJobId],
    queryFn: () => omnixApiClient.getJob(pendingPlaybackJobId),
    enabled: Boolean(pendingPlaybackJobId),
    refetchInterval: (query) => (ACTIVE_STATUSES.has(query.state.data?.status ?? '') ? 1000 : false),
  });

  // Central settings apply until the user changes the studio's own copy.
  useEffect(() => {
    const revision = settingsQuery.data?.profile.revision;
    if (!revision || appliedSettingsRevision.current === revision) return;
    if (!tuningDirty) setOutputSettings(centralOutputSettings);
    if (!effectsDirty) setEffects(centralEffects);
    appliedSettingsRevision.current = revision;
  }, [centralEffects, centralOutputSettings, effectsDirty, settingsQuery.data?.profile.revision, tuningDirty]);

  const scriptSegments = useMemo(() => parseScriptSegments(scriptText), [scriptText]);
  const parsedSpeakers = useMemo(() => parseScriptSpeakers(scriptText), [scriptText]);
  const allAssets = useMemo(() => assetsQuery.data?.assets ?? [], [assetsQuery.data?.assets]);
  const profileAssets = useMemo(() => allAssets.filter((asset) => asset.type === 'voice_profile'), [allAssets]);
  const latestResultAsset = firstResultAsset(allAssets.filter((asset) => asset.type === 'audio'));
  const engineId = selectedEngine?.id || moduleDefaults.providerId || '';
  const deliverySupported = Boolean(selectedEngine?.delivery_instruction);

  const voiceFor = (speaker: ScriptSpeakerRow): string =>
    speakerVoiceAssignments[speaker.name] ?? voiceReference(findMatchingVoice(speaker.name, profileAssets)) ?? voiceReference(profileAssets[0]) ?? '';
  const deliveryFor = (speaker: ScriptSpeakerRow): string => speakerDelivery[speaker.name] ?? '';

  const casting = () => Object.fromEntries(parsedSpeakers.map((speaker) => [speaker.name, {
    voice_id: voiceFor(speaker),
    delivery_instruction: deliverySupported ? deliveryFor(speaker).trim() : '',
  }]));
  const saved = useSavedScript({
    scriptText,
    setScriptText,
    buildWrite: () => ({
      title: scriptTitle.trim() || saved.openScript?.title || parsedSpeakers.map((speaker) => speaker.name).join(', ') || 'Untitled script',
      text: scriptText,
      engine: engineId,
      settings: { output_settings: outputSettings, audio_effects: effects },
      casting: casting(),
    }),
  });

  /** A render of the open saved script (takes are kept) or of the editor text alone. */
  const createJobMutation = useMutation({
    mutationFn: async (renderLineIds?: string[]) => {
      if (!scriptText.trim()) throw new Error('Enter script text before generating speech.');
      const script = await saved.ensureSaved();
      const primary = parsedSpeakers[0] ?? { name: 'Narrator', count: 0 };
      const segments = script
        ? script.lines.map((line) => ({
          index: line.position, speaker: line.speaker, text: line.text, line_id: line.id,
          ...(line.pause_before_ms != null ? { pause_before_ms: line.pause_before_ms } : {}),
        }))
        : scriptSegments;
      return omnixApiClient.createJob({
        module: 'voice',
        type: parsedSpeakers.length > 1 ? 'tts.multi_speaker_synthesize' : 'tts.synthesize',
        resource_class: 'gpu:tts',
        priority: 0,
        input_payload: {
          ...(script ? { script_id: script.id } : {}),
          ...(script && renderLineIds ? { render_line_ids: renderLineIds } : {}),
          text: scriptText,
          // The engine the inspector shows; the job is pinned to it and never switches engines.
          provider_id: engineId || null,
          language: moduleDefaults.language || null,
          speaker: primary.name,
          voice_id: voiceFor(primary) || null,
          script_mode: parsedSpeakers.length > 1 ? 'multi_speaker' : 'single_speaker',
          script_speakers: parsedSpeakers,
          script_segments: segments,
          character_voice_assignments: parsedSpeakers.map((speaker) => ({
            speaker: speaker.name,
            voice_id: voiceFor(speaker) || null,
            ...(deliverySupported && deliveryFor(speaker).trim() ? { delivery_instruction: deliveryFor(speaker).trim() } : {}),
            line_count: speaker.count,
          })),
          output_settings: outputSettings,
          audio_effects: effects,
          save_output: true,
        },
        stages: voiceSynthesisStages(renderLineIds ? segments.filter((segment) => 'line_id' in segment && renderLineIds.includes(String(segment.line_id))) : segments),
      });
    },
    onMutate: () => {
      setSelectedOutputKey('');
      setPendingPlaybackJobId('');
      audioRef.current?.pause();
    },
    onSuccess: async (job) => {
      const output = extractPlayableOutputs([job])[0];
      if (output) {
        setCompletedPlaybackJob(job);
        setSelectedOutputKey(output.key);
      } else if (job.status !== 'failed') {
        setPendingPlaybackJobId(job.id);
      }
      await refreshJobsAndAssets();
    },
  });

  const previewVoiceMutation = useMutation({
    mutationFn: (asset: VoiceAsset) => {
      const voiceId = voiceReference(asset);
      const voiceName = voiceAssetName(asset);
      const text = `This is a preview of ${voiceName} speaking in Voice Studio.`;
      return omnixApiClient.createJob({
        module: 'voice',
        type: 'tts.synthesize',
        resource_class: 'gpu:tts',
        priority: 1,
        input_payload: {
          text,
          provider_id: engineId || null,
          language: moduleDefaults.language || null,
          speaker: voiceName,
          voice_id: voiceId,
          script_mode: 'single_speaker',
          script_speakers: [{ name: 'Preview', count: 1 }],
          script_segments: [{ index: 0, speaker: 'Preview', text }],
          character_voice_assignments: [{ speaker: 'Preview', voice_id: voiceId, line_count: 1 }],
          output_settings: outputSettings,
          audio_effects: effects,
          save_output: true,
        },
        stages: voiceSynthesisStages([{ index: 0, speaker: 'Preview', text }]),
      });
    },
    onSuccess: async (job) => {
      const output = extractPlayableOutputs([job])[0];
      if (output) setSelectedOutputKey(output.key);
      await refreshJobsAndAssets();
    },
  });

  const deleteVoiceMutation = useMutation({
    mutationFn: (asset: VoiceAsset) => omnixApiClient.deleteVoiceAsset(voiceAssetId(asset)),
    onSuccess: async (_result, asset) => {
      const deleted = voiceAssetId(asset);
      setSpeakerVoiceAssignments((current) => Object.fromEntries(Object.entries(current).filter(([, voiceId]) => voiceId !== deleted)));
      setMessage(`${voiceAssetName(asset)} was deleted from the Voice Library.`);
      await queryClient.invalidateQueries({ queryKey: ['platform', 'assets'] });
    },
  });

  const exportMutation = useMutation({
    mutationFn: ({ assetId, request }: { assetId: string; request: ExportRequest }) => omnixApiClient.createJob({
      module: 'voice',
      type: 'voice.export',
      resource_class: 'cpu',
      priority: 1,
      input_payload: { asset_id: assetId, format: request.format, sample_rate: request.sampleRate, loudness: request.loudness },
      stages: [{ id: 'export', label: `Export as ${request.format}`, resource_class: 'cpu', status: 'queued' }],
    }),
    onSuccess: async (job) => {
      setMessage(job.status === 'failed' ? voiceJobErrorMessage(job) : 'Export queued; it appears under Export when ready.');
      await refreshJobsAndAssets();
    },
  });

  const restitchMutation = useMutation({
    mutationFn: async () => {
      const script = await saved.ensureSaved();
      if (!script) throw new Error('Save the script before rebuilding it from takes.');
      return omnixApiClient.createJob({
        module: 'voice',
        type: 'voice.restitch',
        resource_class: 'cpu',
        priority: 0,
        input_payload: { script_id: script.id, output_settings: outputSettings, audio_effects: effects },
        stages: [{ id: 'restitch', label: 'Assemble selected takes', resource_class: 'cpu', status: 'queued' }],
      });
    },
    onSuccess: async (job) => {
      const output = extractPlayableOutputs([job])[0];
      if (output) setSelectedOutputKey(output.key);
      else if (job.status !== 'failed') setPendingPlaybackJobId(job.id);
      else setMessage(voiceJobErrorMessage(job));
      await refreshJobsAndAssets();
    },
  });

  const selectTakeMutation = useMutation({
    mutationFn: ({ lineId, takeId }: { lineId: string; takeId: string }) => {
      if (!saved.openScript) throw new Error('No saved script is open.');
      return voiceApiClient.selectTake(saved.openScript.id, lineId, takeId);
    },
    onSuccess: (script) => {
      saved.setOpenScript(script);
      setMessage('Take selected. Rebuild from takes to hear the whole script with it.');
    },
  });

  const retryMutation = useMutation({
    mutationFn: (jobId: string) => voiceApiClient.retryJob(jobId),
    onSuccess: async (job) => {
      setMessage(`Retry queued: ${job.id}`);
      if (job.type.startsWith('tts.') || job.type === 'voice.restitch') setPendingPlaybackJobId(job.id);
      await refreshJobsAndAssets();
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : 'The job could not be retried.'),
  });

  const cancelMutation = useMutation({
    mutationFn: (jobId: string) => omnixApiClient.cancelJob(jobId, 'Cancelled in Voice Studio'),
    onSettled: async () => { await queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] }); },
  });

  async function refreshJobsAndAssets() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] }),
      queryClient.invalidateQueries({ queryKey: ['platform', 'assets'] }),
    ]);
  }

  const queriedVoiceJobs = useMemo(() => jobsQuery.data?.jobs.filter((job) => job.module === 'voice' || job.module === 'voice-cloning') ?? [], [jobsQuery.data?.jobs]);
  const voiceJobs = useMemo(
    () => mergeVoiceJobs([...queriedVoiceJobs, createJobMutation.data, previewVoiceMutation.data, exportMutation.data, pendingPlaybackJobQuery.data, completedPlaybackJob ?? undefined]),
    [completedPlaybackJob, createJobMutation.data, exportMutation.data, pendingPlaybackJobQuery.data, previewVoiceMutation.data, queriedVoiceJobs],
  );
  const playableOutputs = useMemo(() => extractPlayableOutputs(voiceJobs), [voiceJobs]);
  const isPendingSpeechOutput = createJobMutation.isPending || Boolean(pendingPlaybackJobId);
  const currentOutput = isPendingSpeechOutput ? null : playableOutputs.find((output) => output.key === selectedOutputKey) ?? playableOutputs[0] ?? null;
  const previousOutput = previousTake(playableOutputs, currentOutput);
  const currentOutputTitle = isPendingSpeechOutput ? 'Generating new speech…' : currentOutput?.title ?? (latestResultAsset ? voiceAssetName(latestResultAsset) : `${module.label} output`);
  const playback = useTakePlayback({
    audioRef, outputs: playableOutputs, current: currentOutput, previous: previousOutput,
    selectOutput: setSelectedOutputKey, onMessage: setMessage,
  });
  const effectiveDuration = playback.playbackDuration || currentOutput?.duration || estimateDurationFromText(scriptText);
  const generationFailure = voiceJobErrorMessage(createJobMutation.data) || voiceJobErrorMessage(previewVoiceMutation.data);
  const takeExports = useMemo(() => allAssets
    .filter((asset) => asset.type === 'export' && Boolean(currentOutput?.assetId) && parentIds(asset).includes(currentOutput?.assetId ?? ''))
    .map((asset) => ({ id: voiceAssetId(asset), title: voiceAssetName(asset) })), [allAssets, currentOutput?.assetId]);

  useEffect(() => {
    if (!pendingPlaybackJobId || !pendingPlaybackJobQuery.data) return;
    const job = pendingPlaybackJobQuery.data;
    if (job.status === 'failed') {
      setPendingPlaybackJobId('');
      setMessage(voiceJobErrorMessage(job));
      return;
    }
    const output = extractPlayableOutputs([job])[0];
    if (!output) return;
    setCompletedPlaybackJob(job);
    setSelectedOutputKey(output.key);
    setPendingPlaybackJobId('');
    void refreshJobsAndAssets();
    void saved.reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refresh helper is stable in behaviour
  }, [pendingPlaybackJobId, pendingPlaybackJobQuery.data]);

  useEffect(() => {
    if (playableOutputs.length > 0 && !playableOutputs.some((output) => output.key === selectedOutputKey)) {
      setSelectedOutputKey(playableOutputs[0].key);
    }
  }, [playableOutputs, selectedOutputKey]);

  function castVoice(asset: VoiceAsset) {
    const speaker = parsedSpeakers[0]?.name ?? 'Narrator';
    setSpeakerVoiceAssignments((current) => ({ ...current, [speaker]: voiceReference(asset) }));
    setMessage(`Cast ${voiceAssetName(asset)} as ${speaker}.`);
    selectTool('speak');
  }

  function requestVoiceDelete(asset: VoiceAsset) {
    const name = voiceAssetName(asset);
    if (typeof window !== 'undefined' && !window.confirm(`Delete “${name}”? This permanently removes the cloned voice audio and metadata.`)) return;
    deleteVoiceMutation.mutate(asset);
  }

  function previewVoiceById(voiceId: string) {
    const asset = findVoiceByReference(voiceId, profileAssets);
    if (asset) previewVoiceMutation.mutate(asset);
    else setMessage('Select a library voice before previewing.');
  }

  function selectTool(next: StudioToolId) {
    setTool(next);
    rememberTool(next);
  }

  function saveScript() {
    try {
      window.localStorage.setItem(SCRIPT_STORAGE_KEY, scriptText);
      setMessage('Script saved locally.');
    } catch {
      setMessage('This browser blocked local storage; the script was not saved.');
    }
  }

  function loadScript() {
    let saved: string | null = null;
    try {
      saved = window.localStorage.getItem(SCRIPT_STORAGE_KEY);
    } catch {
      saved = null;
    }
    setScriptText(saved || DEFAULT_SCRIPT);
    setMessage(saved ? 'Loaded saved script.' : 'Loaded example script.');
  }

  const engineStatus = describeEngine(enginesQuery.data, selectedEngine);
  const tools = shippedTools();

  return (
    <WorkspacePanel label={module.label}>
      <div className="voice-studio-app">
        <header className="voice-final-header">
          <div><Title order={2}>Voice Studio</Title><Text size="sm">Write, cast and render speech; design, clone and manage voices; transcribe recordings.</Text></div>
          <TtsEnginePicker />
        </header>

        <div className={tool === 'speak' ? 'voice-studio-body with-inspector' : 'voice-studio-body'}>
          <nav className="voice-tool-rail" aria-label="Voice Studio tools">
            {tools.map((entry) => (
              <button key={entry.id} type="button" className={tool === entry.id ? 'active' : ''} aria-current={tool === entry.id ? 'page' : undefined} title={entry.summary} onClick={() => selectTool(entry.id)}>{entry.label}</button>
            ))}
          </nav>

          <main className="voice-canvas" aria-label={tools.find((entry) => entry.id === tool)?.label ?? 'Speak'}>
            {tool === 'speak' ? (
              <section className="voice-speak" aria-label="Speak">
                <div className="voice-section-head">
                  <div><h3>Script</h3><Text size="sm">Tag lines with <code>name:</code>, add <code>{'{pause 600ms}'}</code> for silence. Ctrl+Enter renders.</Text></div>
                  <div className="script-actions">
                    <PushToTalkButton label="Hold to dictate a line" onText={(text) => setScriptText((current) => (current.trim() ? `${current.replace(/\s+$/, '')}
${text}` : text))} />
                    <Button size="xs" variant="subtle" onClick={() => { setScriptText(''); saved.close(); }}>New</Button>
                    {!saved.available ? <Button size="xs" variant="subtle" onClick={loadScript}>Load Script</Button> : null}
                    {!saved.available ? <Button size="xs" variant="subtle" onClick={saveScript}>Save Script</Button> : null}
                  </div>
                </div>
                {saved.available ? (
                  <div className="voice-script-library" aria-label="Saved scripts">
                    <label>Saved scripts<select aria-label="Saved scripts" value={saved.openScript?.id ?? ''} onChange={(event) => { setScriptTitle(''); if (event.currentTarget.value) saved.open(event.currentTarget.value); else saved.close(); }}>
                      <option value="">Unsaved script</option>
                      {saved.scripts.map((entry) => <option key={entry.id} value={entry.id}>{entry.title || 'Untitled script'}</option>)}
                    </select></label>
                    <label>Title<input aria-label="Script title" value={scriptTitle || saved.openScript?.title || ''} placeholder="Untitled script" onChange={(event) => setScriptTitle(event.currentTarget.value)} /></label>
                    <Button size="xs" variant="light" loading={saved.saving} onClick={() => void saved.save().then(() => setMessage('Script saved.')).catch((error: unknown) => setMessage(error instanceof Error ? error.message : 'The script could not be saved.'))}>{saved.openScript ? (saved.dirty ? 'Save changes' : 'Saved') : 'Save script'}</Button>
                    {saved.openScript ? <Button size="xs" variant="subtle" onClick={() => void saved.save(true).then(() => setMessage('Saved as a new script.'))}>Save as new</Button> : null}
                    {saved.openScript ? <Button size="xs" variant="subtle" loading={restitchMutation.isPending} disabled={!saved.openScript.lines.every((line) => line.takes.length)} title="Assemble the whole script from each line's selected take, without rendering anything." onClick={() => restitchMutation.mutate()}>Rebuild from takes</Button> : null}
                    {saved.openScript ? <Button size="xs" variant="subtle" color="red" onClick={() => { if (window.confirm('Delete this saved script and its take list? The audio stays in the library.')) saved.remove(); }}>Delete</Button> : null}
                  </div>
                ) : null}
                <VoiceScriptEditor value={scriptText} onChange={setScriptText} onGenerate={() => createJobMutation.mutate(undefined)} />
                <ScriptCast
                  speakers={parsedSpeakers}
                  segments={scriptSegments}
                  assets={profileAssets}
                  voiceFor={voiceFor}
                  deliveryFor={deliveryFor}
                  deliverySupported={deliverySupported}
                  engineLabel={selectedEngine?.label ?? ''}
                  onVoiceChange={(speaker, voiceId) => setSpeakerVoiceAssignments((current) => ({ ...current, [speaker]: voiceId }))}
                  onDeliveryChange={(speaker, instruction) => setSpeakerDelivery((current) => ({ ...current, [speaker]: instruction }))}
                  onPreview={previewVoiceById}
                  savedLines={saved.openScript && !saved.dirty ? saved.openScript.lines : undefined}
                  onRegenerateLine={(lineId) => createJobMutation.mutate([lineId])}
                  onSelectTake={(lineId, takeId) => selectTakeMutation.mutate({ lineId, takeId })}
                  busyLineId={createJobMutation.isPending && createJobMutation.variables?.length === 1 ? createJobMutation.variables[0] : ''}
                />
                <div className="voice-generate-row">
                  <Text size="xs">Estimated duration: ~ {Math.round(estimateDurationFromText(scriptText))} s</Text>
                  <Button className="generate-speech-button" type="button" loading={createJobMutation.isPending} onClick={() => createJobMutation.mutate(undefined)}>Generate Speech</Button>
                </div>
                {message ? <div className="voice-success-note" role="status">{message}</div> : null}
                <FeatureSubmitFeedback error={createJobMutation.error} errorPrefix="TTS request" isError={createJobMutation.isError} isPending={createJobMutation.isPending} jobId={createJobMutation.data?.status === 'failed' ? undefined : createJobMutation.data?.id} pendingMessage="Queueing TTS job…" successPrefix="TTS job queued" />
                <FeatureValidationMessage show={Boolean(generationFailure)} message={generationFailure} />
                {currentOutput?.assetId ? <RenderCheckPanel key={currentOutput.assetId} assetId={currentOutput.assetId} /> : null}
              </section>
            ) : tool === 'design' ? (
              <DesignTool onSaved={(name) => { selectTool('voices'); setMessage(`${name} is in your voice library.`); }} />
            ) : tool === 'models' ? (
              <SpeechModelsPanel />
            ) : tool === 'audio-tools' ? (
              <AudioToolsTool assets={allAssets} />
            ) : tool === 'batch' ? (
              <BatchTool assets={allAssets} />
            ) : tool === 'dub' ? (
              <DubbingTool />
            ) : tool === 'transcribe' ? (
              <TranscribeTool
                assets={allAssets}
                onMakeVoice={(seed) => { setCloneSeed(seed); selectTool('voices'); setMessage(`${seed.name}'s sample is ready to clone below.`); }}
              />
            ) : (
              <section className="voice-voices" aria-label="Voices">
                <CloneVoicePanel
                  defaults={{
                    revision: settingsQuery.data?.profile.revision ?? '',
                    providerId: moduleDefaults.voiceCloningProviderId,
                    language: moduleDefaults.cloningLanguage,
                    quality: moduleDefaults.cloningQuality,
                    sttProviderId: moduleDefaults.sttProviderId,
                  }}
                  onFinished={refreshJobsAndAssets}
                  seed={cloneSeed}
                />
                <VoiceLibraryGrid
                  assets={profileAssets}
                  loading={assetsQuery.isLoading}
                  failed={assetsQuery.isError}
                  refreshing={assetsQuery.isFetching}
                  onRefresh={() => void assetsQuery.refetch()}
                  onPreview={(asset) => previewVoiceMutation.mutate(asset)}
                  onUse={castVoice}
                  onDelete={requestVoiceDelete}
                  deletingId={deleteVoiceMutation.isPending && deleteVoiceMutation.variables ? voiceAssetId(deleteVoiceMutation.variables) : ''}
                  deleteFailed={deleteVoiceMutation.isError}
                />
                {message ? <div className="voice-success-note" role="status">{message}</div> : null}
              </section>
            )}
          </main>

          {tool === 'speak' ? (
            <VoiceInspector
              engine={selectedEngine}
              engineStatus={engineStatus}
              outputSettings={outputSettings}
              onSettingChange={(name, value) => { setTuningDirty(true); setOutputSettings((current) => ({ ...current, [name]: value })); }}
              onResetTuning={() => { setOutputSettings(centralOutputSettings); setTuningDirty(false); }}
              effects={effects}
              onToggleEffect={(effect) => { setEffectsDirty(true); setEffects((current) => effectIds(current.includes(effect) ? current.filter((entry) => entry !== effect) : [...current, effect])); }}
              onResetEffects={() => { setEffects(centralEffects); setEffectsDirty(false); }}
              canExport={Boolean(currentOutput?.assetId)}
              exportPending={exportMutation.isPending}
              exportError={exportMutation.isError ? (exportMutation.error instanceof Error ? exportMutation.error.message : 'Export failed.') : ''}
              exports={takeExports}
              onExport={(request) => currentOutput?.assetId && exportMutation.mutate({ assetId: currentOutput.assetId, request })}
            />
          ) : null}
        </div>

        <TransportBar
          audioRef={audioRef}
          current={currentOutput}
          previous={previousOutput}
          title={`${currentOutputTitle} · ${parsedSpeakers.length} speaker${parsedSpeakers.length === 1 ? '' : 's'}`}
          isPlaying={playback.isPlaying}
          playbackTime={playback.playbackTime}
          duration={effectiveDuration}
          onTogglePlayback={() => void playback.toggle()}
          onSeek={playback.seek}
          onSelectOffset={playback.selectOffset}
          onCompare={playback.compare}
          onDownload={playback.download}
          onLoadedDuration={playback.loadedDuration}
          onTimeUpdate={playback.setPlaybackTime}
          onEnded={() => playback.setIsPlaying(false)}
        />
        <JobsTray
          jobs={voiceJobs}
          playableJobIds={new Set(playableOutputs.map((output) => output.jobId))}
          selectedJobId={currentOutput?.jobId ?? ''}
          onSelect={(jobId) => {
            const output = playableOutputs.find((entry) => entry.jobId === jobId);
            if (output) setSelectedOutputKey(output.key);
          }}
          onCancel={(jobId) => cancelMutation.mutate(jobId)}
          cancelling={cancelMutation.isPending ? String(cancelMutation.variables ?? '') : ''}
          onRetry={(jobId) => retryMutation.mutate(jobId)}
          retrying={retryMutation.isPending ? String(retryMutation.variables ?? '') : ''}
        />
      </div>
    </WorkspacePanel>
  );
}

function previousTake(outputs: PlayableVoiceOutput[], current: PlayableVoiceOutput | null): PlayableVoiceOutput | null {
  if (!current) return null;
  const index = outputs.findIndex((output) => output.key === current.key);
  return index >= 0 && index + 1 < outputs.length ? outputs[index + 1] : null;
}

function parentIds(asset: VoiceAsset): string[] {
  const value = (asset as { parent_asset_ids?: unknown }).parent_asset_ids;
  return Array.isArray(value) ? value.filter((entry): entry is string => typeof entry === 'string') : [];
}

function describeEngine(data: Awaited<ReturnType<typeof voiceApiClient.listTtsEngines>> | undefined, engine: { label: string; installed: boolean; unavailable_reason: string } | undefined): string {
  if (!data || !engine) return '';
  const phase = data.switch.phase;
  if (phase === 'unloading' || phase === 'loading' || phase === 'preparing_voices') return 'Switching engines…';
  if (phase === 'failed') return `Did not load: ${data.switch.error || 'unknown error'}`;
  if (!engine.installed) return engine.unavailable_reason || 'Not installed';
  return 'Loaded';
}

function estimateDurationFromText(text: string): number {
  return Math.max(1, Math.min(600, text.trim().length / 14));
}

function voiceSynthesisStages(segments: ScriptSegmentRow[]) {
  return [
    { id: 'parse-script', label: 'Detect script characters', resource_class: 'cpu' as const, status: 'queued' as const },
    { id: 'assign-voices', label: 'Apply voice assignments', resource_class: 'cpu' as const, status: 'queued' as const },
    ...segments.map((segment, index) => ({ id: `synthesize-${index.toString().padStart(4, '0')}`, label: `Generate ${segment.speaker} stage ${index + 1}`, resource_class: 'gpu:tts' as const, status: 'queued' as const })),
    { id: 'stitch-audio', label: 'Assemble with pauses and effects', resource_class: 'cpu' as const, status: 'queued' as const },
    { id: 'store-audio', label: 'Save audio output', resource_class: 'cpu' as const, status: 'queued' as const },
  ];
}
