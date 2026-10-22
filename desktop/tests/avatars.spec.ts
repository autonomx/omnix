import { _electron as electron, expect, test } from '@playwright/test';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

// The setup screen's avatars (desktop roadmap §4.5): one downloads, its preview shows through Omnix, and Live2D's own
// Cubism Core (pinned, from cubism.live2d.com) reads the model. Downloads from Live2D and GitHub: opt in with
// OMNIXDESKTOP_TEST_NETWORK=1.
const DESKTOP = resolve(__dirname, '..');
test.skip(process.env.OMNIXDESKTOP_TEST_NETWORK !== '1', 'set OMNIXDESKTOP_TEST_NETWORK=1 to download an avatar');

test('a Live2D avatar downloads from the setup screen and the official Cubism Core reads it', async () => {
  test.setTimeout(400_000);
  const dataDir = mkdtempSync(join(tmpdir(), 'omnix-desktop-live2d-'));
  const env = { ...Object.fromEntries(Object.entries(process.env).filter(([name]) => name !== 'ELECTRON_RUN_AS_NODE')) as Record<string, string>,
    OMNIXDESKTOP_DATA_DIR: dataDir, OMNIXDESKTOP_RESOURCES: resolve(DESKTOP, 'staging', 'stage') };
  const app = await electron.launch({ env, args: [join(DESKTOP, 'out', 'main.js')] });
  try {
    let main = null;
    for (let i = 0; i < 600 && !main; i += 1) {
      main = app.windows().find((page) => page.url().startsWith('http://127.0.0.1') && page.url().includes('/setup')) ?? null;
      if (!main) await new Promise((r) => setTimeout(r, 500));
    }
    if (!main) throw new Error('no setup window');
    const avatars = main.getByRole('region', { name: 'Live2D avatars' });
    const haru = avatars.getByRole('listitem', { name: 'Haru', exact: true });
    await expect(haru).toBeVisible({ timeout: 120_000 });
    await expect.poll(() => haru.locator('img').evaluate((image: HTMLImageElement) => image.complete && image.naturalWidth),
      { timeout: 60_000 }).toBeGreaterThan(0);
    await avatars.getByRole('checkbox').check();
    await haru.getByRole('button', { name: 'Download' }).click();
    await expect(haru.getByText('Downloaded', { exact: true })).toBeVisible({ timeout: 180_000 });
    const result = await main.evaluate(async () => {
      await new Promise<void>((done, fail) => {
        const script = document.createElement('script');
        script.src = '/api/character-live2d/runtime/live2dcubismcore.min.js';
        script.onload = () => done();
        script.onerror = () => fail(new Error('core did not load'));
        document.head.append(script);
      });
      const core = (window as unknown as { Live2DCubismCore: any }).Live2DCubismCore;
      const base = '/api/character-live2d/assets/character-live2d%3Alive2d-sample-haru/runtime/';
      const descriptor = await (await fetch(`${base}haru.model3.json`)).json();
      const moc = core.Moc.fromArrayBuffer(await (await fetch(base + descriptor.FileReferences.Moc)).arrayBuffer());
      const model = core.Model.fromMoc(moc);
      return { version: core.Version.csmGetVersion(), drawables: model.drawables.count, parameters: model.parameters.count };
    });
    expect(result.drawables).toBeGreaterThan(0);
  } finally {
    await app.close();
    rmSync(dataDir, { recursive: true, force: true, maxRetries: 5 });
  }
});
