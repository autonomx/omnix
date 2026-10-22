// Builds the installer for the staged runtime's platform from out/ (desktop roadmap DT-6.1, DT-8.4):
// Windows NSIS from a windows-x64 stage, macOS dmg + zip from a macos-arm64 or macos-x64 stage (on a Mac).
import { Arch, build, Platform } from 'electron-builder';
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const stage = join(root, 'staging', 'stage');
const fail = (message) => {
  console.error(message);
  process.exit(1);
};

const infoPath = join(stage, 'build-info.json');
if (!existsSync(infoPath)) fail('desktop/staging/stage/build-info.json is missing: run `python desktop/staging/stage.py all`');
const info = JSON.parse(readFileSync(infoPath, 'utf8'));
const stagedPlatform = info.platform ?? 'windows-x64';
const mac = stagedPlatform.startsWith('macos-');
if (mac !== (process.platform === 'darwin')) {
  fail(`desktop/staging/stage holds the ${stagedPlatform} runtime; build its installer on ${mac ? 'macOS' : 'Windows'}`);
}

const required = mac
  ? ['python/bin/python3', 'postgres/bin/postgres']
  : ['python/python.exe', 'postgres/bin/postgres.exe'];
for (const part of [...required, 'app/src/app/desktop/supervise.py', 'app/requirements/desktop/packs/torch-windows-x64.json', 'web/dist/index.html']) {
  if (!existsSync(join(stage, part))) {
    fail(`desktop/staging/stage/${part} is missing: run \`python desktop/staging/stage.py all\` (after \`npm --prefix web run build\`)`);
  }
}

// Notarize only with Apple credentials (an App Store Connect API key, or an Apple ID app-specific password).
const appleCredentials = Boolean(
  (process.env.APPLE_API_KEY && process.env.APPLE_API_KEY_ID && process.env.APPLE_API_ISSUER)
  || (process.env.APPLE_ID && process.env.APPLE_APP_SPECIFIC_PASSWORD && process.env.APPLE_TEAM_ID),
);
if (mac && !appleCredentials) console.warn('no Apple notarization credentials: the app is not notarized');

// Without a Developer ID the app is signed ad hoc. Flipping the Electron fuses rewrites the binaries, and Apple silicon
// kills a bundle whose signature no longer matches, so an unsigned build would not start even on the Mac that built it.
const developerId = mac && Boolean(process.env.CSC_LINK || process.env.CSC_NAME
  || execFileSync('security', ['find-identity', '-v', '-p', 'codesigning'], { encoding: 'utf8' }).includes('Developer ID Application'));
if (mac && !developerId) console.warn('no Developer ID: the app is signed ad hoc and runs only on this Mac');

// Windows signing (desktop roadmap DT-6.2), from the environment; without it the installer is unsigned.
// - Azure Artifact Signing (formerly Trusted Signing): OMNIXDESKTOP_AZURE_SIGNING_ENDPOINT, _ACCOUNT and _PROFILE, plus
//   AZURE_TENANT_ID, AZURE_CLIENT_ID and AZURE_CLIENT_SECRET for the signing identity.
// - A certificate file: electron-builder's own WIN_CSC_LINK (or CSC_LINK) and CSC_KEY_PASSWORD.
// OMNIXDESKTOP_SIGNING_PUBLISHER is the certificate's subject name; updates are installed only when signed by it.
const env = process.env;
const publisher = env.OMNIXDESKTOP_SIGNING_PUBLISHER;
const azure = env.OMNIXDESKTOP_AZURE_SIGNING_ENDPOINT && env.OMNIXDESKTOP_AZURE_SIGNING_ACCOUNT
  && env.OMNIXDESKTOP_AZURE_SIGNING_PROFILE;
const certificate = env.WIN_CSC_LINK || env.CSC_LINK;
let windowsSigning = {};
if (!mac && (azure || certificate)) {
  if (!publisher) fail('set OMNIXDESKTOP_SIGNING_PUBLISHER to the signing certificate subject name');
  windowsSigning = azure
    ? { azureSignOptions: { publisherName: publisher, endpoint: env.OMNIXDESKTOP_AZURE_SIGNING_ENDPOINT,
      codeSigningAccountName: env.OMNIXDESKTOP_AZURE_SIGNING_ACCOUNT, certificateProfileName: env.OMNIXDESKTOP_AZURE_SIGNING_PROFILE } }
    : { signtoolOptions: { publisherName: publisher } };
} else if (!mac) {
  console.warn('no signing configured: the installer is unsigned (SmartScreen warns on other machines)');
}

const targets = mac
  ? Platform.MAC.createTarget(['dmg', 'zip'], stagedPlatform === 'macos-arm64' ? Arch.arm64 : Arch.x64)
  : Platform.WINDOWS.createTarget(['nsis'], Arch.x64);

await build({
  projectDir: root,
  targets,
  config: {
    extends: join(root, 'electron-builder.yml'),
    ...(mac ? { mac: { notarize: appleCredentials, ...(developerId ? {} : { identity: '-' }) } } : { win: windowsSigning }),
  },
  publish: process.argv.includes('--publish') ? 'always' : 'never',
});
console.log(`${stagedPlatform} installer written to desktop/release/`);
