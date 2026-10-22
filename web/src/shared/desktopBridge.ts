/**
 * The desktop shells' bridge, exposed by the Electron preload: `window.omnixDesktop` in the Omnix desktop app
 * (desktop roadmap §4.2), `window.marketPulse` in MarketPulse (W-2). In a browser there is none and every caller keeps
 * its browser behaviour.
 */
export interface TitleBarOverlayColors {
  /** Background of the window-control area. */
  color: string;
  /** Colour of the minimise, maximise and close symbols. */
  symbolColor: string;
}

export interface DesktopServiceState {
  state: string;
  message: string;
}

export interface DesktopBridge {
  /** Which shell: `omnix` for the Omnix desktop app; absent in MarketPulse. */
  readonly product?: 'omnix';
  /** False when the windows keep their native title bar; MarketPulse's are frameless (absent means frameless). */
  readonly frameless?: boolean;
  /** The desktop app's version. */
  readonly version: string;
  /** The platform the shell runs on (`win32`, `darwin`, …). */
  readonly platform: string;
  /** Colours the native window controls drawn over the title-bar area. */
  setTitleBarOverlay(colors: TitleBarOverlayColors): void;
  /** Opens the folder holding the app's logs. */
  revealLogs(): void;
  /** Opens a URL in the system browser (Google sign-in, which refuses embedded browsers). */
  openExternal(url: string): void;
  /** Asks the shell for a fresh first-run sign-in code; false once first run is done. */
  requestLoginCode(): Promise<boolean>;
  /** Omnix: the model services' states (starting, running, blocked, failed) as the supervisor reports them. */
  serviceStates?(): Promise<Record<string, DesktopServiceState>>;
  /** Omnix: look at the installed packs now, after an install or removal, and return the services' states. */
  refreshServices?(): Promise<Record<string, DesktopServiceState>>;
  /** Omnix: move the downloaded runtimes and models to a folder the user picks; the new folder, or null. */
  choosePacksFolder?(): Promise<string | null>;
  /** Omnix: save a zip of logs, versions and pack manifests (no secrets). */
  exportDiagnostics?(): void;
}

declare global {
  interface Window {
    omnixDesktop?: DesktopBridge;
    marketPulse?: DesktopBridge;
  }
}

/** The bridge, or null outside a desktop app. */
export function desktopBridge(): DesktopBridge | null {
  if (typeof window === 'undefined') return null;
  return window.omnixDesktop ?? window.marketPulse ?? null;
}

/** Whether this page runs inside a desktop app. */
export function isDesktopApp(): boolean {
  return desktopBridge() !== null;
}

/** Whether the windows are frameless, so the page draws its own title-bar area (MarketPulse W-4). */
export function hasFramelessWindow(bridge: DesktopBridge | null = desktopBridge()): boolean {
  return bridge !== null && bridge.frameless !== false;
}
