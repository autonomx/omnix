import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { existsSync, linkSync, mkdirSync, mkdtempSync, readdirSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

// The Phase 5 gate on a GPU machine (desktop roadmap §5): from the setup screen's recommended preset to voice input
// and output, in the real app on the staged runtime. Opt in with
//   OMNIXDESKTOP_TEST_HF_CACHE  a Hugging Face cache that already holds the voice models (they are hard-linked into
//                               the fresh packs folder, so only the runtimes are downloaded: about 2.9 GB on Windows)
//   OMNIXDESKTOP_TEST_SPEECH    a WAV of someone saying OMNIXDESKTOP_TEST_SPEECH_WORDS (comma separated)
//   OMNIXDESKTOP_TEST_DATA_DIR  optional: a data folder to keep between runs, so a second run skips the downloads
// It loads the speech and TTS models together (about 14 GB of commit and 7 GB of VRAM): check headroom first.
const DESKTOP = resolve(__dirname, '..');
const STAGE = resolve(DESKTOP, 'staging', 'stage');
const CACHE = process.env.OMNIXDESKTOP_TEST_HF_CACHE ?? '';
const SPEECH = process.env.OMNIXDESKTOP_TEST_SPEECH ?? '';
const WORDS = (process.env.OMNIXDESKTOP_TEST_SPEECH_WORDS ?? 'omnix,desktop').split(',').map((word) => word.trim().toLowerCase());
const KEPT = process.env.OMNIXDESKTOP_TEST_DATA_DIR ?? '';
const VOICE_REPOS = ['models--Qwen--Qwen3-TTS-12Hz-0.6B-Base', 'models--nvidia--nemotron-speech-streaming-en-0.6b',
  'models--nvidia--parakeet_realtime_eou_120m-v1'];

test.skip(!CACHE || !SPEECH, 'set OMNIXDESKTOP_TEST_HF_CACHE and OMNIXDESKTOP_TEST_SPEECH to run the real-model gate');
test.describe.configure({ mode: 'serial' });

function linkTree(source: string, target: string): void {
  mkdirSync(target, { recursive: true });
  for (const name of readdirSync(source)) {
    const from = join(source, name);
    const to = join(target, name);
    if (statSync(from).isDirectory()) linkTree(from, to);
    else linkSync(from, to);
  }
}

async function appWindow(app: ElectronApplication, matcher: (url: string) => boolean, timeout = 300_000): Promise<Page> {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const page = app.windows().find((candidate) => matcher(candidate.url()));
    if (page) return page;
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 500));
  }
  throw new Error(`no window matched; open: ${app.windows().map((page) => page.url()).join(', ')}`);
}

function post(page: Page, path: string, body: unknown): Promise<{ status: number; body: Record<string, unknown> }> {
  return page.evaluate(async ({ path: url, body: payload }) => {
    const csrf = decodeURIComponent((document.cookie.split('; ').find((part) => part.startsWith('omnix_csrf=')) ?? '').split('=')[1] ?? '');
    const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Omnix-Client': 'web',
      'X-Omnix-CSRF': csrf }, body: JSON.stringify(payload) });
    return { status: response.status, body: await response.json() };
  }, { path, body });
}

let app: ElectronApplication;
let dataDir: string;
let main: Page;

test.beforeAll(async () => {
  dataDir = KEPT ? resolve(KEPT) : mkdtempSync(join(tmpdir(), 'omnix-desktop-realmodels-'));
  for (const repo of VOICE_REPOS) {
    if (!existsSync(join(CACHE, repo))) throw new Error(`${CACHE} has no ${repo}`);
    if (!existsSync(join(dataDir, 'packs', 'models', repo))) linkTree(join(CACHE, repo), join(dataDir, 'packs', 'models', repo));
  }
  // Chromium's fake microphone plays the speech, padded with silence so the end of the utterance is heard.
  const microphone = join(dataDir, 'microphone.wav');
  execFileSync(join(STAGE, 'ffmpeg', process.platform === 'win32' ? 'ffmpeg.exe' : 'ffmpeg'), ['-y', '-loglevel', 'error',
    '-i', SPEECH, '-af', 'adelay=750:all=1,apad=pad_dur=3', '-ar', '48000', '-ac', '1', '-c:a', 'pcm_s16le', microphone]);
  const env = { ...Object.fromEntries(Object.entries(process.env).filter(([name]) => name !== 'ELECTRON_RUN_AS_NODE')) as Record<string, string>,
    OMNIXDESKTOP_DATA_DIR: dataDir, OMNIXDESKTOP_RESOURCES: STAGE };
  app = await electron.launch({ env, args: ['--use-fake-device-for-media-stream', `--use-file-for-fake-audio-capture=${microphone}`,
    '--autoplay-policy=no-user-gesture-required', join(DESKTOP, 'out', 'main.js')] });
});

test.afterAll(async () => {
  await app?.close();
  if (!KEPT) rmSync(dataDir, { recursive: true, force: true, maxRetries: 5 });
});

test('the recommended preset downloads voice input and output, and their services start', async () => {
  test.setTimeout(60 * 60_000);
  main = await appWindow(app, (url) => url.startsWith('http://127.0.0.1') && (url.includes('/setup') || url.includes('/chatbot')));
  if (!main.url().includes('/setup')) await main.goto(new URL('/setup', main.url()).toString());  // a kept data folder
  const row = (label: string) => main.getByRole('listitem', { name: label });
  await expect(row('Voice input')).toBeVisible({ timeout: 120_000 });
  const done = async () => (await row('Voice input').getByText('Installed', { exact: true }).count()) > 0
    && (await row('Voice output').getByText('Installed', { exact: true }).count()) > 0;
  if (!(await done())) await download(row);
  await expect.poll(async () => {
    const answer = await main.evaluate(async () => (await fetch('/api/model-packs/capabilities')).json());
    return [answer.capabilities.tts?.running, answer.capabilities.live_stt?.running];
  }, { timeout: 10 * 60_000, intervals: [5_000] }).toEqual([true, true]);
});

async function download(row: (label: string) => ReturnType<Page['getByRole']>): Promise<void> {
  const status = await main.evaluate(async () => (await fetch('/api/model-packs')).json());
  const verdicts = JSON.stringify(status.bundles.map((item: Record<string, unknown>) => [item.bundle, item.status, item.installed,
    item.recommended, item.reasons]));
  // On a GPU machine the recommended preset includes voice input and output; this run keeps only those two, so the
  // image model's 18 GB of commit is not loaded beside them.
  await expect(row('Voice input').getByRole('checkbox'), verdicts).toBeChecked();
  await expect(row('Voice output').getByRole('checkbox'), verdicts).toBeChecked();
  for (const other of ['Transcription', 'Image generation']) {
    const box = row(other).getByRole('checkbox');
    if (await box.isChecked()) await box.uncheck();
  }
  await main.getByRole('button', { name: 'Review licences and download' }).click();
  const review = main.getByRole('dialog', { name: 'Review the licences' });
  // The three voice models need accepting (the runtimes are listed for information only).
  await expect(review.getByRole('checkbox')).toHaveCount(3);
  for (const box of await review.getByRole('checkbox').all()) await box.check();
  await review.getByRole('button', { name: /^(Accept and download|Download)$/ }).click();
  for (const label of ['Voice input', 'Voice output']) {
    await expect(row(label).getByText('Installed', { exact: true })).toBeVisible({ timeout: 50 * 60_000 });
  }
}

test('voice output: a speech job completes through the TTS service', async () => {
  test.setTimeout(10 * 60_000);
  const text = 'Omnix is speaking from the desktop app.';
  const submitted = await post(main, '/api/jobs', {
    module: 'voice', type: 'tts.synthesize', resource_class: 'gpu:tts', priority: 1,
    input_payload: { text, provider_id: null, speaker: 'Narrator', voice_id: null, script_mode: 'single_speaker',
      script_speakers: [{ name: 'Narrator', count: 1 }], script_segments: [{ index: 0, speaker: 'Narrator', text }],
      character_voice_assignments: [{ speaker: 'Narrator', voice_id: null, style: '', line_count: 1 }], save_output: true },
  });
  expect(submitted.status, JSON.stringify(submitted.body)).toBeLessThan(300);
  const jobId = String(submitted.body.id);
  await expect.poll(() => main.evaluate(async (id) => (await (await fetch(`/api/jobs/${id}`)).json()).status, jobId),
    { timeout: 8 * 60_000, intervals: [2_000] }).toBe('completed');
});

test('voice input: a live call hears the microphone, ends the utterance and sends the transcript to chat', async () => {
  test.setTimeout(10 * 60_000);
  await main.goto(new URL('/chatbot', main.url()).toString());
  const seen: string[] = [];
  const note = (line: string) => seen.push(`${new Date().toISOString()} ${line}`);
  main.on('console', (message) => {
    if (message.type() === 'error' || message.type() === 'warning' || /live|stt|websocket/i.test(message.text())) {
      note(`${message.type()}: ${message.text().slice(0, 200)}`);
    }
  });
  main.on('websocket', (socket) => {
    note(`ws open ${socket.url()}`);
    socket.on('framesent', (frame) => { if (typeof frame.payload === 'string' && !frame.payload.includes('"audio"')) note(`ws -> ${frame.payload.slice(0, 120)}`); });
    socket.on('framereceived', (frame) => { if (typeof frame.payload === 'string' && !frame.payload.includes('audio_buffered')) note(`ws <- ${frame.payload.slice(0, 160)}`); });
    socket.on('socketerror', (error) => note(`ws error ${error}`));
    socket.on('close', () => note(`ws closed ${socket.url()}`));
  });
  main.on('request', (request) => { if (/\/api\/(stt|tts\/live-call|chat\/sessions\/[^/]+\/live)/.test(request.url())) note(`req ${request.method()} ${request.url().slice(21, 140)}`); });
  const card = main.locator('.assistant-live-card');
  await expect(card).toBeVisible({ timeout: 60_000 });
  // Chat's runtime installs the streaming voice controller after the page renders; it shows the task picker once it
  // owns the call. A click before then takes the record-then-transcribe fallback instead.
  await expect(card.getByRole('combobox', { name: 'Live task' })).toBeVisible({ timeout: 60_000 });
  // The end of the utterance sends the final transcript as the user's chat message. No word boundaries: an
  // article's text runs its time into the message ("03:28Hello from ...").
  const said = new RegExp(WORDS.map((word) => `(?=.*${word})`).join(''), 'i');
  const turns = main.getByRole('log').getByRole('article').filter({ hasText: said });
  const before = await turns.count();  // a kept data folder keeps earlier runs' calls
  await card.getByRole('button', { name: 'Start Call' }).click();
  try {
    await expect.poll(() => turns.count(), { timeout: 180_000, intervals: [2_000] }).toBeGreaterThan(before);
  } finally {
    console.log(['live call activity:', ...seen.slice(0, 80)].join('\n'));
  }
  await card.getByRole('button', { name: 'End Call' }).click();
});
