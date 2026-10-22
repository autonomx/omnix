import { app } from 'electron';
import { existsSync } from 'node:fs';
import { join, resolve } from 'node:path';

/**
 * Where things live (desktop roadmap §4.9). Packaged, the staged runtime is the app's resources folder; in development
 * it is desktop/staging/stage. OMNIXDESKTOP_DATA_DIR and OMNIXDESKTOP_RESOURCES move them for tests.
 */
export interface DesktopPaths {
  /** python/, postgres/, ffmpeg/, app/, web/ (desktop/staging/stage in development). */
  resources: string;
  /** All per-user data: pgdata, logs, secrets, snapshots, backups, resources, packs, Electron's own session data. */
  data: string;
  logs: string;
  secrets: string;
  python: string;
  postgresBin: string;
  /** The bundled ffmpeg, or null where none is staged (it is then looked up on PATH). */
  ffmpeg: string | null;
  icons: string;
  pages: string;
  preload: string;
}

export function desktopPaths(): DesktopPaths {
  // OMNIXDESKTOP_RESOURCES chooses which python runs, so an installed app never takes it from the environment.
  const resources = process.env.OMNIXDESKTOP_RESOURCES && !app.isPackaged
    ? resolve(process.env.OMNIXDESKTOP_RESOURCES)
    : app.isPackaged ? join(process.resourcesPath, 'runtime') : resolve(__dirname, '..', 'staging', 'stage');
  // OmnixDesktop, not Omnix: the app never reads or rotates a developer Omnix's secrets on the same machine.
  const data = process.env.OMNIXDESKTOP_DATA_DIR
    ? resolve(process.env.OMNIXDESKTOP_DATA_DIR)
    : process.platform === 'win32'
      ? join(process.env.LOCALAPPDATA ?? app.getPath('appData'), 'OmnixDesktop')
      : join(app.getPath('appData'), 'OmnixDesktop');
  const python = process.platform === 'win32' ? join(resources, 'python', 'python.exe') : join(resources, 'python', 'bin', 'python3');
  const ffmpeg = join(resources, 'ffmpeg', process.platform === 'win32' ? 'ffmpeg.exe' : 'ffmpeg');
  return {
    resources,
    data,
    logs: join(data, 'logs'),
    secrets: join(data, 'secrets'),
    python,
    postgresBin: join(resources, 'postgres', 'bin'),
    ffmpeg: existsSync(ffmpeg) ? ffmpeg : null,
    icons: join(__dirname, 'icons'),
    pages: join(__dirname, 'pages'),
    preload: join(__dirname, 'preload.js'),
  };
}
