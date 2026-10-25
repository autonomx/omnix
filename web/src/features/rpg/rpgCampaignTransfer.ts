import { rpgSessionClient } from './api/rpgSessionClient';

/** A campaign carried between Omnix installs as a file (RQ-8.6): saved from Load Game, imported from it. */

function fileName(title: string): string {
  const safe = title.replace(/[^A-Za-z0-9 _-]+/g, '_').trim();
  return `${safe || 'campaign'}.omnix-campaign.json`;
}

/** Save the campaign to a file the browser downloads. */
export async function downloadCampaign(sessionId: string, title: string): Promise<void> {
  const campaignPackage = await rpgSessionClient.exportRpgSession(sessionId);
  const url = URL.createObjectURL(new Blob([JSON.stringify(campaignPackage)], { type: 'application/json' }));
  try {
    const link = document.createElement('a');
    link.href = url;
    link.download = fileName(title);
    document.body.append(link);
    link.click();
    link.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}

function fileText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ''));
    reader.onerror = () => reject(reader.error ?? new Error('The file could not be read.'));
    reader.readAsText(file);
  });
}

/** A campaign file's package, or an error a player can read. */
export async function readCampaignFile(file: File): Promise<Record<string, unknown>> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(await fileText(file));
  } catch {
    throw new Error('This file is not an Omnix campaign.');
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('This file is not an Omnix campaign.');
  }
  return parsed as Record<string, unknown>;
}
