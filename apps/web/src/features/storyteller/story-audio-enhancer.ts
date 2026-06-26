type StoryAudioAsset = {
  id: string;
  module?: string;
  type: string;
  mime_type?: string;
  storage_path?: string;
  created_at?: string;
  metadata?: Record<string, unknown>;
};

type StoryAudioJob = {
  id: string;
  module: string;
  type: string;
  status: string;
  resource_class?: string;
  progress?: { current: number; total: number };
  output_refs?: unknown[];
  error?: { message?: string } | null;
};

type StoryAudioVoiceOption = {
  id: string;
  label: string;
};

type StoryAudioSegment = {
  index: number;
  speaker: string;
  text: string;
  title?: string;
};

type StoryAudioState = {
  audioSource: string;
  filename: string;
  isGenerating: boolean;
  jobId: string;
  lastStoryFingerprint: string;
  progress: number;
  selectedVoiceId: string;
  status: string;
  voices: StoryAudioVoiceOption[];
};

const STORY_AUDIO_ROOT_ID = 'omnix-story-audio-panel';
const STORY_AUDIO_SELECTED_VOICE_KEY = 'omnix.storyteller.audio.selectedVoiceId';
const STORY_AUDIO_POLL_INTERVAL_MS = 1_500;
const STORY_AUDIO_MAX_POLLS = 160;

const storyAudioState: StoryAudioState = {
  audioSource: '',
  filename: 'story-audio.wav',
  isGenerating: false,
  jobId: '',
  lastStoryFingerprint: '',
  progress: 0,
  selectedVoiceId: readSelectedVoiceId(),
  status: 'Ready to narrate the full story.',
  voices: [],
};

let observerStarted = false;
let voiceLoadStarted = false;
let renderScheduled = false;

export function extractStoryTextFromDocument(root: ParentNode = document): string {
  const prose = root.querySelector('.storyteller-prose') as HTMLElement | null;
  const storyModePage = root.querySelector('.story-mode-page') as HTMLElement | null;
  const manuscript = root.querySelector('[aria-label="Story manuscript"]') as HTMLElement | null;
  const source = prose?.innerText || storyModePage?.innerText || manuscript?.innerText || '';
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
    const chapterMatch = cleaned.match(/^chapter\s+\d+\s*[:\-–—]?\s*(.*)$/i);
    if (chapterMatch) {
      if (current.lines.join('\n').trim()) segments.push(current);
      current = { title: cleaned, lines: [cleaned] };
      continue;
    }
    current.lines.push(line);
  }
  if (current.lines.join('\n').trim()) segments.push(current);

  return segments.map((segment, index) => ({
    index,
    speaker: 'Narrator',
    text: segment.lines.join('\n').trim(),
    title: segment.title,
  }));
}

export function voiceOptionsFromAssets(assets: StoryAudioAsset[]): StoryAudioVoiceOption[] {
  return assets
    .filter((asset) => asset.type === 'voice_profile')
    .map((asset) => ({ id: voiceAssetId(asset), label: voiceAssetLabel(asset) }))
    .filter((voice, index, voices) => voice.id && voices.findIndex((entry) => entry.id === voice.id) === index)
    .sort((left, right) => left.label.localeCompare(right.label));
}

function scheduleStoryAudioRender(): void {
  if (renderScheduled) return;
  renderScheduled = true;
  window.requestAnimationFrame(() => {
    renderScheduled = false;
    ensureStoryAudioPanel();
  });
}

function ensureStoryAudioPanel(): void {
  const workspace = document.querySelector('.storyteller-workspace');
  const header = document.querySelector('.storyteller-project-header');
  if (!workspace || !header) return;

  let panel = document.getElementById(STORY_AUDIO_ROOT_ID);
  if (!panel) {
    panel = document.createElement('section');
    panel.id = STORY_AUDIO_ROOT_ID;
    panel.className = 'storyteller-audio-panel';
    panel.setAttribute('aria-label', 'Story audio');
    header.insertAdjacentElement('afterend', panel);
  }

  const storyText = extractStoryTextFromDocument(document);
  const fingerprint = fingerprintStoryAudio(storyText);
  if (fingerprint && fingerprint !== storyAudioState.lastStoryFingerprint) {
    storyAudioState.lastStoryFingerprint = fingerprint;
    if (!storyAudioState.isGenerating) {
      storyAudioState.audioSource = '';
      storyAudioState.progress = 0;
      storyAudioState.jobId = '';
      storyAudioState.filename = `${slugify(readStoryTitle()) || 'story'}-audio.wav`;
      storyAudioState.status = 'Ready to narrate the full story.';
    }
  }

  if (!voiceLoadStarted) {
    voiceLoadStarted = true;
    void loadVoiceProfiles();
  }

  renderStoryAudioPanel(panel, storyText);
}

function renderStoryAudioPanel(panel: HTMLElement, storyText: string): void {
  const hasStory = Boolean(storyText.trim());
  const hasAudio = Boolean(storyAudioState.audioSource);
  const voiceOptions = storyAudioState.voices.length
    ? storyAudioState.voices.map((voice) => `<option value="${escapeHtml(voice.id)}"${voice.id === storyAudioState.selectedVoiceId ? ' selected' : ''}>${escapeHtml(voice.label)}</option>`).join('')
    : '<option value="">No cloned voices found</option>';
  const progressValue = Math.max(0, Math.min(100, storyAudioState.progress));

  panel.innerHTML = `
    <div class="storyteller-audio-copy">
      <p class="eyebrow">Story audio</p>
      <h3>Generate full-story narration</h3>
      <p>Use a cloned voice to narrate the complete manuscript. Multi-chapter stories are queued as chapter-aware segments, stream into the player when audio becomes available, and can be downloaded after synthesis finishes.</p>
    </div>
    <div class="storyteller-audio-controls">
      <label>
        Cloned voice
        <select data-story-audio-voice aria-label="Story audio cloned voice" ${storyAudioState.isGenerating ? 'disabled' : ''}>
          <option value="">Default Voice Studio voice</option>
          ${voiceOptions}
        </select>
      </label>
      <div class="storyteller-audio-actions">
        <button data-story-audio-generate type="button" ${!hasStory || storyAudioState.isGenerating ? 'disabled' : ''}>${storyAudioState.isGenerating ? 'Generating audio…' : 'Generate story audio'}</button>
        <button data-story-audio-download type="button" ${hasAudio ? '' : 'disabled'}>Download audio</button>
      </div>
      <div class="storyteller-audio-progress" role="status" aria-live="polite">
        <span>${escapeHtml(storyAudioState.status)}</span>
        <progress max="100" value="${progressValue}">${progressValue}%</progress>
      </div>
      <audio data-story-audio-player controls preload="metadata" ${hasAudio ? `src="${escapeAttribute(storyAudioState.audioSource)}"` : ''}></audio>
      ${storyAudioState.jobId ? `<small>Voice job: ${escapeHtml(storyAudioState.jobId)}</small>` : ''}
    </div>
  `;

  const voiceSelect = panel.querySelector('[data-story-audio-voice]') as HTMLSelectElement | null;
  voiceSelect?.addEventListener('change', () => {
    storyAudioState.selectedVoiceId = voiceSelect.value;
    persistSelectedVoiceId(voiceSelect.value);
    storyAudioState.status = voiceSelect.value ? 'Selected cloned voice for Storyteller narration.' : 'Using the default Voice Studio voice.';
    ensureStoryAudioPanel();
  });

  panel.querySelector('[data-story-audio-generate]')?.addEventListener('click', () => {
    void generateStoryAudio();
  });
  panel.querySelector('[data-story-audio-download]')?.addEventListener('click', downloadStoryAudio);
}

async function loadVoiceProfiles(): Promise<void> {
  try {
    const response = await fetch('/api/assets');
    if (!response.ok) throw new Error(`Voice profile lookup failed with HTTP ${response.status}.`);
    const payload = await response.json() as { assets?: StoryAudioAsset[] };
    storyAudioState.voices = voiceOptionsFromAssets(Array.isArray(payload.assets) ? payload.assets : []);
    if (!storyAudioState.selectedVoiceId && storyAudioState.voices[0]) {
      storyAudioState.selectedVoiceId = storyAudioState.voices[0].id;
      persistSelectedVoiceId(storyAudioState.selectedVoiceId);
    }
    storyAudioState.status = storyAudioState.voices.length
      ? 'Ready to narrate with a cloned voice.'
      : 'Ready to narrate with the default Voice Studio voice.';
  } catch (error) {
    storyAudioState.status = error instanceof Error ? error.message : 'Voice profile lookup failed.';
  } finally {
    ensureStoryAudioPanel();
  }
}

async function generateStoryAudio(): Promise<void> {
  const text = extractStoryTextFromDocument(document);
  const title = readStoryTitle();
  const segments = splitStoryAudioSegments(text);
  if (!text.trim() || !segments.length) {
    storyAudioState.status = 'Generate or select a story before creating audio.';
    ensureStoryAudioPanel();
    return;
  }

  storyAudioState.audioSource = '';
  storyAudioState.filename = `${slugify(title || 'story')}-audio.wav`;
  storyAudioState.isGenerating = true;
  storyAudioState.progress = 2;
  storyAudioState.status = 'Queueing full-story Voice Studio narration…';
  ensureStoryAudioPanel();

  try {
    const job = await createStoryAudioJob({ title, text, segments, voiceId: storyAudioState.selectedVoiceId });
    storyAudioState.jobId = job.id;
    updateAudioProgressFromJob(job);
    const earlySource = playableAudioSource(job);
    if (earlySource) {
      storyAudioState.audioSource = earlySource;
      storyAudioState.status = 'Streaming generated story audio…';
      ensureStoryAudioPanel();
      playStoryAudioWhenReady();
    }

    const completedJob = job.status === 'completed' || job.status === 'failed' ? job : await pollStoryAudioJob(job.id);
    updateAudioProgressFromJob(completedJob);
    const audioSource = playableAudioSource(completedJob);
    if (completedJob.status === 'failed') {
      throw new Error(completedJob.error?.message || 'Voice Studio audio generation failed.');
    }
    if (!audioSource) {
      throw new Error('Voice Studio did not return downloadable story audio.');
    }
    storyAudioState.audioSource = audioSource;
    storyAudioState.progress = 100;
    storyAudioState.status = 'Full-story audio ready to play or download.';
    ensureStoryAudioPanel();
    playStoryAudioWhenReady();
  } catch (error) {
    storyAudioState.status = error instanceof Error ? error.message : 'Story audio generation failed.';
    storyAudioState.progress = 0;
    ensureStoryAudioPanel();
  } finally {
    storyAudioState.isGenerating = false;
    ensureStoryAudioPanel();
  }
}

async function createStoryAudioJob({ title, text, segments, voiceId }: { title: string; text: string; segments: StoryAudioSegment[]; voiceId: string }): Promise<StoryAudioJob> {
  const request = {
    module: 'voice',
    type: segments.length > 1 ? 'tts.multi_speaker_synthesize' : 'tts.synthesize',
    resource_class: 'gpu:tts',
    priority: 1,
    input_payload: {
      text,
      provider_id: null,
      speaker: 'Narrator',
      voice_id: voiceId || null,
      script_mode: 'story_full_audio',
      story_title: title || null,
      source_module: 'storyteller',
      script_speakers: [{ name: 'Narrator', count: segments.length }],
      script_segments: segments,
      character_voice_assignments: [{ speaker: 'Narrator', voice_id: voiceId || null, style: 'Story narrator', line_count: segments.length }],
      save_output: true,
    },
    stages: [
      { id: 'prepare-story-audio', label: 'Prepare full story narration', resource_class: 'cpu', status: 'queued' },
      ...segments.map((segment) => ({ id: `narrate-story-${String(segment.index + 1).padStart(3, '0')}`, label: segment.title ? `Narrate ${segment.title}` : `Narrate segment ${segment.index + 1}`, resource_class: 'gpu:tts', status: 'queued' })),
      { id: 'stitch-story-audio', label: 'Stitch full story audio', resource_class: 'cpu', status: 'queued' },
      { id: 'store-story-audio', label: 'Save downloadable story audio', resource_class: 'cpu', status: 'queued' },
    ],
  };
  const response = await fetch('/api/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!response.ok) throw new Error(`Story audio job failed with HTTP ${response.status}.`);
  return response.json() as Promise<StoryAudioJob>;
}

async function pollStoryAudioJob(jobId: string): Promise<StoryAudioJob> {
  let lastJob: StoryAudioJob | null = null;
  for (let index = 0; index < STORY_AUDIO_MAX_POLLS; index += 1) {
    await wait(STORY_AUDIO_POLL_INTERVAL_MS);
    const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`);
    if (!response.ok) throw new Error(`Story audio status failed with HTTP ${response.status}.`);
    const job = await response.json() as StoryAudioJob;
    lastJob = job;
    updateAudioProgressFromJob(job);
    const source = playableAudioSource(job);
    if (source && !storyAudioState.audioSource) {
      storyAudioState.audioSource = source;
      storyAudioState.status = 'Streaming generated story audio…';
      ensureStoryAudioPanel();
      playStoryAudioWhenReady();
    } else {
      ensureStoryAudioPanel();
    }
    if (job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled') return job;
  }
  throw new Error(lastJob ? 'Story audio generation timed out before completion.' : 'Story audio job never started.');
}

function updateAudioProgressFromJob(job: StoryAudioJob): void {
  storyAudioState.jobId = job.id;
  if (job.progress && job.progress.total > 0) {
    storyAudioState.progress = Math.min(100, Math.round((job.progress.current / job.progress.total) * 100));
  } else if (job.status === 'completed') {
    storyAudioState.progress = 100;
  } else if (job.status === 'running' || job.status === 'leased') {
    storyAudioState.progress = Math.max(storyAudioState.progress, 35);
  } else if (job.status === 'queued') {
    storyAudioState.progress = Math.max(storyAudioState.progress, 10);
  }
  if (!storyAudioState.audioSource) {
    storyAudioState.status = job.status === 'completed'
      ? 'Finalizing full-story audio…'
      : `Voice Studio narration ${job.status}.`;
  }
}

function playableAudioSource(job: StoryAudioJob): string {
  const refs = Array.isArray(job.output_refs) ? job.output_refs : [];
  for (const ref of refs) {
    if (!ref || typeof ref !== 'object') continue;
    const output = ref as Record<string, unknown>;
    if (output.provider_fallback === true || output.provider_success === false) continue;
    const dataUrl = typeof output.data_url === 'string' ? output.data_url : '';
    if (dataUrl.startsWith('data:audio/')) return dataUrl;
    const audioUrl = typeof output.audio_url === 'string' ? output.audio_url : '';
    if (audioUrl) return audioUrl;
    const url = typeof output.url === 'string' ? output.url : '';
    if (url && /\.(wav|mp3|ogg|webm)(\?|$)/i.test(url)) return url;
  }
  return '';
}

function downloadStoryAudio(): void {
  if (!storyAudioState.audioSource) return;
  const link = document.createElement('a');
  link.href = storyAudioState.audioSource;
  link.download = storyAudioState.filename || 'story-audio.wav';
  link.rel = 'noopener';
  document.body.appendChild(link);
  link.click();
  link.remove();
  storyAudioState.status = `Downloaded ${storyAudioState.filename}.`;
  ensureStoryAudioPanel();
}

function playStoryAudioWhenReady(): void {
  const audio = document.querySelector(`#${STORY_AUDIO_ROOT_ID} audio`) as HTMLAudioElement | null;
  if (!audio || !storyAudioState.audioSource) return;
  audio.src = storyAudioState.audioSource;
  audio.play().catch(() => {
    storyAudioState.status = 'Audio is ready. Press play to start narration.';
    ensureStoryAudioPanel();
  });
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

function voiceAssetId(asset: StoryAudioAsset): string {
  const metadata = asset.metadata ?? {};
  return stringValue(metadata.voice_id) || stringValue(metadata.profile_id) || stringValue(metadata.id) || stringValue(asset.storage_path) || asset.id;
}

function voiceAssetLabel(asset: StoryAudioAsset): string {
  const metadata = asset.metadata ?? {};
  return stringValue(metadata.profile_name) || stringValue(metadata.name) || stringValue(metadata.voice_name) || basename(asset.storage_path) || asset.id;
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
    // Local voice preference is best-effort.
  }
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character] ?? character));
}

function escapeAttribute(value: string): string {
  return escapeHtml(value).replace(/`/g, '&#96;');
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function installStoryAudioEnhancer(): void {
  if (observerStarted || typeof window === 'undefined' || typeof document === 'undefined') return;
  observerStarted = true;
  scheduleStoryAudioRender();
  const observer = new MutationObserver(scheduleStoryAudioRender);
  observer.observe(document.body, { childList: true, subtree: true });
  window.addEventListener('popstate', scheduleStoryAudioRender);
  window.addEventListener('hashchange', scheduleStoryAudioRender);
}

installStoryAudioEnhancer();
