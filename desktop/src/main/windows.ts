import { BrowserWindow, dialog, screen, shell, type BrowserWindowConstructorOptions, type Rectangle } from 'electron';
import { join } from 'node:path';
import { classify } from './navigation';
import type { DesktopPaths } from './paths';
import type { SettingsStore, WindowState } from './settings';

export const SESSION_PARTITION = 'persist:omnix-desktop';
/** The page a window opens when nothing else is asked for. */
export const HOME_PATH = '/chatbot';

function visibleOnSomeDisplay(bounds: Rectangle): boolean {
  return screen.getAllDisplays().some(({ workArea }) => (
    bounds.x < workArea.x + workArea.width && bounds.x + bounds.width > workArea.x
    && bounds.y < workArea.y + workArea.height && bounds.y + bounds.height > workArea.y
  ));
}

/**
 * The app's windows (desktop roadmap §4.2): ordinary framed BrowserWindows (Omnix's layout has its own header, so the
 * native title bar stays), all on one session so window sets share cookies and BroadcastChannel.
 */
export class WindowManager {
  private readonly windows = new Map<string, BrowserWindow>();
  private counter = 0;

  constructor(private readonly paths: DesktopPaths, private readonly store: SettingsStore,
              private readonly origin: () => string | null) {}

  get(key: string): BrowserWindow | undefined {
    const window = this.windows.get(key);
    return window && !window.isDestroyed() ? window : undefined;
  }

  all(): BrowserWindow[] {
    return [...this.windows.values()].filter((window) => !window.isDestroyed());
  }

  focusMain(): void {
    const main = this.get('main') ?? this.all()[0];
    if (!main) {
      // Every window is gone (the last one is normally hidden, not closed): the Dock, the tray and a second launch
      // still bring Omnix back.
      const origin = this.origin();
      if (origin) this.open('main', `${origin}${HOME_PATH}`);
      return;
    }
    if (main.isMinimized()) main.restore();
    main.show();
    main.focus();
  }

  baseOptions(): BrowserWindowConstructorOptions {
    return {
      backgroundColor: '#0f1116',
      icon: join(this.paths.icons, process.platform === 'win32' ? 'icon.ico' : 'icon.png'),
      title: 'Omnix',
      autoHideMenuBar: process.platform !== 'darwin',
      webPreferences: {
        preload: this.paths.preload,
        partition: SESSION_PARTITION,
        contextIsolation: true,
        sandbox: true,
        nodeIntegration: false,
        webSecurity: true,
        spellcheck: false,
      },
    };
  }

  open(key: string, url: string, options: { show?: boolean } = {}): BrowserWindow {
    const existing = this.get(key);
    if (existing) {
      void existing.loadURL(url);
      existing.focus();
      return existing;
    }
    const saved: WindowState | undefined = this.store.load()?.windows[key];
    const bounds = saved && saved.x !== undefined && saved.y !== undefined
      && visibleOnSomeDisplay({ x: saved.x, y: saved.y, width: saved.width, height: saved.height })
      ? { x: saved.x, y: saved.y, width: saved.width, height: saved.height }
      : { width: saved?.width ?? 1440, height: saved?.height ?? 900 };
    const window = new BrowserWindow({ ...this.baseOptions(), ...bounds, minWidth: 900, minHeight: 600, show: false });
    this.windows.set(key, window);
    // A first launch fills the screen: below 1500 px wide the chat's Live Voice rail moves under the chat.
    const maximized = saved ? saved.maximized === true : true;
    window.once('ready-to-show', () => {
      if (options.show === false) {
        // Maximizing shows a window, so one that starts in the tray maximizes when it is first shown.
        if (maximized) window.once('show', () => window.maximize());
        return;
      }
      if (maximized) window.maximize();
      window.show();
    });
    this.guard(window);
    const remember = () => {
      if (window.isDestroyed()) return;
      const current = window.getNormalBounds();
      this.store.update((settings) => {
        settings.windows[key] = { ...current, maximized: window.isMaximized() };
      });
    };
    let timer: NodeJS.Timeout | null = null;
    const later = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(remember, 500);
    };
    window.on('resize', later);
    window.on('move', later);
    window.on('close', remember);
    window.on('closed', () => this.windows.delete(key));
    void window.loadURL(url);
    return window;
  }

  /** Navigation lock and window-open handling for one window. */
  private guard(window: BrowserWindow): void {
    const contents = window.webContents;
    contents.setWindowOpenHandler(({ url, frameName }) => {
      const origin = this.origin();
      const decision = origin ? classify(url, origin, 'window-open') : 'deny';
      if (decision === 'window') {
        // Window sets name their windows (omnix-trading-<key>); the same name reuses its window.
        const key = frameName && frameName !== '_blank' ? frameName : `window-${++this.counter}`;
        this.open(key, url);
      } else if (decision === 'open-external') {
        void shell.openExternal(url);
      }
      return { action: 'deny' };
    });
    contents.on('will-navigate', (event, url) => {
      const origin = this.origin();
      const decision = origin ? classify(url, origin, 'navigate') : 'deny';
      if (decision === 'stay') return;
      event.preventDefault();
      if (decision === 'open-external') void shell.openExternal(url);
    });
    // A server redirect gets the same rules as a navigation.
    contents.on('will-redirect', (event, url) => {
      const origin = this.origin();
      if (origin && classify(url, origin, 'navigate') === 'stay') return;
      event.preventDefault();
    });
    contents.on('will-attach-webview', (event) => event.preventDefault());
    // The crash view: a page whose renderer died says so and offers a reload, instead of a blank window.
    contents.on('render-process-gone', (_event, details) => {
      if (details.reason === 'clean-exit' || window.isDestroyed()) return;
      const cause = details.reason === 'oom' ? 'ran out of memory' : 'stopped unexpectedly';
      void dialog.showMessageBox(window, {
        type: 'warning',
        title: 'Omnix',
        message: 'This window stopped working.',
        detail: `The page ${cause} (${details.reason}). Your data, jobs and downloads are unaffected: the Omnix `
          + 'service keeps running.',
        buttons: ['Reload', 'Close window'],
        defaultId: 0,
        cancelId: 1,
      }).then(({ response }) => {
        if (window.isDestroyed()) return;
        if (response === 0) contents.reload();
        else window.close();
      });
    });
  }

  /** A small local page (splash, error, crash) from the app bundle. */
  shellPage(name: 'splash' | 'error', options: Partial<BrowserWindowConstructorOptions> = {}): BrowserWindow {
    const window = new BrowserWindow({
      width: 520,
      height: 340,
      resizable: false,
      frame: false,
      show: false,
      backgroundColor: '#0f1116',
      icon: join(this.paths.icons, process.platform === 'win32' ? 'icon.ico' : 'icon.png'),
      title: 'Omnix',
      ...options,
      webPreferences: { preload: this.paths.preload, contextIsolation: true, sandbox: true, nodeIntegration: false },
    });
    window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    window.webContents.on('will-navigate', (event) => event.preventDefault());
    window.once('ready-to-show', () => window.show());
    void window.loadFile(join(this.paths.pages, `${name}.html`));
    return window;
  }
}
