import { useEffect, useMemo, useRef, useState } from 'react';
import { omnixApiClient, type AssetListResponse, type JobRecord } from '../../api/client';
import { assignmentRowsFromSegments, mapStoryToAudioSegments, speakerRowsFromSegments, type StoryAudioScriptSegment } from './storyAudioMapper';

export type StoryAudioVoiceOption = {
  id: string;
  label: string;
};

export type StoryAudioSegment = StoryAudioScriptSegment & { title?: string };

type StoryAudioStatus = 'ready' | 'loading_voices' | 'queued' | 'running' | 'completed' | 'failed';

type StoryAudioJobOutputRef = {
  data_url?: unknown;
  audio_url?: unknown;
  url?: unknown;
  provider_fallback?: unknown;
  provider_success?: unknown;
  segments?: unknown;
};

type StoryAudioStreamControlMessage =
  | { type: 'start'; total_segments?: number }
  | { type: 'segment'; index?: number; speaker?: string; text?: string }
  | { type: 'done'; job_id?: string }
  | { type: 'stopped' }
  | { type: 'error'; message?: string; error?: string };

type StoryAudioRealtimeResult = {
  audioUrl: string;
  chunkCount: number;
};

type StoryAudioRealtimeCallbacks = {
  signal: AbortSignal;
  onProgress: (progress: number) => void;
  onStatusMessage: (message: string) => void;
};

const STORY_AUDIO_SELECTED_VOICE_KEY = 'omnix.storyteller.audio.selectedVoiceId';
const STORY_AUDIO_POLL_INTERVAL_MS = 1_500;
const STORY_AUDIO_MAX_POLLS = 160;
const STORY_AUDIO_STREAM_SAMPLE_RATE = 24_000;

export function StoryAudioPanel() {
  const [voices, setVoices] = useState<StoryAudioVoiceOption[]>([]);
  const [selectedVoiceId, setSelectedVoiceId] = useState(() => readSelectedVoiceId());
  const [status, setStatus] = useState<StoryAudioStatus>('ready');
  const [statusMessage, setStatusMessage] = useState('Ready to narrate the full story.');
  const [progress, setProgress] = useState(0);
  const [jobId, setJobId] = useState('');
  const [audioSource, setAudioSource] = useState('');
  const [filename, setFilename] = useState('story-audio.wav');
  const [storySnapshot, setStorySnapshot] = useState(() => readStorySnapshot());
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const generationRunRef = useRef(0);
  const streamAbortRef = useRef<(() => void) | null>(null);

  const canGenerate = Boolean(storySnapshot.text.trim()) && status !== 'queued' && status !== 'running';
  const selectedVoiceLabel = useMemo(() => voiceLabelForId(selectedVoiceId, voices), [selectedVoiceId, voices]);

  useEffect(() => {
    let active = true;
    setStatus('loading_voices');
    setStatusMessage('Loading cloned voices…');
    omnixApiClient.listAssets()
      .then((payload) => {
        if (!active) return;
        const nextVoices = voiceOptionsFromAssets(payload.assets);
        setVoices(nextVoices);
        setSelectedVoiceId((current) => {
          const fallback = current || nextVoices[0]?.id || '';
          persistSelectedVoiceId(fallback);
          return fallback;
        });
        setStatus('ready');
        setStatusMessage(nextVoices.length ? 'Ready to narrate with a cloned voice.' : 'Ready to narrate with the default Voice Studio voice.');
      })
      .catch((error) => {
        if (!active) return;
        setStatus('ready');
        setStatusMessage(error instanceof Error ? error.message : 'Unable to load cloned voices.');
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const refreshSnapshot = () => {
      const next = readStorySnapshot();
      setStorySnapshot((current) => {
        if (current.fingerprint === next.fingerprint) return current;
        streamAbortRef.current?.();
        streamAbortRef.current = null;
        setAudioSource('');
        setProgress(0);
        setJobId('');
        setFilename(`${slugify(next.title || 'story')}-audio.wav`);
        setStatus('ready');
        setStatusMessage('Story changed. Ready to regenerate full-story narration.');
        return next;
      });
    };
    const intervalId = window.setInterval(refreshSnapshot, 1_000);
    window.addEventListener('focus', refreshSnapshot);
    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener('focus', refreshSnapshot);
    };
  }, []);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (audioSource && audio.src !== audioSource) {
      audio.src = audioSource;
      audio.load();
    }
    if (!audioSource && audio.hasAttribute('src')) {
      audio.removeAttribute('src');
      audio.load();
    }
  }, [audioSource]);

  useEffect(() => () => {
    streamAbortRef.current?.();
    streamAbortRef.current = null;
  }, []);

  function handleVoiceChange(value: string): void {
    setSelectedVoiceId(value);
    persistSelectedVoiceId(value);
    setStatusMessage(value ? `Selected ${voiceLabelForId(value, voices) || 'cloned voice'} for narration.` : 'Using the default Voice Studio voice.');
  }

  async function generateStoryAudio(): Promise<void> {
    const snapshot = readStorySnapshot();
    const audioMap = mapStoryToAudioSegments(snapshot.title, snapshot.text, selectedVoiceId);
    const segments = audioMap.segments;
    if (!snapshot.text.trim() || !segments.length) {
      setStatus('failed');
      setStatusMessage('Generate or select a story before creating audio.');
      return;
    }

    const runId = generationRunRef.current + 1;
    generationRunRef.current = runId;
    streamAbortRef.current?.();
    const streamAbortController = new AbortController();
    streamAbortRef.current = () => streamAbortController.abort();
    setStorySnapshot(snapshot);
    setAudioSource('');
    setFilename(`${slugify(snapshot.title || 'story')}-audio.wav`);
    setProgress(2);
    setJobId('');
    setStatus('queued');
    setStatusMessage(`Starting realtime narration for ${segments.length > 1 ? `${segments.length} mapped story segments` : 'the full story'}…`);

    try {
      try {
        const realtimeAudio = await streamStoryAudioViaWebSocket(segments, selectedVoiceId, {
          signal: streamAbortController.signal,
          onProgress: setProgress,
          onStatusMessage: setStatusMessage,
        });
        if (generationRunRef.current !== runId) return;
        streamAbortRef.current = null;
        setAudioSource(realtimeAudio.audioUrl);
        setProgress(100);
        setStatus('completed');
        setStatusMessage(`Realtime story audio complete. Streamed ${realtimeAudio.chunkCount} audio chunks.`);
        return;
      } catch (streamError) {
        if (isAbortError(streamError)) throw streamError;
        if (generationRunRef.current !== runId) return;
        console.warn('[STORY AUDIO] WebSocket stream failed; falling back to job queue:', streamError);
        setProgress((current) => Math.max(current, 5));
        setStatus('queued');
        setStatusMessage('Realtime audio stream unavailable. Falling back to queued Voice Studio generation…');
      }

      const job = await createStoryAudioJob({ title: snapshot.title, text: snapshot.text, segments, voiceId: selectedVoiceId, storyDocumentId: audioMap.document.id });
      if (generationRunRef.current !== runId) return;
      streamAbortRef.current = null;
      setJobId(job.id);
      applyJobProgress(job);
      const earlySource = playableAudioSource(job);
      if (earlySource) {
        setAudioSource(earlySource);
        setStatusMessage('Streaming generated story audio…');
      }

      const completedJob = isTerminalJob(job) ? job : await pollStoryAudioJob(job.id, runId);
      if (generationRunRef.current !== runId) return;
      applyJobProgress(completedJob);
      if (completedJob.status === 'failed') throw new Error(jobErrorMessage(completedJob));
      if (completedJob.status === 'canceled') throw new Error('Voice Studio audio generation was canceled.');
      const source = playableAudioSource(completedJob);
      if (!source) throw new Error('Voice Studio did not return downloadable story audio.');
      setAudioSource(source);
      setProgress(100);
      setStatus('completed');
      setStatusMessage('Full-story audio ready to play or download.');
    } catch (error) {
      if (generationRunRef.current !== runId) return;
      streamAbortRef.current = null;
      setStatus('failed');
      setProgress(0);
      setStatusMessage(isAbortError(error) ? 'Story audio generation was stopped.' : error instanceof Error ? error.message : 'Story audio generation failed.');
    }
  }

  async function pollStoryAudioJob(id: string, runId: number): Promise<JobRecord> {
    let lastJob: JobRecord | null = null;
    for (let index = 0; index < STORY_AUDIO_MAX_POLLS; index += 1) {
      await wait(STORY_AUDIO_POLL_INTERVAL_MS);
      if (generationRunRef.current !== runId) throw new Error('Story audio generation was interrupted.');
      const job = await omnixApiClient.getJob(id);
      lastJob = job;
      applyJobProgress(job);
      const source = playableAudioSource(job);
      if (source && !audioSource) {
        setAudioSource(source);
        setStatusMessage('Streaming generated story audio…');
      }
      if (isTerminalJob(job)) return job;
    }
    throw new Error(lastJob ? 'Story audio generation timed out before completion.' : 'Story audio job never started.');
  }

  function applyJobProgress(job: JobRecord): void {
    setJobId(job.id);
    if (job.progress && job.progress.total > 0) {
      setProgress(Math.min(100, Math.round((job.progress.current / job.progress.total) * 100)));
    } else if (job.status === 'completed') {
      setProgress(100);
    } else if (job.status === 'running' || job.status === 'leased') {
      setProgress((current) => Math.max(current, 35));
    } else if (job.status === 'queued') {
      setProgress((current) => Math.max(current, 10));
    }
    if (job.status === 'queued' || job.status === 'running' || job.status === 'leased') {
      setStatus('running');
      setStatusMessage(`Voice Studio narration ${job.status}.`);
    }
  }

  function downloadAudio(): void {
    if (!audioSource) return;
    const link = document.createElement('a');
    link.href = audioSource;
    link.download = filename;
    link.rel = 'noopener';
    document.body.appendChild(link);
    link.click();
    link.remove();
    setStatusMessage(`Downloaded ${filename}.`);
  }

  return (
    <section className="storyteller-audio-panel" aria-label="Story audio">
      <div className="storyteller-audio-copy">
        <p className="eyebrow">Story audio</p>
        <h3>Generate full-story narration</h3>
        <p>Use the structured story document and Voice Cast assignments to narrate the manuscript. Dialogue blocks use character voices when assigned, while narration and missing voices fall back to the narrator voice.</p>
      </div>
      <div className="storyteller-audio-controls">
        <label>
          Default narrator voice
          <select aria-label="Story audio cloned voice" disabled={status === 'queued' || status === 'running'} value={selectedVoiceId} onChange={(event) => handleVoiceChange(event.currentTarget.value)}>
            <option value="">Default Voice Studio voice</option>
            {voices.map((voice) => <option key={voice.id} value={voice.id}>{voice.label}</option>)}
          </select>
        </label>
        <div className="storyteller-audio-actions">
          <button disabled={!canGenerate} type="button" onClick={() => void generateStoryAudio()}>{status === 'queued' || status === 'running' ? 'Generating audio…' : 'Generate story audio'}</button>
          <button disabled={!audioSource} type="button" onClick={downloadAudio}>Download audio</button>
        </div>
        <div className="storyteller-audio-progress" role="status" aria-live="polite">
          <span>{statusMessage}</span>
          <progress max="100" value={Math.max(0, Math.min(100, progress))}>{progress}%</progress>
        </div>
        <audio ref={audioRef} controls preload="metadata" />
        <small>{jobId ? `Voice job: ${jobId}` : selectedVoiceLabel ? `Narrator voice: ${selectedVoiceLabel}` : 'Narrator voice: default'}</small>
      </div>
    </section>
  );
}

export function readStorySnapshot(): { title: string; text: string; fingerprint: string } {
  const text = extractStoryTextFromDocument(document);
  const title = readStoryTitle();
  return { title, text, fingerprint: fingerprintStoryAudio(text) };
}

export function extractStoryTextFromDocument(root: ParentNode = document): string {
  const prose = root.querySelector('.storyteller-prose') as HTMLElement | null;
  const storyModePage = root.querySelector('.story-mode-page') as HTMLElement | null;
  const manuscript = root.querySelector('[aria-label="Story manuscript"]') as HTMLElement | null;
  const source = prose?.innerText || prose?.textContent || storyModePage?.innerText || storyModePage?.textContent || manuscript?.innerText || manuscript?.textContent || '';
  return normalizeStoryAudioText(source);
}

export function splitStoryAudioSegments(text: string): StoryAudioSegment[] {
  const normalized = normalizeStoryAudioText(text);
  if (!normalized) return [];
  const lines = normalized.split('\n');
  const segments: Array<{ title?: string; lines: string[] }> = [];
  let current: { title?: string; lines: string[] } = { title: 'Story', lines: [] };
  for (const line of lines) {
    const cleaned = line.replace(/^#{1,4}\s*/, '').trim();
    if (/^chapter\s+\d+\s*[:\-–—]?/i.test(cleaned)) {
      if (current.lines.join('\n').trim()) segments.push(current);
      current = { title: cleaned, lines: [cleaned] };
      continue;
    }
    current.lines.push(line);
  }
  if (current.lines.join('\n').trim()) segments.push(current);
  return segments.map((segment, index) => ({ index, speaker: 'Narrator', text: segment.lines.join('\n').trim(), title: segment.title, voice_id: null, character_id: 'narrator', block_id: `legacy-${index}`, chapter_id: `legacy-${index}` }));
}

export function voiceOptionsFromAssets(assets: AssetListResponse['assets']): StoryAudioVoiceOption[] {
  return assets
    .filter((asset) => asset.type === 'voice_profile')
    .map((asset) => ({ id: voiceAssetId(asset), label: voiceAssetLabel(asset) }))
    .filter((voice, index, allVoices) => Boolean(voice.id) && allVoices.findIndex((candidate) => candidate.id === voice.id) === index)
    .sort((left, right) => left.label.localeCompare(right.label));
}

async function createStoryAudioJob({ title, text, segments, voiceId, storyDocumentId }: { title: string; text: string; segments: StoryAudioScriptSegment[]; voiceId: string; storyDocumentId: string }): Promise<JobRecord> {
  return omnixApiClient.createJob({
    module: 'voice',
    type: segments.length > 1 ? 'tts.multi_speaker_synthesize' : 'tts.synthesize',
    resource_class: 'gpu:tts',
    priority: 1,
    input_payload: {
      text,
      provider_id: null,
      speaker: 'Narrator',
      voice_id: voiceId || null,
      script_mode: segments.length > 1 ? 'story_structured_audio' : 'single_speaker',
      story_title: title || null,
      story_document_id: storyDocumentId,
      source_module: 'storyteller',
      source_mapping: 'story_blocks_to_voice_cast',
      script_speakers: speakerRowsFromSegments(segments),
      script_segments: segments,
      character_voice_assignments: assignmentRowsFromSegments(segments),
      save_output: true,
    },
    stages: [
      { id: 'prepare-story-audio', label: 'Prepare structured story narration', resource_class: 'cpu', status: 'queued' },
      ...segments.map((segment) => ({ id: `narrate-story-${String(segment.index + 1).padStart(3, '0')}`, label: `Narrate ${segment.speaker} segment ${segment.index + 1}`, resource_class: 'gpu:tts' as const, status: 'queued' as const })),
      { id: 'stitch-story-audio', label: 'Stitch full story audio', resource_class: 'cpu', status: 'queued' },
      { id: 'store-story-audio', label: 'Save downloadable story audio', resource_class: 'cpu', status: 'queued' },
    ],
  }, { timeoutMs: 120_000, timeoutMessage: 'Story audio generation timed out after 120s.' });
}

function streamStoryAudioViaWebSocket(segments: StoryAudioScriptSegment[], fallbackVoiceId: string, callbacks: StoryAudioRealtimeCallbacks): Promise<StoryAudioRealtimeResult> {
  return new Promise((resolve, reject) => {
    if (typeof window === 'undefined' || typeof WebSocket === 'undefined' || typeof AudioContext === 'undefined') {
      reject(new Error('Realtime story audio requires browser WebSocket and AudioContext support.'));
      return;
    }

    const audioContext = new AudioContext({ sampleRate: STORY_AUDIO_STREAM_SAMPLE_RATE, latencyHint: 'interactive' });
    const pcmChunks: Uint8Array[] = [];
    const voiceMapping = buildVoiceMappingFromSegments(segments, fallbackVoiceId);
    const url = defaultStoryAudioWebSocketUrl(window.location);
    const socket = new WebSocket(url);
    socket.binaryType = 'arraybuffer';
    let finished = false;
    let totalSegments = segments.length;
    let nextPlaybackTime = audioContext.currentTime;

    const cleanup = () => {
      callbacks.signal.removeEventListener('abort', abort);
    };

    const finish = (result: StoryAudioRealtimeResult) => {
      if (finished) return;
      finished = true;
      cleanup();
      try { socket.close(); } catch { /* best-effort */ }
      const drainMs = Math.max(250, Math.round(Math.max(0, nextPlaybackTime - audioContext.currentTime + 0.25) * 1000));
      window.setTimeout(() => { void audioContext.close().catch(() => undefined); }, drainMs);
      resolve(result);
    };

    const fail = (error: unknown) => {
      if (finished) return;
      finished = true;
      cleanup();
      try { socket.close(); } catch { /* best-effort */ }
      void audioContext.close().catch(() => undefined);
      reject(error instanceof Error ? error : new Error('Realtime story audio failed.'));
    };

    function abort() {
      try {
        if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'stop' }));
      } catch { /* best-effort */ }
      fail(makeAbortError('Story audio stream was stopped.'));
    }

    callbacks.signal.addEventListener('abort', abort, { once: true });
    if (callbacks.signal.aborted) {
      abort();
      return;
    }

    socket.onopen = () => {
      if (audioContext.state === 'suspended') void audioContext.resume().catch(() => undefined);
      callbacks.onStatusMessage('Realtime narration connected. Waiting for the first audio chunk…');
      socket.send(JSON.stringify({
        type: 'start',
        segments: segments.map((segment) => ({ speaker: segment.speaker, text: segment.text })),
        voice_mapping: voiceMapping,
        voice_map: voiceMapping,
        default_voices: { narrator: fallbackVoiceId || null, male: fallbackVoiceId || null, female: fallbackVoiceId || null },
        job_id: `story-${Date.now()}`,
      }));
    };

    socket.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        const chunk = event.data.slice(0);
        pcmChunks.push(new Uint8Array(chunk));
        nextPlaybackTime = schedulePcmChunk(audioContext, chunk, nextPlaybackTime);
        return;
      }

      try {
        const message = JSON.parse(String(event.data)) as StoryAudioStreamControlMessage;
        if (message.type === 'start') {
          totalSegments = typeof message.total_segments === 'number' && message.total_segments > 0 ? message.total_segments : totalSegments;
          callbacks.onStatusMessage('Realtime narration streaming…');
          callbacks.onProgress(8);
          return;
        }
        if (message.type === 'segment') {
          const index = typeof message.index === 'number' ? message.index : 0;
          const current = Math.min(totalSegments, index + 1);
          callbacks.onProgress(Math.min(99, Math.max(10, Math.round((current / Math.max(1, totalSegments)) * 100))));
          callbacks.onStatusMessage(`Playing ${message.speaker || 'Narrator'} segment ${current}/${totalSegments} as it streams…`);
          return;
        }
        if (message.type === 'done') {
          callbacks.onProgress(100);
          callbacks.onStatusMessage('Realtime narration complete. Preparing replay/download audio…');
          const audioBlob = pcmChunksToWavBlob(pcmChunks, STORY_AUDIO_STREAM_SAMPLE_RATE);
          finish({ audioUrl: URL.createObjectURL(audioBlob), chunkCount: pcmChunks.length });
          return;
        }
        if (message.type === 'stopped') {
          fail(makeAbortError('Story audio stream was stopped.'));
          return;
        }
        if (message.type === 'error') {
          fail(new Error(message.message || message.error || 'Realtime story audio stream failed.'));
        }
      } catch (error) {
        fail(error);
      }
    };

    socket.onerror = () => fail(new Error('Realtime story audio websocket failed.'));
    socket.onclose = () => {
      if (!finished) fail(new Error('Realtime story audio websocket closed before completion.'));
    };
  });
}

function buildVoiceMappingFromSegments(segments: StoryAudioScriptSegment[], fallbackVoiceId: string): Record<string, string> {
  const mapping: Record<string, string> = {};
  for (const segment of segments) {
    const voiceId = segment.voice_id || (segment.speaker === 'Narrator' ? fallbackVoiceId : '') || '';
    if (!voiceId) continue;
    mapping[segment.speaker] = voiceId;
    mapping[segment.speaker.toLowerCase().trim()] = voiceId;
  }
  return mapping;
}

function defaultStoryAudioWebSocketUrl(locationLike: Pick<Location, 'protocol' | 'host'>): string {
  const protocol = locationLike.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${locationLike.host}/ws/audiobook`;
}

function schedulePcmChunk(audioContext: AudioContext, chunk: ArrayBuffer, nextPlaybackTime: number): number {
  const pcm16 = new Int16Array(chunk);
  if (!pcm16.length) return nextPlaybackTime;

  const audioBuffer = audioContext.createBuffer(1, pcm16.length, STORY_AUDIO_STREAM_SAMPLE_RATE);
  const channel = audioBuffer.getChannelData(0);
  for (let index = 0; index < pcm16.length; index += 1) {
    channel[index] = Math.max(-1, Math.min(1, pcm16[index] / 32768));
  }

  const source = audioContext.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(audioContext.destination);
  const startAt = Math.max(audioContext.currentTime + 0.02, nextPlaybackTime);
  source.start(startAt);
  return startAt + audioBuffer.duration;
}

function pcmChunksToWavBlob(chunks: Uint8Array[], sampleRate: number): Blob {
  const dataSize = chunks.reduce((sum, chunk) => sum + chunk.byteLength, 0);
  const header = new ArrayBuffer(44);
  const view = new DataView(header);
  const channels = 1;
  const byteRate = sampleRate * channels * 2;
  const blockAlign = channels * 2;

  writeAscii(view, 0, 'RIFF');
  view.setUint32(4, 36 + dataSize, true);
  writeAscii(view, 8, 'WAVE');
  writeAscii(view, 12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, channels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, 16, true);
  writeAscii(view, 36, 'data');
  view.setUint32(40, dataSize, true);

  const parts: BlobPart[] = [header];
  for (const chunk of chunks) {
    parts.push(chunk.buffer.slice(chunk.byteOffset, chunk.byteOffset + chunk.byteLength));
  }
  return new Blob(parts, { type: 'audio/wav' });
}

function writeAscii(view: DataView, offset: number, value: string): void {
  for (let index = 0; index < value.length; index += 1) view.setUint8(offset + index, value.charCodeAt(index));
}

function makeAbortError(message: string): Error {
  const error = new Error(message);
  error.name = 'AbortError';
  return error;
}

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError';
}

function playableAudioSource(job: JobRecord): string {
  const refs = Array.isArray(job.output_refs) ? job.output_refs : [];
  for (const ref of refs) {
    const output = ref as StoryAudioJobOutputRef | null;
    if (!output || isFallbackVoiceOutput(output)) continue;
    const dataUrl = typeof output.data_url === 'string' ? output.data_url : '';
    if (dataUrl.startsWith('data:audio/')) return dataUrl;
    const audioUrl = typeof output.audio_url === 'string' ? output.audio_url : '';
    if (audioUrl) return audioUrl;
    const url = typeof output.url === 'string' ? output.url : '';
    if (url && /\.(wav|mp3|ogg|webm)(\?|$)/i.test(url)) return url;
  }
  return '';
}

function isFallbackVoiceOutput(ref: StoryAudioJobOutputRef): boolean {
  if (ref.provider_fallback === true || ref.provider_success === false) return true;
  const segments = Array.isArray(ref.segments) ? ref.segments : [];
  return segments.some((segment) => {
    const row = segment as { provider_fallback?: unknown; provider_success?: unknown } | null;
    return row?.provider_fallback === true || row?.provider_success === false;
  });
}

function isTerminalJob(job: JobRecord): boolean {
  return job.status === 'completed' || job.status === 'failed' || job.status === 'canceled';
}

function jobErrorMessage(job: JobRecord): string {
  const error = job.error as { message?: unknown } | null | undefined;
  return typeof error?.message === 'string' ? error.message : 'Voice Studio audio generation failed.';
}

function readStoryTitle(): string {
  return (document.querySelector('.storyteller-project-copy h1') as HTMLElement | null)?.innerText.trim() || 'Untitled story';
}

function normalizeStoryAudioText(value: string): string {
  return value.replace(/\r\n/g, '\n').split('\n').map((line) => line.trim()).filter(Boolean).join('\n\n').trim();
}

function fingerprintStoryAudio(text: string): string {
  return `${text.length}:${text.slice(0, 80)}:${text.slice(-80)}`;
}

function voiceAssetId(asset: AssetListResponse['assets'][number]): string {
  return stringValue(asset.storage_path) || stringValue(asset.metadata?.voice_id) || stringValue(asset.metadata?.profile_id) || stringValue(asset.metadata?.id) || asset.id;
}

function voiceAssetLabel(asset: AssetListResponse['assets'][number]): string {
  return stringValue(asset.metadata?.profile_name) || stringValue(asset.metadata?.name) || stringValue(asset.metadata?.voice_name) || basename(asset.storage_path) || asset.id.replace(/^voice-cloning:/, '').replace(/^asset:/, '');
}

function voiceLabelForId(voiceId: string, voices: StoryAudioVoiceOption[]): string {
  return voices.find((voice) => voice.id === voiceId)?.label || voiceId;
}

function stringValue(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function basename(path: string | undefined): string {
  return path?.split(/[\\/]/).pop()?.replace(/\.[^.]+$/, '') || '';
}

function slugify(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'story';
}

function readSelectedVoiceId(): string {
  try {
    return typeof window !== 'undefined' ? window.localStorage.getItem(STORY_AUDIO_SELECTED_VOICE_KEY) ?? '' : '';
  } catch {
    return '';
  }
}

function persistSelectedVoiceId(value: string): void {
  try {
    if (!value) window.localStorage.removeItem(STORY_AUDIO_SELECTED_VOICE_KEY);
    else window.localStorage.setItem(STORY_AUDIO_SELECTED_VOICE_KEY, value);
  } catch {
    // Voice selection persistence is best-effort.
  }
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}
