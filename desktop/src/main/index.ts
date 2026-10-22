import {
  app, BrowserWindow, dialog, ipcMain, Menu, nativeImage, Notification, session, shell, Tray,
  type IpcMainEvent, type IpcMainInvokeEvent, type MenuItemConstructorOptions, type WebContents,
} from 'electron';
import { cpSync, existsSync, readdirSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { AlertBadge, alertDotBitmap, NotificationListener } from './notifications';
import { desktopPaths } from './paths';
import { SecretStore, secretEnvironment } from './secrets';
import { SettingsStore, choosePorts, type DesktopSettings } from './settings';
import { BackendSupervisor, type SupervisorEvent } from './supervisor';
import { HOME_PATH, SESSION_PARTITION, WindowManager } from './windows';
import { exportDiagnostics } from './diagnostics';
import { Updates } from './updates';
import { updateMenuItem, updateTooltip } from './updateStatus';
import { appUserModelId, DEV_SHORTCUT_NAME } from './identity';
import { allowPermission } from './permissions';

const paths = desktopPaths();
// Electron's own data (session, cookies, caches) lives with the rest of the desktop app's data.
app.setPath('userData', join(paths.data, 'electron'));
app.setAppUserModelId(appUserModelId(app.isPackaged));

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else if (process.argv.includes('--quit')) {
  // `Omnix --quit` (the installer's shutdown request) with no Omnix running: nothing to stop.
  app.exit(0);
} else {
  void main();
}

let quitting = false;
const SETUP_PATH = '/setup';

async function main(): Promise<void> {
  await app.whenReady();
  const store = SettingsStore.in(paths.data);
  let settings: DesktopSettings = await store.loadOrCreate();
  const secrets = new SecretStore(paths.secrets).loadOrCreate();
  let origin: string | null = null;
  const windows = new WindowManager(paths, store, () => origin);
  const startHidden = process.argv.includes('--hidden');
  let splash: BrowserWindow | null = null;
  let errorWindow: BrowserWindow | null = null;
  let lastStatus: unknown = { kind: 'step', message: 'Starting…' };
  let supervisor: BackendSupervisor;
  // The model services' last reported states, for the setup screen (service events from the supervisor).
  const serviceStates: Record<string, { state: string; message: string }> = {};

  hardenSession(() => origin);

  // Single instance: a second launch shows the running app; `--quit` (the installer, before it replaces the files)
  // quits it cleanly, stopping the backend and PostgreSQL first.
  app.on('second-instance', (_event, argv) => {
    if (argv.includes('--quit')) app.quit();
    else windows.focusMain();
  });

  const sendStatus = (status: unknown) => {
    lastStatus = status;
    for (const window of [splash, errorWindow]) {
      if (window && !window.isDestroyed()) window.webContents.send('ox:status', status);
    }
  };

  // The snapshot a failed update took just before migrating: the only data the user may put back.
  let failedUpdateSnapshot: string | null = null;
  const showError = (event: { message: string; log?: string | null; step?: string; snapshot?: string | null }) => {
    splash?.destroy();
    splash = null;
    if (!errorWindow || errorWindow.isDestroyed()) {
      errorWindow = windows.shellPage('error', { width: 680, height: 420 });
    }
    failedUpdateSnapshot = event.snapshot ?? null;
    const taken = failedUpdateSnapshot ? snapshotTime(failedUpdateSnapshot) : null;
    sendStatus({ kind: 'error', message: event.message, log: event.log ?? '', step: event.step, snapshot: taken });
    errorWindow.show();
  };

  const signedInWorkspace = async (): Promise<string | null> => {
    if (!origin) return null;
    try {
      const response = await session.fromPartition(SESSION_PARTITION).fetch(`${origin}/api/auth/session`, { credentials: 'include' });
      const body = await response.json() as { authenticated?: boolean; workspace_id?: string | null };
      return body.authenticated ? body.workspace_id ?? null : null;
    } catch {
      return null;
    }
  };

  // Trading alerts arrive as desktop notifications (MarketPulse S-6, shared with Omnix's trading module).
  const alertDot = nativeImage.createFromBitmap(alertDotBitmap(16), { width: 16, height: 16 });
  const badge = new AlertBadge((count) => {
    if (process.platform === 'darwin') app.dock?.setBadge(count ? String(count) : '');
    else windows.get('main')?.setOverlayIcon(count ? alertDot : null, count ? `${count} new alert${count === 1 ? '' : 's'}` : '');
  });
  app.on('browser-window-focus', () => badge.seen());
  const shown = new Set<Notification>();
  const listener = new NotificationListener(secrets.notifySecret, {
    signedInWorkspace,
    show: (title, body, url) => {
      const notification = new Notification({ title, body, icon: join(paths.icons, 'icon-256.png') });
      shown.add(notification);
      for (const old of shown) {
        if (shown.size <= 100) break;
        shown.delete(old);
      }
      notification.on('close', () => shown.delete(notification));
      notification.on('click', () => {
        shown.delete(notification);
        if (!origin) return;
        // Only a page of the app itself: the delivery's link is relative, and anything else is ignored.
        const target = new URL(url, origin);
        if (target.origin !== origin) return;
        const main = windows.get('main');
        if (main) {
          void main.loadURL(target.toString());
          windows.focusMain();
        } else {
          windows.open('main', target.toString());
        }
      });
      notification.show();
      tray?.setToolTip(`Omnix — ${title}`);
      badge.alert(BrowserWindow.getFocusedWindow() !== null);
    },
  });
  // The listener must own its port: if another process held it, alerts would go to that process (with the secret).
  let notificationsListening = false;
  const listenForNotifications = async (): Promise<boolean> => {
    if (notificationsListening) return true;
    try {
      await listener.listen(settings.notifyPort);
      notificationsListening = true;
    } catch {
      showError({ message: `port_busy: notifications ${settings.notifyPort}`, step: 'ports' });
    }
    return notificationsListening;
  };

  const openApp = async (firstRun: boolean) => {
    if (!origin) return;
    // The setup screen (desktop roadmap §4.5) opens once, on the first start; later it is Settings, Models.
    const firstPage = settings.setupOffered ? HOME_PATH : SETUP_PATH;
    let url = `${origin}${firstPage}`;
    if (firstRun) {
      // First run: the owner's one-time sign-in; the setup screen then asks for the owner's email and password.
      try {
        const result = await supervisor.command('login-code');
        if (typeof result.code === 'string' && result.code) {
          url = `${origin}/api/auth/local/callback?code=${encodeURIComponent(result.code)}&next=${encodeURIComponent(`${SETUP_PATH}?first_run=1`)}`;
        }
      } catch {
        url = `${origin}/login`;
      }
    }
    if (!settings.setupOffered) settings = store.update((current) => Object.assign(current, { setupOffered: true }));
    const main = windows.open('main', url, { show: !startHidden || firstRun });
    main.on('close', (event) => {
      // Closing the last window keeps Omnix running in the tray, so jobs and downloads carry on.
      if (!quitting && windows.all().length === 1) {
        event.preventDefault();
        main.hide();
      }
    });
    splash?.destroy();
    splash = null;
  };

  const startBackend = (options: { restoreSnapshot?: string } = {}) => {
    errorWindow?.destroy();
    errorWindow = null;
    if (!startHidden && (!splash || splash.isDestroyed())) splash = windows.shellPage('splash');
    const google = googleClient();
    supervisor = new BackendSupervisor(paths, settings,
      { ...secretEnvironment(secrets), ...(google ? { OMNIXDESKTOP_GOOGLE_CLIENT_SECRET: google.clientSecret } : {}) },
      google?.clientId ?? null);
    supervisor.on('event', (event: SupervisorEvent) => {
      if (event.event === 'step') sendStatus({ kind: 'step', message: event.message, step: event.step });
      else if (event.event === 'ready') {
        const firstLaunch = origin === null;
        origin = event.origin;
        if (firstLaunch || !windows.get('main')) void openApp(event.first_run);
        else if (splash && !splash.isDestroyed()) {
          // A restart with the app already open (a packs folder move, Retry): the splash has done its job.
          splash.destroy();
          splash = null;
        }
      } else if (event.event === 'error') showError(event);
      else if (event.event === 'service') {
        serviceStates[event.service] = { state: event.state, message: event.message };
        for (const window of windows.all()) window.webContents.send('ox:service-state', event);
      } else if (event.event === 'restored') {
        showError({
          step: 'restored',
          message: 'Your data is back as it was before the update. This version of Omnix cannot use it: '
            + 'install the previous release, then start Omnix again.',
        });
      }
    });
    supervisor.on('exit', (code: number | null) => {
      if (!quitting && code !== 0 && !errorWindow) showError({ message: `The backend stopped (exit ${code}).`, step: 'backend' });
    });
    supervisor.start(options);
  };

  const probeHardware = async (): Promise<unknown> => (await supervisor.command('hardware', 30_000)).hardware ?? null;

  // IPC from the bundled shell pages.
  ipcMain.on('ox:info', (event) => {
    event.returnValue = { version: app.getVersion(), platform: process.platform, origin };
  });
  ipcMain.on('ox:status-ready', (event) => event.sender.send('ox:status', lastStatus));
  ipcMain.on('ox:retry', (event) => {
    if (!fromShellPage(event)) return;
    void supervisor.stop().then(async () => {
      if (await listenForNotifications()) startBackend();
    });
  });
  ipcMain.on('ox:new-ports', async (event) => {
    if (!fromShellPage(event)) return;
    // The origin changes with the port, which resets window layouts kept in the browser.
    const ports = await choosePorts();
    settings = store.update((current) => Object.assign(current, ports));
    app.relaunch();
    quitting = true;
    await supervisor.stop();
    app.exit(0);
  });
  ipcMain.on('ox:restore-snapshot', (event) => {
    const snapshot = failedUpdateSnapshot;
    if (!fromShellPage(event) || !snapshot) return;
    void supervisor.stop().then(() => startBackend({ restoreSnapshot: snapshot }));
  });
  ipcMain.on('ox:previous-release', (event) => {
    if (fromShellPage(event)) void shell.openExternal(RELEASES_URL);
  });
  ipcMain.on('ox:export-diagnostics', (event) => {
    if (fromShellPage(event) || fromApp(event)) {
      void exportDiagnostics(paths, settings, BrowserWindow.fromWebContents(event.sender), probeHardware);
    }
  });
  ipcMain.on('ox:quit', (event) => {
    if (fromShellPage(event) || fromApp(event)) app.quit();
  });
  ipcMain.on('ox:reveal-logs', (event) => {
    if (fromShellPage(event) || fromApp(event)) void shell.openPath(paths.logs);
  });
  ipcMain.on('ox:close-window', (event) => {
    if (fromShellPage(event)) BrowserWindow.fromWebContents(event.sender)?.close();
  });

  // IPC from the gateway's pages (the `window.omnixDesktop` bridge).
  function fromApp(event: IpcMainEvent | IpcMainInvokeEvent): boolean {
    const url = event.senderFrame?.url;
    return Boolean(origin && url && new URL(url).origin === origin);
  }
  function fromShellPage(event: IpcMainEvent | IpcMainInvokeEvent): boolean {
    const url = event.senderFrame?.url ?? '';
    if (!url.startsWith('file:')) return false;
    try {
      return dirname(fileURLToPath(url)).toLowerCase() === resolve(paths.pages).toLowerCase();
    } catch {
      return false;
    }
  }
  async function ownerSignedIn(): Promise<boolean> {
    if (!origin) return false;
    try {
      const response = await session.fromPartition(SESSION_PARTITION).fetch(`${origin}/api/auth/session`, { credentials: 'include' });
      const body = await response.json() as { authenticated?: boolean; user_id?: string | null };
      return Boolean(body.authenticated && body.user_id === 'user:local');
    } catch {
      return false;
    }
  }
  ipcMain.on('ox:open-external', (event, url: string) => {
    if (!fromApp(event)) return;
    try {
      const parsed = new URL(url);
      if (parsed.protocol === 'https:' || (parsed.protocol === 'http:' && origin && parsed.origin === origin)) {
        void shell.openExternal(parsed.toString());
      }
    } catch {
      // Not a URL: ignored.
    }
  });
  ipcMain.handle('ox:request-login-code', async (event) => {
    if (!fromApp(event) || !origin) return false;
    // Only while the owner has no password; the supervisor refuses otherwise.
    const result = await supervisor.command('login-code');
    if (typeof result.code !== 'string' || !result.code) return false;
    await event.sender.loadURL(`${origin}/api/auth/local/callback?code=${encodeURIComponent(result.code)}&next=${encodeURIComponent(`${SETUP_PATH}?first_run=1`)}`);
    return true;
  });
  ipcMain.handle('ox:service-states', (event) => (fromApp(event) ? { ...serviceStates } : {}));
  ipcMain.handle('ox:refresh-services', async (event) => {
    if (!fromApp(event)) return {};
    try {
      const result = await supervisor.command('reconcile', 120_000);
      return (result.services as Record<string, { state: string; message: string }>) ?? {};
    } catch {
      return { ...serviceStates };
    }
  });
  // The uninstaller reads the moved folder from this plain file (it cannot parse desktop.json) to offer removing it.
  const usePacksFolder = (target: string) => {
    settings = store.update((saved) => Object.assign(saved, { packsDir: target }));
    // UTF-16LE: NSIS's FileReadUTF16LE reads any path; FileRead would use the ANSI code page.
    writeFileSync(join(paths.data, 'packs-location.txt'), Buffer.from(target, 'utf16le'));
  };
  ipcMain.handle('ox:choose-packs-folder', async (event) => {
    if (!fromApp(event) || !(await ownerSignedIn())) return null;
    const window = BrowserWindow.fromWebContents(event.sender);
    const picked = await dialog.showOpenDialog(window ?? undefined as unknown as BrowserWindow, {
      title: 'Where should Omnix keep its downloaded models?',
      properties: ['openDirectory', 'createDirectory'],
    });
    if (picked.canceled || !picked.filePaths[0]) return null;
    const target = join(picked.filePaths[0], 'OmnixPacks');
    const current = settings.packsDir ?? join(paths.data, 'packs');
    if (resolve(target).toLowerCase() === resolve(current).toLowerCase()) return current;
    if (existsSync(target) && readdirSync(target).length > 0) {
      await dialog.showMessageBox({ type: 'warning', title: 'Omnix', message: `${target} is not empty.`,
        detail: 'Choose another folder, or empty this one first.' });
      return null;
    }
    // The model services stop while their packs move; the backend restarts on the new folder.
    await supervisor.stop();
    sendStatus({ kind: 'step', message: 'Moving your downloaded models…' });
    splash = windows.shellPage('splash');
    let leftBehind = '';
    let renamed = false;  // the packs are at the target now: never delete it
    let copying = false;  // the target is this attempt's partial copy: deleting it loses nothing
    try {
      if (existsSync(current)) {
        try {
          renameSync(current, target);
          renamed = true;
        } catch {
          // Another drive: copy, and use the copy as soon as it is complete.
          copying = true;
          // Timestamps kept: a pack's sources keep their times on the new drive (its bytecode needs none).
          cpSync(current, target, { recursive: true, errorOnExist: true, preserveTimestamps: true });
          copying = false;
          usePacksFolder(target);
          try {
            rmSync(current, { recursive: true, force: true });
          } catch {
            leftBehind = current;  // a file still locked (antivirus): the copy is in use, the old folder can go later
          }
        }
      }
      usePacksFolder(target);
    } catch (error) {
      // A copy that failed part-way is removed, so the same folder can be chosen again; a rename whose setting could
      // not be saved is moved back. Either way Omnix carries on with the models where they were.
      if (copying) rmSync(target, { recursive: true, force: true });
      else if (renamed && settings.packsDir !== target) {
        try {
          renameSync(target, current);
        } catch {
          // Left where it is; the error below names the folder.
        }
      }
      startBackend();
      await dialog.showMessageBox({ type: 'error', title: 'Omnix', message: 'The models could not be moved.',
        detail: error instanceof Error ? error.message : String(error) });
      return null;
    }
    startBackend();
    if (leftBehind) {
      void dialog.showMessageBox({ type: 'info', title: 'Omnix', message: 'Your models are in the new folder.',
        detail: `Some files in ${leftBehind} could not be deleted yet; you can delete that folder yourself.` });
    }
    return target;
  });

  const manageLoginItem = app.isPackaged && !process.env.OMNIXDESKTOP_DATA_DIR;
  let updateLabel = '';
  const updates = new Updates((state) => {
    const status = updateTooltip(state);
    if (status) tray?.setToolTip(`Omnix — ${status}`);
    const label = updateMenuItem(state).label;
    if (label === updateLabel) return;
    updateLabel = label;
    trayMenu?.refresh();
    Menu.setApplicationMenu(buildMenu(() => origin, windows, paths.logs, () => updateMenuItems(updates)));
  });
  const trayMenu = createTray(() => windows.focusMain(), () => openPage(origin, windows, '/settings'),
    () => openPage(origin, windows, SETUP_PATH), () => app.quit(), {
      updateItems: () => updateMenuItems(updates),
      startAtLogin: () => settings.startAtLogin,
      setStartAtLogin: (on) => {
        settings = store.update((current) => Object.assign(current, { startAtLogin: on }));
        if (manageLoginItem) app.setLoginItemSettings({ openAtLogin: on, args: ['--hidden'] });
      },
    });
  const tray: Tray | null = trayMenu?.tray ?? null;
  if (process.platform === 'darwin') {
    app.dock?.setMenu(Menu.buildFromTemplate([{ label: 'Show Omnix', click: () => windows.focusMain() }]));
    if (!app.isPackaged) app.dock?.setIcon(join(paths.icons, 'icon-256.png'));
  }
  if (process.platform === 'win32' && !app.isPackaged && !process.env.OMNIXDESKTOP_DATA_DIR) {
    // Windows shows a development run's notifications only through a Start menu shortcut with its AppUserModelID.
    shell.writeShortcutLink(join(app.getPath('appData'), 'Microsoft', 'Windows', 'Start Menu', 'Programs', DEV_SHORTCUT_NAME), {
      target: process.execPath,
      args: `"${app.getAppPath()}"`,
      icon: join(paths.icons, 'icon.ico'),
      iconIndex: 0,
      appUserModelId: appUserModelId(false),
      description: 'Omnix (development run)',
    });
  }
  Menu.setApplicationMenu(buildMenu(() => origin, windows, paths.logs, () => updateMenuItems(updates)));
  if (manageLoginItem) app.setLoginItemSettings({ openAtLogin: settings.startAtLogin, args: ['--hidden'] });
  // A daily pg_dump while the backend runs; the supervisor keeps the newest seven.
  setInterval(() => void backupIfDue(), 60 * 60_000);

  app.on('window-all-closed', () => {
    // Keep running in the tray (macOS and Windows alike); Quit is in the tray and the menu.
  });
  app.on('activate', () => windows.focusMain());
  app.on('before-quit', (event) => {
    // Every quit waits for the backend: a second Quit while it stops would otherwise orphan the supervisor.
    event.preventDefault();
    if (quitting) return;
    quitting = true;
    listener.close();
    void supervisor.stop().then(() => app.exit(0));
  });

  updates.start();
  if (await listenForNotifications()) startBackend();

  async function backupIfDue(): Promise<void> {
    const last = settings.lastBackupAt ? Date.parse(settings.lastBackupAt) : 0;
    if (!origin || Date.now() - last < 24 * 60 * 60_000) return;
    try {
      const result = await supervisor.command('backup', 30 * 60_000);
      if (typeof result.path === 'string') {
        settings = store.update((current) => Object.assign(current, { lastBackupAt: new Date().toISOString() }));
      }
    } catch {
      // Retried within the hour.
    }
  }
}

const RELEASES_URL = 'https://github.com/autonomx/omnix-desktop/releases';

/** The time in a snapshot's name (pgdata-20261017T183955Z), as the error page shows it. */
function snapshotTime(snapshot: string): string {
  const match = /pgdata-(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})/.exec(snapshot);
  return match ? `${match[1]}-${match[2]}-${match[3]} ${match[4]}:${match[5]} UTC` : 'before the update';
}

/**
 * The build's Google OAuth client of type Desktop (google-oauth.json next to the app, or desktop/config in
 * development), or null: Google sign-in is offered only when the publisher configured one. A Desktop client's secret
 * is not confidential (it ships with every install); PKCE protects the flow.
 */
function googleClient(): { clientId: string; clientSecret: string } | null {
  const candidates = [join(process.resourcesPath ?? '', 'google-oauth.json'), join(__dirname, '..', 'config', 'google-oauth.json')];
  if (!app.isPackaged && process.env.OMNIXDESKTOP_GOOGLE_OAUTH) candidates.unshift(process.env.OMNIXDESKTOP_GOOGLE_OAUTH);
  for (const candidate of candidates) {
    if (!existsSync(candidate)) continue;
    try {
      const parsed = JSON.parse(readFileSync(candidate, 'utf8')) as { client_id?: string; client_secret?: string };
      if (parsed.client_id && parsed.client_secret) return { clientId: parsed.client_id, clientSecret: parsed.client_secret };
    } catch {
      // A broken file means no Google sign-in, not a broken app.
    }
  }
  return null;
}

function hardenSession(origin: () => string | null): void {
  for (const target of [session.fromPartition(SESSION_PARTITION), session.defaultSession]) {
    // Notifications, clipboard writes, and the microphone for the app's own pages only (live voice, dictation).
    target.setPermissionRequestHandler((contents: WebContents | null, permission, callback, details) => {
      const requesting = (details as { requestingUrl?: string }).requestingUrl ?? contents?.getURL() ?? '';
      const mediaTypes = (details as { mediaTypes?: string[] }).mediaTypes ?? [];
      callback(allowPermission(permission, requesting, origin(), mediaTypes));
    });
    target.setPermissionCheckHandler((_contents, permission, requestingOrigin, details) => {
      const mediaType = (details as { mediaType?: string }).mediaType;
      return allowPermission(permission, requestingOrigin, origin(), mediaType ? [mediaType] : []);
    });
  }
  app.on('web-contents-created', (_event, contents) => {
    contents.on('will-attach-webview', (event) => event.preventDefault());
  });
}

interface TrayToggles {
  updateItems: () => MenuItemConstructorOptions[];
  startAtLogin: () => boolean;
  setStartAtLogin: (on: boolean) => void;
}

function createTray(
  show: () => void, openSettings: () => void, openSetup: () => void, quit: () => void, toggles: TrayToggles,
): { tray: Tray; refresh: () => void } | null {
  try {
    const name = process.platform === 'darwin' ? 'trayTemplate.png' : process.platform === 'win32' ? 'icon-32.png' : 'icon-16.png';
    const icon = nativeImage.createFromPath(join(__dirname, 'icons', name));
    if (process.platform === 'darwin') icon.setTemplateImage(true);
    const tray = new Tray(icon);
    tray.setToolTip('Omnix');
    const menu = () => Menu.buildFromTemplate([
      { label: 'Show Omnix', click: show },
      { label: 'Models and downloads…', click: openSetup },
      { label: 'Settings…', click: openSettings },
      ...toggles.updateItems(),
      { type: 'separator' },
      { label: 'Start Omnix when I sign in', type: 'checkbox', checked: toggles.startAtLogin(),
        click: (item) => toggles.setStartAtLogin(item.checked) },
      { type: 'separator' },
      { label: 'Quit Omnix', click: quit },
    ]);
    tray.setContextMenu(menu());
    tray.on('right-click', () => tray.setContextMenu(menu()));
    tray.on('click', show);
    return { tray, refresh: () => tray.setContextMenu(menu()) };
  } catch {
    return null;
  }
}

function updateMenuItems(updates: Updates): MenuItemConstructorOptions[] {
  if (!updates.enabled) return [];
  const { label, action } = updateMenuItem(updates.current());
  return [{ label, enabled: action !== null, click: () => { if (action) updates.act(action); } }];
}

/** Shows a page of the app in the main window, opening it if it is closed; nothing before the backend is up. */
function openPage(origin: string | null, windows: WindowManager, path: string): void {
  const main = windows.get('main');
  if (origin && main) {
    void main.loadURL(`${origin}${path}`);
    windows.focusMain();
  } else if (origin) {
    windows.open('main', `${origin}${path}`);
  }
}

function buildMenu(
  origin: () => string | null, windows: WindowManager, logs: string, updateItems: () => MenuItemConstructorOptions[],
): Menu {
  const go = (path: string) => () => openPage(origin(), windows, path);
  const template: MenuItemConstructorOptions[] = [
    ...(process.platform === 'darwin' ? [{ role: 'appMenu' as const }] : []),
    {
      label: 'File',
      submenu: [
        { label: 'Chat', click: go(HOME_PATH) },
        { label: 'Models and downloads…', click: go(SETUP_PATH) },
        { label: 'Settings…', click: go('/settings') },
        { type: 'separator' },
        { label: 'Open logs folder', click: () => void shell.openPath(logs) },
        { label: 'Export diagnostics…', click: () => void exportDiagnostics(paths, SettingsStore.in(paths.data).load(), null) },
        { type: 'separator' },
        { role: 'quit' },
      ],
    },
    { role: 'editMenu' },
    {
      label: 'View',
      submenu: [
        { role: 'reload', accelerator: 'F5' },
        { role: 'togglefullscreen' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        ...(app.isPackaged ? [] : [{ type: 'separator' as const }, { role: 'toggleDevTools' as const }]),
      ],
    },
    { role: 'windowMenu' },
    {
      role: 'help',
      submenu: [
        { label: `Omnix ${app.getVersion()}`, enabled: false },
        ...updateItems(),
        { label: 'Third-party licences', click: () => void shell.openPath(join(desktopPaths().resources, 'licenses')) },
      ],
    },
  ];
  return Menu.buildFromTemplate(template);
}
