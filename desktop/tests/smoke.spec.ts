import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import { execFileSync, spawn } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

const DESKTOP = resolve(__dirname, '..');
const STAGE = resolve(DESKTOP, 'staging', 'stage');
const PASSWORD = 'a long first passphrase';

interface ProcessRow { pid: number; ppid: number; command: string }

/** Every process with its parent and command line (PowerShell on Windows, ps on macOS). */
function processes(): ProcessRow[] {
  if (process.platform !== 'win32') {
    return execFileSync('ps', ['-axo', 'pid=,ppid=,command='], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 })
      .split('\n').map((line) => line.trim().match(/^(\d+)\s+(\d+)\s+(.*)$/)).filter((match) => match !== null)
      .map((match) => ({ pid: Number(match![1]), ppid: Number(match![2]), command: match![3] }));
  }
  const out = execFileSync('powershell', ['-NoProfile', '-Command',
    'Get-CimInstance Win32_Process | Select-Object ProcessId, ParentProcessId, CommandLine | ConvertTo-Json -Compress'],
  { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
  return (JSON.parse(out) as { ProcessId: number; ParentProcessId: number; CommandLine: string | null }[])
    .map((row) => ({ pid: row.ProcessId, ppid: row.ParentProcessId, command: row.CommandLine ?? '' }));
}

function mentions(row: ProcessRow, dataDir: string): boolean {
  const line = row.command.toLowerCase();
  const needle = dataDir.toLowerCase();
  return line.includes(needle) || line.includes(needle.replaceAll('\\', '/'));
}

/** The backend's python and postgres processes started for this data folder. */
function backendProcesses(dataDir: string): string[] {
  return processes().filter((row) => /python|postgres/i.test(row.command) && mentions(row, dataDir)).map((row) => row.command);
}

/** This machine's first NVIDIA GPU, as nvidia-smi names it, or null without one. */
function hostNvidiaGpu(): string | null {
  try {
    return execFileSync('nvidia-smi', ['--query-gpu=name', '--format=csv,noheader'], { encoding: 'utf8' }).split('\n')[0].trim() || null;
  } catch {
    return null;
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

test.describe.configure({ mode: 'serial' });

// The Electron smoke suite (desktop roadmap DT-4.3): the real app on the staged runtime (desktop/staging/stage) with a
// fresh data folder. The first start runs initdb and every migration, so it is slow.
let app: ElectronApplication;
let dataDir: string;
let main: Page;
let origin: string;

function launchEnv(): Record<string, string> {
  // Without ELECTRON_RUN_AS_NODE (an editor's extension host sets it), Electron would start as plain Node.
  return { ...Object.fromEntries(Object.entries(process.env).filter(([name]) => name !== 'ELECTRON_RUN_AS_NODE')) as Record<string, string>,
    OMNIXDESKTOP_DATA_DIR: dataDir, OMNIXDESKTOP_RESOURCES: STAGE };
}

test.beforeAll(async () => {
  dataDir = mkdtempSync(join(tmpdir(), 'omnix-desktop-smoke-'));
  app = await electron.launch({ args: [join(DESKTOP, 'out', 'main.js')], env: launchEnv() });
});

test.afterAll(async () => {
  try {
    await app?.close();
  } catch {
    // Already closed by the quit test.
  }
  rmSync(dataDir, { recursive: true, force: true, maxRetries: 5 });
});

test('first run goes through the splash to the setup screen, with this computer\'s verdicts', async () => {
  const splash = await appWindow(app, (url) => url.startsWith('file:') && url.includes('splash.html'), 30_000);
  await expect(splash.locator('h1')).toHaveText('Omnix');
  main = await appWindow(app, (url) => url.startsWith('http://127.0.0.1') && url.includes('/setup'));
  origin = new URL(main.url()).origin;
  await expect(main.getByRole('heading', { name: 'Set up Omnix' })).toBeVisible({ timeout: 120_000 });
  await expect(main.getByRole('region', { name: 'Secure your account' })).toBeVisible();
  // The bundles come from the backend's hardware probe and catalog: each one is listed, available or not.
  for (const bundle of ['Voice input', 'Voice output', 'Transcription', 'Image generation']) {
    await expect(main.getByRole('listitem', { name: bundle })).toBeVisible({ timeout: 60_000 });
  }
  // The probe runs in the backend's stripped environment and still sees this machine's NVIDIA GPU.
  const gpu = hostNvidiaGpu();
  if (gpu) await expect(main.locator('.setup-hardware')).toContainText(gpu);
  const bridge = await main.evaluate(() => {
    const desktop = (window as unknown as { omnixDesktop?: { product?: string; frameless?: boolean; requestLoginCode?: unknown } }).omnixDesktop;
    return { product: desktop?.product, frameless: desktop?.frameless, code: typeof desktop?.requestLoginCode };
  });
  expect(bridge).toEqual({ product: 'omnix', frameless: false, code: 'function' });
});

test('the owner sets a first password without the install credential', async () => {
  await main.goto(`${origin}/settings?category=overview`);
  await expect(main.getByText(/signed in from the Omnix app on this computer/)).toBeVisible({ timeout: 60_000 });
  await expect(main.getByLabel('Install credential', { exact: true })).toHaveCount(0);
  await main.getByLabel(/^Password/).fill(PASSWORD);
  await main.getByRole('button', { name: 'Set password' }).click();
  await expect.poll(() => main.evaluate(async () => (await (await fetch('/api/auth/session')).json()).account?.has_password),
    { timeout: 30_000 }).toBe(true);
});

test('the microphone is the app\'s alone and audio only; the camera is refused', async () => {
  const microphone = await main.evaluate(() => navigator.mediaDevices.getUserMedia({ audio: true })
    .then((stream) => { stream.getTracks().forEach((track) => track.stop()); return 'granted'; }, (error: Error) => error.name));
  // Allowed: a stream, or no usable microphone on this machine; never a refusal.
  expect(['granted', 'NotFoundError', 'NotReadableError']).toContain(microphone);
  const camera = await main.evaluate(() => navigator.mediaDevices.getUserMedia({ video: true }).then(() => 'granted', (error: Error) => error.name));
  expect(camera).toBe('NotAllowedError');
});

test('links leave the app only for the system browser, and navigation stays on the app', async () => {
  await app.evaluate(({ shell }) => {
    (globalThis as unknown as { opened: string[] }).opened = [];
    shell.openExternal = async (url: string) => {
      (globalThis as unknown as { opened: string[] }).opened.push(url);
    };
  });
  const before = app.windows().length;
  await main.evaluate(() => window.open('https://example.com/news', '_blank'));
  await main.evaluate(() => window.open('file:///C:/Windows/win.ini', '_blank'));
  // Another local service (a developer Omnix's STT) is neither opened nor reachable as a window.
  await main.evaluate(() => window.open('http://127.0.0.1:5201/health', '_blank'));
  await expect.poll(() => app.evaluate(() => (globalThis as unknown as { opened: string[] }).opened)).toEqual(['https://example.com/news']);
  expect(app.windows().length).toBe(before);
  await main.evaluate(() => {
    location.href = 'https://example.com/elsewhere';
  });
  await main.waitForTimeout(1_000);
  expect(new URL(main.url()).origin).toBe(origin);
});

test('the model pack API answers inside the app, counting the shared Torch layer once', async () => {
  const status = await main.evaluate(async () => (await fetch('/api/model-packs')).json());
  expect(status.enabled).toBe(true);
  expect(status.bundles.map((bundle: { bundle: string }) => bundle.bundle)).toEqual(
    expect.arrayContaining(['voice-input', 'voice-output', 'transcription', 'image-generation']));
  const selection = await main.evaluate(async () => {
    const csrf = decodeURIComponent((document.cookie.split('; ').find((part) => part.startsWith('omnix_csrf=')) ?? '').split('=')[1] ?? '');
    const response = await fetch('/api/model-packs/selection', { method: 'POST', headers: {
      'Content-Type': 'application/json', 'X-Omnix-Client': 'web', 'X-Omnix-CSRF': csrf }, body: JSON.stringify({ bundles: ['voice-input', 'voice-output'] }) });
    return response.json();
  });
  if (process.platform === 'win32') {
    // Torch (about 2.5 GB) once for both bundles, plus their two overlays.
    expect(selection.runtime_bytes).toBeGreaterThan(2.5e9);
    expect(selection.runtime_bytes).toBeLessThan(3.5e9);
  }
});

test('a window whose page crashes offers a reload and comes back', async () => {
  await app.evaluate(({ dialog }) => {
    (dialog as unknown as { showMessageBox: () => Promise<unknown> }).showMessageBox = async () => ({ response: 0, checkboxChecked: false });
  });
  const id = await app.evaluate(({ BrowserWindow }, url) => {
    const contents = BrowserWindow.getAllWindows().find((window) => window.webContents.getURL() === url)!.webContents;
    contents.forcefullyCrashRenderer();
    return contents.id;
  }, main.url());
  await expect.poll(() => app.evaluate(async ({ webContents }, contentsId) => {
    const contents = webContents.fromId(contentsId);
    if (!contents) return 'gone';
    if (contents.isCrashed()) return 'crashed';
    let timer: NodeJS.Timeout | undefined;
    try {
      const found = await Promise.race([
        contents.executeJavaScript('Boolean(document.documentElement.dataset.omnixActiveModule)'),
        new Promise((resolveLater) => { timer = setTimeout(() => resolveLater('timeout'), 2000); }),
      ]);
      return found === true ? 'ready' : String(found);
    } catch (error) {
      return `script failed: ${String(error)}`;
    } finally {
      clearTimeout(timer);
    }
  }, id), { timeout: 90_000 }).toBe('ready');
});

test('with every window gone, the Dock or tray brings Omnix back', async () => {
  await app.evaluate(({ BrowserWindow }) => {
    for (const window of BrowserWindow.getAllWindows()) window.destroy();
  });
  await expect.poll(() => app.windows().length).toBe(0);
  await app.evaluate(({ app: electronApp }) => electronApp.emit('activate'));
  main = await appWindow(app, (url) => url.startsWith(origin) && url.includes('/chatbot'));
});

test('quitting leaves no backend process, even when Quit is chosen twice', async () => {
  expect(backendProcesses(dataDir).length).toBeGreaterThan(0);
  const exited = new Promise((resolveExit) => app.process().once('exit', resolveExit));
  await app.evaluate(({ app: electronApp }) => {
    electronApp.quit();
    setTimeout(() => electronApp.quit(), 1000);
  });
  await exited;
  expect(backendProcesses(dataDir)).toEqual([]);
});

test('the next launch opens chat signed in, without the setup screen', async () => {
  app = await electron.launch({ args: [join(DESKTOP, 'out', 'main.js')], env: launchEnv() });
  const page = await appWindow(app, (url) => url.startsWith(origin) && url.includes('/chatbot'), 300_000);
  expect(page.url()).not.toContain('/setup');
  expect(await page.evaluate(async () => (await (await fetch('/api/auth/session')).json()).account?.has_password)).toBe(true);
});

test('a second launch with --quit (the installer, before replacing files) stops the running app cleanly', async () => {
  const running = app.process();
  expect(backendProcesses(dataDir).length).toBeGreaterThan(0);
  const electronPath = (await import('electron')).default as unknown as string;
  const quitter = spawn(electronPath, [join(DESKTOP, 'out', 'main.js'), '--quit'], { env: launchEnv(), stdio: 'ignore' });
  await new Promise((resolveExit) => quitter.on('exit', resolveExit));
  await expect.poll(() => running.exitCode, { timeout: 60_000 }).not.toBeNull();
  await expect.poll(() => backendProcesses(dataDir).length, { timeout: 60_000 }).toBe(0);
});
