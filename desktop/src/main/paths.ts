import { app } from 'electron';
import { existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';

/**
 * Where things live (desktop roadmap §4.9). Packaged, the staged runtime is the app's resources folder; in development
 * it is desktop/staging/stage. OMNIXDESKTOP_DATA_DIR and OMNIXDESKTOP_RESOURCES move them for tests.
 */
export interface DesktopPaths {
  /** python/, postgres/, ffmpeg/, app/, web/ (desktop/staging/stage in development). */
  resources: string;
  /** All per-user data: pgdata, logs, secrets, snapshots, backups, resources, Electron's own session data. */
  data: string;
  /**
   * Where downloaded runtimes and models go unless the user moved them (settings.packsDir): on Windows, the installed
   * app's own folder, so removing Omnix's folder removes its downloads; elsewhere, and in development, the data folder.
   */
  defaultPacks: string;
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

/**
 * The deepest file a pack holds is about 165 characters below the packs folder (a runtime's
 * site/transformers/.../__pycache__/...pyc), and Windows paths stop at 260: a packs folder longer than this stays in the
 * data folder (%LOCALAPPDATA%, short) rather than next to an app installed in a deep folder.
 */
export const MAX_PACKS_FOLDER_LENGTH = 90;

export function installPacksFolder(installFolder: string, data: string): string {
  const packs = join(installFolder, 'packs');
  return packs.length <= MAX_PACKS_FOLDER_LENGTH ? packs : join(data, 'packs');
}

/** The packs folder in use: the one the user moved them to, or the default. */
export function packsFolder(paths: Pick<DesktopPaths, 'defaultPacks'>, packsDir?: string): string {
  return packsDir ?? paths.defaultPacks;
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
    defaultPacks: app.isPackaged && process.platform === 'win32' ? installPacksFolder(dirname(process.execPath), data) : join(data, 'packs'),
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
