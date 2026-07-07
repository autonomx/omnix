export type AppearanceEffectSettings = {
  mode: string;
  density: string;
  reduceMotion: boolean;
};

export type OmnixAppearanceMode = 'system' | 'light' | 'dark';
export type ResolvedOmnixAppearanceMode = 'light' | 'dark';

export function resolveAppearanceMode(mode: string): ResolvedOmnixAppearanceMode {
  if (mode === 'light' || mode === 'dark') return mode;
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return 'dark';
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

export function applyAppearanceSettings(settings: AppearanceEffectSettings): void {
  if (typeof document === 'undefined') return;
  document.documentElement.dataset.omnixAppearance = resolveAppearanceMode(settings.mode);
  document.documentElement.dataset.omnixAppearancePreference = settings.mode;
  document.documentElement.dataset.omnixDensity = settings.density;
  document.documentElement.classList.toggle('omnix-reduce-motion', settings.reduceMotion);
}
