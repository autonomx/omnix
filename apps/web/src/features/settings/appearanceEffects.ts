export type AppearanceEffectSettings = {
  mode: string;
  density: string;
  reduceMotion: boolean;
};

export function applyAppearanceSettings(settings: AppearanceEffectSettings): void {
  if (typeof document === 'undefined') return;
  document.documentElement.dataset.omnixAppearance = settings.mode;
  document.documentElement.dataset.omnixDensity = settings.density;
  document.documentElement.classList.toggle('omnix-reduce-motion', settings.reduceMotion);
}
