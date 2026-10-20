import type { AssetListResponse } from '../../api/client';

export type VoiceAsset = AssetListResponse['assets'][number];

/** The voice a job names: its asset id, which the TTS provider resolves (WP-4.10). */
export function voiceReference(asset: VoiceAsset | undefined): string {
  const value = (asset as { id?: unknown } | undefined)?.id;
  return typeof value === 'string' ? value : '';
}

export function voiceFileName(asset: VoiceAsset | undefined): string {
  const value = (asset as { file_name?: unknown } | undefined)?.file_name;
  return typeof value === 'string' ? value : '';
}

export function voiceAssetId(asset: VoiceAsset | undefined): string {
  const value = (asset as { id?: unknown } | undefined)?.id;
  return typeof value === 'string' ? value : 'voice';
}

export function voiceAssetMetadata(asset: VoiceAsset): Record<string, unknown> {
  const value = (asset as { metadata?: unknown }).metadata;
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

export function voiceAssetName(asset: VoiceAsset): string {
  const metadata = voiceAssetMetadata(asset);
  const preferred = metadata.profile_name ?? metadata.name ?? metadata.voice_name ?? metadata.title;
  if (typeof preferred === 'string' && preferred.trim()) return preferred.trim();
  const source = voiceFileName(asset) || voiceAssetId(asset);
  return source.split(/[\\/]/).pop()?.replace(/\.[^.]+$/, '') || voiceAssetId(asset);
}

export function voiceProfileName(asset: VoiceAsset): string {
  const metadata = voiceAssetMetadata(asset);
  const preferred = metadata.voice_id ?? metadata.voice_clone_id;
  if (typeof preferred === 'string' && preferred.trim()) return preferred.trim();
  return voiceAssetId(asset).replace(/^voice-cloning:/, '').replace(/^asset:/, '');
}

export function voiceInitial(asset: VoiceAsset): string {
  return voiceAssetName(asset).slice(0, 2).toUpperCase() || 'VC';
}

/** Where a library voice came from. */
export function voiceSource(asset: VoiceAsset): 'cloned' | 'designed' | 'preset' {
  const source = voiceAssetMetadata(asset).source;
  if (source === 'designed' || source === 'preset') return source;
  return asset.module === 'voice-cloning' ? 'cloned' : 'preset';
}

export function voiceLanguage(asset: VoiceAsset): string {
  const language = voiceAssetMetadata(asset).language;
  return typeof language === 'string' ? language : '';
}

export function findMatchingVoice(name: string, assets: VoiceAsset[]): VoiceAsset | undefined {
  const normalizedName = name.toLowerCase();
  return assets.find((asset) => voiceAssetName(asset).toLowerCase().includes(normalizedName) || voiceProfileName(asset).toLowerCase().includes(normalizedName));
}

/** Older saved assignments name the voice's file path; newer ones its asset id. */
export function findVoiceByReference(voiceId: string, assets: VoiceAsset[]): VoiceAsset | undefined {
  const fileName = voiceId.split(/[\\/]/).pop();
  return assets.find((entry) => voiceReference(entry) === voiceId || (Boolean(fileName) && voiceFileName(entry) === fileName));
}

export function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatPlaybackTime(value: number): string {
  const safe = Number.isFinite(value) ? Math.max(0, value) : 0;
  const minutes = Math.floor(safe / 60).toString().padStart(2, '0');
  const seconds = Math.floor(safe % 60).toString().padStart(2, '0');
  return `${minutes}:${seconds}`;
}

export function safeDownloadName(value: string): string {
  return value.replace(/[^A-Za-z0-9_.-]+/g, '-').replace(/^-+|-+$/g, '') || 'voice-output';
}

export function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(reader.error ?? new Error('Audio sample could not be read.'));
    reader.readAsDataURL(blob);
  });
}
