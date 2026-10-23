import { expect, test } from '@playwright/test';
import { request } from 'node:http';
import { classify } from '../src/main/navigation';
import { AlertBadge, alertDotBitmap, NotificationListener, type DesktopDelivery } from '../src/main/notifications';
import { APP_ID, appUserModelId } from '../src/main/identity';
import { allowPermission } from '../src/main/permissions';
import { choosePorts } from '../src/main/settings';
import { checkResultMessage, updateMenuItem, updateTooltip } from '../src/main/updateStatus';
import { rotateLog } from '../src/main/supervisor';
import { installPacksFolder, MAX_PACKS_FOLDER_LENGTH, packsFolder } from '../src/main/paths';
import { mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const ORIGIN = 'http://127.0.0.1:47900';

test.describe('navigation rules (MarketPulse §4.4, shared)', () => {
  test('the app origin stays, its popups become windows, the web opens outside, the rest is refused', () => {
    expect(classify(`${ORIGIN}/chatbot`, ORIGIN, 'navigate')).toBe('stay');
    expect(classify(`${ORIGIN}/setup?first_run=1`, ORIGIN, 'navigate')).toBe('stay');
    expect(classify(`${ORIGIN}/trading?window=a`, ORIGIN, 'window-open')).toBe('window');
    expect(classify('https://www.sec.gov/filing', ORIGIN, 'window-open')).toBe('open-external');
    expect(classify('http://news.example.com/', ORIGIN, 'navigate')).toBe('open-external');
    expect(classify('file:///C:/Windows/win.ini', ORIGIN, 'window-open')).toBe('deny');
    expect(classify('javascript:alert(1)', ORIGIN, 'navigate')).toBe('deny');
    expect(classify('http://127.0.0.1:8000/api/admin', ORIGIN, 'window-open')).toBe('deny');
    expect(classify('http://localhost:5432/', ORIGIN, 'navigate')).toBe('deny');
    expect(classify('https://user:pw@example.com/', ORIGIN, 'navigate')).toBe('deny');
    expect(classify('not a url', ORIGIN, 'navigate')).toBe('deny');
  });
});

function delivery(changes: Partial<DesktopDelivery> = {}): DesktopDelivery {
  return {
    delivery_id: 'd1', event_kind: 'alert', workspace_id: 'workspace:local', title: 'Omnix alert',
    message: 'AAPL crossed 200', alert_id: 'a1', trigger_id: 't1', instrument_id: 'equity:NASDAQ:AAPL',
    created_at: new Date().toISOString(), url: '/trading?alert=a1', ...changes,
  };
}

function post(port: number, body: string, secret: string): Promise<number> {
  return new Promise((resolvePromise, reject) => {
    const outgoing = request({ host: '127.0.0.1', port, path: '/notify', method: 'POST',
      headers: { Authorization: `Bearer ${secret}`, 'Content-Type': 'application/json' } }, (response) => {
      response.resume();
      resolvePromise(response.statusCode ?? 0);
    });
    outgoing.on('error', reject);
    outgoing.end(body);
  });
}

test.describe('desktop notification listener (roadmap §4.9)', () => {
  test('shows a delivery for the signed-in account and answers 200; refuses a wrong secret', async () => {
    const shown: Array<[string, string, string]> = [];
    const listener = new NotificationListener('s3cret', {
      signedInWorkspace: async () => 'workspace:local',
      show: (title, body, url) => shown.push([title, body, url]),
    });
    await listener.listen(47960);
    try {
      expect(await post(47960, JSON.stringify(delivery()), 'wrong')).toBe(401);
      expect(shown).toEqual([]);
      expect(await post(47960, JSON.stringify(delivery()), 's3cret')).toBe(200);
      expect(shown).toEqual([['Omnix alert', 'AAPL crossed 200', '/trading?alert=a1']]);
      expect(await post(47960, 'not json', 's3cret')).toBe(400);
    } finally {
      listener.close();
    }
  });

  test('never shows another account its content', async () => {
    const shown: string[] = [];
    const listener = new NotificationListener('s', { signedInWorkspace: async () => 'workspace:other', show: (_t, body) => shown.push(body) });

    await listener.deliver(delivery());

    expect(shown).toEqual(['An alert fired for another account.']);
  });

  test('collects deliveries from while the computer slept into one summary', async () => {
    const shown: string[] = [];
    const now = Date.parse('2026-10-19T14:00:00Z');
    const listener = new NotificationListener('s', { signedInWorkspace: async () => 'workspace:local', show: (_t, body) => shown.push(body) }, () => now);
    const stale = new Date(now - 3 * 60 * 60_000).toISOString();

    await listener.deliver(delivery({ created_at: stale }));
    await listener.deliver(delivery({ created_at: stale, delivery_id: 'd2' }));
    await listener.deliver(delivery({ created_at: stale, delivery_id: 'd3' }));
    expect(shown).toEqual([]);
    listener.flushStale('Omnix alert');

    expect(shown).toEqual(['3 alerts fired while you were away.']);
    listener.close();
  });
});

test('the alert badge counts alerts that arrive while Omnix is not in front, and clears when it is', () => {
  const shown: number[] = [];
  const badge = new AlertBadge((count) => shown.push(count));

  badge.alert(true);
  badge.alert(false);
  badge.alert(false);
  badge.seen();
  badge.seen();
  badge.alert(false);

  expect(shown).toEqual([1, 2, 0, 1]);
  const dot = alertDotBitmap(16);
  expect(dot.length).toBe(16 * 16 * 4);
  expect([...dot.subarray((8 * 16 + 8) * 4, (8 * 16 + 8) * 4 + 4)]).toEqual([0x45, 0x36, 0xf2, 255]);
  expect(dot[3]).toBe(0); // a transparent corner
});

test('the shell rotates supervisor.log past its size, keeping three', () => {
  const folder = mkdtempSync(join(tmpdir(), 'omnix-desktop-log-'));
  const log = join(folder, 'supervisor.log');
  for (const generation of ['a', 'b', 'c', 'd', 'e']) {
    writeFileSync(log, generation.repeat(20));
    rotateLog(log, 10, 3);
  }
  writeFileSync(log, 'short');
  rotateLog(log, 10, 3);

  expect(readdirSync(folder).sort()).toEqual(['supervisor.log', 'supervisor.log.1', 'supervisor.log.2', 'supervisor.log.3']);
  expect(readFileSync(join(folder, 'supervisor.log.1'), 'utf8')[0]).toBe('e');
  expect(readFileSync(join(folder, 'supervisor.log.3'), 'utf8')[0]).toBe('c');
  rmSync(folder, { recursive: true, force: true });
});

test("the microphone is the app origin's alone, audio only (desktop roadmap DT-4.2)", () => {
  expect(allowPermission('media', `${ORIGIN}/chatbot`, ORIGIN, ['audio'])).toBe(true);
  expect(allowPermission('media', `${ORIGIN}/chatbot`, ORIGIN, ['audio', 'video'])).toBe(false);
  expect(allowPermission('media', `${ORIGIN}/chatbot`, ORIGIN, [])).toBe(false);
  expect(allowPermission('media', 'https://example.com/', ORIGIN, ['audio'])).toBe(false);
  expect(allowPermission('media', 'http://127.0.0.1:8000/', ORIGIN, ['audio'])).toBe(false);
  expect(allowPermission('media', `${ORIGIN}/`, null, ['audio'])).toBe(false);
  expect(allowPermission('geolocation', `${ORIGIN}/`, ORIGIN)).toBe(false);
  expect(allowPermission('notifications', 'https://example.com/', ORIGIN)).toBe(true);
});

test("first-run ports are distinct and never a developer Omnix's model service ports", async () => {
  const ports = await choosePorts();
  const values = Object.values(ports);
  expect(new Set(values).size).toBe(values.length);
  for (const developerPort of [5101, 5201, 5301, 8000, 5432]) expect(values).not.toContain(developerPort);
  expect(Object.keys(ports).sort()).toEqual(['httpPort', 'imagePort', 'metricsPort', 'notifyPort', 'pgPort', 'sttPort', 'ttsPort']);
});

test('a development run has its own AppUserModelID, so its shortcut never gives the installed app its icon', () => {
  const builderAppId = /^appId:\s*(\S+)/m.exec(readFileSync(join(__dirname, '..', 'electron-builder.yml'), 'utf8'))?.[1];
  expect(APP_ID).toBe(builderAppId);
  expect(appUserModelId(true)).toBe(APP_ID);
  expect(appUserModelId(false)).toBe(`${APP_ID}.dev`);
});

test.describe('updates (desktop roadmap DT-6.3)', () => {
  test('the menu item checks, shows progress, then offers Restart to Update', () => {
    expect(updateMenuItem({ kind: 'idle' })).toEqual({ label: 'Check for Updates…', action: 'check' });
    expect(updateMenuItem({ kind: 'checking' })).toEqual({ label: 'Checking for Updates…', action: null });
    expect(updateMenuItem({ kind: 'downloading', version: '0.1.5', percent: null }).label).toBe('Downloading Omnix 0.1.5…');
    expect(updateMenuItem({ kind: 'downloading', version: '0.1.5', percent: 42 })).toEqual({ label: 'Downloading Omnix 0.1.5… 42%', action: null });
    expect(updateMenuItem({ kind: 'ready', version: '0.1.5' })).toEqual({ label: 'Restart to Update to 0.1.5', action: 'restart' });
    expect(updateMenuItem({ kind: 'available', version: '0.1.5' })).toEqual({ label: 'Download Omnix 0.1.5…', action: 'download' });
    expect(updateMenuItem({ kind: 'up-to-date' }).action).toBe('check');
    expect(updateMenuItem({ kind: 'failed' }).action).toBe('check');
  });

  test('a check the user asked for always answers, and a ready update can restart from the answer', () => {
    expect(checkResultMessage({ kind: 'up-to-date' }, '0.1.4')).toMatchObject({ message: 'Omnix is up to date', detail: 'Version 0.1.4 is the latest.', confirm: null });
    expect(checkResultMessage({ kind: 'failed' }, '0.1.4')?.message).toBe('Could not check for updates');
    expect(checkResultMessage({ kind: 'downloading', version: '0.1.5', percent: 3 }, '0.1.4')?.confirm).toBeNull();
    expect(checkResultMessage({ kind: 'ready', version: '0.1.5' }, '0.1.4')).toMatchObject({ buttons: ['Restart Now', 'Later'], confirm: 'restart' });
    expect(checkResultMessage({ kind: 'available', version: '0.1.5' }, '0.1.4')).toMatchObject({ confirm: 'download' });
    expect(checkResultMessage({ kind: 'checking' }, '0.1.4')).toBeNull();
  });

  test('the tray tooltip mentions an update only while there is one', () => {
    expect(updateTooltip({ kind: 'up-to-date' })).toBe('');
    expect(updateTooltip({ kind: 'ready', version: '0.1.5' })).toBe('Omnix 0.1.5 is ready: restart to update');
  });
});

test.describe('downloaded models folder', () => {
  test('lives in the install folder, unless that path is too deep for Windows, and a moved folder wins', () => {
    const data = join('C:', 'Users', 'me', 'AppData', 'Local', 'OmnixDesktop');
    expect(installPacksFolder(join('F:', 'Omnix'), data)).toBe(join('F:', 'Omnix', 'packs'));
    const deep = join('D:', 'x'.repeat(MAX_PACKS_FOLDER_LENGTH));
    expect(installPacksFolder(deep, data)).toBe(join(data, 'packs'));
    const paths = { defaultPacks: join('F:', 'Omnix', 'packs') };
    expect(packsFolder(paths)).toBe(paths.defaultPacks);
    expect(packsFolder(paths, join('E:', 'OmnixPacks'))).toBe(join('E:', 'OmnixPacks'));
  });
});
