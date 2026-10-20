import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  // Never forward an unmocked call to an operator's gateway; workspaces render their empty and error states.
  await page.route((url) => url.pathname.startsWith('/api/'), (route) => route.fulfill({
    status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'unmocked_test_route' }),
  }));
  await page.route((url) => url.pathname === '/events' || url.pathname.startsWith('/events/'), (route) => route.abort());
});

const workspaces = [
  ['RPG', '/rpg'],
  ['Chatbot', '/chatbot'],
  ['Storyteller', '/storyteller'],
  ['Podcast', '/podcast'],
  ['Voice Studio', '/voice'],
  ['Voice Cloning', '/voice-cloning'],
  ['STT', '/stt'],
  ['Image Generation', '/image-generation'],
  ['Audiobook', '/audiobook'],
  ['Trading', '/trading'],
  ['Providers', '/providers'],
  ['Models', '/models'],
  ['Jobs / Runs', '/jobs'],
  ['Assets', '/assets'],
  ['Reports', '/reports'],
  ['Settings', '/settings'],
  ['Diagnostics', '/diagnostics'],
] as const;

for (const [workspace, route] of workspaces) {
  test(`${workspace} has no critical or serious accessibility violations`, async ({ page }) => {
    await page.goto(route);
    await expect(page.getByRole('banner').getByLabel(`${workspace}, Local-first`)).toBeVisible();
    // Analyse the loaded workspace, not the lazy-loading fallback.
    await expect(page.getByText(/^Loading .* workspace…$/)).toHaveCount(0, { timeout: 20_000 });

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    const blocking = results.violations
      .filter((violation) => violation.impact === 'critical' || violation.impact === 'serious')
      .map((violation) => ({ id: violation.id, nodes: violation.nodes.slice(0, 5).map((node) => node.target.join(' ')) }));
    expect(blocking).toEqual([]);
  });
}

test('Voice Studio Transcribe with an open transcript has no critical or serious accessibility violations', async ({ page }) => {
  const document = {
    schema: 'omnix-transcript-v1', language: 'en', duration: 4, engine: 'Parakeet-TDT', diarized: true,
    speakers: ['Speaker 1', 'Speaker 2'], text: 'Hello there. Hi.', source_asset_id: 'audio:talk',
    segments: [
      { start: 0, end: 1.5, speaker: 'Speaker 1', text: 'Hello there.', words: [
        { start: 0, end: 0.6, word: 'Hello', confidence: 0.9 }, { start: 0.7, end: 1.5, word: 'there.', confidence: 0.4 },
      ] },
      { start: 2, end: 2.6, speaker: 'Speaker 2', text: 'Hi.', words: [{ start: 2, end: 2.6, word: 'Hi.', confidence: 0.95 }] },
    ],
  };
  await page.route((url) => url.pathname === '/api/assets', (route) => route.fulfill({ json: { assets: [
    { id: 'audio:talk', module: 'voice', type: 'audio', mime_type: 'audio/wav', file_name: 'talk.wav', metadata: { title: 'Team call' }, created_at: '2026-10-19T00:00:00Z' },
    { id: 'transcript:t', module: 'stt', type: 'transcript', mime_type: 'application/json', file_name: 't.json', metadata: { title: 'Transcript of Team call' }, created_at: '2026-10-19T00:01:00Z' },
  ] } }));
  await page.route((url) => url.pathname === '/api/voice/transcripts/transcript%3At', (route) => route.fulfill({
    json: { asset_id: 'transcript:t', title: 'Transcript of Team call', revision: 1, document },
  }));
  await page.goto('/voice');
  await expect(page.getByText(/^Loading .* workspace…$/)).toHaveCount(0, { timeout: 20_000 });
  await page.getByRole('navigation', { name: 'Voice Studio tools' }).getByRole('button', { name: 'Transcribe' }).click();
  await page.getByLabel('Transcripts').selectOption('transcript:t');
  await expect(page.getByRole('button', { name: 'there.' })).toBeVisible();

  const results = await new AxeBuilder({ page })
    .include('.voice-canvas')
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  const blocking = results.violations
    .filter((violation) => violation.impact === 'critical' || violation.impact === 'serious')
    .map((violation) => ({ id: violation.id, nodes: violation.nodes.slice(0, 5).map((node) => node.target.join(' ')) }));
  expect(blocking).toEqual([]);
});

test('Voice Studio Batch with a run open has no critical or serious accessibility violations', async ({ page }) => {
  const steps = [{ tool: 'isolate', settings: {} }, { tool: 'transcribe', settings: {} }];
  const run = {
    id: 'vbatch:1', recipe_id: 'vrecipe:1', recipe_version: 1, title: 'Clean', watch_folder: '', status: 'running',
    created_at: '2026-10-19T00:00:00Z', updated_at: '', steps, counts: { done: 1, running: 1 },
    items: [
      { id: 'vbitem:1', position: 0, source_asset_id: 'audio:talk', current_asset_id: 'audio:talk', step_index: 2, status: 'done', job_id: '', attempts: 0, outputs: [{ tool: 'isolate', title: 'Team call (vocals)' }], error: '', output_name: '' },
      { id: 'vbitem:2', position: 1, source_asset_id: 'audio:b', current_asset_id: 'audio:b', step_index: 0, status: 'running', job_id: 'job:1', attempts: 1, outputs: [], error: 'engine crashed', output_name: '' },
    ],
  };
  await page.route((url) => url.pathname === '/api/assets', (route) => route.fulfill({ json: { assets: [
    { id: 'audio:talk', module: 'voice', type: 'audio', mime_type: 'audio/wav', file_name: 'talk.wav', metadata: { title: 'Team call' }, created_at: '2026-10-19T00:00:00Z' },
  ] } }));
  await page.route((url) => url.pathname === '/api/voice/recipes', (route) => route.fulfill({ json: {
    recipes: [{ id: 'vrecipe:1', name: 'Clean', version: 1, steps, created_at: '', updated_at: '' }], tools: ['isolate', 'transcribe'],
  } }));
  await page.route((url) => url.pathname === '/api/voice/batches', (route) => route.fulfill({ json: { runs: [run] } }));
  await page.route((url) => url.pathname.startsWith('/api/voice/batches/'), (route) => route.fulfill({ json: run }));
  await page.route((url) => url.pathname === '/api/voice/clients', (route) => route.fulfill({ json: { clients: [], capabilities: ['voice.speak', 'voice.design'] } }));
  await page.goto('/voice');
  await expect(page.getByText(/^Loading .* workspace…$/)).toHaveCount(0, { timeout: 20_000 });
  await page.getByRole('navigation', { name: 'Voice Studio tools' }).getByRole('button', { name: 'Batch' }).click();
  await page.getByRole('button', { name: 'Clean', exact: true }).click();
  await expect(page.getByText('1 of 2 finished · running')).toBeVisible();
  await page.getByText('API clients and MCP').click();
  await page.getByRole('button', { name: 'New recipe' }).click();

  const results = await new AxeBuilder({ page })
    .include('.voice-canvas')
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  const blocking = results.violations
    .filter((violation) => violation.impact === 'critical' || violation.impact === 'serious')
    .map((violation) => ({ id: violation.id, nodes: violation.nodes.slice(0, 5).map((node) => node.target.join(' ')) }));
  expect(blocking).toEqual([]);
});
