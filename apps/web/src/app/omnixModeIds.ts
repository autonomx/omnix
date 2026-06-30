export const OMNIX_MODE_IDS = ['normal', 'live', 'agent', 'house', 'podcast', 'rpg'] as const;

export type OmnixModeId = typeof OMNIX_MODE_IDS[number];

export interface OmnixModeInfo {
  id: OmnixModeId;
  label: string;
}

export const OMNIX_MODE_INFO: readonly OmnixModeInfo[] = [
  { id: 'normal', label: 'Normal chat' },
  { id: 'live', label: 'Live chat' },
  { id: 'agent', label: 'Agent mode' },
  { id: 'house', label: 'House AI' },
  { id: 'podcast', label: 'Podcast' },
  { id: 'rpg', label: 'RPG' },
];

export function isOmnixModeId(value: string | undefined): value is OmnixModeId {
  return Boolean(value && (OMNIX_MODE_IDS as readonly string[]).includes(value));
}

export function getOmnixModeInfo(mode: OmnixModeId): OmnixModeInfo {
  return OMNIX_MODE_INFO.find((item) => item.id === mode) ?? OMNIX_MODE_INFO[0];
}
