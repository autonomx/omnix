import { createServer } from 'node:net';
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';

/** Saved bounds of one window, by window key (`main`, or a window set's key). */
export interface WindowState {
  x?: number;
  y?: number;
  width: number;
  height: number;
  maximized?: boolean;
}

/**
 * What the shell decides once and keeps (desktop roadmap §4.2): the ports, chosen at first run and never moved
 * silently (the HTTP port is part of the origin, which owns the window layouts; the model services' ports are never a
 * developer Omnix's 5101/5201/5301), plus preferences, the packs folder and window bounds.
 */
export interface DesktopSettings {
  httpPort: number;
  pgPort: number;
  metricsPort: number;
  notifyPort: number;
  sttPort: number;
  ttsPort: number;
  imagePort: number;
  startAtLogin: boolean;
  /** Where runtime and model packs live, when the user moved them (Settings, Models); the data folder otherwise. */
  packsDir?: string;
  /** Whether the setup screen has been offered once (it stays in Settings, Models). */
  setupOffered?: boolean;
  /** When the daily backup last succeeded (ISO time); absent before the first. */
  lastBackupAt?: string;
  windows: Record<string, WindowState>;
}

type PortSettings = Pick<DesktopSettings, 'httpPort' | 'pgPort' | 'metricsPort' | 'notifyPort' | 'sttPort' | 'ttsPort' | 'imagePort'>;

const DEFAULT_PORTS: PortSettings = {
  httpPort: 47900, metricsPort: 47901, notifyPort: 47902, pgPort: 47903, sttPort: 47911, ttsPort: 47912, imagePort: 47913,
};

export function portFree(port: number): Promise<boolean> {
  return new Promise((resolvePromise) => {
    const server = createServer();
    server.once('error', () => resolvePromise(false));
    server.listen({ port, host: '127.0.0.1', exclusive: true }, () => server.close(() => resolvePromise(true)));
  });
}

function anyFreePort(): Promise<number> {
  return new Promise((resolvePromise, reject) => {
    const server = createServer();
    server.once('error', reject);
    server.listen({ port: 0, host: '127.0.0.1' }, () => {
      const address = server.address();
      const port = typeof address === 'object' && address ? address.port : 0;
      server.close(() => resolvePromise(port));
    });
  });
}

/** First run: the default ports where free, otherwise any free port; later runs never change them. */
export async function choosePorts(): Promise<PortSettings> {
  const chosen: Record<string, number> = {};
  const taken = new Set<number>();
  for (const [name, port] of Object.entries(DEFAULT_PORTS)) {
    let candidate = port;
    if (!(await portFree(candidate)) || taken.has(candidate)) {
      do candidate = await anyFreePort(); while (taken.has(candidate));
    }
    taken.add(candidate);
    chosen[name] = candidate;
  }
  return chosen as PortSettings;
}

export class SettingsStore {
  constructor(private readonly path: string) {}

  static in(dataDir: string): SettingsStore {
    return new SettingsStore(join(dataDir, 'desktop.json'));
  }

  exists(): boolean {
    return existsSync(this.path);
  }

  load(): DesktopSettings | null {
    if (!this.exists()) return null;
    return JSON.parse(readFileSync(this.path, 'utf8')) as DesktopSettings;
  }

  save(settings: DesktopSettings): void {
    mkdirSync(dirname(this.path), { recursive: true });
    const temporary = `${this.path}.tmp`;
    writeFileSync(temporary, JSON.stringify(settings, null, 2), 'utf8');
    renameSync(temporary, this.path);
  }

  async loadOrCreate(): Promise<DesktopSettings> {
    const existing = this.load();
    if (existing) return existing;
    const created: DesktopSettings = { ...(await choosePorts()), startAtLogin: false, windows: {} };
    this.save(created);
    return created;
  }

  update(change: (settings: DesktopSettings) => void): DesktopSettings {
    const settings = this.load();
    if (!settings) throw new Error('settings are not created yet');
    change(settings);
    this.save(settings);
    return settings;
  }
}
