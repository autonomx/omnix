import { DEFAULT_OMNIX_THEME, resolveOmnixThemeId, type OmnixThemeId } from '../../design/appearanceThemes';

export type AppearanceEffectSettings = {
  mode: string;
  theme?: string;
  density: string;
  reduceMotion: boolean;
};

export type OmnixAppearanceMode = 'system' | 'light' | 'dark';
export type ResolvedOmnixAppearanceMode = 'light' | 'dark';

export type OmnixAppearanceChangeDetail = {
  mode: OmnixAppearanceMode;
  resolvedMode: ResolvedOmnixAppearanceMode;
  theme: OmnixThemeId;
};

export const OMNIX_APPEARANCE_MODE_STORAGE_KEY = 'omnix.appearance.mode';
export const OMNIX_THEME_STORAGE_KEY = 'omnix.appearance.theme';
export const OMNIX_APPEARANCE_CHANGE_EVENT = 'omnix:appearance-change';

export function normalizeAppearanceMode(mode: unknown): OmnixAppearanceMode {
  return mode === 'light' || mode === 'dark' || mode === 'system' ? mode : 'system';
}

export function resolveAppearanceMode(mode: string): ResolvedOmnixAppearanceMode {
  const normalizedMode = normalizeAppearanceMode(mode);
  if (normalizedMode === 'light' || normalizedMode === 'dark') return normalizedMode;
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return 'dark';
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

export function loadStoredAppearancePreferences(): {
  mode: OmnixAppearanceMode | null;
  theme: OmnixThemeId | null;
} {
  if (typeof window === 'undefined') return { mode: null, theme: null };
  try {
    const storedMode = window.localStorage.getItem(OMNIX_APPEARANCE_MODE_STORAGE_KEY);
    const storedTheme = window.localStorage.getItem(OMNIX_THEME_STORAGE_KEY);
    return {
      mode: storedMode === 'system' || storedMode === 'light' || storedMode === 'dark' ? storedMode : null,
      theme: storedTheme ? resolveOmnixThemeId(storedTheme) : null,
    };
  } catch {
    return { mode: null, theme: null };
  }
}

export function applyAppearanceSettings(settings: AppearanceEffectSettings): OmnixAppearanceChangeDetail {
  const mode = normalizeAppearanceMode(settings.mode);
  const resolvedMode = resolveAppearanceMode(mode);
  const theme = resolveOmnixThemeId(settings.theme ?? DEFAULT_OMNIX_THEME);
  if (typeof document !== 'undefined') {
    document.documentElement.dataset.omnixAppearance = resolvedMode;
    document.documentElement.dataset.omnixAppearancePreference = mode;
    document.documentElement.dataset.omnixTheme = theme;
    document.documentElement.dataset.omnixDensity = settings.density;
    document.documentElement.classList.toggle('omnix-reduce-motion', settings.reduceMotion);
  }
  return { mode, resolvedMode, theme };
}

export function commitAppearanceSettings(settings: AppearanceEffectSettings): OmnixAppearanceChangeDetail {
  const detail = applyAppearanceSettings(settings);
  if (typeof window === 'undefined') return detail;
  try {
    window.localStorage.setItem(OMNIX_APPEARANCE_MODE_STORAGE_KEY, detail.mode);
    window.localStorage.setItem(OMNIX_THEME_STORAGE_KEY, detail.theme);
  } catch {
    // Appearance persistence is best-effort in private or locked-down browser contexts.
  }
  window.dispatchEvent(new CustomEvent<OmnixAppearanceChangeDetail>(OMNIX_APPEARANCE_CHANGE_EVENT, { detail }));
  return detail;
}
