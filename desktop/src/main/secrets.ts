import { safeStorage } from 'electron';
import { randomBytes } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

/**
 * The secrets the shell owns (desktop roadmap §4.2, as MarketPulse §4.6): the database role passwords and the notification listener's secret.
 * Generated at first run, stored with Electron's safeStorage (DPAPI on Windows, Keychain on macOS), and passed to the
 * supervisor in its environment, never written in plain text. User-entered keys stay in Omnix's own stores.
 */
export interface DesktopSecrets {
  dbOwnerPassword: string;
  dbAppPassword: string;
  notifySecret: string;
  googleClientSecret?: string;
}

function newSecret(): string {
  return randomBytes(32).toString('base64url');
}

export class SecretStore {
  private readonly path: string;

  constructor(secretsDir: string) {
    this.path = join(secretsDir, 'desktop-secrets.bin');
  }

  loadOrCreate(): DesktopSecrets {
    if (!safeStorage.isEncryptionAvailable()) {
      throw new Error('the operating system credential store is not available');
    }
    if (existsSync(this.path)) {
      return JSON.parse(safeStorage.decryptString(readFileSync(this.path))) as DesktopSecrets;
    }
    const created: DesktopSecrets = { dbOwnerPassword: newSecret(), dbAppPassword: newSecret(), notifySecret: newSecret() };
    this.save(created);
    return created;
  }

  save(secrets: DesktopSecrets): void {
    mkdirSync(join(this.path, '..'), { recursive: true });
    const temporary = `${this.path}.tmp`;
    writeFileSync(temporary, safeStorage.encryptString(JSON.stringify(secrets)));
    renameSync(temporary, this.path);
  }
}

/** The supervisor's environment for these secrets (read by app.desktop.env). */
export function secretEnvironment(secrets: DesktopSecrets): Record<string, string> {
  const env: Record<string, string> = {
    OMNIXDESKTOP_DB_OWNER_PASSWORD: secrets.dbOwnerPassword,
    OMNIXDESKTOP_DB_APP_PASSWORD: secrets.dbAppPassword,
    OMNIXDESKTOP_NOTIFY_SECRET: secrets.notifySecret,
  };
  if (secrets.googleClientSecret) env.OMNIXDESKTOP_GOOGLE_CLIENT_SECRET = secrets.googleClientSecret;
  return env;
}
